# Baseline verification

Local verification on23October2026:

- Backend regression suite:61SQLite tests passed;60PostgreSQL17/pgvector tests passed before the final budget case was added (the complete suite also runs in CI). Coverage includes import/publication, review, money/evidence rules, seller balancing, sparse cohorts, cursor behavior, leases/retries, authorization, takedown cleanup and model budget gating.
- Frontend strict TypeScript, ESLint and optimized Next.js production build passed.
- Eight discovery/compare/admin/responsive browser flows passed at1440×1000 and390×844, including comparison removal and mobile filter dialog. Two further browser workflows imported source content, ran the separate worker, accepted review, found the listing and verified the original seller link.
- PostgreSQL migration from an empty database and downgrade/upgrade succeeded. All27application tables had RLS; runtime-role access was verified separately from migration-owner access.
- Docker images built and the local PostgreSQL/API/worker/web stack reached healthy startup. This establishes local container operation, not production cloud deployment.
- Production npm audit reported zero vulnerabilities at the checked lockfile; the known unfixed dev-tool advisory and follow-up are recorded in OPERATIONS.md.
- Impeccable detector returned no findings. The independent visual review's verdict pass marked four specific fixes resolved: conditional demo labels, URL-synchronized comparison removal, mobile evidence typography and44px actions. That verdict covers those fixes and the six supplied captures, not every possible application state.

Live capabilities still require Meta/Supabase/model credentials, platform eligibility evidence, permitted real samples and a deployed restore/monitoring exercise. No paid model quality/cost measurement or real Hanoi coverage is asserted. See TRACEABILITY.md for deferred items. GitHub CI records the authoritative checks for each pushed head; merges must reference that exact passing head.
