"""Tests for Section 3 data transformation."""

import sys
import importlib.util
from pathlib import Path

import pytest

# section-3 has a hyphen so we can't use normal imports
_transform_path = Path(__file__).resolve().parent.parent / "section-3" / "transform.py"
_spec = importlib.util.spec_from_file_location("transform", _transform_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

transform = _mod.transform
parse_german_date = _mod.parse_german_date
compute_due_date = _mod.compute_due_date
compute_line_total = _mod.compute_line_total
compute_vat = _mod.compute_vat
group_by_invoice = _mod.group_by_invoice
check_required_fields = _mod.check_required_fields


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_record(**overrides) -> dict:
    """Return a valid System A flat record; override any key."""
    base = {
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
        "item_description": "Cloud Hosting",
        "item_quantity": "3",
        "item_unit_price": "450.00",
        "item_vat_rate": "19",
        "payment_days": "30",
        "iban": "DE89370400440532013000",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestParseGermanDate:
    def test_valid(self):
        assert parse_german_date("15.03.2024") == "2024-03-15"

    def test_leading_zeros(self):
        assert parse_german_date("01.01.2024") == "2024-01-01"

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Cannot parse date"):
            parse_german_date("2024-03-15")

    def test_empty_string(self):
        with pytest.raises(ValueError):
            parse_german_date("")


class TestComputeDueDate:
    def test_30_days(self):
        assert compute_due_date("2024-03-15", 30) == "2024-04-14"

    def test_crosses_year(self):
        assert compute_due_date("2024-12-15", 30) == "2025-01-14"


class TestComputeLineTotal:
    def test_basic(self):
        assert compute_line_total(3, 450.00) == 1350.00

    def test_decimal_precision(self):
        assert compute_line_total(1, 89.50) == 89.50


class TestComputeVat:
    def test_19_percent(self):
        assert compute_vat(2864.50, 19) == 544.26


class TestGroupByInvoice:
    def test_groups_correctly(self):
        records = [make_record(), make_record(item_description="SSL Cert")]
        grouped = group_by_invoice(records)
        assert len(grouped) == 1
        assert len(grouped["2024-0892"]) == 2

    def test_multiple_invoices(self):
        records = [make_record(), make_record(invoice_number="2024-0999")]
        grouped = group_by_invoice(records)
        assert len(grouped) == 2

    def test_skips_empty_invoice_number(self):
        records = [make_record(invoice_number="")]
        grouped = group_by_invoice(records)
        assert len(grouped) == 0


class TestCheckRequiredFields:
    def test_all_present(self):
        assert check_required_fields(make_record()) == []

    def test_missing_field(self):
        record = make_record()
        record["seller_name"] = ""
        missing = check_required_fields(record)
        assert "seller_name" in missing


# ---------------------------------------------------------------------------
# Full transform tests
# ---------------------------------------------------------------------------

class TestTransform:
    def test_single_invoice_single_item(self):
        result = transform([make_record()])
        assert result.success
        assert len(result.invoices) == 1
        inv = result.invoices[0]
        assert inv["invoiceNumber"] == "2024-0892"
        assert inv["issueDate"] == "2024-03-15"
        assert len(inv["lineItems"]) == 1
        assert inv["lineItems"][0]["lineTotal"] == 1350.00

    def test_single_invoice_multiple_items(self):
        records = [
            make_record(item_description="Cloud Hosting", item_quantity="3", item_unit_price="450.00"),
            make_record(item_description="SSL Cert", item_quantity="1", item_unit_price="89.50"),
            make_record(item_description="Support", item_quantity="15", item_unit_price="95.00"),
        ]
        result = transform(records)
        assert result.success
        inv = result.invoices[0]
        assert len(inv["lineItems"]) == 3
        assert inv["totals"]["netAmount"] == 2864.50
        assert inv["totals"]["vatAmount"] == 544.26
        assert inv["totals"]["grossAmount"] == 3408.76

    def test_empty_input(self):
        result = transform([])
        assert not result.success
        assert "No records provided" in result.errors[0]

    def test_missing_required_field(self):
        record = make_record()
        record["seller_name"] = ""
        result = transform([record])
        assert not result.success
        assert "missing required fields" in result.errors[0]

    def test_invalid_quantity(self):
        result = transform([make_record(item_quantity="abc")])
        assert not result.success

    def test_invalid_date(self):
        result = transform([make_record(invoice_date="not-a-date")])
        assert not result.success

    def test_multiple_invoices(self):
        records = [
            make_record(invoice_number="INV-001"),
            make_record(invoice_number="INV-002"),
        ]
        result = transform(records)
        assert result.success
        assert len(result.invoices) == 2