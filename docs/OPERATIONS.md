# Operations runbook

## Local operation

Use README's Docker command for the reference startup. API readiness checks database/schema access; worker and web wait for it. Configuration example contains only non-production defaults. API and worker share code and a database; frontend communicates through an authenticated Next.js server proxy. Python optional ML libraries are not installed in API containers.

The non-Docker SQLite mode is for local development only. To use local PostgreSQL, start `docker compose up -d db`, set DATABASE_URL to `postgresql+psycopg://bouquet:bouquet-local-only@127.0.0.1:5433/bouquetbrowse`, then run `uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head`. Test only an isolated database ending `_test`; fixtures drop all application tables there.

## Private pilot setup

Provisioning paid infrastructure, domain ownership, Meta approval and production credentials are external setup tasks. No live private deployment is claimed by this repository.

1. Create Supabase PostgreSQL with pgvector, Auth asymmetric signing keys and a **private** `bouquet-media` bucket. Disable public sign-up. Invite testers explicitly in the Supabase console. Do not publish the demo credentials or use APP_MODE=demo on a public host.
2. Use separate migration-owner and runtime database credentials. Apply Alembic with the owner. All app tables enable RLS and revoke anon/authenticated/PUBLIC grants. Disable the Data API if unused, or remove the application's schema from its exposed schemas. Raw tables are accessed only through FastAPI. Do not expose enrichment tables through browser APIs.
3. Provision a non-login group `bouquet_runtime` using deploy/runtime-role.sql, then grant it to your dedicated login role. The runtime role has application-table DML through role-specific RLS policies; it cannot alter schema or bypass RLS. Set DATABASE_URL to that dedicated login for api/worker. Do not use an Auth service key as a database password. Pool size is five plus two overflow per process; choose connection/session-pooler mode compatible with psycopg and these limits.
4. Set APP_MODE=pilot, HTTPS PUBLIC_ORIGIN, Supabase URL/publishable key, server-only Storage secret key, and a random INTERNAL_API_TOKEN of at least32 characters. The secret key is never sent to the browser. Use secure secret delivery, not repository files. Configuration rejects incomplete pilot settings. Pilot web and API must share PUBLIC_ORIGIN and internal token.
5. Add app membership by Auth UUID: `python -m bouquetbrowse.cli member --user-id UUID --role tester` (or reviewer/admin), with the runtime environment configured. This command does not create an Auth user or send mail. Membership is read from the database, never user-editable JWT metadata. Reviewer can review; only admin can import, sync, retry and take down.
6. Build containers. Run migrations as an explicit deployment step with owner credentials, then start the runtime API/worker using a command that omits migrations. The default API container startup runs migrations for the local demo; override it for least-privilege production. Set PUBLIC_HOST and enable the Caddy https profile after DNS is configured. Expose only Caddy ports80/443, never database/API ports publicly. Caddy handles TLS and HSTS. Configure a VM firewall and backups.
7. Verify tester access, denied unauthenticated/admin calls, expired/revoked membership, private media access, same-origin mutation checks, secure HttpOnly cookies, source failures, budget breaker and a real restore drill before inviting users. Access cookies expire; the server-only `/api/auth/refresh` consumes the HttpOnly refresh cookie and never returns tokens to browser JS. Otherwise users can sign in again. Logout clears this browser session; provider-wide session revocation uses Supabase administration.

Next's BFF has same-origin mutation checks and a5MB request cap. The API is private behind the proxy token and independently verifies JWTs/roles. Never put a real secret in any NEXT_PUBLIC variable. Do not render captions as HTML.

## Live enrichment and acquisition

Enable EXTRACTION_PROVIDER=openai only with OPENAI_API_KEY. Defaults use gpt-6-luna; stronger-model setting is recorded but automatic escalation waits for evaluation. store=false, strict schema, no model tools and application grounding checks apply. Monthly spending reservations are conservative and stay charged against the limit when actual cost is unknown; inspect CostEntry before manually reconciling a failed reservation. Provider billing may differ from token estimates; compare invoices and image usage before raising the budget.

Text vectors use text-embedding-3-small. Without its key, live search reports keyword-only operation. Demo vectors are explicitly synthetic and do not backfill live records. For SigLIP, install the optional `vision` extra in a dedicated worker environment (`uv sync --project apps/api --extra vision --frozen`), set IMAGE_EMBEDDING_PROVIDER=siglip and SIGLIP_REVISION to a reviewed exact Hugging Face commit. Review the model license/download and available RAM first. The lightweight default Docker worker deliberately does not install torch. Model artifacts stay out of Git.

Threads and Instagram need approved flags plus actual tokens and account/version configuration. Register known sellers through reviewed operator records. See SOURCE-FEASIBILITY.md. Configuration is not proof of approval. API errors become visible failed/retryable jobs. A deleted/inaccessible source must never be changed into sold-out inventory. Current bounded clients do not certify exhaustive pagination or deleted-post polling.

