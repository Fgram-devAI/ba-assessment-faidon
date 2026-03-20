import { describe, it, expect } from "vitest";
import { InvoiceSchema, AddressSchema, PartySchema, LineItemSchema, TotalsSchema, PaymentTermsSchema, PaymentMeansSchema } from "../models.js";

// ---------------------------------------------------------------------------
// Valid fixture
// ---------------------------------------------------------------------------

const VALID_INVOICE = {
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
    { description: "Cloud Hosting", quantity: 3, unitPrice: 450.0, vatRate: 19, lineTotal: 1350.0 },
    { description: "SSL Cert", quantity: 1, unitPrice: 89.5, vatRate: 19, lineTotal: 89.5 },
    { description: "Support", quantity: 15, unitPrice: 95.0, vatRate: 19, lineTotal: 1425.0 },
  ],
  totals: { netAmount: 2864.5, vatAmount: 544.26, grossAmount: 3408.76 },
  paymentTerms: { dueDays: 30, dueDate: "2024-04-14" },
  paymentMeans: { iban: "DE89370400440532013000" },
};

// ---------------------------------------------------------------------------
// Address
// ---------------------------------------------------------------------------

describe("AddressSchema", () => {
  it("accepts valid address", () => {
    const result = AddressSchema.safeParse({ street: "Main St", city: "Berlin", postalCode: "10115", countryCode: "DE" });
    expect(result.success).toBe(true);
  });

  it("rejects empty street", () => {
    const result = AddressSchema.safeParse({ street: "", city: "Berlin", postalCode: "10115", countryCode: "DE" });
    expect(result.success).toBe(false);
  });

  it("rejects lowercase country code", () => {
    const result = AddressSchema.safeParse({ street: "Main St", city: "Berlin", postalCode: "10115", countryCode: "de" });
    expect(result.success).toBe(false);
  });

  it("rejects 3-letter country code", () => {
    const result = AddressSchema.safeParse({ street: "Main St", city: "Berlin", postalCode: "10115", countryCode: "DEU" });
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Party
// ---------------------------------------------------------------------------

describe("PartySchema", () => {
  it("accepts valid party", () => {
    const result = PartySchema.safeParse({
      name: "Test GmbH",
      address: { street: "St 1", city: "Berlin", postalCode: "10115", countryCode: "DE" },
      vatId: "DE123456789",
    });
    expect(result.success).toBe(true);
  });

  it("rejects invalid VAT ID (no country code)", () => {
    const result = PartySchema.safeParse({
      name: "Test GmbH",
      address: { street: "St 1", city: "Berlin", postalCode: "10115", countryCode: "DE" },
      vatId: "123456789",
    });
    expect(result.success).toBe(false);
  });

  it("rejects VAT ID with lowercase country code", () => {
    const result = PartySchema.safeParse({
      name: "Test GmbH",
      address: { street: "St 1", city: "Berlin", postalCode: "10115", countryCode: "DE" },
      vatId: "de123456789",
    });
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// LineItem
// ---------------------------------------------------------------------------

describe("LineItemSchema", () => {
  it("accepts valid line item", () => {
    const result = LineItemSchema.safeParse({ description: "Hosting", quantity: 3, unitPrice: 450, vatRate: 19, lineTotal: 1350 });
    expect(result.success).toBe(true);
  });

  it("rejects zero quantity", () => {
    const result = LineItemSchema.safeParse({ description: "Hosting", quantity: 0, unitPrice: 450, vatRate: 19, lineTotal: 0 });
    expect(result.success).toBe(false);
  });

  it("rejects negative unit price", () => {
    const result = LineItemSchema.safeParse({ description: "Hosting", quantity: 1, unitPrice: -10, vatRate: 19, lineTotal: -10 });
    expect(result.success).toBe(false);
  });

  it("rejects wrong lineTotal", () => {
    const result = LineItemSchema.safeParse({ description: "Hosting", quantity: 3, unitPrice: 450, vatRate: 19, lineTotal: 999 });
    expect(result.success).toBe(false);
  });

  it("rejects VAT rate over 100", () => {
    const result = LineItemSchema.safeParse({ description: "Hosting", quantity: 1, unitPrice: 100, vatRate: 150, lineTotal: 100 });
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Totals
// ---------------------------------------------------------------------------

describe("TotalsSchema", () => {
  it("accepts valid totals", () => {
    const result = TotalsSchema.safeParse({ netAmount: 100, vatAmount: 19, grossAmount: 119 });
    expect(result.success).toBe(true);
  });

  it("rejects mismatched gross", () => {
    const result = TotalsSchema.safeParse({ netAmount: 100, vatAmount: 19, grossAmount: 200 });
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// PaymentTerms
// ---------------------------------------------------------------------------

describe("PaymentTermsSchema", () => {
  it("accepts valid terms", () => {
    const result = PaymentTermsSchema.safeParse({ dueDays: 30, dueDate: "2024-04-14" });
    expect(result.success).toBe(true);
  });

  it("rejects zero dueDays", () => {
    const result = PaymentTermsSchema.safeParse({ dueDays: 0, dueDate: "2024-04-14" });
    expect(result.success).toBe(false);
  });

  it("rejects bad date format", () => {
    const result = PaymentTermsSchema.safeParse({ dueDays: 30, dueDate: "14-04-2024" });
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// PaymentMeans
// ---------------------------------------------------------------------------

describe("PaymentMeansSchema", () => {
  it("accepts valid IBAN", () => {
    const result = PaymentMeansSchema.safeParse({ iban: "DE89370400440532013000" });
    expect(result.success).toBe(true);
  });

  it("strips spaces from IBAN", () => {
    const result = PaymentMeansSchema.safeParse({ iban: "DE89 3704 0044 0532 0130 00" });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.iban).toBe("DE89370400440532013000");
    }
  });

  it("rejects too short IBAN", () => {
    const result = PaymentMeansSchema.safeParse({ iban: "DE89" });
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Full Invoice
// ---------------------------------------------------------------------------

describe("InvoiceSchema", () => {
  it("accepts valid invoice", () => {
    const result = InvoiceSchema.safeParse(VALID_INVOICE);
    expect(result.success).toBe(true);
  });

  it("rejects empty invoiceNumber", () => {
    const result = InvoiceSchema.safeParse({ ...VALID_INVOICE, invoiceNumber: "" });
    expect(result.success).toBe(false);
  });

  it("rejects bad issueDate format", () => {
    const result = InvoiceSchema.safeParse({ ...VALID_INVOICE, issueDate: "15.03.2024" });
    expect(result.success).toBe(false);
  });

  it("rejects empty lineItems", () => {
    const result = InvoiceSchema.safeParse({ ...VALID_INVOICE, lineItems: [] });
    expect(result.success).toBe(false);
  });

  it("rejects netAmount mismatch with line items", () => {
    const bad = {
      ...VALID_INVOICE,
      totals: { netAmount: 9999, vatAmount: 544.26, grossAmount: 10543.26 },
    };
    const result = InvoiceSchema.safeParse(bad);
    expect(result.success).toBe(false);
  });
});