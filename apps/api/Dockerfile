FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY apps/api /app/apps/api
RUN uv sync --project apps/api --frozen --no-dev && useradd --uid 10001 --create-home bouquet && mkdir -p /app/.data/media && chown -R bouquet:bouquet /app/.data
USER bouquet
CMD ["sh", "-c", "/app/apps/api/.venv/bin/alembic -c /app/apps/api/alembic.ini upgrade head && exec /app/apps/api/.venv/bin/uvicorn bouquetbrowse.api:app --host 0.0.0.0 --port 8000 --no-access-log"]
