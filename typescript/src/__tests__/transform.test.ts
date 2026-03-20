import { describe, it, expect } from "vitest";
import { transform, type SystemARecord } from "../transform.js";

const VALID_RECORD: SystemARecord = {
  invoice_number: "2024-0892",
  invoice_date: "15.03.2024",
  seller_name: "TechSolutions GmbH",
  seller_street: "Musterstrasse 42",
  seller_city: "Berlin",
  seller_zip: "10115",
  seller_country: "DE",
  seller_vat_id: "DE123456789",
  buyer_name: "Digital Services AG",
  buyer_city: "Munchen",
  buyer_vat_id: "DE987654321",
  item_description: "Cloud Hosting",
  item_quantity: "3",
  item_unit_price: "450.00",
  item_vat_rate: "19",
  payment_days: "30",
  iban: "DE89370400440532013000",
};

describe("transform", () => {
  it("transforms a single record", () => {
    const result = transform([VALID_RECORD]);
    expect(result.success).toBe(true);
    expect(result.invoices).toHaveLength(1);
    expect(result.invoices[0].invoiceNumber).toBe("2024-0892");
    expect(result.invoices[0].issueDate).toBe("2024-03-15");
  });

  it("computes correct totals", () => {
    const result = transform([VALID_RECORD]);
    expect(result.invoices[0].totals.netAmount).toBe(1350);
    expect(result.invoices[0].totals.vatAmount).toBe(256.5);
    expect(result.invoices[0].totals.grossAmount).toBe(1606.5);
  });

  it("computes correct due date", () => {
    const result = transform([VALID_RECORD]);
    expect(result.invoices[0].paymentTerms.dueDate).toBe("2024-04-14");
    expect(result.invoices[0].paymentTerms.dueDays).toBe(30);
  });

  it("groups multiple records into one invoice", () => {
    const record2: SystemARecord = { ...VALID_RECORD, item_description: "SSL Cert", item_quantity: "1", item_unit_price: "89.50" };
    const result = transform([VALID_RECORD, record2]);
    expect(result.success).toBe(true);
    expect(result.invoices).toHaveLength(1);
    expect(result.invoices[0].lineItems).toHaveLength(2);
  });

  it("handles multiple invoices", () => {
    const record2: SystemARecord = { ...VALID_RECORD, invoice_number: "2024-0893" };
    const result = transform([VALID_RECORD, record2]);
    expect(result.success).toBe(true);
    expect(result.invoices).toHaveLength(2);
  });

  it("returns error for empty records", () => {
    const result = transform([]);
    expect(result.success).toBe(false);
    expect(result.errors).toHaveLength(1);
  });

  it("returns error for invalid date", () => {
    const bad: SystemARecord = { ...VALID_RECORD, invoice_date: "invalid" };
    const result = transform([bad]);
    expect(result.success).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("returns error for non-numeric quantity", () => {
    const bad: SystemARecord = { ...VALID_RECORD, item_quantity: "abc" };
    const result = transform([bad]);
    expect(result.success).toBe(false);
  });

  it("strips IBAN spaces", () => {
    const spaced: SystemARecord = { ...VALID_RECORD, iban: "DE89 3704 0044 0532 0130 00" };
    const result = transform([spaced]);
    expect(result.success).toBe(true);
    expect(result.invoices[0].paymentMeans.iban).toBe("DE89370400440532013000");
  });
});