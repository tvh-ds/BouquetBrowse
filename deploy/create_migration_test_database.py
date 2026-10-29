"""Create a separate disposable CI database; never clear an existing database."""

import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from bouquetbrowse.config import get_settings

url = make_url(get_settings().database_url)
name = url.database or ""
if not re.fullmatch(r"[a-z][a-z0-9_]*_migrations_test", name):
    raise SystemExit("Only an explicitly named *_migrations_test database may be created.")
engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
with engine.connect() as connection:
    if connection.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": name}):
        raise SystemExit("Migration test database already exists; refusing to reset it.")
    # Name is constrained above and quoted by the SQLAlchemy dialect.
    connection.execute(text(f"CREATE DATABASE {connection.dialect.identifier_preparer.quote(name)}"))
engine.dispose()
print("Created isolated migration test database.")
