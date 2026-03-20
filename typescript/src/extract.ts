import Anthropic from "@anthropic-ai/sdk";
import OpenAI from "openai";
import { readFileSync, existsSync } from "fs";
import { resolve, join } from "path";
import { InvoiceSchema, type Invoice } from "./models.js";
import dotenv from "dotenv";
dotenv.config({ path: resolve(__dirname, "../../.env") });

// ---------------------------------------------------------------------------
// Sample invoice paths (shared with Python — lives in /samples/)
// ---------------------------------------------------------------------------

const SAMPLES_DIR = resolve(__dirname, "../../samples");
const DEFAULT_SAMPLE = join(SAMPLES_DIR, "invoice_de.txt");

function loadSampleInvoice(): string {
  if (existsSync(DEFAULT_SAMPLE)) {
    return readFileSync(DEFAULT_SAMPLE, "utf-8").trim();
  }
  throw new Error(`Default sample not found at ${DEFAULT_SAMPLE}`);
}

// ---------------------------------------------------------------------------
// Prompts
// ---------------------------------------------------------------------------

const SYSTEM_PROMPT =
  "You are a precise data extraction assistant. " +
  "You extract structured data from invoices in any language or format. " +
  "Return ONLY valid JSON — no markdown, no explanation, no code fences.";

const EXTRACTION_PROMPT = `Extract the following invoice into JSON matching this exact schema:

{
  "invoiceNumber": "string",
  "issueDate": "YYYY-MM-DD",
  "seller": {
    "name": "string",
    "address": { "street": "string", "city": "string", "postalCode": "string", "countryCode": "2-letter ISO code" },
    "vatId": "string (country code + digits, e.g. DE123456789)"
  },
  "buyer": {
    "name": "string",
    "address": { "street": "string", "city": "string", "postalCode": "string", "countryCode": "2-letter ISO code" },
    "vatId": "string"
  },
  "lineItems": [
    {
      "description": "string",
      "quantity": "integer > 0",
      "unitPrice": "float >= 0",
      "vatRate": "float (percentage, e.g. 19)",
      "lineTotal": "float (must equal quantity * unitPrice)"
    }
  ],
  "totals": {
    "netAmount": "float (sum of all lineTotal values)",
    "vatAmount": "float",
    "grossAmount": "float (netAmount + vatAmount)"
  },
  "paymentTerms": {
    "dueDays": "integer > 0",
    "dueDate": "YYYY-MM-DD (issueDate + dueDays)"
  },
  "paymentMeans": {
    "iban": "string (no spaces)"
  }
}

Rules:
- Detect the language and date format automatically.
- Convert any date format to ISO 8601 (YYYY-MM-DD).
- Convert any local number format (e.g. 1.350,00 or 1,350.00) to standard floats (1350.00).
- Compute dueDate by adding dueDays to issueDate.
- Remove spaces from IBAN.
- If a field is not present in the text, infer it from context where possible.
- Return ONLY the JSON object, nothing else.

Invoice text:
`;

// ---------------------------------------------------------------------------
// LLM provider calls
// ---------------------------------------------------------------------------

async function callAnthropic(prompt: string): Promise<string> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) throw new Error("ANTHROPIC_API_KEY not set in environment");

  const client = new Anthropic({ apiKey });
  const response = await client.messages.create({
    model: "claude-sonnet-4-20250514",
    max_tokens: 2048,
    system: SYSTEM_PROMPT,
    messages: [{ role: "user", content: prompt }],
  });

  const block = response.content[0];
  if (block.type === "text") return block.text;
  throw new Error("Unexpected response type from Anthropic");
}

async function callOpenAI(prompt: string): Promise<string> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error("OPENAI_API_KEY not set in environment");

  const client = new OpenAI({ apiKey });
  const response = await client.chat.completions.create({
    model: "gpt-4o-mini",
    temperature: 0,
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: prompt },
    ],
  });

  return response.choices[0].message.content ?? "";
}

async function callGemini(prompt: string): Promise<string> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) throw new Error("GEMINI_API_KEY not set in environment");

  const model = process.env.GEMINI_MODEL ?? "gemini-2.5-flash-lite";
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;

  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      system_instruction: { parts: [{ text: SYSTEM_PROMPT }] },
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { temperature: 0 },
    }),
  });

  if (!response.ok) {
    throw new Error(`Gemini API error ${response.status}: ${await response.text()}`);
  }

  const data = await response.json();
  return data.candidates[0].content.parts[0].text;
}

type ProviderFn = (prompt: string) => Promise<string>;

const PROVIDERS: Record<string, ProviderFn> = {
  anthropic: callAnthropic,
  openai: callOpenAI,
  gemini: callGemini,
};

// ---------------------------------------------------------------------------
// JSON cleanup
// ---------------------------------------------------------------------------

