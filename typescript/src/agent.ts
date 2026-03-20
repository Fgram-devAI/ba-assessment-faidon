import Anthropic from "@anthropic-ai/sdk";
import OpenAI from "openai";
import { resolve } from "path";
import { createInterface } from "readline";
import dotenv from "dotenv";
import { INVOICES } from "./data.js";

dotenv.config({ path: resolve(__dirname, "../../.env") });

// ---------------------------------------------------------------------------
// Tool implementations
// ---------------------------------------------------------------------------

function searchInvoices(
  query: string,
  dateFrom?: string,
  dateTo?: string
): Record<string, unknown>[] {
  const queryLower = query.toLowerCase();
  const results: Record<string, unknown>[] = [];

  for (const inv of INVOICES) {
    const searchable = [
      inv.id,
      inv.customer,
      inv.status,
      inv.date,
      ...inv.items.map((i) => i.description),
    ]
      .join(" ")
      .toLowerCase();

    if (searchable.includes(queryLower)) {
      if (dateFrom && inv.date < dateFrom) continue;
      if (dateTo && inv.date > dateTo) continue;

      results.push({
        id: inv.id,
        customer: inv.customer,
        date: inv.date,
        net_total: inv.net_total,
        gross_total: inv.gross_total,
        status: inv.status,
      });
    }
  }

  return results;
}

function getInvoiceDetails(invoiceId: string): Record<string, unknown> {
  const inv = INVOICES.find((i) => i.id === invoiceId);
  if (!inv) return { error: `Invoice ${invoiceId} not found` };
  return inv as unknown as Record<string, unknown>;
}

function calculateTotal(invoiceIds: string[]): Record<string, unknown> {
  let net = 0;
  let vat = 0;
  let gross = 0;
  const found: string[] = [];
  const notFound: string[] = [];

  for (const id of invoiceIds) {
    const inv = INVOICES.find((i) => i.id === id);
    if (inv) {
      net += inv.net_total;
      vat += inv.vat_amount;
      gross += inv.gross_total;
      found.push(id);
    } else {
      notFound.push(id);
    }
  }

  const result: Record<string, unknown> = {
    invoice_ids: found,
    net_total: Math.round(net * 100) / 100,
    vat_total: Math.round(vat * 100) / 100,
    gross_total: Math.round(gross * 100) / 100,
  };

  if (notFound.length > 0) result.not_found = notFound;
  return result;
}

// Tool registry
const TOOL_FUNCTIONS: Record<string, (args: Record<string, unknown>) => unknown> = {
  search_invoices: (args) =>
    searchInvoices(args.query as string, args.date_from as string | undefined, args.date_to as string | undefined),
  get_invoice_details: (args) => getInvoiceDetails(args.invoice_id as string),
  calculate_total: (args) => calculateTotal(args.invoice_ids as string[]),
};

function executeTool(name: string, args: Record<string, unknown>): string {
  const fn = TOOL_FUNCTIONS[name];
  if (!fn) return JSON.stringify({ error: `Unknown tool: ${name}` });
  try {
    return JSON.stringify(fn(args));
  } catch (e) {
    return JSON.stringify({ error: `Tool execution failed: ${e}` });
  }
}

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------

const TOOLS_ANTHROPIC: Anthropic.Tool[] = [
  {
    name: "search_invoices",
    description:
      "Search invoices by customer name, invoice number, or keyword. Returns matching invoice summaries.",
    input_schema: {
      type: "object" as const,
      properties: {
        query: { type: "string", description: "Search term: customer name, invoice number, status, or keyword" },
        date_from: { type: "string", description: "Optional start date filter (YYYY-MM-DD)" },
        date_to: { type: "string", description: "Optional end date filter (YYYY-MM-DD)" },
      },
      required: ["query"],
    },
  },
  {
    name: "get_invoice_details",
    description: "Get full details for a specific invoice including all line items, totals, and status.",
    input_schema: {
      type: "object" as const,
      properties: {
        invoice_id: { type: "string", description: "The invoice ID (e.g. INV-001)" },
      },
      required: ["invoice_id"],
    },
  },
  {
    name: "calculate_total",
    description: "Calculate combined net, VAT, and gross totals across multiple invoices.",
    input_schema: {
      type: "object" as const,
      properties: {
        invoice_ids: {
          type: "array",
          items: { type: "string" },
          description: "List of invoice IDs to sum up",
        },
      },
      required: ["invoice_ids"],
    },
  },
];

const TOOLS_OPENAI: OpenAI.ChatCompletionTool[] = TOOLS_ANTHROPIC.map((tool) => ({
  type: "function" as const,
  function: {
    name: tool.name,
    description: tool.description,
    parameters: tool.input_schema as Record<string, unknown>,
  },
}));

// ---------------------------------------------------------------------------
// System prompt
// ---------------------------------------------------------------------------

