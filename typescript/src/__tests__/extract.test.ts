import { describe, it, expect, vi } from "vitest";
import { extractInvoice } from "../extract.js";

// ---------------------------------------------------------------------------
// Mock LLM response (what a real provider would return)
// ---------------------------------------------------------------------------

const MOCK_LLM_RESPONSE = JSON.stringify({
  invoiceNumber: "2024-0892",
  issueDate: "2024-03-15",
  seller: {
    name: "TechSolutions GmbH",
    address: { street: "Musterstrasse 42", city: "Berlin", postalCode: "10115", countryCode: "DE" },
    vatId: "DE123456789",
  },
  buyer: {
    name: "Digital Services AG",
    address: { street: "Hauptweg 7", city: "Munchen", postalCode: "80331", countryCode: "DE" },
    vatId: "DE987654321",
  },
  lineItems: [
    { description: "Cloud Hosting", quantity: 3, unitPrice: 450, vatRate: 19, lineTotal: 1350 },
    { description: "SSL Cert", quantity: 1, unitPrice: 89.5, vatRate: 19, lineTotal: 89.5 },
    { description: "Support", quantity: 15, unitPrice: 95, vatRate: 19, lineTotal: 1425 },
  ],
  totals: { netAmount: 2864.5, vatAmount: 544.26, grossAmount: 3408.76 },
  paymentTerms: { dueDays: 30, dueDate: "2024-04-14" },
  paymentMeans: { iban: "DE89370400440532013000" },
});

// ---------------------------------------------------------------------------
// Mock the Anthropic SDK
// ---------------------------------------------------------------------------

vi.mock("@anthropic-ai/sdk", () => ({
  default: class {
    messages = {
      create: vi.fn().mockResolvedValue({
        content: [{ type: "text", text: MOCK_LLM_RESPONSE }],
      }),
    };
  },
}));

// Set a fake key so the provider check passes
process.env.ANTHROPIC_API_KEY = "test-key";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("extractInvoice (mocked)", () => {
  it("extracts and validates a valid invoice", async () => {
    const result = await extractInvoice("some invoice text", "anthropic");
    expect(result.invoice).not.toBeNull();
    expect(result.errors).toHaveLength(0);
    expect(result.invoice?.invoiceNumber).toBe("2024-0892");
  });

  it("returns correct line items", async () => {
    const result = await extractInvoice("some invoice text", "anthropic");
    expect(result.invoice?.lineItems).toHaveLength(3);
    expect(result.invoice?.lineItems[0].lineTotal).toBe(1350);
  });

  it("returns correct totals", async () => {
    const result = await extractInvoice("some invoice text", "anthropic");
    expect(result.invoice?.totals.netAmount).toBe(2864.5);
    expect(result.invoice?.totals.vatAmount).toBe(544.26);
    expect(result.invoice?.totals.grossAmount).toBe(3408.76);
  });

  it("returns correct payment terms", async () => {
    const result = await extractInvoice("some invoice text", "anthropic");
    expect(result.invoice?.paymentTerms.dueDays).toBe(30);
    expect(result.invoice?.paymentTerms.dueDate).toBe("2024-04-14");
  });

  it("returns error for unknown provider", async () => {
    const result = await extractInvoice("text", "nonexistent");
    expect(result.invoice).toBeNull();
    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.errors[0]).toContain("Unknown provider");
  });
});

// ---------------------------------------------------------------------------
// Test JSON cleanup edge cases
// ---------------------------------------------------------------------------

describe("extractInvoice handles malformed responses", () => {
  it("handles markdown-wrapped JSON", async () => {
    const { default: Anthropic } = await import("@anthropic-ai/sdk");
    const client = new Anthropic();
    (client.messages.create as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      content: [{ type: "text", text: "```json\n" + MOCK_LLM_RESPONSE + "\n```" }],
    });

    const result = await extractInvoice("text", "anthropic");
    expect(result.invoice).not.toBeNull();
  });
});