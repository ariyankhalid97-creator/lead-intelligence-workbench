# Local AI consistency memory

Lead Extractor uses retrieval memory, not hidden model training. The installed Ollama model remains unchanged.

## What is remembered

Each niche receives one compact SQLite snapshot containing:

- completed and partial workflow counts;
- historical provider success, failure and retained-record totals;
- aggregate email, phone and website coverage;
- user-approved and user-rejected search terminology;
- recorded outreach outcome counts; and
- explicit rules that keep memory separate from evidence.

The snapshot is refreshed after a compiled workflow, reviewed teaching change or recorded outcome. It can also be rebuilt from the Local AI panel.

## What is never placed in prompt memory

- business or person names;
- email addresses and phone numbers;
- website or profile URLs;
- scraped page text and evidence excerpts; or
- credentials, browser sessions, campaign content or Google Sheets data.

Lead-specific evidence stays in the evidence ledger and is supplied only to the bounded task that needs it.

## Authority order

1. Current immutable evidence IDs and literal excerpts.
2. Deterministic validation, identity, contact-quality and outreach-safety rules.
3. Reviewed niche-pack terminology and exclusions.
4. Aggregate historical consistency memory.
5. Model suggestions.

Lower levels cannot override higher levels. Historical source performance is descriptive and does not claim that a provider is currently available.

## Why this implementation

The project reviewed durable local memory patterns from LangGraph SQLite, Mem0, LangMem and Letta. A small native SQLite layer fits this application better than introducing a vector database or agent server: it is auditable, deterministic, private, easy to repair and already uses the application's existing database lifecycle.