const SYSTEM_PROMPT =
  "You are a helpful invoice assistant with access to an invoice database.\n\n" +
  "IMPORTANT RULES:\n" +
  "1. ALWAYS use tools to look up data before answering. NEVER guess or say you cannot.\n" +
  "2. You have 3 tools: search_invoices, get_invoice_details, calculate_total.\n" +
  "3. search_invoices searches across customer names, invoice IDs, statuses (paid/pending/overdue), " +
  "dates, and item descriptions. For example, to find overdue invoices, search for 'overdue'.\n" +
  "4. get_invoice_details returns full line items for a specific invoice ID.\n" +
  "5. calculate_total sums net/vat/gross across a list of invoice IDs.\n" +
  "6. If your first search returns no results, try different keywords or broader terms.\n" +
  "7. When you have enough data, provide a clear, specific answer with numbers.";

// ---------------------------------------------------------------------------
// Agent: tool call log type
// ---------------------------------------------------------------------------

export interface ToolCall {
  tool: string;
  input: Record<string, unknown>;
  output: unknown;
}

export interface AgentResult {
  answer: string;
  tool_calls: ToolCall[];
  provider: string;
  history: unknown[];
}

// ---------------------------------------------------------------------------
// Anthropic agent loop
// ---------------------------------------------------------------------------

async function runAnthropicAgent(
  question: string,
  history: Anthropic.MessageParam[] = []
): Promise<{ answer: string; toolCalls: ToolCall[]; history: Anthropic.MessageParam[] }> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) throw new Error("ANTHROPIC_API_KEY not set in environment");

  const client = new Anthropic({ apiKey });
  const messages: Anthropic.MessageParam[] = [...history, { role: "user", content: question }];
  const toolCalls: ToolCall[] = [];

  while (true) {
    const response = await client.messages.create({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1024,
      system: SYSTEM_PROMPT,
      tools: TOOLS_ANTHROPIC,
      messages,
    });

    if (response.stop_reason === "tool_use") {
      const toolResults: Anthropic.ToolResultBlockParam[] = [];

      for (const block of response.content) {
        if (block.type === "tool_use") {
          console.log(`  [tool] ${block.name}(${JSON.stringify(block.input)})`);
          const result = executeTool(block.name, block.input as Record<string, unknown>);
          toolCalls.push({
            tool: block.name,
            input: block.input as Record<string, unknown>,
            output: JSON.parse(result),
          });
          toolResults.push({ type: "tool_result", tool_use_id: block.id, content: result });
        }
      }

      messages.push({ role: "assistant", content: response.content });
      messages.push({ role: "user", content: toolResults });
    } else {
      let answer = "";
      for (const block of response.content) {
        if (block.type === "text") answer += block.text;
      }
      messages.push({ role: "assistant", content: response.content });
      return { answer, toolCalls, history: messages };
    }
  }
}

// ---------------------------------------------------------------------------
// OpenAI agent loop
// ---------------------------------------------------------------------------

async function runOpenAIAgent(
  question: string,
  history: OpenAI.ChatCompletionMessageParam[] = []
): Promise<{ answer: string; toolCalls: ToolCall[]; history: OpenAI.ChatCompletionMessageParam[] }> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error("OPENAI_API_KEY not set in environment");

  const client = new OpenAI({ apiKey });
  const messages: OpenAI.ChatCompletionMessageParam[] = history.length
    ? [...history, { role: "user", content: question }]
    : [{ role: "system", content: SYSTEM_PROMPT }, { role: "user", content: question }];
  const toolCallsLog: ToolCall[] = [];

  while (true) {
    const response = await client.chat.completions.create({
      model: "gpt-4o-mini",
      messages,
      tools: TOOLS_OPENAI,
    });

    const choice = response.choices[0];

    if (choice.finish_reason === "tool_calls") {
      messages.push(choice.message);

      for (const tc of choice.message.tool_calls ?? []) {
        if (tc.type !== "function") continue;
        const toolInput = JSON.parse(tc.function.arguments);
        console.log(`  [tool] ${tc.function.name}(${JSON.stringify(toolInput)})`);
        const result = executeTool(tc.function.name, toolInput);
        toolCallsLog.push({
          tool: tc.function.name,
          input: toolInput,
          output: JSON.parse(result),
        });
        messages.push({ role: "tool", tool_call_id: tc.id, content: result });
      }
    } else {
      const answer = choice.message.content ?? "";
      messages.push({ role: "assistant", content: answer });
      return { answer, toolCalls: toolCallsLog, history: messages };
    }
  }
}

// ---------------------------------------------------------------------------
// Gemini agent loop
// ---------------------------------------------------------------------------

interface GeminiPart {
  text?: string;
  functionCall?: { name: string; args: Record<string, unknown> };
  functionResponse?: { name: string; response: { result: unknown } };
}

interface GeminiContent {
  role: string;
  parts: GeminiPart[];
}

