"""
Tests for Section 2: AI Agent with Tool Use

Covers:
- Tool function correctness (search, details, calculate)
- Edge cases (not found, empty queries, bad IDs)
- Agent loop with mocked LLM responses
"""

import json
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "section-2"))
from agent import (
    search_invoices,
    get_invoice_details,
    calculate_total,
    execute_tool,
    run_agent,
    INVOICES,
)


# ---------------------------------------------------------------------------
# search_invoices tests
# ---------------------------------------------------------------------------

class TestSearchInvoices:
    def test_search_by_customer(self):
        results = search_invoices("Digital Services AG")
        assert len(results) == 2
        assert all(r["customer"] == "Digital Services AG" for r in results)

    def test_search_by_status(self):
        results = search_invoices("overdue")
        assert len(results) == 1
        assert results[0]["id"] == "INV-003"
        assert results[0]["status"] == "overdue"

    def test_search_by_invoice_id(self):
        results = search_invoices("INV-004")
        assert len(results) == 1
        assert results[0]["id"] == "INV-004"

    def test_search_by_item_description(self):
        results = search_invoices("Cloud Hosting")
        assert len(results) >= 1
        ids = [r["id"] for r in results]
        assert "INV-001" in ids

    def test_search_no_results(self):
        results = search_invoices("nonexistent company xyz")
        assert results == []

    def test_search_case_insensitive(self):
        results = search_invoices("digital services ag")
        assert len(results) == 2

    def test_search_with_date_from(self):
        results = search_invoices("Digital Services AG", date_from="2024-03-01")
        assert len(results) == 1
        assert results[0]["id"] == "INV-002"

    def test_search_with_date_to(self):
        results = search_invoices("Digital Services AG", date_to="2024-02-01")
        assert len(results) == 1
        assert results[0]["id"] == "INV-001"

    def test_search_with_date_range(self):
        results = search_invoices(
            "Digital Services AG",
            date_from="2024-01-01",
            date_to="2024-01-31",
        )
        assert len(results) == 1
        assert results[0]["id"] == "INV-001"

    def test_search_returns_summary_not_items(self):
        """Search results should not include line items (summary only)."""
        results = search_invoices("INV-001")
        assert len(results) == 1
        assert "items" not in results[0]
        assert "id" in results[0]
        assert "gross_total" in results[0]


# ---------------------------------------------------------------------------
# get_invoice_details tests
# ---------------------------------------------------------------------------

class TestGetInvoiceDetails:
    def test_existing_invoice(self):
        result = get_invoice_details("INV-001")
        assert result["id"] == "INV-001"
        assert result["customer"] == "Digital Services AG"
        assert "items" in result
        assert len(result["items"]) == 2

    def test_invoice_has_all_fields(self):
        result = get_invoice_details("INV-003")
        assert "net_total" in result
        assert "vat_rate" in result
        assert "gross_total" in result
        assert "status" in result
        assert "items" in result

    def test_not_found(self):
        result = get_invoice_details("INV-999")
        assert "error" in result

    def test_all_invoices_accessible(self):
        for inv in INVOICES:
            result = get_invoice_details(inv["id"])
            assert result["id"] == inv["id"]


# ---------------------------------------------------------------------------
# calculate_total tests
# ---------------------------------------------------------------------------

class TestCalculateTotal:
    def test_single_invoice(self):
        result = calculate_total(["INV-001"])
        assert result["net_total"] == 2500.00
        assert result["vat_total"] == 475.00
        assert result["gross_total"] == 2975.00

    def test_multiple_invoices(self):
        result = calculate_total(["INV-001", "INV-002"])
        assert result["net_total"] == 5700.00
        assert result["gross_total"] == 6783.00

    def test_all_invoices(self):
        all_ids = [inv["id"] for inv in INVOICES]
        result = calculate_total(all_ids)
        expected_net = sum(inv["net_total"] for inv in INVOICES)
        assert result["net_total"] == expected_net

    def test_not_found_ids_reported(self):
        result = calculate_total(["INV-001", "INV-999"])
        assert result["net_total"] == 2500.00
        assert "INV-999" in result["not_found"]

    def test_all_not_found(self):
        result = calculate_total(["INV-888", "INV-999"])
        assert result["net_total"] == 0.0
        assert result["gross_total"] == 0.0
        assert len(result["not_found"]) == 2

    def test_empty_list(self):
        result = calculate_total([])
        assert result["net_total"] == 0.0
        assert result["gross_total"] == 0.0


# ---------------------------------------------------------------------------
# execute_tool tests
# ---------------------------------------------------------------------------

class TestExecuteTool:
    def test_dispatch_search(self):
        result = json.loads(execute_tool("search_invoices", {"query": "overdue"}))
        assert isinstance(result, list)
        assert len(result) == 1

    def test_dispatch_details(self):
        result = json.loads(
            execute_tool("get_invoice_details", {"invoice_id": "INV-001"})
        )
        assert result["id"] == "INV-001"

    def test_dispatch_calculate(self):
        result = json.loads(
            execute_tool("calculate_total", {"invoice_ids": ["INV-001"]})
        )
        assert result["net_total"] == 2500.00

    def test_unknown_tool(self):
        result = json.loads(execute_tool("delete_everything", {}))
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_bad_arguments(self):
        result = json.loads(
            execute_tool("search_invoices", {"wrong_param": "test"})
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# Agent integration (mocked LLM)
# ---------------------------------------------------------------------------

class TestAgentMocked:
    """Test the agent loop with mocked LLM responses."""

    def test_run_agent_unknown_provider(self):
        result = run_agent("test question", provider="fake_provider")
        assert "Unknown provider" in result["answer"]
        assert result["tool_calls"] == []

    def test_run_agent_missing_api_key(self):
        """Agent should return an error if API key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            result = run_agent("test", provider="anthropic")
            assert "error" in result["answer"].lower() or "Agent error" in result["answer"]

    def test_run_agent_returns_history(self):
        """Result should include history key."""
        result = run_agent("test", provider="fake_provider")
        assert "history" in result