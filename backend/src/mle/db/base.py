from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from mle.core.config import get_settings


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


def create_engine() -> AsyncEngine:
    settings = get_settings()
    normalized_url = _normalize_database_url(settings.database_url)
    return create_async_engine(
        normalized_url,
        echo=False,
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )


engine: AsyncEngine = create_engine()
async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


def _pg_migration_sql_002() -> str:
    """Ruta: backend/sql/002_users_and_opportunity_owner.sql (desde src/mle/db/base.py, 4 niveles arriba)."""
    sql_path = Path(__file__).resolve().parent.parent.parent.parent / "sql" / "002_users_and_opportunity_owner.sql"
    if not sql_path.is_file():
        return ""
    return sql_path.read_text(encoding="utf-8")


async def init_db() -> None:
    import mle.db.models as _mle_db_models  # noqa: F401 — registrar modelos en SQLModel.metadata

    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
        if engine.dialect.name != "postgresql":
            return
        # create_all no altera tablas ya existentes; columnas nuevas en modelos requieren migración.
        await connection.execute(
            text(
                "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS "
                "profile_overrides JSONB NOT NULL DEFAULT '{}'::jsonb"
            )
        )
        block = _pg_migration_sql_002()
        if not block:
            return
        for part in block.split(";"):
            stmt = " ".join(
                line for line in part.splitlines()
                if line.strip() and not line.strip().startswith("--")
            ).strip()
            if not stmt:
                continue
            await connection.execute(text(stmt + ";"))

