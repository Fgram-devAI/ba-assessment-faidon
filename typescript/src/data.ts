/**
 * Mock invoice data (from the assessment).
 * Shared across agent and Express app.
 */

export interface InvoiceItem {
  description: string;
  quantity: number;
  unit_price: number;
  total: number;
}

export interface MockInvoice {
  id: string;
  customer: string;
  date: string;
  net_total: number;
  vat_rate: number;
  vat_amount: number;
  gross_total: number;
  status: string;
  items: InvoiceItem[];
}

export const INVOICES: MockInvoice[] = [
  {
    id: "INV-001",
    customer: "Digital Services AG",
    date: "2024-01-15",
    net_total: 2500.0,
    vat_rate: 0.19,
    vat_amount: 475.0,
    gross_total: 2975.0,
    status: "paid",
    items: [
      { description: "Cloud Hosting Q1", quantity: 1, unit_price: 1500.0, total: 1500.0 },
      { description: "Support Hours", quantity: 10, unit_price: 100.0, total: 1000.0 },
    ],
  },
  {
    id: "INV-002",
    customer: "Digital Services AG",
    date: "2024-04-15",
    net_total: 3200.0,
    vat_rate: 0.19,
    vat_amount: 608.0,
    gross_total: 3808.0,
    status: "pending",
    items: [
      { description: "Cloud Hosting Q2", quantity: 1, unit_price: 1800.0, total: 1800.0 },
      { description: "API Integration", quantity: 1, unit_price: 1400.0, total: 1400.0 },
    ],
  },
  {
    id: "INV-003",
    customer: "Munchen Logistics GmbH",
    date: "2024-03-01",
    net_total: 8500.0,
    vat_rate: 0.19,
    vat_amount: 1615.0,
    gross_total: 10115.0,
    status: "overdue",
    items: [
      { description: "Warehouse Management System", quantity: 1, unit_price: 5000.0, total: 5000.0 },
      { description: "Training Sessions", quantity: 5, unit_price: 500.0, total: 2500.0 },
      { description: "Data Migration", quantity: 1, unit_price: 1000.0, total: 1000.0 },
    ],
  },
  {
    id: "INV-004",
    customer: "Berlin Startup Hub",
    date: "2024-02-20",
    net_total: 1200.0,
    vat_rate: 0.19,
    vat_amount: 228.0,
    gross_total: 1428.0,
    status: "paid",
    items: [
      { description: "Website Redesign", quantity: 1, unit_price: 800.0, total: 800.0 },
      { description: "SEO Optimization", quantity: 1, unit_price: 400.0, total: 400.0 },
    ],
  },
];