"""
Section 2: AI Agent with Tool Use

A command-line agent that answers questions about invoices using
Claude's native tool-calling API. Runs a multi-step loop where the LLM
decides which tool to call, we execute it, feed results back, and repeat
until the LLM produces a final text answer.

Usage:
    python section-2/agent.py
    python section-2/agent.py -p openai
    python section-2/agent.py -p gemini
"""

import argparse
import os
import sys
import json
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Mock invoice data (from the assessment)
# ---------------------------------------------------------------------------

INVOICES = [
    {
        "id": "INV-001",
        "customer": "Digital Services AG",
        "date": "2024-01-15",
        "net_total": 2500.00,
        "vat_rate": 0.19,
        "vat_amount": 475.00,
        "gross_total": 2975.00,
        "status": "paid",
        "items": [
            {
                "description": "Cloud Hosting Q1",
                "quantity": 1,
                "unit_price": 1500.00,
                "total": 1500.00,
            },
            {
                "description": "Support Hours",
                "quantity": 10,
                "unit_price": 100.00,
                "total": 1000.00,
            },
        ],
    },
    {
        "id": "INV-002",
        "customer": "Digital Services AG",
        "date": "2024-04-15",
        "net_total": 3200.00,
        "vat_rate": 0.19,
        "vat_amount": 608.00,
        "gross_total": 3808.00,
        "status": "pending",
        "items": [
            {
                "description": "Cloud Hosting Q2",
                "quantity": 1,
                "unit_price": 1800.00,
                "total": 1800.00,
            },
            {
                "description": "API Integration",
                "quantity": 1,
                "unit_price": 1400.00,
                "total": 1400.00,
            },
        ],
    },
    {
        "id": "INV-003",
        "customer": "Munchen Logistics GmbH",
        "date": "2024-03-01",
        "net_total": 8500.00,
        "vat_rate": 0.19,
        "vat_amount": 1615.00,
        "gross_total": 10115.00,
        "status": "overdue",
        "items": [
            {
                "description": "Warehouse Management System",
                "quantity": 1,
                "unit_price": 5000.00,
                "total": 5000.00,
            },
            {
                "description": "Training Sessions",
                "quantity": 5,
                "unit_price": 500.00,
                "total": 2500.00,
            },
            {
                "description": "Data Migration",
                "quantity": 1,
                "unit_price": 1000.00,
                "total": 1000.00,
            },
        ],
    },
    {
        "id": "INV-004",
        "customer": "Berlin Startup Hub",
        "date": "2024-02-20",
        "net_total": 1200.00,
        "vat_rate": 0.19,
        "vat_amount": 228.00,
        "gross_total": 1428.00,
        "status": "paid",
        "items": [
            {
                "description": "Website Redesign",
                "quantity": 1,
                "unit_price": 800.00,
                "total": 800.00,
            },
            {
                "description": "SEO Optimization",
                "quantity": 1,
                "unit_price": 400.00,
                "total": 400.00,
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def search_invoices(
    query: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Search invoices by customer name, invoice number, or keyword."""
    query_lower = query.lower()
    results = []

    for inv in INVOICES:
        # Match against id, customer, status, or item descriptions
        searchable = " ".join([
            inv["id"],
            inv["customer"],
            inv["status"],
            inv["date"],
            *(item["description"] for item in inv["items"]),
        ]).lower()

        if query_lower in searchable:
            # Apply date filters
            if date_from and inv["date"] < date_from:
                continue
            if date_to and inv["date"] > date_to:
                continue

            # Return summary (without full items for search results)
            results.append({
                "id": inv["id"],
                "customer": inv["customer"],
                "date": inv["date"],
                "net_total": inv["net_total"],
                "gross_total": inv["gross_total"],
                "status": inv["status"],
            })

    return results


def get_invoice_details(invoice_id: str) -> dict:
    """Get full details for a specific invoice including line items."""
    for inv in INVOICES:
        if inv["id"] == invoice_id:
            return inv
    return {"error": f"Invoice {invoice_id} not found"}


def calculate_total(invoice_ids: list[str]) -> dict:
    """Calculate net, vat, and gross totals across multiple invoices."""
    net = Decimal("0")
    vat = Decimal("0")
    gross = Decimal("0")
    found = []
    not_found = []

    for inv_id in invoice_ids:
        invoice = next((inv for inv in INVOICES if inv["id"] == inv_id), None)
        if invoice:
            net += Decimal(str(invoice["net_total"]))
            vat += Decimal(str(invoice["vat_amount"]))
            gross += Decimal(str(invoice["gross_total"]))
            found.append(inv_id)
        else:
            not_found.append(inv_id)

    result = {
        "invoice_ids": found,
        "net_total": float(net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "vat_total": float(vat.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "gross_total": float(gross.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
    }

    if not_found:
        result["not_found"] = not_found

    return result


# Tool registry for dispatching
TOOL_FUNCTIONS = {
    "search_invoices": search_invoices,
    "get_invoice_details": get_invoice_details,
    "calculate_total": calculate_total,
}


# ---------------------------------------------------------------------------
# Tool definitions for Claude API
# ---------------------------------------------------------------------------

TOOLS_ANTHROPIC = [
    {
        "name": "search_invoices",
        "description": "Search invoices by customer name, invoice number, or keyword. Returns matching invoice summaries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term: customer name, invoice number, status, or keyword",
                },
                "date_from": {
                    "type": "string",
                    "description": "Optional start date filter (YYYY-MM-DD)",
                },
                "date_to": {
                    "type": "string",
                    "description": "Optional end date filter (YYYY-MM-DD)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_invoice_details",
        "description": "Get full details for a specific invoice including all line items, totals, and status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {
                    "type": "string",
                    "description": "The invoice ID (e.g. INV-001)",
                },
            },
            "required": ["invoice_id"],
        },
    },
    {
        "name": "calculate_total",
        "description": "Calculate combined net, VAT, and gross totals across multiple invoices.",
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of invoice IDs to sum up",
                },
            },
            "required": ["invoice_ids"],
        },
    },
]

# OpenAI uses a slightly different format (function calling)
TOOLS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }
    for tool in TOOLS_ANTHROPIC
]


# ---------------------------------------------------------------------------
# Execute a tool call
# ---------------------------------------------------------------------------

def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name with the given arguments. Returns JSON string."""
    if name not in TOOL_FUNCTIONS:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        result = TOOL_FUNCTIONS[name](**arguments)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {e}"})


# ---------------------------------------------------------------------------
# System prompt (shared across all providers)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a helpful invoice assistant with access to an invoice database.\n\n"
    "IMPORTANT RULES:\n"
    "1. ALWAYS use tools to look up data before answering. NEVER guess or say you cannot.\n"
    "2. You have 3 tools: search_invoices, get_invoice_details, calculate_total.\n"
    "3. search_invoices searches across customer names, invoice IDs, statuses (paid/pending/overdue), "
    "dates, and item descriptions. For example, to find overdue invoices, search for 'overdue'.\n"
    "4. get_invoice_details returns full line items for a specific invoice ID.\n"
    "5. calculate_total sums net/vat/gross across a list of invoice IDs.\n"
    "6. If your first search returns no results, try different keywords or broader terms.\n"
    "7. When you have enough data, provide a clear, specific answer with numbers."
)


# ---------------------------------------------------------------------------
# Agent loops (one per provider)
# ---------------------------------------------------------------------------

def run_anthropic_agent(
    question: str, history: list[dict] | None = None
) -> tuple[str, list[dict], list[dict]]:
    """
    Run the tool-use agent loop using the Anthropic SDK.
    Returns (final_answer, tool_calls_log, updated_history).
    """
    from anthropic import Anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment or .env")

    client = Anthropic(api_key=api_key)
    messages = history if history else []
    messages.append({"role": "user", "content": question})
    tool_calls_log: list[dict] = []

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS_ANTHROPIC,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_id = block.id

                    print(f"  [tool] {tool_name}({json.dumps(tool_input)})")
                    result = execute_tool(tool_name, tool_input)
                    tool_calls_log.append({
                        "tool": tool_name,
                        "input": tool_input,
                        "output": json.loads(result),
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        else:
            answer = ""
            for block in response.content:
                if hasattr(block, "text"):
                    answer += block.text
            # Add final assistant response to history
            messages.append({"role": "assistant", "content": response.content})
            return answer, tool_calls_log, messages


def run_openai_agent(
    question: str, history: list[dict] | None = None
) -> tuple[str, list[dict], list[dict]]:
    """
    Run the tool-use agent loop using the OpenAI SDK.
    Returns (final_answer, tool_calls_log, updated_history).
    """
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment or .env")

    client = OpenAI(api_key=api_key)

    if history:
        messages = history
    else:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.append({"role": "user", "content": question})
    tool_calls_log: list[dict] = []

    while True:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS_OPENAI,
        )

        choice = response.choices[0]

        if choice.finish_reason == "tool_calls":
            messages.append(choice.message)

            for tool_call in choice.message.tool_calls:
                tool_name = tool_call.function.name
                tool_input = json.loads(tool_call.function.arguments)

                print(f"  [tool] {tool_name}({json.dumps(tool_input)})")
                result = execute_tool(tool_name, tool_input)
                tool_calls_log.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "output": json.loads(result),
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

        else:
            messages.append({"role": "assistant", "content": choice.message.content})
            return choice.message.content, tool_calls_log, messages


def run_gemini_agent(
    question: str, history: list[dict] | None = None
) -> tuple[str, list[dict], list[dict]]:
    """
    Run the tool-use agent loop using the Gemini REST API.
    Returns (final_answer, tool_calls_log, updated_history).
    """
    import httpx

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in environment or .env")

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    def _clean_schema(schema: dict) -> dict:
        cleaned = {
            "type": schema["type"],
            "properties": schema["properties"],
        }
        if "required" in schema:
            cleaned["required"] = schema["required"]
        return cleaned

    gemini_tools = [{
        "function_declarations": [
            {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": _clean_schema(tool["input_schema"]),
            }
            for tool in TOOLS_ANTHROPIC
        ]
    }]

    contents = history if history else []
    contents.append({"role": "user", "parts": [{"text": question}]})
    tool_calls_log: list[dict] = []

    system_instruction = {
        "parts": [{"text": SYSTEM_PROMPT}]
    }

    while True:
        payload = {
            "system_instruction": system_instruction,
            "contents": contents,
            "tools": gemini_tools,
        }

        response = httpx.post(url, json=payload, timeout=60)
        if response.status_code != 200:
            raise RuntimeError(
                f"Gemini API error {response.status_code}: {response.text}"
            )
        data = response.json()

        candidate = data["candidates"][0]
        parts = candidate["content"]["parts"]

        function_calls = [p for p in parts if "functionCall" in p]

        if function_calls:
            contents.append({"role": "model", "parts": parts})

            function_responses = []
            for fc_part in function_calls:
                fc = fc_part["functionCall"]
                tool_name = fc["name"]
                tool_input = fc.get("args", {})

                print(f"  [tool] {tool_name}({json.dumps(tool_input)})")
                result = execute_tool(tool_name, tool_input)
                tool_calls_log.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "output": json.loads(result),
                })

                function_responses.append({
                    "functionResponse": {
                        "name": tool_name,
                        "response": {"result": json.loads(result)},
                    }
                })

            for fr in function_responses:
                contents.append({"role": "function", "parts": [fr]})

        else:
            answer = ""
            for part in parts:
                if "text" in part:
                    answer += part["text"]
            # Add final model response to history
            contents.append({"role": "model", "parts": [{"text": answer}]})
            return answer, tool_calls_log, contents


AGENT_RUNNERS = {
    "anthropic": run_anthropic_agent,
    "openai": run_openai_agent,
    "gemini": run_gemini_agent,
}


# ---------------------------------------------------------------------------
# Public API (used by Section 5 FastAPI)
# ---------------------------------------------------------------------------

def run_agent(
    question: str,
    provider: str = "anthropic",
    history: list[dict] | None = None,
) -> dict:
    """
    Run the invoice agent and return a structured result.

    Returns dict with: answer, tool_calls, provider, history
    """
    if provider not in AGENT_RUNNERS:
        return {
            "answer": f"Unknown provider '{provider}'. Choose: {list(AGENT_RUNNERS.keys())}",
            "tool_calls": [],
            "provider": provider,
            "history": history or [],
        }

    try:
        answer, tool_calls, updated_history = AGENT_RUNNERS[provider](
            question, history
        )
        return {
            "answer": answer,
            "tool_calls": tool_calls,
            "provider": provider,
            "history": updated_history,
        }
    except Exception as e:
        return {
            "answer": f"Agent error: {e}",
            "tool_calls": [],
            "provider": provider,
            "history": history or [],
        }


# ---------------------------------------------------------------------------
# CLI conversation loop
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Invoice AI agent with tool use.")
    parser.add_argument(
        "--provider", "-p",
        choices=list(AGENT_RUNNERS.keys()),
        default=os.getenv("LLM_PROVIDER", "anthropic").lower(),
        help="LLM provider (default: anthropic)",
    )
    args = parser.parse_args()

    print(f"Invoice Agent (provider: {args.provider})")
    print("Ask questions about invoices. Type 'quit' or 'exit' to stop.\n")

    history: list[dict] | None = None

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not question:
            continue

        # Catch exit intent — only on short inputs to avoid false positives
        words = set(question.lower().split())
        exit_words = {"quit", "exit", "q", "bye", "stop"}
        if len(words) <= 3 and words & exit_words:
            print("Bye!")
            break

        print()
        result = run_agent(question, provider=args.provider, history=history)
        history = result["history"]
        print(f"\nAgent: {result['answer']}")

        if result["tool_calls"]:
            print(f"\n  Tools used: {[tc['tool'] for tc in result['tool_calls']]}")
        print()