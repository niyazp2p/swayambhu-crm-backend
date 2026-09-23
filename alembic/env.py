import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.db.base import Base
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Read DATABASE_URL and normalize
raw_url = os.getenv("DATABASE_URL") or getattr(settings, "DATABASE_URL", None) or ""
raw_url = raw_url.strip().strip('"').strip("'")

# Strip channel_binding if present
if "channel_binding=require" in raw_url:
    raw_url = raw_url.replace("&channel_binding=require", "").replace("channel_binding=require&", "").replace("channel_binding=require", "")

# Ensure synchronous psycopg2 dialect for Alembic runner
if raw_url.startswith("postgresql+asyncpg://"):
    sync_db_url = raw_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
elif raw_url.startswith("postgres://"):
    sync_db_url = raw_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif raw_url.startswith("postgresql://"):
    sync_db_url = raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)
else:
    host = settings.POSTGRES_SERVER
    if host == "crm_db":
        host = "localhost"
    sync_db_url = (
        f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{host}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


def run_migrations_offline() -> None:
    context.configure(
        url=sync_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        sync_db_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()