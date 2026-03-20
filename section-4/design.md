# Section 4 — System Design & Critical Thinking

## 1. Architecture

```
  [Email/API/Upload]
         |
    Ingestion Layer  ──>  Object Store (S3/GCS)
         |
    Message Queue (RabbitMQ / SQS)
         |
    Worker Pool (auto-scaled)
     ├── OCR (if scanned image)
     ├── LLM Extraction (raw text → JSON)
     ├── Pydantic Validation
     └── Security Check (input sanitization, delimiter wrapping)
         |
    ┌────┴────┐
  PASS      FAIL
    |         |
 PostgreSQL  Dead Letter Queue ──> Human Review Dashboard
    |
  REST API (FastAPI)
    |
  Downstream Systems
```

The system follows an event-driven architecture. Ingestion services (email listeners, API upload endpoints) drop raw files into object storage and publish an event to a message queue. Worker nodes pick up events, run OCR if needed, call the LLM for extraction, and validate output through Pydantic schemas. Valid results go to PostgreSQL, failures route to a dead letter queue for human review. A FastAPI layer exposes the stored data to downstream consumers — same pattern I use in Section 5 of this project.

## 2. Reliability

The pipeline uses a dead letter queue (DLQ) pattern so failures never block processing. When the Pydantic validation step catches missing fields, wrong totals, or VAT mismatches in the LLM output, the worker doesn't crash — it routes the raw document alongside the flawed JSON to the DLQ and moves on to the next invoice. A review dashboard reads from this queue and presents the original invoice side-by-side with the flagged data, so a human operator can correct specific fields without re-running the entire extraction. Once corrected, the validated payload goes straight to the primary database, bypassing the LLM entirely. This keeps throughput steady at scale while containing the 5% failure rate to a manageable review workload of roughly 25 invoices per day.

## 3. Cost

At one API call per invoice, the daily cost is straightforward: 500 * $0.03 = **$15/day** (~$450/month). To cut that by 50%, I'd implement model routing — use a cheaper, faster model (like Claude Haiku or GPT-4o-mini at ~$0.005/call) as the primary extraction engine for all standard invoices. Only if the cheap model's output fails Pydantic validation do we fall back to the expensive model for a retry. In practice, most invoices follow predictable formats, so the cheap model handles 80-90% of them on the first pass. This drops the daily cost to roughly $5-8 while maintaining accuracy through the same validation layer we already have. An alternative long-term strategy is deploying a fine-tuned smaller model on dedicated infrastructure, which trades upfront setup cost for near-zero per-invoice cost at high volumes.

## 4. Scaling

10,000 invoices/day is about 7 invoices per minute sustained, with likely spikes during business hours. The event-driven queue architecture handles this without fundamental redesign — the queue buffers incoming work, and we auto-scale worker nodes horizontally based on queue depth. The main bottleneck becomes LLM API rate limits, which we handle with exponential backoff and request batching across multiple API keys or providers. On the database side, we'd add connection pooling (PgBouncer) and potentially read replicas to keep the API layer responsive under heavier query loads. If the volume keeps growing beyond that, the model routing strategy from Q3 becomes even more valuable — processing 10k invoices through a cheap model first significantly reduces both cost and API pressure on the expensive provider.