async function runGeminiAgent(
  question: string,
  history: GeminiContent[] = []
): Promise<{ answer: string; toolCalls: ToolCall[]; history: GeminiContent[] }> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) throw new Error("GEMINI_API_KEY not set in environment");

  const model = process.env.GEMINI_MODEL ?? "gemini-2.5-flash-lite";
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;

  // Clean schema for Gemini (no extra fields)
  function cleanSchema(schema: Record<string, unknown>): Record<string, unknown> {
    const cleaned: Record<string, unknown> = {
      type: schema.type,
      properties: schema.properties,
    };
    if (schema.required) cleaned.required = schema.required;
    return cleaned;
  }

  const geminiTools = [
    {
      function_declarations: TOOLS_ANTHROPIC.map((t) => ({
        name: t.name,
        description: t.description,
        parameters: cleanSchema(t.input_schema as Record<string, unknown>),
      })),
    },
  ];

  const contents: GeminiContent[] = [...history, { role: "user", parts: [{ text: question }] }];
  const toolCallsLog: ToolCall[] = [];

  while (true) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        system_instruction: { parts: [{ text: SYSTEM_PROMPT }] },
        contents,
        tools: geminiTools,
      }),
    });

    if (!response.ok) {
      throw new Error(`Gemini API error ${response.status}: ${await response.text()}`);
    }

    const data = await response.json();
    const parts: GeminiPart[] = data.candidates[0].content.parts;
    const functionCalls = parts.filter((p: GeminiPart) => p.functionCall);

    if (functionCalls.length > 0) {
      contents.push({ role: "model", parts });

      for (const fcPart of functionCalls) {
        const fc = fcPart.functionCall!;
        console.log(`  [tool] ${fc.name}(${JSON.stringify(fc.args)})`);
        const result = executeTool(fc.name, fc.args);
        toolCallsLog.push({
          tool: fc.name,
          input: fc.args,
          output: JSON.parse(result),
        });

        contents.push({
          role: "function",
          parts: [
            {
              functionResponse: {
                name: fc.name,
                response: { result: JSON.parse(result) },
              },
            },
          ],
        });
      }
    } else {
      let answer = "";
      for (const part of parts) {
        if (part.text) answer += part.text;
      }
      contents.push({ role: "model", parts: [{ text: answer }] });
      return { answer, toolCalls: toolCallsLog, history: contents };
    }
  }
}

// ---------------------------------------------------------------------------
// Public API (used by Express app)
// ---------------------------------------------------------------------------

export async function runAgent(
  question: string,
  provider: string = "anthropic",
  history: unknown[] = []
): Promise<AgentResult> {
  try {
    let result;
    switch (provider) {
      case "anthropic":
        result = await runAnthropicAgent(question, history as Anthropic.MessageParam[]);
        break;
      case "openai":
        result = await runOpenAIAgent(question, history as OpenAI.ChatCompletionMessageParam[]);
        break;
      case "gemini":
        result = await runGeminiAgent(question, history as GeminiContent[]);
        break;
      default:
        return {
          answer: `Unknown provider '${provider}'. Choose: anthropic, openai, gemini`,
          tool_calls: [],
          provider,
          history,
        };
    }
    return { answer: result.answer, tool_calls: result.toolCalls, provider, history: result.history };
  } catch (e) {
    return {
      answer: `Agent error: ${e instanceof Error ? e.message : e}`,
      tool_calls: [],
      provider,
      history,
    };
  }
}

// Export tool functions for testing
export { searchInvoices, getInvoiceDetails, calculateTotal };
export { INVOICES } from "./data.js";

// ---------------------------------------------------------------------------
// CLI conversation loop
// ---------------------------------------------------------------------------

async function main() {
  const args = process.argv.slice(2);
  let provider = process.env.LLM_PROVIDER?.toLowerCase() ?? "anthropic";

  for (let i = 0; i < args.length; i++) {
    if ((args[i] === "--provider" || args[i] === "-p") && args[i + 1]) {
      provider = args[i + 1];
      i++;
    }
  }

  console.log(`Invoice Agent (provider: ${provider})`);
  console.log("Ask questions about invoices. Type 'quit' or 'exit' to stop.\n");

  const rl = createInterface({ input: process.stdin, output: process.stdout });

  const prompt = (): Promise<string> =>
    new Promise((resolve) => rl.question("You: ", resolve));

  let history: unknown[] = [];

  while (true) {
    const question = (await prompt()).trim();

    if (!question) continue;

    const words = new Set(question.toLowerCase().split(/\s+/));
    const exitWords = new Set(["quit", "exit", "q", "bye", "stop"]);
    if (words.size <= 3 && [...words].some((w) => exitWords.has(w))) {
      console.log("Bye!");
      rl.close();
      break;
    }

    console.log();
    const result = await runAgent(question, provider, history);
    history = result.history;
    console.log(`\nAgent: ${result.answer}`);

    if (result.tool_calls.length > 0) {
      console.log(`\n  Tools used: [${result.tool_calls.map((tc) => tc.tool).join(", ")}]`);
    }
    console.log();
  }
}

if (process.argv[1]?.includes("agent")) {
  main().catch(console.error);
}