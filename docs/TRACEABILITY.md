# Requirement coverage

Status: **implemented** means baseline code and fixture behavior; **configured** means code requires external credentials; **deferred** means not claimed in this delivery.

| Requirement | Status / implementation |
|---|---|
| All MVP pages and bilingual mobile flows | Implemented: apps/web/src/app and components |
| Private tester/reviewer/admin access | Demo + configured Supabase JWT verification and application membership; private cloud deployment not provisioned |
| PostgreSQL/pgvector schema, append-oriented provenance | Implemented migration, 27+ domain/operations tables; SQLite local fallback |
| Import → job → extraction → review → publish | Implemented; API integration tests and admin UI |
| Price parsing, delivery/deposit separation, ambiguity | Implemented deterministic rules and grounding validation; real accuracy unmeasured |
| Structured multimodal extraction | Configured OpenAI Responses provider, bounded requests; real quality/cost unmeasured; automatic stronger-model escalation deferred pending evaluation |
| Model provenance, confidence and commercial review | Implemented assertion envelopes, run versions, review audit; calibration deferred |
| Search/facets/cursors | Implemented bilingual aliases, keyword and RRF; exact filtered pgvector on PostgreSQL, local cosine fallback for SQLite |
| Visual recommendations | Demo hybrid vectors and actual stored-image/text similarity path; optional pinned SigLIP worker; real recall unmeasured |
| Strict seller-balanced cohorts and sparse samples | Implemented domain rules, independent pool, reproducible snapshots, exclusions; no budget bias |
| Advertised price history | Implemented evidence-linked observations; synthetic histories labeled; no invented market trends |
| Source acquisition | Configured official clients and actionable disabled states; actual platform feasibility remains external |
| Anonymous public post collection | Implemented admin URL preview → editable import draft; bounded Threads/Instagram HTML and Threads share redirects; one live Threads post parsed, broad coverage unvalidated |
| Jobs, retries, lease recovery, idempotency | Implemented, tested; single bounded worker; large-scale concurrency not load-tested |
| Deduplication/configuration identity | Exact IDs/hashes, same-seller explicit configuration keys; near-duplicate auto merges deliberately review-only/deferred |
| Media validation and private storage | Implemented pinned DNS/host allowlists/limits, processing and Supabase REST storage; no arbitrary website fetching |
| Corrections/takedowns | Implemented suppression, queued purge, derived vectors/cohort cleanup and retention worker |
| Cost budget/usage ledger | Implemented conservative reservations/circuit breaker; paid measurements not run |
| Operational status | Admin job/source/cost/coverage views, request IDs and health endpoints; external alert delivery deferred until deployment |
| Docker and CI | Implemented locked dependencies, unit/PG/browser/build/clean-start checks |
| Backups/private deployment | Runbook and local backup utility; paid VM, production DNS/credentials, restore drill and real monitoring pending |
| Evaluation/coverage goals | Protocol recorded, no real sample or quality metrics invented |
| V1 customer reference uploads, seller claims, saved searches | Deferred |
| Checkout, learned ranking, forecasting, training, warehouse | Deferred |

Initial baseline is one coordinated module branch codex/00-bootstrap. Subsequent modules must replace fixtures and close these external-validation gaps with measured evidence, not relabel demonstrations as live capability.
