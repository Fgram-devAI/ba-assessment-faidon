# TypeScript Implementation

Full TypeScript implementation of the invoice processing system, mirroring the Python version.

## Tech Stack

- **Node.js 20+** / **TypeScript 5**
- **Zod** — schema validation (Pydantic equivalent)
- **Express** — web API (FastAPI equivalent)
- **Anthropic SDK** — native tool-calling for Claude
- **OpenAI SDK** — GPT-4o-mini support
- **Gemini REST API** — free-tier provider
- **Vitest** — testing
- **tsx** — run TypeScript directly without build step

## Project Structure

```
src/
  models.ts          # Zod schemas with validators
  transform.ts       # Flat CSV dicts → nested validated JSON
  extract.ts         # LLM extraction from raw text (multi-provider)
  agent.ts           # AI agent with native tool use + conversation memory
  data.ts            # Shared mock invoice data
  app.ts             # Express API (port 3000)
  __tests__/
    models.test.ts   # Schema validation tests
    transform.test.ts # Transformation logic tests
    extract.test.ts  # Mocked LLM extraction tests
    agent.test.ts    # Tool function tests
```

## Setup

```bash
cd typescript
npm install
```

Uses the same `.env` file from the project root:

```env
ANTHROPIC_API_KEY=your-key-here
OPENAI_API_KEY=your-key-here
GEMINI_API_KEY=your-key-here
```

## Usage

### Data Transformation

```bash
npx tsx src/transform.ts
```

### LLM Extraction

```bash
# Default: Anthropic with sample invoice
npx tsx src/extract.ts

# Switch provider
npx tsx src/extract.ts -p openai
npx tsx src/extract.ts -p gemini

# Extract from file
npx tsx src/extract.ts ../samples/invoice_en.txt -p gemini
```

### AI Agent (Interactive CLI)

```bash
npx tsx src/agent.ts
npx tsx src/agent.ts -p openai
npx tsx src/agent.ts -p gemini
```

Supports multi-step reasoning with conversation memory across turns.

### Express API

```bash
npx tsx src/app.ts
```

API runs on `http://localhost:3000`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/invoices/extract` | Extract structured data from raw text via LLM |
| `POST` | `/invoices/transform` | Transform flat records to nested JSON |
| `POST` | `/invoices/query` | Natural language questions via AI agent |
| `GET` | `/invoices` | List all invoices (mock + stored) |
| `GET` | `/health` | Health check |

**Example requests:**

```bash
# Transform
curl -X POST http://localhost:3000/invoices/transform \
  -H "Content-Type: application/json" \
  -d '{"records": [{"invoice_number": "2024-0892", "invoice_date": "15.03.2024", "seller_name": "TechSolutions GmbH", "seller_street": "Musterstrasse 42", "seller_city": "Berlin", "seller_zip": "10115", "seller_country": "DE", "seller_vat_id": "DE123456789", "buyer_name": "Digital Services AG", "buyer_city": "Munchen", "buyer_vat_id": "DE987654321", "item_description": "Cloud Hosting", "item_quantity": "3", "item_unit_price": "450.00", "item_vat_rate": "19", "payment_days": "30", "iban": "DE89370400440532013000"}]}'

# Query
curl -X POST http://localhost:3000/invoices/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Which invoices are overdue?", "provider": "gemini"}'

# List invoices
curl http://localhost:3000/invoices
```

## Docker

```bash
# From project root
docker build -f typescript/Dockerfile -t invoice-api-ts .
docker run -p 3000:3000 --env-file .env invoice-api-ts
```

## Tests

```bash
# Run all tests
npm test

# Watch mode
npm run test:watch
```

All tests use mocked LLM responses — no API keys needed to run the test suite.

## Key Differences from Python

| Aspect | Python | TypeScript |
|--------|--------|------------|
| Validation | Pydantic v2 | Zod |
| API | FastAPI (port 8000) | Express (port 3000) |
| Testing | Pytest | Vitest |
| LLM SDK | anthropic / openai | @anthropic-ai/sdk / openai |
| Runtime | Python 3.11+ | Node 20+ via tsx |