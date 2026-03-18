"""Tests for Pydantic v2 invoice models."""

import pytest
from pydantic import ValidationError

from models import Address, Party, LineItem, Totals, PaymentTerms, PaymentMeans, Invoice


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_valid_invoice(**overrides) -> dict:
    """Return a valid invoice dict; override any top-level key."""
    base = {
        "invoiceNumber": "2024-0892",
        "issueDate": "2024-03-15",
        "seller": {
            "name": "TechSolutions GmbH",
            "address": {
                "street": "Musterstrasse 42",
                "city": "Berlin",
                "postalCode": "10115",
                "countryCode": "DE",
            },
            "vatId": "DE123456789",
        },
        "buyer": {
            "name": "Digital Services AG",
            "address": {
                "street": "Hauptweg 7",
                "city": "Munchen",
                "postalCode": "80331",
                "countryCode": "DE",
            },
            "vatId": "DE987654321",
        },
        "lineItems": [
            {
                "description": "Cloud Hosting",
                "quantity": 3,
                "unitPrice": 450.00,
                "vatRate": 19,
                "lineTotal": 1350.00,
            },
        ],
        "totals": {"netAmount": 1350.00, "vatAmount": 256.50, "grossAmount": 1606.50},
        "paymentTerms": {"dueDays": 30, "dueDate": "2024-04-14"},
        "paymentMeans": {"iban": "DE89370400440532013000"},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Address
# ---------------------------------------------------------------------------

class TestAddress:
    def test_valid(self):
        addr = Address(street="Main St", city="Berlin", postalCode="10115", countryCode="DE")
        assert addr.country_code == "DE"

    def test_invalid_country_code_lowercase(self):
        with pytest.raises(ValidationError):
            Address(street="Main St", city="Berlin", postalCode="10115", countryCode="de")

    def test_invalid_country_code_too_long(self):
        with pytest.raises(ValidationError):
            Address(street="Main St", city="Berlin", postalCode="10115", countryCode="DEU")

    def test_empty_street_rejected(self):
        with pytest.raises(ValidationError):
            Address(street="", city="Berlin", postalCode="10115", countryCode="DE")


# ---------------------------------------------------------------------------
# Party (seller / buyer)
# ---------------------------------------------------------------------------

class TestParty:
    def test_valid_vat_id(self):
        party = Party(
            name="Test GmbH",
            address={"street": "St", "city": "City", "postalCode": "123", "countryCode": "DE"},
            vatId="DE123456789",
        )
        assert party.vat_id == "DE123456789"

    def test_invalid_vat_id_no_digits(self):
        with pytest.raises(ValidationError, match="Invalid VAT ID"):
            Party(
                name="Test",
                address={"street": "St", "city": "City", "postalCode": "123", "countryCode": "DE"},
                vatId="INVALID",
            )

    def test_invalid_vat_id_lowercase(self):
        with pytest.raises(ValidationError):
            Party(
                name="Test",
                address={"street": "St", "city": "City", "postalCode": "123", "countryCode": "DE"},
                vatId="de123456789",
            )


# ---------------------------------------------------------------------------
# LineItem
# ---------------------------------------------------------------------------

class TestLineItem:
    def test_valid(self):
        item = LineItem(description="Hosting", quantity=3, unitPrice=100.0, vatRate=19, lineTotal=300.0)
        assert item.line_total == 300.0

    def test_line_total_mismatch(self):
        with pytest.raises(ValidationError, match="lineTotal"):
            LineItem(description="Hosting", quantity=3, unitPrice=100.0, vatRate=19, lineTotal=999.0)

    def test_negative_quantity(self):
        with pytest.raises(ValidationError):
            LineItem(description="Hosting", quantity=-1, unitPrice=100.0, vatRate=19, lineTotal=-100.0)

    def test_zero_quantity(self):
        with pytest.raises(ValidationError):
            LineItem(description="Hosting", quantity=0, unitPrice=100.0, vatRate=19, lineTotal=0)

    def test_negative_unit_price(self):
        with pytest.raises(ValidationError):
            LineItem(description="Hosting", quantity=1, unitPrice=-50.0, vatRate=19, lineTotal=-50.0)

    def test_vat_rate_over_100(self):
        with pytest.raises(ValidationError):
            LineItem(description="Hosting", quantity=1, unitPrice=100.0, vatRate=150, lineTotal=100.0)


# ---------------------------------------------------------------------------
# Totals
# ---------------------------------------------------------------------------

class TestTotals:
    def test_valid(self):
        t = Totals(netAmount=1000.0, vatAmount=190.0, grossAmount=1190.0)
        assert t.gross_amount == 1190.0

    def test_gross_mismatch(self):
        with pytest.raises(ValidationError, match="grossAmount"):
            Totals(netAmount=1000.0, vatAmount=190.0, grossAmount=9999.0)


# ---------------------------------------------------------------------------
# PaymentTerms
# ---------------------------------------------------------------------------

class TestPaymentTerms:
    def test_valid(self):
        pt = PaymentTerms(dueDays=30, dueDate="2024-04-14")
        assert pt.due_days == 30

    def test_invalid_date_format(self):
        with pytest.raises(ValidationError, match="ISO 8601"):
            PaymentTerms(dueDays=30, dueDate="15.03.2024")

    def test_zero_due_days(self):
        with pytest.raises(ValidationError):
            PaymentTerms(dueDays=0, dueDate="2024-04-14")


# ---------------------------------------------------------------------------
# PaymentMeans
# ---------------------------------------------------------------------------

class TestPaymentMeans:
    def test_valid_iban(self):
        pm = PaymentMeans(iban="DE89370400440532013000")
        assert pm.iban == "DE89370400440532013000"

    def test_iban_with_spaces_cleaned(self):
        pm = PaymentMeans(iban="DE89 3704 0044 0532 0130 00")
        assert pm.iban == "DE89370400440532013000"

    def test_invalid_iban(self):
        with pytest.raises(ValidationError, match="IBAN"):
            PaymentMeans(iban="NOTANIBAN")

    def test_iban_too_short(self):
        with pytest.raises(ValidationError):
            PaymentMeans(iban="DE89")


# ---------------------------------------------------------------------------
# Invoice (full model)
# ---------------------------------------------------------------------------

class TestInvoice:
    def test_valid_invoice(self):
        inv = Invoice(**make_valid_invoice())
        assert inv.invoice_number == "2024-0892"

    def test_invalid_issue_date(self):
        with pytest.raises(ValidationError, match="ISO 8601"):
            Invoice(**make_valid_invoice(issueDate="15.03.2024"))

    def test_missing_invoice_number(self):
        data = make_valid_invoice()
        del data["invoiceNumber"]
        with pytest.raises(ValidationError):
            Invoice(**data)

    def test_empty_line_items(self):
        with pytest.raises(ValidationError):
            Invoice(**make_valid_invoice(lineItems=[]))

    def test_net_amount_mismatch(self):
        with pytest.raises(ValidationError, match="netAmount"):
            Invoice(**make_valid_invoice(
                totals={"netAmount": 9999.0, "vatAmount": 256.50, "grossAmount": 10255.50}
            ))

    def test_json_serialization_uses_aliases(self):
        inv = Invoice(**make_valid_invoice())
        data = inv.model_dump(by_alias=True)
        assert "invoiceNumber" in data
        assert "lineItems" in data
        assert "postalCode" in data["seller"]["address"]