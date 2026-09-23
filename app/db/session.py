import os
import ssl
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import settings

# 1. Read and normalize raw connection URL
raw_url = os.getenv("DATABASE_URL") or getattr(settings, "DATABASE_URL", None) or ""
raw_url = raw_url.strip().strip('"').strip("'")

# 2. Strip parameters incompatible with asyncpg
if "channel_binding=require" in raw_url:
    raw_url = (
        raw_url.replace("&channel_binding=require", "")
        .replace("channel_binding=require&", "")
        .replace("channel_binding=require", "")
    )

# 3. Convert sslmode=... to ssl=... for asyncpg compatibility
if "sslmode=" in raw_url:
    raw_url = raw_url.replace("sslmode=require", "ssl=require").replace("sslmode=prefer", "ssl=prefer")

# 4. Enforce asyncpg dialect
if raw_url:
    if raw_url.startswith("postgres://"):
        async_db_url = raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif raw_url.startswith("postgresql://"):
        async_db_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        async_db_url = raw_url
else:
    host = settings.POSTGRES_SERVER
    if host == "crm_db":
        host = "localhost"
    async_db_url = (
        f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{host}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )

# Configure SSL context for cloud providers (Neon/AWS RDS)
connect_args = {}
if "neon.tech" in async_db_url or "ssl=require" in async_db_url:
    # Ensure standard SSL context without certificate validation rejection
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    connect_args["ssl"] = ctx
    # Remove query string parameter once passed in connect_args to avoid duplicate arg collision
    if "?" in async_db_url:
        async_db_url = async_db_url.split("?")[0]

engine = create_async_engine(
    async_db_url,
    connect_args=connect_args,
    echo=False,
    future=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async_session_factory = AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()