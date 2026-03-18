import argparse
import os
import sys
import json
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

from dotenv import load_dotenv

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from models import Invoice

load_dotenv()

# ---------------------------------------------------------------------------
# Sample invoice text (used only when no input is provided)
# ---------------------------------------------------------------------------

SAMPLE_INVOICE = """
Rechnung Nr. 2024-0892
Datum: 15.03.2024
Von:
TechSolutions GmbH
Musterstrasse 42
10115 Berlin
USt-IdNr.: DE123456789
An:
Digital Services AG
Hauptweg 7
80331 Munchen
USt-IdNr.: DE987654321
Pos. 1: Cloud Hosting Premium (Jan-Mar 2024) - 3 x 450,00 EUR = 1.350,00 EUR
Pos. 2: SSL-Zertifikat Erneuerung - 1 x 89,50 EUR = 89,50 EUR
Pos. 3: Technischer Support (15 Stunden) - 15 x 95,00 EUR = 1.425,00 EUR
Nettobetrag: 2.864,50 EUR
USt. 19%: 544,26 EUR
Bruttobetrag: 3.408,76 EUR
Zahlungsziel: 30 Tage
Bankverbindung: IBAN DE89 3704 0044 0532 0130 00
""".strip()

# ---------------------------------------------------------------------------
# Extraction prompt (language-agnostic)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a precise data extraction assistant. "
    "You extract structured data from invoices in any language or format. "
    "Return ONLY valid JSON — no markdown, no explanation, no code fences."
)

EXTRACTION_PROMPT = """Extract the following invoice into JSON matching this exact schema:

{{
  "invoiceNumber": "string",
  "issueDate": "YYYY-MM-DD",
  "seller": {{
    "name": "string",
    "address": {{ "street": "string", "city": "string", "postalCode": "string", "countryCode": "2-letter ISO code" }},
    "vatId": "string (country code + digits, e.g. DE123456789)"
  }},
  "buyer": {{
    "name": "string",
    "address": {{ "street": "string", "city": "string", "postalCode": "string", "countryCode": "2-letter ISO code" }},
    "vatId": "string"
  }},
  "lineItems": [
    {{
      "description": "string",
      "quantity": integer > 0,
      "unitPrice": float >= 0,
      "vatRate": float (percentage, e.g. 19),
      "lineTotal": float (must equal quantity * unitPrice)
    }}
  ],
  "totals": {{
    "netAmount": float (sum of all lineTotal values),
    "vatAmount": float,
    "grossAmount": float (netAmount + vatAmount)
  }},
  "paymentTerms": {{
    "dueDays": integer > 0,
    "dueDate": "YYYY-MM-DD (issueDate + dueDays)"
  }},
  "paymentMeans": {{
    "iban": "string (no spaces)"
  }}
}}

Rules:
- Detect the language and date format automatically.
- Convert any date format to ISO 8601 (YYYY-MM-DD).
- Convert any local number format (e.g. 1.350,00 or 1,350.00) to standard floats (1350.00).
- Compute dueDate by adding dueDays to issueDate.
- Remove spaces from IBAN.
- If a field is not present in the text, infer it from context where possible.
- Return ONLY the JSON object, nothing else.

Invoice text:
{invoice_text}"""


# ---------------------------------------------------------------------------
# Input reading
# ---------------------------------------------------------------------------

def read_input() -> str:
    """
    Read invoice text from:
      1. File path passed as CLI argument
      2. Stdin (if piped)
      3. Fall back to the built-in sample
    """
    # Check for file argument
    if len(sys.argv) > 1:
        file_path = Path(sys.argv[1])
        if not file_path.exists():
            print(f"Error: file not found — {file_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Reading invoice from: {file_path}")
        return file_path.read_text(encoding="utf-8").strip()

    # Check for piped stdin
    if not sys.stdin.isatty():
        text = sys.stdin.read().strip()
        if text:
            print("Reading invoice from: stdin")
            return text

    # Default to sample
    print("No input provided — using built-in sample invoice")
    return SAMPLE_INVOICE


# ---------------------------------------------------------------------------
# LLM provider abstraction
# ---------------------------------------------------------------------------

