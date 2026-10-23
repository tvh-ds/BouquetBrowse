import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from bouquetbrowse import adapters, api, providers, worker
from bouquetbrowse import db as database
from bouquetbrowse.auth import demo_token
from bouquetbrowse.db import Base, make_engine
from bouquetbrowse.seed import seed_demo


@pytest.fixture
def db(tmp_path, monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    if url.startswith("postgresql") and not (make_url(url).database or "").endswith("_test"):
        raise pytest.UsageError("Refusing destructive test setup: PostgreSQL database name must end in _test.")
    engine = make_engine(url)
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.drop_all(connection)
        Base.metadata.create_all(connection)
    factory = sessionmaker(engine, expire_on_commit=False)
    for module in [database, api, providers, adapters, worker]:
        monkeypatch.setattr(module, "SessionLocal", factory)
    monkeypatch.setattr(api, "engine", engine)
    monkeypatch.setattr(database, "engine", engine)
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def seeded(db):
    seed_demo(db)
    return db


@pytest.fixture
def client(db):
    with TestClient(api.app) as client:
        yield client


@pytest.fixture
def admin_headers():
    return {"X-Bouquet-Proxy": "localhost-proxy-demo-token", "Authorization": f"Bearer {demo_token('admin')}"}


@pytest.fixture
def tester_headers():
    return {"X-Bouquet-Proxy": "localhost-proxy-demo-token", "Authorization": f"Bearer {demo_token('tester')}"}
