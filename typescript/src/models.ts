import { z } from "zod";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const iso8601Date = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, "Must be ISO 8601 format (YYYY-MM-DD)");

const vatId = z
  .string()
  .regex(
    /^[A-Z]{2}\d+$/,
    "VAT ID must be a 2-letter country code followed by digits (e.g. DE123456789)"
  );

const iban = z
  .string()
  .transform((v) => v.replace(/\s/g, ""))
  .pipe(
    z
      .string()
      .regex(
        /^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$/,
        "Invalid IBAN: must be 2-letter country code, 2 check digits, 11-30 alphanumeric chars"
      )
  );

// ---------------------------------------------------------------------------
// Sub-schemas
// ---------------------------------------------------------------------------

export const AddressSchema = z.object({
  street: z.string().min(1),
  city: z.string().min(1),
  postalCode: z.string().min(1),
  countryCode: z
    .string()
    .length(2)
    .regex(/^[A-Z]{2}$/, "Must be a 2-letter country code"),
});

export const PartySchema = z.object({
  name: z.string().min(1),
  address: AddressSchema,
  vatId: vatId,
});

export const LineItemSchema = z
  .object({
    description: z.string().min(1),
    quantity: z.number().int().positive("Quantity must be > 0"),
    unitPrice: z.number().nonnegative("Unit price must be >= 0"),
    vatRate: z
      .number()
      .min(0, "VAT rate must be >= 0")
      .max(100, "VAT rate must be <= 100"),
    lineTotal: z.number(),
  })
  .superRefine((item, ctx) => {
    const expected = Math.round(item.quantity * item.unitPrice * 100) / 100;
    if (Math.abs(item.lineTotal - expected) > 0.01) {
      ctx.addIssue({
        code: "custom",
        message: `lineTotal ${item.lineTotal} does not match quantity (${item.quantity}) * unitPrice (${item.unitPrice}) = ${expected}`,
      });
    }
  });

export const TotalsSchema = z
  .object({
    netAmount: z.number(),
    vatAmount: z.number(),
    grossAmount: z.number(),
  })
  .superRefine((t, ctx) => {
    const expected = Math.round((t.netAmount + t.vatAmount) * 100) / 100;
    if (Math.abs(t.grossAmount - expected) > 0.01) {
      ctx.addIssue({
        code: "custom",
        message: `grossAmount ${t.grossAmount} != netAmount (${t.netAmount}) + vatAmount (${t.vatAmount}) = ${expected}`,
      });
    }
  });

export const PaymentTermsSchema = z.object({
  dueDays: z.number().int().positive("Due days must be > 0"),
  dueDate: iso8601Date,
});

export const PaymentMeansSchema = z.object({
  iban: iban,
});

// ---------------------------------------------------------------------------
// Root invoice schema
// ---------------------------------------------------------------------------

export const InvoiceSchema = z
  .object({
    invoiceNumber: z.string().min(1),
    issueDate: iso8601Date,
    seller: PartySchema,
    buyer: PartySchema,
    lineItems: z.array(LineItemSchema).min(1),
    totals: TotalsSchema,
    paymentTerms: PaymentTermsSchema,
    paymentMeans: PaymentMeansSchema,
  })
  .superRefine((inv, ctx) => {
    const lineSum =
      Math.round(
        inv.lineItems.reduce((sum, item) => sum + item.lineTotal, 0) * 100
      ) / 100;
    if (Math.abs(inv.totals.netAmount - lineSum) > 0.01) {
      ctx.addIssue({
        code: "custom",
        message: `netAmount (${inv.totals.netAmount}) does not match sum of line item totals (${lineSum})`,
      });
    }
  });

// ---------------------------------------------------------------------------
// Inferred types (use these throughout the app)
// ---------------------------------------------------------------------------

export type Address = z.infer<typeof AddressSchema>;
export type Party = z.infer<typeof PartySchema>;
export type LineItem = z.infer<typeof LineItemSchema>;
export type Totals = z.infer<typeof TotalsSchema>;
export type PaymentTerms = z.infer<typeof PaymentTermsSchema>;
export type PaymentMeans = z.infer<typeof PaymentMeansSchema>;
export type Invoice = z.infer<typeof InvoiceSchema>;