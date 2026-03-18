"""
Section 3: API Integration & Data Transformation

Transforms System A flat records (one dict per line item) into
System B nested Invoice JSON, validated through Pydantic models.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field

# Ensure project root is on the path so `models` can be imported
# regardless of where the script is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from models import Invoice


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class TransformResult:
    """Holds the transformed invoice(s) and any validation warnings/errors."""

    invoices: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def parse_german_date(date_str: str) -> str:
    """Convert German date format (DD.MM.YYYY) to ISO 8601 (YYYY-MM-DD)."""
    try:
        dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Cannot parse date '{date_str}': expected DD.MM.YYYY")


def compute_due_date(issue_date_iso: str, payment_days: int) -> str:
    """Add payment_days to an ISO date string and return ISO date string."""
    dt = datetime.strptime(issue_date_iso, "%Y-%m-%d")
    due = dt + timedelta(days=payment_days)
    return due.strftime("%Y-%m-%d")


def safe_int(value: str, field_name: str) -> int:
    """Parse a string to int with a clear error on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ValueError(f"'{field_name}' must be an integer, got '{value}'")


def safe_float(value: str, field_name: str) -> float:
    """Parse a string to float with a clear error on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        raise ValueError(f"'{field_name}' must be a number, got '{value}'")


def compute_line_total(quantity: int, unit_price: float) -> float:
    """Compute line total using Decimal to avoid floating-point drift."""
    result = Decimal(str(quantity)) * Decimal(str(unit_price))
    return float(result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def compute_vat(net: float, vat_rate: float) -> float:
    """Compute VAT amount from net and rate (rate as percentage, e.g. 19)."""
    result = Decimal(str(net)) * Decimal(str(vat_rate)) / Decimal("100")
    return float(result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def group_by_invoice(records: list[dict]) -> dict[str, list[dict]]:
    """Group flat records by invoice_number."""
    grouped: dict[str, list[dict]] = {}
    for record in records:
        inv_num = record.get("invoice_number", "").strip()
        if not inv_num:
            continue
        grouped.setdefault(inv_num, []).append(record)
    return grouped


# ---------------------------------------------------------------------------
# Single-invoice transformation
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "invoice_number", "invoice_date", "seller_name", "seller_street",
    "seller_city", "seller_zip", "seller_country", "seller_vat_id",
    "buyer_name", "buyer_city", "buyer_vat_id",
    "item_description", "item_quantity", "item_unit_price", "item_vat_rate",
    "payment_days", "iban",
]


def check_required_fields(record: dict) -> list[str]:
    """Return a list of missing required field names."""
    return [f for f in REQUIRED_FIELDS if not record.get(f, "").strip()]


def transform_single_invoice(
    invoice_number: str,
    records: list[dict],
) -> dict:
    """
    Transform a group of flat System A records (same invoice_number)
    into a single System B dict ready for Pydantic validation.

    Raises ValueError on critical issues.
    """
    # Use the first record for header-level fields
    header = records[0]

    # --- Check required fields on the header ---
    missing = check_required_fields(header)
    if missing:
        raise ValueError(
            f"Invoice {invoice_number}: missing required fields: {missing}"
        )

    # --- Dates ---
    issue_date = parse_german_date(header["invoice_date"])
    payment_days = safe_int(header["payment_days"], "payment_days")
    due_date = compute_due_date(issue_date, payment_days)

    # --- Line items ---
    line_items: list[dict] = []
    for row in records:
        quantity = safe_int(row["item_quantity"], "item_quantity")
        unit_price = safe_float(row["item_unit_price"], "item_unit_price")
        vat_rate = safe_float(row["item_vat_rate"], "item_vat_rate")
        line_total = compute_line_total(quantity, unit_price)

        line_items.append({
            "description": row["item_description"].strip(),
            "quantity": quantity,
            "unitPrice": unit_price,
            "vatRate": vat_rate,
            "lineTotal": line_total,
        })

    # --- Totals (computed from line items) ---
    net_amount = float(
        sum(Decimal(str(li["lineTotal"])) for li in line_items)
        .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )
    # Use the VAT rate from the first line item (assuming uniform rate)
    vat_rate = line_items[0]["vatRate"]
    vat_amount = compute_vat(net_amount, vat_rate)
    gross_amount = float(
        (Decimal(str(net_amount)) + Decimal(str(vat_amount)))
        .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )

    # --- Build System B dict ---
    return {
        "invoiceNumber": invoice_number,
        "issueDate": issue_date,
        "seller": {
            "name": header["seller_name"].strip(),
            "address": {
                "street": header["seller_street"].strip(),
                "city": header["seller_city"].strip(),
                "postalCode": header["seller_zip"].strip(),
                "countryCode": header["seller_country"].strip().upper(),
            },
            "vatId": header["seller_vat_id"].strip(),
        },
        "buyer": {
            "name": header["buyer_name"].strip(),
            "address": {
                "street": header.get("buyer_street", "").strip() or "N/A",
                "city": header["buyer_city"].strip(),
                "postalCode": header.get("buyer_zip", "").strip() or "N/A",
                "countryCode": header.get("buyer_country", "").strip().upper()
                or header["seller_country"].strip().upper(),
            },
            "vatId": header["buyer_vat_id"].strip(),
        },
        "lineItems": line_items,
        "totals": {
            "netAmount": net_amount,
            "vatAmount": vat_amount,
            "grossAmount": gross_amount,
        },
        "paymentTerms": {
            "dueDays": payment_days,
            "dueDate": due_date,
        },
        "paymentMeans": {
            "iban": header["iban"].strip(),
        },
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def transform(records: list[dict]) -> TransformResult:
    """
    Transform a list of flat System A records into validated System B invoices.

    Groups records by invoice_number, builds nested dicts, and validates
    each through the Invoice Pydantic model.

    Returns a TransformResult with validated invoices and any errors/warnings.
    """
    result = TransformResult()

    if not records:
        result.errors.append("No records provided")
        return result

    grouped = group_by_invoice(records)

    if not grouped:
        result.errors.append("No valid invoice_number found in records")
        return result

    for invoice_number, group in grouped.items():
        try:
            # Step 1: Build the nested dict
            invoice_dict = transform_single_invoice(invoice_number, group)

            # Step 2: Validate through Pydantic
            invoice = Invoice(**invoice_dict)

            # Step 3: Serialize with aliases for System B output
            result.invoices.append(invoice.model_dump(by_alias=True))

        except ValueError as e:
            result.errors.append(f"Invoice {invoice_number}: {e}")
        except Exception as e:
            result.errors.append(
                f"Invoice {invoice_number}: unexpected error — {e}"
            )

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Sample data from the assessment
    system_a_records = [
        {
            "invoice_number": "2024-0892",
            "invoice_date": "15.03.2024",
            "seller_name": "TechSolutions GmbH",
            "seller_street": "Musterstrasse 42",
            "seller_city": "Berlin",
            "seller_zip": "10115",
            "seller_country": "DE",
            "seller_vat_id": "DE123456789",
            "buyer_name": "Digital Services AG",
            "buyer_city": "Munchen",
            "buyer_vat_id": "DE987654321",
            "item_description": "Cloud Hosting Premium (Jan-Mar 2024)",
            "item_quantity": "3",
            "item_unit_price": "450.00",
            "item_vat_rate": "19",
            "payment_days": "30",
            "iban": "DE89370400440532013000",
        },
        {
            "invoice_number": "2024-0892",
            "invoice_date": "15.03.2024",
            "seller_name": "TechSolutions GmbH",
            "seller_street": "Musterstrasse 42",
            "seller_city": "Berlin",
            "seller_zip": "10115",
            "seller_country": "DE",
            "seller_vat_id": "DE123456789",
            "buyer_name": "Digital Services AG",
            "buyer_city": "Munchen",
            "buyer_vat_id": "DE987654321",
            "item_description": "SSL-Zertifikat Erneuerung",
            "item_quantity": "1",
            "item_unit_price": "89.50",
            "item_vat_rate": "19",
            "payment_days": "30",
            "iban": "DE89370400440532013000",
        },
        {
            "invoice_number": "2024-0892",
            "invoice_date": "15.03.2024",
            "seller_name": "TechSolutions GmbH",
            "seller_street": "Musterstrasse 42",
            "seller_city": "Berlin",
            "seller_zip": "10115",
            "seller_country": "DE",
            "seller_vat_id": "DE123456789",
            "buyer_name": "Digital Services AG",
            "buyer_city": "Munchen",
            "buyer_vat_id": "DE987654321",
            "item_description": "Technischer Support (15 Stunden)",
            "item_quantity": "15",
            "item_unit_price": "95.00",
            "item_vat_rate": "19",
            "payment_days": "30",
            "iban": "DE89370400440532013000",
        },
    ]

    result = transform(system_a_records)

    print("=" * 60)
    print("TRANSFORMATION RESULT")
    print("=" * 60)

    if result.success:
        print(f"\nSUCCESS: {len(result.invoices)} invoice(s) transformed\n")
        print(json.dumps(result.invoices, indent=2))
    else:
        print(f"\nFAILED with {len(result.errors)} error(s):\n")
        for err in result.errors:
            print(f"  ERROR: {err}")

    if result.warnings:
        print(f"\n{len(result.warnings)} warning(s):")
        for w in result.warnings:
            print(f"  WARN: {w}")
