import { InvoiceSchema, type Invoice } from "./models.js";

// ---------------------------------------------------------------------------
// Result container
// ---------------------------------------------------------------------------

export interface TransformResult {
  invoices: Invoice[];
  errors: string[];
  warnings: string[];
  success: boolean;
}

// ---------------------------------------------------------------------------
// Types for System A flat records
// ---------------------------------------------------------------------------

export interface SystemARecord {
  invoice_number: string;
  invoice_date: string;
  seller_name: string;
  seller_street: string;
  seller_city: string;
  seller_zip: string;
  seller_country: string;
  seller_vat_id: string;
  buyer_name: string;
  buyer_city: string;
  buyer_vat_id: string;
  buyer_street?: string;
  buyer_zip?: string;
  buyer_country?: string;
  item_description: string;
  item_quantity: string;
  item_unit_price: string;
  item_vat_rate: string;
  payment_days: string;
  iban: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseGermanDate(dateStr: string): string {
  const trimmed = dateStr.trim();
  const match = trimmed.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  if (!match) {
    throw new Error(`Cannot parse date '${dateStr}': expected DD.MM.YYYY`);
  }
  const [, day, month, year] = match;
  return `${year}-${month}-${day}`;
}

function computeDueDate(issueDateIso: string, paymentDays: number): string {
  const dt = new Date(issueDateIso);
  dt.setDate(dt.getDate() + paymentDays);
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, "0");
  const d = String(dt.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function safeInt(value: string, fieldName: string): number {
  const n = parseInt(value, 10);
  if (isNaN(n)) {
    throw new Error(`'${fieldName}' must be an integer, got '${value}'`);
  }
  return n;
}

function safeFloat(value: string, fieldName: string): number {
  const n = parseFloat(value);
  if (isNaN(n)) {
    throw new Error(`'${fieldName}' must be a number, got '${value}'`);
  }
  return n;
}

function roundTwo(n: number): number {
  return Math.round(n * 100) / 100;
}

// ---------------------------------------------------------------------------
// Grouping
// ---------------------------------------------------------------------------

function groupByInvoice(
  records: SystemARecord[]
): Map<string, SystemARecord[]> {
  const grouped = new Map<string, SystemARecord[]>();
  for (const record of records) {
    const invNum = record.invoice_number?.trim();
    if (!invNum) continue;
    const existing = grouped.get(invNum) ?? [];
    existing.push(record);
    grouped.set(invNum, existing);
  }
  return grouped;
}

// ---------------------------------------------------------------------------
// Required fields check
// ---------------------------------------------------------------------------

const REQUIRED_FIELDS: (keyof SystemARecord)[] = [
  "invoice_number",
  "invoice_date",
  "seller_name",
  "seller_street",
  "seller_city",
  "seller_zip",
  "seller_country",
  "seller_vat_id",
  "buyer_name",
  "buyer_city",
  "buyer_vat_id",
  "item_description",
  "item_quantity",
  "item_unit_price",
  "item_vat_rate",
  "payment_days",
  "iban",
];

function checkRequiredFields(record: SystemARecord): string[] {
  return REQUIRED_FIELDS.filter((f) => {
    const val = record[f];
    return !val || !val.trim();
  });
}

// ---------------------------------------------------------------------------
// Single invoice transformation
// ---------------------------------------------------------------------------

function transformSingleInvoice(
  invoiceNumber: string,
  records: SystemARecord[]
): Invoice {
  const header = records[0];

  const missing = checkRequiredFields(header);
  if (missing.length > 0) {
    throw new Error(
      `Invoice ${invoiceNumber}: missing required fields: ${missing.join(", ")}`
    );
  }

  // Dates
  const issueDate = parseGermanDate(header.invoice_date);
  const paymentDays = safeInt(header.payment_days, "payment_days");
  const dueDate = computeDueDate(issueDate, paymentDays);

  // Line items
  const lineItems = records.map((row) => {
    const quantity = safeInt(row.item_quantity, "item_quantity");
    const unitPrice = safeFloat(row.item_unit_price, "item_unit_price");
    const vatRate = safeFloat(row.item_vat_rate, "item_vat_rate");
    const lineTotal = roundTwo(quantity * unitPrice);

    return {
      description: row.item_description.trim(),
      quantity,
      unitPrice,
      vatRate,
      lineTotal,
    };
  });

  // Totals
  const netAmount = roundTwo(
    lineItems.reduce((sum, li) => sum + li.lineTotal, 0)
  );
  const vatRate = lineItems[0].vatRate;
  const vatAmount = roundTwo((netAmount * vatRate) / 100);
  const grossAmount = roundTwo(netAmount + vatAmount);

  // Build System B object
  const invoiceData = {
    invoiceNumber,
    issueDate,
    seller: {
      name: header.seller_name.trim(),
      address: {
        street: header.seller_street.trim(),
        city: header.seller_city.trim(),
        postalCode: header.seller_zip.trim(),
        countryCode: header.seller_country.trim().toUpperCase(),
      },
      vatId: header.seller_vat_id.trim(),
    },
    buyer: {
      name: header.buyer_name.trim(),
      address: {
        street: header.buyer_street?.trim() || "N/A",
        city: header.buyer_city.trim(),
        postalCode: header.buyer_zip?.trim() || "N/A",
        countryCode:
          header.buyer_country?.trim().toUpperCase() ||
          header.seller_country.trim().toUpperCase(),
      },
      vatId: header.buyer_vat_id.trim(),
    },
    lineItems,
    totals: { netAmount, vatAmount, grossAmount },
    paymentTerms: { dueDays: paymentDays, dueDate },
    paymentMeans: { iban: header.iban.trim() },
  };

  // Validate through Zod
  const parsed = InvoiceSchema.parse(invoiceData);
  return parsed;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function transform(records: SystemARecord[]): TransformResult {
  const result: TransformResult = {
    invoices: [],
    errors: [],
    warnings: [],
    success: true,
  };

  if (!records || records.length === 0) {
    result.errors.push("No records provided");
    result.success = false;
    return result;
  }

  const grouped = groupByInvoice(records);

  if (grouped.size === 0) {
    result.errors.push("No valid invoice_number found in records");
    result.success = false;
    return result;
  }

  for (const [invoiceNumber, group] of grouped) {
    try {
      const invoice = transformSingleInvoice(invoiceNumber, group);
      result.invoices.push(invoice);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      result.errors.push(`Invoice ${invoiceNumber}: ${msg}`);
    }
  }

  result.success = result.errors.length === 0;
  return result;
}

// ---------------------------------------------------------------------------
// CLI entry point
// ---------------------------------------------------------------------------

if (process.argv[1]?.includes("transform")) {
  const sampleRecords: SystemARecord[] = [
    {
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
      item_description: "Cloud Hosting Premium (Jan-Mar 2024)",
      item_quantity: "3",
      item_unit_price: "450.00",
      item_vat_rate: "19",
      payment_days: "30",
      iban: "DE89370400440532013000",
    },
    {
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
      item_description: "SSL-Zertifikat Erneuerung",
      item_quantity: "1",
      item_unit_price: "89.50",
      item_vat_rate: "19",
      payment_days: "30",
      iban: "DE89370400440532013000",
    },
    {
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
      item_description: "Technischer Support (15 Stunden)",
      item_quantity: "15",
      item_unit_price: "95.00",
      item_vat_rate: "19",
      payment_days: "30",
      iban: "DE89370400440532013000",
    },
  ];

  const result = transform(sampleRecords);

  console.log("=".repeat(60));
  console.log("TRANSFORMATION RESULT");
  console.log("=".repeat(60));

  if (result.success) {
    console.log(`\nSUCCESS: ${result.invoices.length} invoice(s) transformed\n`);
    console.log(JSON.stringify(result.invoices, null, 2));
  } else {
    console.log(`\nFAILED with ${result.errors.length} error(s):\n`);
    for (const err of result.errors) {
      console.log(`  ERROR: ${err}`);
    }
  }

  if (result.warnings.length > 0) {
    console.log(`\n${result.warnings.length} warning(s):`);
    for (const w of result.warnings) {
      console.log(`  WARN: ${w}`);
    }
  }
}