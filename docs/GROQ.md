# Groq setup for bounded local testing

Groq (console.groq.com) is a separate provider from xAI/Grok. Its key belongs in the ignored root `.env` as `GROQ_API_KEY`. It must never be placed in `OPENAI_API_KEY` or a `NEXT_PUBLIC_*` field. Select generation explicitly:

```dotenv
MODEL_PROVIDER=groq
GROQ_API_KEY=YOUR_PRIVATE_KEY
GROQ_PLANNER_MODEL=qwen/qwen3.8-27b
GROQ_EXTRACTION_MODEL=qwen/qwen3.8-27b
GROQ_ESCALATION_MODEL=qwen/qwen3.8-27b
EXTRACTION_PROVIDER=groq
DISCOVERY_ENABLED=false
RECURRING_ENABLED=false
```

Restart API/worker processes after editing `.env`; process environment variables take precedence over the file. There is no automatic collection, model download or inference during configuration. The dedicated Threads session, PostgreSQL migrations/checkpoints, manual resume and a bounded discovery command are still needed. Follow LOCAL-RECURRING-OPERATIONS.md for those steps. Existing SQLite remains the demo database; changing DATABASE_URL does not migrate its records automatically.

## Models and limits

The default Qwen model accepts text and images and supports strict structured output. It is a provider preview, so availability can change; its suitability for mixed flowers has not been established. All three roles initially use the same model: a regional recheck is not necessarily a stronger model. `openai/gpt-oss-20b` and `openai/gpt-oss-120b` on Groq are supported for text-only interpretation; they cannot replace an image-capable discovery planner or recognition model. Model IDs with an `openai/` prefix on Groq still use the Groq endpoint and Groq key.

Groq calls use the existing OpenAI SDK's strict Chat Completions parser against the fixed HTTPS Groq endpoint, with no model tools, no automatic HTTP retries and full application evidence validation. Requests adapt image parts and token limits explicitly; OpenAI generation continues using its existing Responses parser. Each call allows at most three images. Ordinary offers analyze at most two original chunks (six images) and one bounded regional recheck; remaining media is recorded as unprocessed. No provider silently substitutes for another.

Free-plan token/request limits depend on the account and model. A key's presence or successful authenticated model-list request does not establish free billing, usable inference quota or flower accuracy. Rate-limit/API failures remain visible through receipts and jobs; uncertain calls retain reservations and require explicit replay. Do not retry repeatedly to evade a quota.

## Accounting, provenance and recovery

Costs are conservative estimates at documented paid list rates, even on a free account: Qwen input/output $0.80/$4.00 per million tokens; GPT-OSS 20B $0.075/$0.30; GPT-OSS 120B $0.15/$0.60. Provider usage is normalized to input/output tokens and marked `published_paid_rate_estimate`; this ledger is not a provider invoice or a claim that a free-tier request was charged. Missing usage retains the reservation estimate. Existing monthly/per-work circuit breakers and uncertain-call replay requirements apply.

Generation provider and model identifiers are pinned in execution/release configuration. Receipts and recognition caches distinguish providers. A provider change cannot resume earlier-provider work or reuse its qualification proof. Graph behavior is `threads-graphs-v10`; interrupted older graphs require their compatible code or explicit reprocessing. Keys and credentials never enter checkpoints. Recognition categories remain tentative until the current provider/model configuration passes the real-data benchmark.

Text embeddings remain independently OpenAI-backed and require a separate OpenAI key. Groq-only live search uses keywords; it does not send a Groq key to the OpenAI embedding endpoint. Optional local SigLIP features are unchanged and load no weights during setup.

## Verification boundary

CI tests strict request serialization, provider/key isolation, image limits/truncation, invalid structured output, provider-specific estimates, pinned-provider rejection and uncertain-call reuse with fictional responses. No CI test uses a live key. Authenticated `/models` access only verifies account access. Live inference, Threads collection, quality proofs and recurring startup require explicit test/activation commands; none is implied by the adapter's synthetic tests.

Official references checked 31 October 2026: [SDK compatibility](https://console.groq.com/docs/openai), [structured outputs](https://console.groq.com/docs/structured-outputs), [vision](https://console.groq.com/docs/vision), [model prices](https://console.groq.com/docs/models), [rate limits](https://console.groq.com/docs/rate-limits), [data controls](https://console.groq.com/docs/your-data). Provider availability, rates, quotas and retention rules may change.
