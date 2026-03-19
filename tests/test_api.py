"""
Tests for Section 5: FastAPI Invoice Processing API

Covers the 5+ meaningful tests required by the assessment:
1. Successful extraction (mocked LLM)
2. Valid transformation
3. Invalid input (422 errors)
4. Query endpoint (mocked agent)
5. GET /invoices listing
6. Edge cases
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

# Load app module from hyphenated directory
ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("app_mod", ROOT / "section-5" / "app.py")
app_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_mod)

app = app_mod.app
invoice_store = app_mod.invoice_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_store():
    """Reset the in-memory store before each test."""
    invoice_store.clear()
    yield
    invoice_store.clear()


@pytest.fixture
def client():
    return TestClient(app)


VALID_TRANSFORM_PAYLOAD = {
    "records": [
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
            "item_description": "Cloud Hosting Premium",
            "item_quantity": "3",
            "item_unit_price": "450.00",
            "item_vat_rate": "19",
            "payment_days": "30",
            "iban": "DE89370400440532013000",
        }
    ]
}

MOCK_INVOICE_DICT = {
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
            "description": "Cloud Hosting Premium",
            "quantity": 3,
            "unitPrice": 450.0,
            "vatRate": 19.0,
            "lineTotal": 1350.0,
        }
    ],
    "totals": {
        "netAmount": 1350.0,
        "vatAmount": 256.5,
        "grossAmount": 1606.5,
    },
    "paymentTerms": {"dueDays": 30, "dueDate": "2024-04-14"},
    "paymentMeans": {"iban": "DE89370400440532013000"},
}


# ---------------------------------------------------------------------------
# 1. GET /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# 2. POST /invoices/transform — valid
# ---------------------------------------------------------------------------

class TestTransform:
    def test_valid_transform(self, client):
        response = client.post("/invoices/transform", json=VALID_TRANSFORM_PAYLOAD)
        assert response.status_code == 200
        data = response.json()
        assert len(data["invoices"]) == 1
        assert data["invoices"][0]["invoiceNumber"] == "2024-0892"
        assert data["errors"] == []

    def test_transform_stores_invoice(self, client):
        client.post("/invoices/transform", json=VALID_TRANSFORM_PAYLOAD)
        assert len(invoice_store) == 1

    def test_transform_correct_totals(self, client):
        response = client.post("/invoices/transform", json=VALID_TRANSFORM_PAYLOAD)
        inv = response.json()["invoices"][0]
        assert inv["totals"]["netAmount"] == 1350.0
        assert inv["totals"]["vatAmount"] == 256.5
        assert inv["totals"]["grossAmount"] == 1606.5

    def test_transform_date_conversion(self, client):
        response = client.post("/invoices/transform", json=VALID_TRANSFORM_PAYLOAD)
        inv = response.json()["invoices"][0]
        assert inv["issueDate"] == "2024-03-15"
        assert inv["paymentTerms"]["dueDate"] == "2024-04-14"


# ---------------------------------------------------------------------------
# 3. POST /invoices/transform — invalid input (422)
# ---------------------------------------------------------------------------

class TestTransformInvalid:
    def test_empty_records(self, client):
        response = client.post("/invoices/transform", json={"records": []})
        assert response.status_code == 422

    def test_missing_records_field(self, client):
        response = client.post("/invoices/transform", json={})
        assert response.status_code == 422

    def test_no_body(self, client):
        response = client.post("/invoices/transform")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# 4. POST /invoices/extract — mocked LLM
# ---------------------------------------------------------------------------

class TestExtract:
    def test_extract_success_mocked(self, client):
        """Mock the extract module to avoid real API calls."""
        mock_invoice = MagicMock()
        mock_invoice.model_dump.return_value = MOCK_INVOICE_DICT

        with patch.object(app_mod, "extract_mod") as mock_mod:
            mock_mod.extract_invoice.return_value = (mock_invoice, [])
            response = client.post(
                "/invoices/extract",
                json={"text": "Rechnung Nr. 2024-0892 long enough text", "provider": "anthropic"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["validation_passed"] is True
        assert data["invoice"]["invoiceNumber"] == "2024-0892"

    def test_extract_failure_returns_422(self, client):
        """When LLM fails to extract, return 422."""
        with patch.object(app_mod, "extract_mod") as mock_mod:
            mock_mod.extract_invoice.return_value = (
                None,
                ["Attempt 1: malformed JSON"],
            )
            response = client.post(
                "/invoices/extract",
                json={"text": "Some random text here that is long enough", "provider": "anthropic"},
            )

        assert response.status_code == 422

    def test_extract_invalid_provider(self, client):
        response = client.post(
            "/invoices/extract",
            json={"text": "Some invoice text here that is long enough", "provider": "fake_llm"},
        )
        assert response.status_code == 422

    def test_extract_text_too_short(self, client):
        response = client.post(
            "/invoices/extract",
            json={"text": "Hi", "provider": "anthropic"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# 5. POST /invoices/query — mocked agent
# ---------------------------------------------------------------------------

class TestQuery:
    def test_query_success_mocked(self, client):
        with patch.object(app_mod, "agent_mod") as mock_mod:
            mock_mod.run_agent.return_value = {
                "answer": "INV-003 from Munchen Logistics GmbH is overdue.",
                "tool_calls": [
                    {"tool": "search_invoices", "input": {"query": "overdue"}, "output": []}
                ],
                "provider": "anthropic",
                "history": [],
            }
            response = client.post(
                "/invoices/query",
                json={"question": "Which invoices are overdue?"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "overdue" in data["answer"].lower()
        assert len(data["tool_calls"]) == 1
        assert data["tool_calls"][0]["tool"] == "search_invoices"

    def test_query_invalid_provider(self, client):
        response = client.post(
            "/invoices/query",
            json={"question": "Which invoices are overdue?", "provider": "fake"},
        )
        assert response.status_code == 422

    def test_query_too_short(self, client):
        response = client.post(
            "/invoices/query",
            json={"question": "Hi"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# 6. GET /invoices
# ---------------------------------------------------------------------------

class TestListInvoices:
    def test_returns_mock_data(self, client):
        response = client.get("/invoices")
        assert response.status_code == 200
        data = response.json()
        mock_invoices = [inv for inv in data if inv.get("source") == "mock"]
        assert len(mock_invoices) == 4

    def test_includes_transformed(self, client):
        client.post("/invoices/transform", json=VALID_TRANSFORM_PAYLOAD)
        response = client.get("/invoices")
        data = response.json()
        stored = [inv for inv in data if inv.get("source") == "extracted/transformed"]
        assert len(stored) == 1

    def test_includes_extracted(self, client):
        """Extracted invoices should appear in the listing."""
        mock_invoice = MagicMock()
        mock_invoice.model_dump.return_value = MOCK_INVOICE_DICT

        with patch.object(app_mod, "extract_mod") as mock_mod:
            mock_mod.extract_invoice.return_value = (mock_invoice, [])
            client.post(
                "/invoices/extract",
                json={"text": "Rechnung Nr. 2024-0892 long enough text", "provider": "anthropic"},
            )

        response = client.get("/invoices")
        data = response.json()
        stored = [inv for inv in data if inv.get("source") == "extracted/transformed"]
        assert len(stored) == 1