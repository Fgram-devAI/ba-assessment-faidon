"""
Section 5: End-to-End Invoice Processing API

FastAPI application that combines Sections 1–3 into a working web API:
- POST /invoices/extract  — LLM extraction from raw text
- POST /invoices/transform — Flat CSV dicts → nested JSON
- POST /invoices/query — Natural language agent queries
- GET  /invoices — All stored invoices

Run:
    uvicorn section-5.app:app --reload
"""

import importlib.util
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Module imports from other sections (hyphenated directory names)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent

# models.py — at project root
sys.path.insert(0, str(ROOT))
from models import Invoice  # noqa: E402


def _load_module(name: str, file_path: Path):
    """Load a Python module from a hyphenated directory path."""
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


extract_mod = _load_module("extract", ROOT / "section-1" / "extract.py")
transform_mod = _load_module("transform", ROOT / "section-3" / "transform.py")
agent_mod = _load_module("agent", ROOT / "section-2" / "agent.py")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("invoice-api")


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

invoice_store: list[dict] = []


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ExtractRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=10,
        description="Raw unstructured invoice text to extract data from",
    )
    provider: str = Field(
        default="anthropic",
        description="LLM provider: anthropic, openai, or gemini",
    )


class ExtractResponse(BaseModel):
    invoice: dict
    validation_passed: bool
    errors: list[str] = []


class TransformRequest(BaseModel):
    records: list[dict] = Field(
        ...,
        min_length=1,
        description="Flat CSV-style records (System A format)",
    )


class TransformResponse(BaseModel):
    invoices: list[dict]
    warnings: list[str] = []
    errors: list[str] = []


class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        description="Natural language question about invoices",
    )
    provider: str = Field(
        default="anthropic",
        description="LLM provider: anthropic, openai, or gemini",
    )


class QueryResponse(BaseModel):
    answer: str
    tool_calls: list[dict] = []
    provider: str


class ErrorResponse(BaseModel):
    detail: str
    errors: list[str] = []


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Invoice Processing API",
    description=(
        "End-to-end invoice processing: LLM extraction, data transformation, "
        "and natural language queries via an AI agent with tool use."
    ),
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# POST /invoices/extract
# ---------------------------------------------------------------------------

@app.post(
    "/invoices/extract",
    response_model=ExtractResponse,
    responses={422: {"model": ErrorResponse}},
)
async def extract_invoice(request: ExtractRequest):
    """
    Extract structured invoice data from raw text using an LLM.

    Sends the text to the chosen LLM provider, parses the response into
    a validated Invoice schema, and stores the result in memory.
    """
    logger.info("Extract request — provider=%s, text_length=%d", request.provider, len(request.text))

    valid_providers = {"anthropic", "openai", "gemini"}
    if request.provider not in valid_providers:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid provider '{request.provider}'. Choose from: {sorted(valid_providers)}",
        )

    invoice, errors = extract_mod.extract_invoice(
        request.text, provider=request.provider
    )

    if invoice is None:
        raise HTTPException(
            status_code=422,
            detail="Extraction failed — LLM could not produce valid data",
        )

    invoice_dict = invoice.model_dump(by_alias=True)

    if not errors:
        invoice_store.append(invoice_dict)
        logger.info("Stored invoice %s", invoice_dict.get("invoiceNumber"))

    return ExtractResponse(
        invoice=invoice_dict,
        validation_passed=len(errors) == 0,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# POST /invoices/transform
# ---------------------------------------------------------------------------

@app.post(
    "/invoices/transform",
    response_model=TransformResponse,
    responses={422: {"model": ErrorResponse}},
)
async def transform_records(request: TransformRequest):
    """
    Transform flat CSV-style records (System A) into nested JSON (System B).

    Groups records by invoice_number, merges line items, validates the
    output through Pydantic models, and stores valid invoices in memory.
    """
    logger.info("Transform request — %d records", len(request.records))

    result = transform_mod.transform(request.records)

    if not result.invoices and result.errors:
        raise HTTPException(
            status_code=422,
            detail="Transformation failed — no valid invoices produced",
        )

    invoices_out = []
    for inv_dict in result.invoices:
        invoices_out.append(inv_dict)
        invoice_store.append(inv_dict)
        logger.info("Stored invoice %s", inv_dict.get("invoiceNumber"))

    return TransformResponse(
        invoices=invoices_out,
        warnings=result.warnings,
        errors=result.errors,
    )


# ---------------------------------------------------------------------------
# POST /invoices/query
# ---------------------------------------------------------------------------

@app.post(
    "/invoices/query",
    response_model=QueryResponse,
)
async def query_invoices(request: QueryRequest):
    """
    Answer a natural language question about invoices using the AI agent.

    The agent uses tool calling to search invoices, get details, and
    calculate totals. Returns the answer and which tools were called.
    """
    logger.info("Query request — provider=%s, question=%s", request.provider, request.question[:80])

    valid_providers = {"anthropic", "openai", "gemini"}
    if request.provider not in valid_providers:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid provider '{request.provider}'. Choose from: {sorted(valid_providers)}",
        )

    result = agent_mod.run_agent(request.question, provider=request.provider)

    return QueryResponse(
        answer=result["answer"],
        tool_calls=result["tool_calls"],
        provider=result["provider"],
    )


# ---------------------------------------------------------------------------
# GET /invoices
# ---------------------------------------------------------------------------

@app.get("/invoices", response_model=list[dict])
async def list_invoices():
    """
    Return all invoices currently stored in memory.

    Includes mock data from the agent module plus any invoices extracted
    or transformed via the endpoints above.
    """
    # Combine agent's mock data with extracted/transformed invoices
    mock_invoices = [
        {
            "id": inv["id"],
            "customer": inv["customer"],
            "date": inv["date"],
            "net_total": inv["net_total"],
            "gross_total": inv["gross_total"],
            "status": inv["status"],
            "source": "mock",
        }
        for inv in agent_mod.INVOICES
    ]

    stored = [
        {**inv, "source": "extracted/transformed"}
        for inv in invoice_store
    ]

    return mock_invoices + stored


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Run directly: python section-5/app.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)