def call_anthropic(prompt: str) -> str:
    """Call Claude via the Anthropic SDK and return the text response."""
    from anthropic import Anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment or .env")

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def call_openai(prompt: str) -> str:
    """Call GPT-4o-mini via the OpenAI SDK and return the text response."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment or .env")

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content


def call_gemini(prompt: str) -> str:
    """Call Gemini 2.5 Flash Lite via the REST API (free tier)."""
    import httpx

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in environment or .env")

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0},
    }

    response = httpx.post(url, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


PROVIDERS = {
    "anthropic": call_anthropic,
    "openai": call_openai,
    "gemini": call_gemini,
}


# ---------------------------------------------------------------------------
# Extraction with retry
# ---------------------------------------------------------------------------

def clean_json_response(raw: str) -> str:
    """Strip markdown code fences and whitespace from LLM response."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def extract_invoice(
    invoice_text: str,
    provider: str = "anthropic",
    max_retries: int = 3,
) -> tuple[Invoice | None, list[str]]:
    """
    Send invoice text to the LLM, parse and validate the response.

    Returns (validated Invoice or None, list of error messages).
    Retries up to max_retries times on malformed or invalid output.
    """
    if provider not in PROVIDERS:
        return None, [f"Unknown provider '{provider}'. Choose: {list(PROVIDERS.keys())}"]

    call_llm = PROVIDERS[provider]
    prompt = EXTRACTION_PROMPT.format(invoice_text=invoice_text)
    errors: list[str] = []

    for attempt in range(1, max_retries + 1):
        try:
            raw_response = call_llm(prompt)

            cleaned = clean_json_response(raw_response)
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError as e:
                errors.append(f"Attempt {attempt}: Invalid JSON — {e}")
                continue

            invoice = Invoice(**data)
            return invoice, []

        except Exception as e:
            errors.append(f"Attempt {attempt}: {e}")
            continue

    return None, errors


# ---------------------------------------------------------------------------
# Validation report
# ---------------------------------------------------------------------------

def print_validation_report(invoice: Invoice | None, errors: list[str]) -> None:
    """Print a clear pass/fail validation report to stdout."""
    print("=" * 60)
    print("INVOICE EXTRACTION — VALIDATION REPORT")
    print("=" * 60)

    if invoice is None:
        print("\nRESULT: FAIL\n")
        for err in errors:
            print(f"  ERROR: {err}")
        return

    print("\nRESULT: PASS\n")
    data = invoice.model_dump(by_alias=True)
    print(json.dumps(data, indent=2))

    # Cross-validation checks
    print("\n" + "-" * 40)
    print("CROSS-VALIDATION CHECKS:")
    print("-" * 40)

    # Check 1: Line item sum == netAmount
    line_sum = sum(Decimal(str(li["lineTotal"])) for li in data["lineItems"])
    line_sum_f = float(line_sum.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    net = data["totals"]["netAmount"]
    check1 = abs(net - line_sum_f) <= 0.01
    print(f"  Line items sum ({line_sum_f}) == netAmount ({net}): "
          f"{'PASS' if check1 else 'FAIL'}")

    # Check 2: VAT calculation
    vat_rate = data["lineItems"][0]["vatRate"]
    expected_vat = float(
        (Decimal(str(net)) * Decimal(str(vat_rate)) / Decimal("100"))
        .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )
    actual_vat = data["totals"]["vatAmount"]
    check2 = abs(actual_vat - expected_vat) <= 0.01
    print(f"  VAT: {net} * {vat_rate}% = {expected_vat} == {actual_vat}: "
          f"{'PASS' if check2 else 'FAIL'}")

    # Check 3: Gross = net + VAT
    expected_gross = float(
        (Decimal(str(net)) + Decimal(str(actual_vat)))
        .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )
    actual_gross = data["totals"]["grossAmount"]
    check3 = abs(actual_gross - expected_gross) <= 0.01
    print(f"  Gross: {net} + {actual_vat} = {expected_gross} == {actual_gross}: "
          f"{'PASS' if check3 else 'FAIL'}")

    all_pass = check1 and check2 and check3
    print(f"\n  OVERALL: {'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract structured data from invoice text using an LLM.")
    parser.add_argument("file", nargs="?", help="Path to invoice text file")
    parser.add_argument(
        "--provider", "-p",
        choices=list(PROVIDERS.keys()),
        default=os.getenv("LLM_PROVIDER", "anthropic").lower(),
        help="LLM provider to use (default: anthropic, or set LLM_PROVIDER env var)",
    )
    args = parser.parse_args()

    # Override sys.argv so read_input() picks up the file arg
    if args.file:
        sys.argv = [sys.argv[0], args.file]
    else:
        sys.argv = [sys.argv[0]]

    print(f"Using LLM provider: {args.provider}\n")

    invoice_text = read_input()
    print()

    invoice, errors = extract_invoice(invoice_text, provider=args.provider)
    print_validation_report(invoice, errors)