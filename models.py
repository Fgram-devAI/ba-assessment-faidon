"""
Pydantic v2 models for the System B invoice schema.

Defines strict validation rules for invoice data including:
- VAT ID format (2-letter country code + digits)
- IBAN format validation
- Line item total verification (quantity * unitPrice == lineTotal)
- Positive quantity/price constraints
- ISO 8601 date enforcement
"""

import re
from decimal import Decimal, ROUND_HALF_UP

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Reusable sub-models
# ---------------------------------------------------------------------------

class Address(BaseModel):
    street: str = Field(..., min_length=1)
    city: str = Field(..., min_length=1)
    postal_code: str = Field(..., alias="postalCode", min_length=1)
    country_code: str = Field(
        ...,
        alias="countryCode",
        min_length=2,
        max_length=2,
        pattern=r"^[A-Z]{2}$",
    )

    model_config = {"populate_by_name": True}


class Party(BaseModel):
    """Seller or buyer entity on an invoice."""

    name: str = Field(..., min_length=1)
    address: Address
    vat_id: str = Field(..., alias="vatId")

    model_config = {"populate_by_name": True}

    @field_validator("vat_id")
    @classmethod
    def validate_vat_id(cls, v: str) -> str:
        """VAT ID must be a 2-letter country code followed by digits."""
        if not re.match(r"^[A-Z]{2}\d+$", v):
            raise ValueError(
                f"Invalid VAT ID '{v}': must be a 2-letter country code "
                "followed by digits (e.g. DE123456789)"
            )
        return v


class LineItem(BaseModel):
    description: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., alias="unitPrice", ge=0)
    vat_rate: float = Field(..., alias="vatRate", ge=0, le=100)
    line_total: float = Field(..., alias="lineTotal")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def verify_line_total(self) -> "LineItem":
        """lineTotal must strictly equal quantity * unitPrice."""
        expected = Decimal(str(self.quantity)) * Decimal(str(self.unit_price))
        expected = float(expected.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        if abs(self.line_total - expected) > 0.01:
            raise ValueError(
                f"lineTotal {self.line_total} does not match "
                f"quantity ({self.quantity}) * unitPrice ({self.unit_price}) "
                f"= {expected}"
            )
        return self


class Totals(BaseModel):
    net_amount: float = Field(..., alias="netAmount")
    vat_amount: float = Field(..., alias="vatAmount")
    gross_amount: float = Field(..., alias="grossAmount")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def verify_gross(self) -> "Totals":
        """grossAmount must equal netAmount + vatAmount."""
        expected = Decimal(str(self.net_amount)) + Decimal(str(self.vat_amount))
        expected = float(expected.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        if abs(self.gross_amount - expected) > 0.01:
            raise ValueError(
                f"grossAmount {self.gross_amount} != "
                f"netAmount ({self.net_amount}) + vatAmount ({self.vat_amount}) "
                f"= {expected}"
            )
        return self


class PaymentTerms(BaseModel):
    due_days: int = Field(..., alias="dueDays", gt=0)
    due_date: str = Field(..., alias="dueDate")

    model_config = {"populate_by_name": True}

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v: str) -> str:
        """dueDate must be a valid ISO 8601 date (YYYY-MM-DD)."""
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError(
                f"Invalid ISO 8601 date '{v}': expected format YYYY-MM-DD"
            )
        return v


class PaymentMeans(BaseModel):
    iban: str

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: str) -> str:
        """
        Basic IBAN format validation:
        - Strip spaces
        - 2-letter country code + 2 check digits + up to 30 alphanumeric chars
        - Length between 15 and 34 characters
        """
        cleaned = v.replace(" ", "")
        if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$", cleaned):
            raise ValueError(
                f"Invalid IBAN format '{v}': must be 2-letter country code, "
                "2 check digits, followed by 11-30 alphanumeric characters"
            )
        return cleaned


# ---------------------------------------------------------------------------
# Root invoice model
# ---------------------------------------------------------------------------

class Invoice(BaseModel):
    """System B invoice schema — the canonical validated representation."""

    invoice_number: str = Field(..., alias="invoiceNumber", min_length=1)
    issue_date: str = Field(..., alias="issueDate")
    seller: Party
    buyer: Party
    line_items: list[LineItem] = Field(..., alias="lineItems", min_length=1)
    totals: Totals
    payment_terms: PaymentTerms = Field(..., alias="paymentTerms")
    payment_means: PaymentMeans = Field(..., alias="paymentMeans")

    model_config = {"populate_by_name": True}

    @field_validator("issue_date")
    @classmethod
    def validate_issue_date(cls, v: str) -> str:
        """issueDate must be a valid ISO 8601 date (YYYY-MM-DD)."""
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError(
                f"Invalid ISO 8601 date '{v}': expected format YYYY-MM-DD"
            )
        return v

    @model_validator(mode="after")
    def verify_net_amount_matches_line_items(self) -> "Invoice":
        """netAmount must equal the sum of all lineItem totals."""
        line_sum = sum(
            Decimal(str(item.line_total)) for item in self.line_items
        )
        line_sum_float = float(
            line_sum.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        if abs(self.totals.net_amount - line_sum_float) > 0.01:
            raise ValueError(
                f"netAmount ({self.totals.net_amount}) does not match "
                f"sum of line item totals ({line_sum_float})"
            )
        return self
