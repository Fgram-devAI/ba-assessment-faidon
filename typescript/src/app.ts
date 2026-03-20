import express, { Request, Response } from "express";
import { resolve } from "path";
import dotenv from "dotenv";

import { InvoiceSchema, type Invoice } from "./models.js";
import { transform, type SystemARecord } from "./transform.js";
import { extractInvoice } from "./extract.js";
import { runAgent } from "./agent.js";
import { INVOICES } from "./data.js";

dotenv.config({ path: resolve(__dirname, "../../.env") });

const app = express();
app.use(express.json());

const PORT = parseInt(process.env.PORT ?? "3000", 10);

// ---------------------------------------------------------------------------
// In-memory store
// ---------------------------------------------------------------------------

const invoiceStore: Invoice[] = [];

// ---------------------------------------------------------------------------
// GET /health
// ---------------------------------------------------------------------------

app.get("/health", (_req: Request, res: Response) => {
  res.json({ status: "ok" });
});

// ---------------------------------------------------------------------------
// GET /invoices
// ---------------------------------------------------------------------------

app.get("/invoices", (_req: Request, res: Response) => {
  res.json({
    mock_invoices: INVOICES,
    stored_invoices: invoiceStore,
    total: INVOICES.length + invoiceStore.length,
  });
});

// ---------------------------------------------------------------------------
// POST /invoices/extract
// ---------------------------------------------------------------------------

interface ExtractBody {
  text: string;
  provider?: string;
}

app.post("/invoices/extract", async (req: Request, res: Response) => {
  const body = req.body as ExtractBody;

  if (!body.text || body.text.trim().length < 10) {
    res.status(422).json({
      error: "Validation error",
      detail: "Field 'text' is required and must be at least 10 characters",
    });
    return;
  }

  const provider = body.provider ?? "anthropic";
  console.log(`[extract] provider=${provider}, text_length=${body.text.length}`);

  const result = await extractInvoice(body.text.trim(), provider);

  if (!result.invoice) {
    res.status(422).json({
      error: "Extraction failed",
      detail: result.errors,
    });
    return;
  }

  invoiceStore.push(result.invoice);
  res.json({
    invoice: result.invoice,
    provider,
  });
});

// ---------------------------------------------------------------------------
// POST /invoices/transform
// ---------------------------------------------------------------------------

interface TransformBody {
  records: SystemARecord[];
}

app.post("/invoices/transform", (req: Request, res: Response) => {
  const body = req.body as TransformBody;

  if (!body.records || !Array.isArray(body.records) || body.records.length === 0) {
    res.status(422).json({
      error: "Validation error",
      detail: "Field 'records' is required and must be a non-empty array",
    });
    return;
  }

  console.log(`[transform] records=${body.records.length}`);

  const result = transform(body.records);

  if (!result.success) {
    res.status(422).json({
      error: "Transformation failed",
      detail: result.errors,
    });
    return;
  }

  // Store transformed invoices
  for (const inv of result.invoices) {
    invoiceStore.push(inv);
  }

  res.json({
    invoices: result.invoices,
    warnings: result.warnings,
    errors: result.errors,
  });
});

// ---------------------------------------------------------------------------
// POST /invoices/query
// ---------------------------------------------------------------------------

interface QueryBody {
  question: string;
  provider?: string;
}

app.post("/invoices/query", async (req: Request, res: Response) => {
  const body = req.body as QueryBody;

  if (!body.question || body.question.trim().length === 0) {
    res.status(422).json({
      error: "Validation error",
      detail: "Field 'question' is required",
    });
    return;
  }

  const provider = body.provider ?? "anthropic";
  console.log(`[query] provider=${provider}, question="${body.question}"`);

  const result = await runAgent(body.question.trim(), provider);

  res.json({
    answer: result.answer,
    tool_calls: result.tool_calls,
    provider: result.provider,
  });
});

// ---------------------------------------------------------------------------
// Start server
// ---------------------------------------------------------------------------

if (process.argv[1]?.includes("app")) {
  app.listen(PORT, () => {
    console.log(`Invoice API (TypeScript) running on http://localhost:${PORT}`);
    console.log(`API docs: http://localhost:${PORT}/health`);
  });
}

export { app };