## Failure handling and retention

Check `/health/live` and `/health/ready`, Studio Sources/Jobs, last successful checkpoint, pending review count and model cost reservations. Integrate external alerting only after selecting the deployment monitor. Alert on stale acquisition, failed/exhausted jobs, growing backlog, errors and approaching model/total budgets. Logs contain IDs and error categories, not credentials/captions. Set container log rotation (e.g. max-size10m/max-file3) and external log retention30days.

Jobs have at-least-once delivery, ten-minute leases and bounded operations. Failed permissions/configuration errors require correction before Retry. No unbounded provider retries. Processing keys are versioned; reprocess stages assertions and leaves accepted revisions in place until reviewed. Keep one worker until concurrency behavior/load are measured.

Daily retention scrubs expired raw payloads after30days, media/vectors after90days, derived listing content after365days and cohort snapshots after7days. Shorter grant deadlines override defaults when recorded. Accepted evidence quotes are retained facts and may remain after raw payload expiry; takedown scrubs them. Takedown suppresses immediately, then purges associated source content, media, vectors, assertions, prices and cohorts while preserving minimal removal/audit records. Media shared with another active product is retained until its last applicable reference is removed. Review deletion scope for a seller-wide request and apply to every affected listing. Do not reimport withdrawn source IDs.

## Backup and recovery

RPO target24h, RTO target4h; these are not established until a timed restore succeeds. Supabase database backups do not include Storage objects. Export the database and private bucket separately to encrypted access-controlled storage. Store takedown/deletion records independently so they can be replayed after restore.

`python deploy/backup.py OUTPUT_DIRECTORY` creates a local Docker development database custom-format dump and media-volume tar using subprocesses without shell interpolation. It refuses to overwrite files. This is not a Supabase backup: for pilot use managed DB backups plus a paginated private Storage export, validate checksums/object counts, and include it in the restore drill. Keep all exports outside Git and apply source retention rules to backup copies.

Restore rehearsal: create an isolated PostgreSQL database and private test bucket, restore DB/media, apply migrations, replay every deletion newer than the backup, then validate counts, representative media, memberships, search, review and takedown. Never let the restored worker contact live sources until deletion replay and credential isolation are complete. Record elapsed time, last recoverable timestamp, failures and owner. A dump existing on disk does not prove recovery.

## Dependency review

Python uv.lock and npm package-lock.json pin resolved dependencies. CI checks runtime npm advisories. At baseline npm reported an unfixed dev-only braces≤3.0.3 advisory through eslint-config-next/fast-glob/micromatch; current registry latest was3.0.3. Runtime `npm audit --omit=dev --audit-level=high` was clear. The affected glob parser handles trusted repository lint patterns, not public app input; keep CI changes reviewed, do not process untrusted glob rules, and recheck/upstream-upgrade when patched. Do not force-downgrade Next to hide this finding. Python dependency advisories and image OS packages should be reviewed before cloud release; no vulnerability-free claim is made.
# Local discovery runtime preparation

The runtime dependency review upgraded Pillow 12.3.0 to 13.0.0 because the image pipeline accepts external images and the older release had reported decoder/encoder vulnerabilities. The installed locked Python environment audited clean after the upgrade on 29 October 2026. This is a point-in-time advisory check, not a guarantee about future advisories or all supply-chain risk.

Run Alembic as the migration owner, then `uv run --project apps/api python deploy/setup_graph_checkpoints.py`, then apply `deploy/runtime-role.sql`. Checkpoint setup creates tables/indexes and is deliberately absent from API/worker startup. Runtime roles receive DML and schema usage, not CREATE or checkpoint-migration ownership. The graph checkpointer uses the private `graph_checkpoints` schema and disables pickle fallback. Recurring execution requires PostgreSQL; in-memory checkpoints are only test doubles.

Jobs use a renewable two-minute lease and thirty-second heartbeat. Cancelling or reclaiming a job fences the previous attempt. Model-call receipts and reservations commit before dispatch; uncertain outcomes pause work and retain spending. Explicit replay must be authorized and fit a new reservation; ordinary job retry does not authorize it. Paid requests use no SDK automatic retries. Job completion and publication must recheck ownership and source applicability. Retention/takedown storage deletions are durable jobs outside database transactions.

Trust boundaries: Threads content and model output cannot select arbitrary code, network destinations, storage paths or roles. The browser session, API/model keys and private source evidence are assets; they never enter graph checkpoints, prompts as credentials, public fixture commits or telemetry. Application authorization gates administration; graph resume payloads do not approve evidence. Domain facts and call receipts must be revalidated after checkpoint recovery.
