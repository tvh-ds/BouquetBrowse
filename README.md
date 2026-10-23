# BouquetBrowse
finding your flowers

A private Hanoi bouquet discovery and advertised-price comparison pilot. Next.js, FastAPI, PostgreSQL/pgvector, and a durable Python worker.

**The runnable baseline uses 30 fictional listings across eight fictional sellers. Photos are AI-generated. Prices, source captions and histories are synthetic.** Live collection and ML quality are not certified by the demo.

## Run with Docker

Install Docker with Compose, then from a fresh checkout:

```sh
docker compose up --build -d --wait
```

Open [localhost:3000](http://localhost:3000). The sign-in screen has tester and catalog-studio demo buttons. All exposed application ports bind to loopback. No API keys are required. First build downloads dependencies; no model weights are downloaded.

Demo credentials: `tester@bouquetbrowse.local` / `demo-tester`, or `admin@bouquetbrowse.local` / `demo-admin`. Never expose this mode publicly. `docker compose down` preserves data; do not remove volumes unless deliberately resetting the local demo.

## Run without Docker

Use Python 3.12, uv 0.10.9, and Node 24. The development fallback uses SQLite; PostgreSQL integration is tested separately.

```sh
uv sync --project apps/api --frozen
npm --prefix apps/web ci --ignore-scripts
uv run --project apps/api python -m uvicorn bouquetbrowse.api:app --host 127.0.0.1 --port 8000
```

In two additional terminals:

```sh
uv run --project apps/api python -m bouquetbrowse.worker --schedule
npm --prefix apps/web run dev
```

The API starts and seeds the localhost demo. To process a single job: `uv run --project apps/api python -m bouquetbrowse.worker --once`.

## Try the complete workflow

1. Enter the catalog studio demo, open Import and edit the provided JSON. Explicitly set the content-use confirmation to true for your own permitted content.
2. Import with a unique source ID. The worker extracts caption facts; the listing appears in Reviews.
3. Inspect the exact price and size evidence, correct or accept the extraction, then publish.
4. Search the catalog, inspect Sources & evidence, add bouquets to the comparison tray, and inspect the independent qualified benchmark.
5. Original-post links appear when supplied; fictional demo sellers have no fabricated social profiles. Failed jobs can be retried from Studio.

Similar appearance does not establish price comparability. Benchmarks exclude the selected seller, use one qualified configuration per other seller, and suppress aggregates below five sellers. Budgets filter browsing, never benchmark membership.

## Checks

```sh
uv run --project apps/api ruff check apps/api
uv run --project apps/api pytest apps/api/tests -q
npm --prefix apps/web run check
npm --prefix apps/web run build
cd apps/web
npx playwright install chromium
npm run test:e2e
```

Set `TEST_DATABASE_URL` to an isolated PostgreSQL/pgvector database whose name ends in `_test` to run the same suite against PostgreSQL. **The test fixture deletes that database's application tables.** CI also checks migrations, generated API contracts, production dependency advisories, browser flows and clean Docker startup.

See [blueprint](docs/BLUEPRINT.md), [requirement coverage](docs/TRACEABILITY.md), [operations and deployment](docs/OPERATIONS.md), [source feasibility](docs/SOURCE-FEASIBILITY.md), and [evaluation status](docs/EVALUATION.md). The authorized delivery workflow is in [AGENTS.md](AGENTS.md).
