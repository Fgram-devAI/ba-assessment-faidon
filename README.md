# BA Assessment — Faidon

An end-to-end invoice processing system built with Python, FastAPI, and the Anthropic SDK.

## Architecture

```mermaid
graph LR
    subgraph Inputs
        A[Raw German Text] -->|POST /invoices/extract| E[LLM Extraction]
        B[Flat CSV Dicts] -->|POST /invoices/transform| T[Transformer]
        C[Natural Language Query] -->|POST /invoices/query| AG[AI Agent]
    end

    subgraph Core
        E --> V[Pydantic Validation]
        T --> V
        V --> S[(In-Memory Store)]
        AG -->|tool calls| Tools[search / details / calculate]
        Tools --> S
    end

    subgraph Output
        S -->|GET /invoices| JSON[Validated Invoice JSON]
        AG --> Answer[Agent Response]
    end
```

## Implementation Roadmap

- [x] **Phase 1** — Pydantic v2 schemas (`models.py`)
- [x] **Phase 2** — Data transformation: flat CSV dicts → nested JSON (`section-3/transform.py`)
- [ ] **Phase 3** — LLM extraction: raw German text → validated JSON (`section-1/extract.py`)
- [ ] **Phase 4** — AI agent with native tool use (`section-2/agent.py`)
- [ ] **Phase 5** — FastAPI endpoints, Dockerfile, pytest suite (`section-5/`)
- [ ] **Written** — Conceptual questions (`section-1/answers.md`)
- [ ] **Written** — System design answers (`section-4/design.md`)

## Project Structure

```
models.py             # Pydantic v2 schemas (shared across sections)
/section-1/
  extract.py          # 1A — LLM-based structured data extraction
  answers.md          # 1B — Conceptual questions
/section-2/
  agent.py            # AI agent with native tool use
/section-3/
  transform.py        # API data transformation (flat → nested)
/section-4/
  design.md           # System design answers
/section-5/
  app.py              # FastAPI application
  tests/              # Pytest suite
  Dockerfile
requirements.txt
README.md
```

## Tech Stack

- **Python 3.11+**
- **Pydantic v2** — data modeling and validation
- **Anthropic SDK** — direct LLM integration (no LangChain / LlamaIndex)
- **FastAPI** — web API (Section 5)
- **Pytest** — testing

## LLM Provider

**Anthropic (Claude)** — chosen for its native structured tool-use API and strong performance on multilingual document extraction (the invoices are in German).

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Set your API key:

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

## Assumptions

- All monetary values use EUR.
- VAT IDs follow the format: 2-letter country code + digits (e.g. `DE123456789`).
- Dates are normalized to ISO 8601 (`YYYY-MM-DD`).
- IBAN validation is format-based (country code + check digits + account), not checksum-verified.

## What I'd Improve Given More Time

- Full IBAN checksum validation (mod-97).
- PDF / scanned image ingestion with OCR.
- Persistent database storage instead of in-memory store.
- Rate limiting and authentication on the API.
- CI/CD pipeline with automated test runs.