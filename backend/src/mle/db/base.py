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
    """Carga 002 si existe (desarrollo con repo clonado). En Docker/ wheel el .sql no se incluye; usamos _pg_apply_users_and_owner_migrations embebida."""
    sql_path = Path(__file__).resolve().parent.parent.parent.parent / "sql" / "002_users_and_opportunity_owner.sql"
    if not sql_path.is_file():
        return ""
    return sql_path.read_text(encoding="utf-8")


def _pg_apply_lead_contact_fields_migrations() -> list[str]:
    """
    Migración embebida para sql/003_lead_contact_fields.sql.
    Añade phone, address, schedule_text, enriched_sources al Lead para auto-enrich.
    """
    return [
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS phone VARCHAR(40)",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS address VARCHAR(500)",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS schedule_text VARCHAR(500)",
        (
            "ALTER TABLE leads ADD COLUMN IF NOT EXISTS enriched_sources "
            "JSONB NOT NULL DEFAULT '{}'::jsonb"
        ),
    ]


def _pg_apply_users_and_owner_migrations() -> list[str]:
    """
    Misma lógica que sql/002_users_and_opportunity_owner.sql, en SQL embebida.
    Obligatorio: el .sql en disco no acompaña al paquete instalado en contenedor, y sin esto
    falta la columna opportunities.owner_user_id.
    """
    return [
        """
        CREATE TABLE IF NOT EXISTS users (
          id UUID PRIMARY KEY,
          email VARCHAR(255) NOT NULL,
          password_hash VARCHAR(255) NOT NULL,
          display_name VARCHAR(160) NOT NULL,
          role VARCHAR(32) NOT NULL DEFAULT 'user',
          is_active BOOLEAN NOT NULL DEFAULT true,
          created_at TIMESTAMPTZ NOT NULL
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)",
        "CREATE INDEX IF NOT EXISTS ix_users_is_active ON users (is_active)",
        (
            "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS owner_user_id "
            "UUID REFERENCES users (id)"
        ),
        "CREATE INDEX IF NOT EXISTS ix_opportunities_owner_user_id ON opportunities (owner_user_id)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE opportunities ALTER COLUMN job_id DROP NOT NULL",
        "ALTER TABLE opportunities ALTER COLUMN exa_preview_index DROP NOT NULL",
        (
            "ALTER TABLE opportunities DROP CONSTRAINT IF EXISTS uq_opportunity_job_preview_idx"
        ),
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_opportunity_job_preview_idx "
            "ON opportunities (job_id, exa_preview_index) WHERE job_id IS NOT NULL AND exa_preview_index IS NOT NULL"
        ),
    ]


def _pg_rename_directory_entries_to_exa_raw_entries() -> str:
    """
    Rename pre-create_all: libera el nombre 'directory*' para el nuevo concepto.
    Si existe la tabla vieja y NO existe la nueva, se renombra. Idempotente.
    """
    return """
    DO $$
    BEGIN
      IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'directory_entries')
         AND NOT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'exa_raw_entries') THEN
        ALTER TABLE directory_entries RENAME TO exa_raw_entries;
      END IF;
    END $$;
    """


def _pg_apply_directories_migrations() -> list[str]:
    """
    Migración embebida para sql/004_directories.sql.
    Añade columnas en search_jobs y opportunities, y migra Opps legacy al directorio 'Sin clasificar'.
    Las tablas `directories` y `directory_steps` las crea SQLModel.metadata.create_all.
    """
    return [
        # search_jobs.directory_id
        "ALTER TABLE search_jobs ADD COLUMN IF NOT EXISTS directory_id UUID REFERENCES directories (id)",
        "CREATE INDEX IF NOT EXISTS ix_search_jobs_directory_id ON search_jobs (directory_id)",
        # opportunities — nuevos campos
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS directory_id UUID REFERENCES directories (id)",
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS current_step_id UUID REFERENCES directory_steps (id)",
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS terminated_at TIMESTAMPTZ",
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS terminated_outcome VARCHAR(32)",
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS terminated_note VARCHAR(500)",
        "CREATE INDEX IF NOT EXISTS ix_opportunities_directory_id ON opportunities (directory_id)",
        "CREATE INDEX IF NOT EXISTS ix_opportunities_current_step_id ON opportunities (current_step_id)",
    ]


# Mapa legacy stage → posición 0-indexed en el directorio "Sin clasificar"
LEGACY_STAGES_ORDER = [
    "first_contact",
    "presentation",
    "response",
    "documents_wait",
    "agreement_sign",
    "medicatel_profile",
]


async def _seed_sin_clasificar_directory(connection) -> None:
    """
    Crea un directorio compartido 'Sin clasificar' con los 6 steps legacy
    y migra todas las Opps existentes (sin directorio) a él.
    Idempotente: si el directorio ya existe, no hace nada.
    """
    existing = await connection.execute(
        text("SELECT id FROM directories WHERE name = 'Sin clasificar' LIMIT 1")
    )
    row = existing.fetchone()
    if row is not None:
        directory_id = row[0]
    else:
        new_dir = await connection.execute(
            text(
                """
                INSERT INTO directories (id, name, description, created_at, updated_at)
                VALUES (gen_random_uuid(), 'Sin clasificar',
                        'Directorio creado automáticamente para opportunities previas al sistema de directorios.',
                        NOW(), NOW())
                RETURNING id
                """
            )
        )
        directory_id = new_dir.fetchone()[0]

    # Crear steps si no existen (idempotente por nombre + directory_id).
    # CAST explícito: asyncpg no puede deducir el tipo de :name cuando aparece
    # solo en SELECT y en WHERE sin ancla de columna. Forzamos VARCHAR para evitar
    # AmbiguousParameterError (text vs character varying).
    for order, stage in enumerate(LEGACY_STAGES_ORDER):
        is_terminal = stage == "medicatel_profile"
        is_won = stage == "medicatel_profile"
        await connection.execute(
            text(
                """
                INSERT INTO directory_steps (id, directory_id, name, display_order, is_terminal, is_won, created_at)
                SELECT gen_random_uuid(), :dir_id, CAST(:name AS VARCHAR(120)), :ord, :term, :won, NOW()
                WHERE NOT EXISTS (
                  SELECT 1 FROM directory_steps
                  WHERE directory_id = :dir_id AND name = CAST(:name AS VARCHAR(120))
                )
                """
            ),
            {"dir_id": directory_id, "name": stage, "ord": order, "term": is_terminal, "won": is_won},
        )

    # Asignar Opps huérfanas a este directorio + mapear su stage legacy a un step.
    steps_map_result = await connection.execute(
        text(
            "SELECT name, id FROM directory_steps WHERE directory_id = :dir_id"
        ),
        {"dir_id": directory_id},
    )
    step_by_name = {row[0]: row[1] for row in steps_map_result.fetchall()}
    for stage_name, step_id in step_by_name.items():
        await connection.execute(
            text(
                """
                UPDATE opportunities
                SET directory_id = :dir_id,
                    current_step_id = :step_id
                WHERE directory_id IS NULL AND stage = :stage
                """
            ),
            {"dir_id": directory_id, "step_id": step_id, "stage": stage_name},
        )
    # Opps con stage desconocido → al primer step.
    first_step_id = step_by_name.get(LEGACY_STAGES_ORDER[0])
    if first_step_id is not None:
        await connection.execute(
            text(
                """
                UPDATE opportunities
                SET directory_id = :dir_id,
                    current_step_id = :step_id
                WHERE directory_id IS NULL
                """
            ),
            {"dir_id": directory_id, "step_id": first_step_id},
        )


async def init_db() -> None:
    import mle.db.models as _mle_db_models  # noqa: F401 — registrar modelos en SQLModel.metadata

    # Fase 1: rename pre-create_all (solo postgres), para no crear tabla vacía nueva.
    async with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            await connection.execute(text(_pg_rename_directory_entries_to_exa_raw_entries()))

    # Fase 2: create_all para tablas nuevas (directories, directory_steps, exa_raw_entries si no existe).
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
        for stmt in _pg_apply_users_and_owner_migrations():
            await connection.execute(text(stmt))
        for stmt in _pg_apply_lead_contact_fields_migrations():
            await connection.execute(text(stmt))
        for stmt in _pg_apply_directories_migrations():
            await connection.execute(text(stmt))
        await _seed_sin_clasificar_directory(connection)
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
