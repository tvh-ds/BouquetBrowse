# Local recurring operations

Code is implemented; activation is deferred. Credentials remain placeholders, `DISCOVERY_ENABLED=false`, `RECURRING_ENABLED=false`, and real-data proof gates are closed. No Windows task has been registered or started during this delivery. Live tests await the user's command.

## Setup and activation

Use PostgreSQL 17/pgvector, apply Alembic migrations as owner, run `deploy/setup_graph_checkpoints.py`, then apply `deploy/runtime-role.sql` for a separate DML runtime role. SQLite supports demo/unit checks, not recurring collection. Docker Desktop currently has an unrelated local backend startup fault; its data/settings have not been reset. PostgreSQL/container validation runs in CI; local PostgreSQL recovery remains pending.

Install the locked browser extra and Chromium using OPERATIONS.md. Install optional CV only when wanted; SigLIP weights load only on that configured path and its revision is pinned. Set the local model key privately, restart processes, and sign in directly through `python -m bouquetbrowse.cli browser-login`. No cookies are copied. Session challenges pause collection.

Manual bounded discovery can collect the private evaluation dataset before publication qualification. Complete the separately commanded twenty-conversation/100-image evaluation and audited approval in PILOT-VALIDATION.md. Then explicitly configure recurring operation. `python -m bouquetbrowse.cli operations-ready` checks configuration and proof gates without browsing or inference.

`deploy/install-local-tasks.ps1` registers disabled tasks by default. `-Enable` refuses until recurring configuration and both audited gates pass. Invoke it only when startup installation is wanted. Tasks use the current user, limited privilege, interactive sign-in, hidden PowerShell, no stored password, no wake-from-sleep or start-when-available catch-up, and one instance per role. Registration does not start a task immediately. `deploy/run-local-role.ps1` uses the installed Python environment; Codex need not stay open. API/web processes retain their existing deployment startup.

## Schedule, health and digest

Three roles run: scheduler, browser and offer. The offer role also prepares media and handles maintenance jobs. The scheduler checks every thirty seconds for Hanoi starts at 06:00, 10:00, 14:00, 18:00 and 22:00. A ninety-second tolerance accommodates polling; older missed windows never create catch-up collection bursts. Each slot is idempotent and closes within twenty minutes of its scheduled start, including planning. An overlapping manual run makes the slot missed. Restarts cancel queued work whose window expired.

Frontier allocation remains 40% refresh / 40% search-profile / 20% FYP with spillover. Unresolved offer evidence requests the next eligible slot; ordinary posts refresh daily and established profiles weekly. Source access is distinct from inventory. Existing admin pause/cancel controls remain available. Admin-only `/v1/admin/operations/status` reports role heartbeats and active-lease health, recent slot outcomes, actual non-demo coverage, spending and proof readiness. A valid renewable lease counts as worker activity during long jobs. External alert delivery is a deployment configuration concern.

After the final slot closes, a Hanoi-day digest freezes durable changes. Offline days become explicitly partial at startup after scheduling was activated. An installation never enabled does not generate fake digest days. Late enrichment waits for the next digest. Schedule bookkeeping covers the last thirty days and does not imply older gaps were observed. Worker logs rotate under ignored `.data/logs/`, retaining thirty daily files per role; operational logs contain IDs and failure types, not captions or credentials.

## Retention and deletion

Raw source/buyer context expires after thirty days, media at ninety days or earlier policy deadlines, accepted facts at twelve months, and logs at thirty days. Expiry removes derived claims, analysis/review copies, canonical evidence, recognition results, source-linked digest entries and catalog eligibility. Content-free identity tombstones support deletion/deduplication. Media/vector and checkpoint cleanup use durable jobs; checkpoint removal covers snapshots, blobs and intermediate writes.

Takedown suppression is immediate. Purge cancels affected graphs, strips evidence copies and records content-free deletion identities. A model response arriving after deletion settles its financial receipt without restoring its result. Media dependency receipts cover image-only evaluation calls without an offer. Checkpoint writes hold a shared application execution lock, preventing a withdrawn execution from recreating state after purge. Cancellation can retain a financial receipt; uncertain reservations are never automatically replayed or refunded.

## Backups and recovery

`python deploy/backup.py <private-directory>` exports a PostgreSQL custom dump, separate streamed retained-media archive (filesystem or configured private Storage), a deletion ledger from the same API deployment, and SHA-256/size manifests. Failed exports do not create a complete manifest. Keep files under ignored `.data` or outside Git and retain newer deletion ledgers separately. DB/media snapshots are not a single zero-write-loss transaction. Apply source/deletion retention to backup copies too.

`uv run --project apps/api python deploy/restore_rehearsal.py <manifest> --deletions <current-ledger.jsonl> --media-directory <new-private-directory>` needs a precreated empty `*_restore_test` PostgreSQL database in `RESTORE_DATABASE_URL` and compatible native `pg_restore`. It refuses the application database, existing tables and an existing media directory. It verifies manifests, restores DB, replays current deletions, expires evidence, cancels graphs and pauses collection. Only still-permitted media goes into the isolated directory; live Storage is untouched. Check counts, representative API/media reads, roles, search, review and takedown against that target. Reapply runtime grants before deployment. Do not serve a restore or start live workers before deletion replay and media cleanup finish.

Automated checks exercise a fictional SQLite snapshot, later takedown, isolated restore and current-ledger replay. That scope does not measure real PostgreSQL/media RPO or RTO. The twenty-four-hour RPO and four-hour RTO remain targets. Real coverage, quality, inference cost/latency and recovery timing wait for the user's live-test command and must be reported separately from fixture success.
