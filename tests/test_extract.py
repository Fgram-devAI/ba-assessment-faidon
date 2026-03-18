"""Tests for Section 1A LLM extraction pipeline.

- Mocked tests: always run, test parsing/validation/retry logic
- Real API tests: only run when API keys are set, use free-tier models
"""

import os
import sys
import json
import importlib.util
from pathlib import Path

import pytest

# section-1 has a hyphen so we use importlib
_extract_path = Path(__file__).resolve().parent.parent / "section-1" / "extract.py"
_spec = importlib.util.spec_from_file_location("extract", _extract_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

extract_invoice = _mod.extract_invoice
clean_json_response = _mod.clean_json_response
PROVIDERS = _mod.PROVIDERS
SAMPLE_INVOICE = _mod.SAMPLE_INVOICE


# ---------------------------------------------------------------------------
# Valid mock LLM response
# ---------------------------------------------------------------------------

VALID_LLM_RESPONSE = json.dumps({
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
            "description": "Cloud Hosting Premium (Jan-Mar 2024)",
            "quantity": 3,
            "unitPrice": 450.00,
            "vatRate": 19,
            "lineTotal": 1350.00,
        },
        {
            "description": "SSL-Zertifikat Erneuerung",
            "quantity": 1,
            "unitPrice": 89.50,
            "vatRate": 19,
            "lineTotal": 89.50,
        },
        {
            "description": "Technischer Support (15 Stunden)",
            "quantity": 15,
            "unitPrice": 95.00,
            "vatRate": 19,
            "lineTotal": 1425.00,
        },
    ],
    "totals": {
        "netAmount": 2864.50,
        "vatAmount": 544.26,
        "grossAmount": 3408.76,
    },
    "paymentTerms": {"dueDays": 30, "dueDate": "2024-04-14"},
    "paymentMeans": {"iban": "DE89370400440532013000"},
})


# ===========================================================================
# MOCKED TESTS (always run, no API keys needed)
# ===========================================================================

class TestCleanJsonResponse:
    def test_plain_json(self):
        assert clean_json_response('{"a": 1}') == '{"a": 1}'

    def test_strips_markdown_fences(self):
        raw = '```json\n{"a": 1}\n```'
        assert clean_json_response(raw) == '{"a": 1}'

    def test_strips_fences_no_language(self):
        raw = '```\n{"a": 1}\n```'
        assert clean_json_response(raw) == '{"a": 1}'

    def test_strips_whitespace(self):
        assert clean_json_response('  \n{"a": 1}\n  ') == '{"a": 1}'


class TestExtractWithMock:
    """Test extraction pipeline with mocked LLM responses."""

    def setup_method(self):
        """Register mock provider before each test."""
        pass

    def teardown_method(self):
        """Clean up mock provider after each test."""
        PROVIDERS.pop("mock", None)

    def test_valid_response(self):
        PROVIDERS["mock"] = lambda prompt: VALID_LLM_RESPONSE
        invoice, errors = extract_invoice("some text", provider="mock")
        assert invoice is not None
        assert errors == []
        assert invoice.invoice_number == "2024-0892"
        assert len(invoice.line_items) == 3
        assert invoice.totals.gross_amount == 3408.76

    def test_response_with_code_fences(self):
        wrapped = f"```json\n{VALID_LLM_RESPONSE}\n```"
        PROVIDERS["mock"] = lambda prompt: wrapped
        invoice, errors = extract_invoice("some text", provider="mock")
        assert invoice is not None
        assert errors == []

    def test_invalid_json_retries(self):
        PROVIDERS["mock"] = lambda prompt: "this is not json"
        invoice, errors = extract_invoice("some text", provider="mock", max_retries=2)
        assert invoice is None
        assert len(errors) == 2
        assert "Invalid JSON" in errors[0]

    def test_valid_json_but_fails_validation(self):
        bad_data = json.dumps({"invoiceNumber": ""})
        PROVIDERS["mock"] = lambda prompt: bad_data
        invoice, errors = extract_invoice("some text", provider="mock", max_retries=1)
        assert invoice is None
        assert len(errors) == 1

    def test_unknown_provider(self):
        invoice, errors = extract_invoice("some text", provider="nonexistent")
        assert invoice is None
        assert "Unknown provider" in errors[0]

    def test_retry_then_succeed(self):
        call_count = 0

        def flaky(prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            return "not json" if call_count == 1 else VALID_LLM_RESPONSE

        PROVIDERS["mock"] = flaky
        invoice, errors = extract_invoice("some text", provider="mock", max_retries=3)
        assert invoice is not None
        assert errors == []
        assert call_count == 2

    def test_llm_exception_retries(self):
        PROVIDERS["mock"] = lambda prompt: (_ for _ in ()).throw(ConnectionError("API down"))
        invoice, errors = extract_invoice("some text", provider="mock", max_retries=2)
        assert invoice is None
        assert len(errors) == 2
        assert "API down" in errors[0]

    def test_cross_validation_values(self):
        """Verify the extracted data matches expected values from the assessment."""
        PROVIDERS["mock"] = lambda prompt: VALID_LLM_RESPONSE
        invoice, _ = extract_invoice("some text", provider="mock")
        data = invoice.model_dump(by_alias=True)

        # Line items
        assert data["lineItems"][0]["lineTotal"] == 1350.00
        assert data["lineItems"][1]["lineTotal"] == 89.50
        assert data["lineItems"][2]["lineTotal"] == 1425.00

        # Totals
        assert data["totals"]["netAmount"] == 2864.50
        assert data["totals"]["vatAmount"] == 544.26
        assert data["totals"]["grossAmount"] == 3408.76

        # Payment
        assert data["paymentTerms"]["dueDays"] == 30
        assert data["paymentMeans"]["iban"] == "DE89370400440532013000"


# ===========================================================================
# REAL API TESTS (only run when API keys are available, use free-tier models)
# ===========================================================================

# Skip conditions
has_gemini_key = pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set",
)


def _assert_valid_extraction(invoice, errors):
    """Shared assertions for real API extraction tests."""
    assert invoice is not None, f"Extraction failed: {errors}"
    assert errors == []
    assert invoice.invoice_number == "2024-0892"
    assert len(invoice.line_items) == 3
    assert abs(invoice.totals.net_amount - 2864.50) <= 0.01
    assert abs(invoice.totals.vat_amount - 544.26) <= 0.01
    assert abs(invoice.totals.gross_amount - 3408.76) <= 0.01


@has_gemini_key
class TestGeminiExtraction:
    def test_sample_invoice(self):
        invoice, errors = extract_invoice(SAMPLE_INVOICE, provider="gemini")
        _assert_valid_extraction(invoice, errors)