function cleanJsonResponse(raw: string): string {
  let text = raw.trim();
  if (text.startsWith("```")) {
    text = text.includes("\n") ? text.split("\n").slice(1).join("\n") : text.slice(3);
  }
  if (text.endsWith("```")) {
    text = text.slice(0, -3);
  }
  return text.trim();
}

// ---------------------------------------------------------------------------
// Extraction with retry
// ---------------------------------------------------------------------------

export interface ExtractionResult {
  invoice: Invoice | null;
  errors: string[];
}

export async function extractInvoice(
  invoiceText: string,
  provider: string = "anthropic",
  maxRetries: number = 3
): Promise<ExtractionResult> {
  if (!(provider in PROVIDERS)) {
    return {
      invoice: null,
      errors: [`Unknown provider '${provider}'. Choose: ${Object.keys(PROVIDERS).join(", ")}`],
    };
  }

  const callLlm = PROVIDERS[provider];
  const prompt = EXTRACTION_PROMPT + invoiceText;
  const errors: string[] = [];

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const rawResponse = await callLlm(prompt);
      const cleaned = cleanJsonResponse(rawResponse);

      let data: unknown;
      try {
        data = JSON.parse(cleaned);
      } catch (e) {
        errors.push(`Attempt ${attempt}: Invalid JSON — ${e instanceof Error ? e.message : e}`);
        continue;
      }

      const invoice = InvoiceSchema.parse(data);
      return { invoice, errors: [] };
    } catch (e) {
      errors.push(`Attempt ${attempt}: ${e instanceof Error ? e.message : e}`);
      continue;
    }
  }

  return { invoice: null, errors };
}

// ---------------------------------------------------------------------------
// Cross-validation checks
// ---------------------------------------------------------------------------

function roundTwo(n: number): number {
  return Math.round(n * 100) / 100;
}

function printValidationReport(result: ExtractionResult): void {
  console.log("=".repeat(60));
  console.log("INVOICE EXTRACTION — VALIDATION REPORT");
  console.log("=".repeat(60));

  if (!result.invoice) {
    console.log("\nRESULT: FAIL\n");
    for (const err of result.errors) {
      console.log(`  ERROR: ${err}`);
    }
    return;
  }

  console.log("\nRESULT: PASS\n");
  console.log(JSON.stringify(result.invoice, null, 2));

  const inv = result.invoice;
  console.log("\n" + "-".repeat(40));
  console.log("CROSS-VALIDATION CHECKS:");
  console.log("-".repeat(40));

  // Check 1: Line items sum == netAmount
  const lineSum = roundTwo(inv.lineItems.reduce((sum, li) => sum + li.lineTotal, 0));
  const net = inv.totals.netAmount;
  const check1 = Math.abs(net - lineSum) <= 0.01;
  console.log(`  Line items sum (${lineSum}) == netAmount (${net}): ${check1 ? "PASS" : "FAIL"}`);

  // Check 2: VAT calculation
  const vatRate = inv.lineItems[0].vatRate;
  const expectedVat = roundTwo((net * vatRate) / 100);
  const actualVat = inv.totals.vatAmount;
  const check2 = Math.abs(actualVat - expectedVat) <= 0.01;
  console.log(`  VAT: ${net} * ${vatRate}% = ${expectedVat} == ${actualVat}: ${check2 ? "PASS" : "FAIL"}`);

  // Check 3: Gross = net + VAT
  const expectedGross = roundTwo(net + actualVat);
  const actualGross = inv.totals.grossAmount;
  const check3 = Math.abs(actualGross - expectedGross) <= 0.01;
  console.log(`  Gross: ${net} + ${actualVat} = ${expectedGross} == ${actualGross}: ${check3 ? "PASS" : "FAIL"}`);

  const allPass = check1 && check2 && check3;
  console.log(`\n  OVERALL: ${allPass ? "ALL CHECKS PASSED" : "SOME CHECKS FAILED"}`);
}

// ---------------------------------------------------------------------------
// CLI entry point
// ---------------------------------------------------------------------------

async function main() {
  const args = process.argv.slice(2);

  // Parse --provider / -p flag
  let provider = process.env.LLM_PROVIDER?.toLowerCase() ?? "anthropic";
  let filePath: string | null = null;

  for (let i = 0; i < args.length; i++) {
    if ((args[i] === "--provider" || args[i] === "-p") && args[i + 1]) {
      provider = args[i + 1];
      i++;
    } else if (!args[i].startsWith("-")) {
      filePath = args[i];
    }
  }

  console.log(`Using LLM provider: ${provider}\n`);

  // Read input
  let invoiceText: string;
  if (filePath) {
    const fullPath = resolve(filePath);
    console.log(`Reading invoice from: ${fullPath}`);
    invoiceText = readFileSync(fullPath, "utf-8").trim();
  } else {
    console.log(`No input provided — using sample from: ${DEFAULT_SAMPLE}`);
    invoiceText = loadSampleInvoice();
  }

  console.log();

  const result = await extractInvoice(invoiceText, provider);
  printValidationReport(result);
}

// Run if executed directly
main().catch(console.error);
