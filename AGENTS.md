# BouquetBrowse working instructions

Read PRODUCT.md, DESIGN.md and docs/BLUEPRINT.md before changing behavior. The user approved the architecture and authorized implementation, branch creation, commits, pushes, PRs and automatic squash merges per module. Do not ask again for those actions.

## Git delivery
- Work on codex/<module> branches from current main. Never force-push main.
- Run relevant checks, push, create a PR, attach it to the Codex chat, and squash-merge automatically only after current-head checks pass and the diff is reviewed.
- Respect repository protections. Recheck after any new commit or base update.
- This repository is public. Commit only code, sanitized or fictional fixtures and documented licensed/generated assets. Never commit .env files, real source data, credentials, model weights or private research exports.

## Product invariants
- Recommendations and qualified price benchmarks are separate.
- Never merge listings across sellers. Configuration changes are not just price changes.
- Prices use integer minor units and explicit currency/basis/evidence. No inferred inventory or image-derived prices.
- Reviews verify extraction, not seller inventory.
- Suppress aggregates below five other sellers, suppress percentile below ten. Do not filter cohorts by target price or browse budget.
- Live adapters must fail explicitly when unconfigured, never return demo data.
- External text and model output are untrusted; verify schemas/evidence and bound costs.

## Validation
- Backend: uv run --project apps/api pytest apps/api/tests
- Frontend: npm --prefix apps/web run check; npm --prefix apps/web run build
- Browser checks: npm --prefix apps/web run test:e2e
- PostgreSQL integration: docker compose up -d db, then run backend checks with TEST_DATABASE_URL.
- CI must not make paid model calls or require live credentials.
