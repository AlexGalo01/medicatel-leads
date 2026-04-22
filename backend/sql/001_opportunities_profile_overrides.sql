-- Añade columna para overrides del CV en ficha de oportunidad (About, ubicación, experiencias).
-- Aplicar una vez en PostgreSQL si la tabla opportunities ya existía antes de este cambio.
-- create_all de SQLModel no altera tablas existentes.

ALTER TABLE opportunities
ADD COLUMN IF NOT EXISTS profile_overrides JSONB NOT NULL DEFAULT '{}'::jsonb;
