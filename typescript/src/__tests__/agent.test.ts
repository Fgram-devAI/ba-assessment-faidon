import { describe, it, expect } from "vitest";
import { searchInvoices, getInvoiceDetails, calculateTotal, INVOICES } from "../agent.js";

// ---------------------------------------------------------------------------
// searchInvoices
// ---------------------------------------------------------------------------

describe("searchInvoices", () => {
  it("finds invoices by customer name", () => {
    const results = searchInvoices("Digital Services");
    expect(results).toHaveLength(2);
    expect(results[0].id).toBe("INV-001");
    expect(results[1].id).toBe("INV-002");
  });

  it("finds invoices by status", () => {
    const results = searchInvoices("overdue");
    expect(results).toHaveLength(1);
    expect(results[0].id).toBe("INV-003");
  });

  it("finds invoices by item description", () => {
    const results = searchInvoices("Cloud Hosting");
    expect(results).toHaveLength(2);
  });

  it("finds invoices by ID", () => {
    const results = searchInvoices("INV-004");
    expect(results).toHaveLength(1);
    expect(results[0].customer).toBe("Berlin Startup Hub");
  });

  it("returns empty for no match", () => {
    const results = searchInvoices("nonexistent");
    expect(results).toHaveLength(0);
  });

  it("filters by date range", () => {
    const results = searchInvoices("Digital Services", "2024-03-01", "2024-12-31");
    expect(results).toHaveLength(1);
    expect(results[0].id).toBe("INV-002");
  });

  it("is case insensitive", () => {
    const results = searchInvoices("digital services ag");
    expect(results).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// getInvoiceDetails
// ---------------------------------------------------------------------------

describe("getInvoiceDetails", () => {
  it("returns full invoice with items", () => {
    const result = getInvoiceDetails("INV-001");
    expect(result.id).toBe("INV-001");
    expect(result.items).toBeDefined();
    expect((result.items as unknown[]).length).toBe(2);
  });

  it("returns error for unknown ID", () => {
    const result = getInvoiceDetails("INV-999");
    expect(result.error).toBeDefined();
    expect(result.error).toContain("not found");
  });
});

// ---------------------------------------------------------------------------
// calculateTotal
// ---------------------------------------------------------------------------

describe("calculateTotal", () => {
  it("sums multiple invoices", () => {
    const result = calculateTotal(["INV-001", "INV-002"]);
    expect(result.net_total).toBe(5700);
    expect(result.vat_total).toBe(1083);
    expect(result.gross_total).toBe(6783);
    expect(result.invoice_ids).toEqual(["INV-001", "INV-002"]);
  });

  it("handles single invoice", () => {
    const result = calculateTotal(["INV-003"]);
    expect(result.net_total).toBe(8500);
    expect(result.gross_total).toBe(10115);
  });

  it("reports not found IDs", () => {
    const result = calculateTotal(["INV-001", "INV-999"]);
    expect(result.not_found).toEqual(["INV-999"]);
    expect(result.invoice_ids).toEqual(["INV-001"]);
  });

  it("sums all invoices", () => {
    const allIds = INVOICES.map((i) => i.id);
    const result = calculateTotal(allIds);
    expect(result.net_total).toBe(15400);
  });
});