from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from mle.core.config import get_settings


def _normalize_database_url(database_url: str) -> str:
    from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgresql+asyncpg://"):
        parsed = urlparse(database_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        sslmode = params.pop("sslmode", [None])[0]
        if sslmode and "ssl" not in params:
            params["ssl"] = ["require"] if sslmode == "require" else ["prefer"]
        new_query = urlencode({k: v[0] for k, v in params.items()})
        database_url = urlunparse(parsed._replace(query=new_query))
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


def _pg_apply_company_enrichment_fields() -> list[str]:
    """
    Migración embebida para sql/005_company_enrichment_fields.sql.
    Añade website, facebook_url, instagram_url al Lead para búsquedas de negocios.
    """
    return [
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS website VARCHAR(500)",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS facebook_url VARCHAR(500)",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS instagram_url VARCHAR(500)",
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


def _pg_apply_url_scrape_jobs_migration() -> list[str]:
    """
    Migración embebida para url_scrape_jobs.
    La tabla la crea SQLModel.metadata.create_all; aquí solo creamos índices y fijamos FKs.
    """
    return [
        "CREATE INDEX IF NOT EXISTS ix_url_scrape_jobs_status ON url_scrape_jobs (status)",
        "CREATE INDEX IF NOT EXISTS ix_url_scrape_jobs_directory_id ON url_scrape_jobs (directory_id)",
        "CREATE INDEX IF NOT EXISTS ix_url_scrape_jobs_created_at ON url_scrape_jobs (created_at DESC)",
        "ALTER TABLE url_scrape_jobs DROP CONSTRAINT IF EXISTS url_scrape_jobs_directory_id_fkey",
        "ALTER TABLE url_scrape_jobs ADD CONSTRAINT url_scrape_jobs_directory_id_fkey "
        "FOREIGN KEY (directory_id) REFERENCES directories(id) ON DELETE CASCADE",
    ]


def _pg_apply_directory_sources_migration() -> list[str]:
    """
    Migración embebida para sql/006_directory_sources.sql.
    La tabla la crea SQLModel.metadata.create_all; aquí índices y FKs.
    """
    return [
        "CREATE INDEX IF NOT EXISTS idx_directory_sources_directory ON directory_sources (directory_id)",
        "CREATE INDEX IF NOT EXISTS idx_directory_sources_status ON directory_sources (status)",
        "CREATE INDEX IF NOT EXISTS idx_directory_sources_scrape_job ON directory_sources (scrape_job_id)",
        "ALTER TABLE directory_sources DROP CONSTRAINT IF EXISTS directory_sources_directory_id_fkey",
        "ALTER TABLE directory_sources ADD CONSTRAINT directory_sources_directory_id_fkey "
        "FOREIGN KEY (directory_id) REFERENCES directories(id) ON DELETE CASCADE",
        "ALTER TABLE directory_sources DROP CONSTRAINT IF EXISTS directory_sources_scrape_job_id_fkey",
        "ALTER TABLE directory_sources ADD CONSTRAINT directory_sources_scrape_job_id_fkey "
        "FOREIGN KEY (scrape_job_id) REFERENCES url_scrape_jobs(id) ON DELETE SET NULL",
        "ALTER TABLE directory_sources DROP CONSTRAINT IF EXISTS directory_sources_source_search_job_id_fkey",
        "ALTER TABLE directory_sources ADD CONSTRAINT directory_sources_source_search_job_id_fkey "
        "FOREIGN KEY (source_search_job_id) REFERENCES search_jobs(id) ON DELETE SET NULL",
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
        for stmt in _pg_apply_company_enrichment_fields():
            await connection.execute(text(stmt))
        for stmt in _pg_apply_directories_migrations():
            await connection.execute(text(stmt))
        await connection.execute(
            text("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS contact_type VARCHAR(32)")
        )
        for stmt in _pg_apply_url_scrape_jobs_migration():
            await connection.execute(text(stmt))
        for stmt in _pg_apply_directory_sources_migration():
            await connection.execute(text(stmt))
        await connection.execute(
            text(
                "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS "
                "scrape_job_id UUID REFERENCES url_scrape_jobs(id) ON DELETE SET NULL"
            )
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_opportunities_scrape_job ON opportunities(scrape_job_id)"
            )
        )

        # 013: auto_push en url_scrape_jobs + scraping_site_ids en search_jobs
        await connection.execute(
            text(
                "ALTER TABLE url_scrape_jobs ADD COLUMN IF NOT EXISTS "
                "auto_push BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        await connection.execute(
            text(
                "ALTER TABLE search_jobs ADD COLUMN IF NOT EXISTS "
                "scraping_site_ids JSONB NOT NULL DEFAULT '[]'::jsonb"
            )
        )
        # scraping_sites FKs e índices (tabla creada por create_all)
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_scraping_sites_last_job "
                "ON scraping_sites(last_scrape_job_id)"
            )
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_scraping_sites_created_by "
                "ON scraping_sites(created_by_user_id)"
            )
        )

        # ALTER TABLE scraping_sites — ADD enrich_prompt column
        await connection.execute(
            text(
                "ALTER TABLE scraping_sites ADD COLUMN IF NOT EXISTS "
                "enrich_prompt TEXT"
            )
        )

        # ALTER TABLE url_scrape_jobs — ADD scraping_site_id column
        await connection.execute(
            text(
                "ALTER TABLE url_scrape_jobs ADD COLUMN IF NOT EXISTS "
                "scraping_site_id UUID REFERENCES scraping_sites(id) ON DELETE SET NULL"
            )
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_url_scrape_jobs_scraping_site "
                "ON url_scrape_jobs(scraping_site_id)"
            )
        )

        # Seed: doctoresdehonduras.com as a built-in scraping site.
        # Insert only if no row with this URL exists yet (handles deleted + recreated cases).
        _ddh_scrape_prompt = (
            "Extrae cada médico que aparece en esta página. "
            "MUY IMPORTANTE: Usa la sección '=== LINKS Y TELÉFONOS DEL DOM ===' que contiene los datos estructurados. "
            "Cada línea LINK tiene: href (URL del perfil), text (nombre + especialidad), phone (teléfono directo). "
            "Para cada médico extrae: "
            "1. primary_url: toma el href de la línea LINK (ej: /Doctores/Detalles/NNN) "
            "2. display_title: nombre completo del médico del campo text "
            "3. city: si aparece en el text, extrae ubicación/ciudad; sino, deja en blanco "
            "4. phones: extrae del campo phone de la línea LINK (ej: [\"2242-6565\"]); si no hay, lista vacía "
            "5. snippet: especialidad del médico del text "
            "Devuelve JSON con entries: [{\"primary_url\": \"/Doctores/Detalles/774\", \"display_title\": \"Dra. Kendy Portillo\", "
            "\"snippet\": \"Neurología\", \"phones\": [\"2242-6565\"], \"emails\": []}]"
        )
        _ddh_enrich_prompt = (
            "Esta es la página de perfil de un médico hondureño. "
            "Busca la sección 'Información de Contacto' que aparece debajo del perfil. "
            "Extrae SOLO email(s) y WhatsApp (los teléfonos ya fueron capturados del listado). "
            "Mira patrones como: 'Email:', 'Correo:', 'WhatsApp:', 'Tel:', etc. "
            "Devuelve JSON: {\"entries\": [{\"phones\": [], \"emails\": [\"...@...\"], \"whatsapp\": [\"...\"]}]} "
            "Si no hay email ni WhatsApp, devuelve listas vacías."
        )
        await connection.execute(
            text("""
                INSERT INTO scraping_sites (id, url, title, scrape_prompt, enrich_prompt, created_at, updated_at)
                SELECT
                    '00000000-0000-0000-0000-000000000001',
                    'https://www.doctoresdehonduras.com',
                    'Doctores de Honduras',
                    :scrape_prompt,
                    :enrich_prompt,
                    now(), now()
                WHERE NOT EXISTS (
                    SELECT 1 FROM scraping_sites WHERE url LIKE '%doctoresdehonduras.com%'
                )
            """), {"scrape_prompt": _ddh_scrape_prompt, "enrich_prompt": _ddh_enrich_prompt}
        )
        # If a row already exists but has null prompts (e.g. manually created), fill them in.
        await connection.execute(
            text("""
                UPDATE scraping_sites
                SET
                    scrape_prompt = COALESCE(scrape_prompt, :scrape_prompt),
                    enrich_prompt = COALESCE(enrich_prompt, :enrich_prompt),
                    updated_at    = now()
                WHERE url LIKE '%doctoresdehonduras.com%'
                  AND (scrape_prompt IS NULL OR enrich_prompt IS NULL)
            """), {"scrape_prompt": _ddh_scrape_prompt, "enrich_prompt": _ddh_enrich_prompt}
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
