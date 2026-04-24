-- Directorios compartidos con steps custom (reemplazan el enum stage fijo en opportunities).
-- Renombra la tabla anterior directory_entries → exa_raw_entries para liberar el nombre.

-- 1. Rename (solo si aplica).
DO $$
BEGIN
  IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'directory_entries')
     AND NOT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'exa_raw_entries') THEN
    ALTER TABLE directory_entries RENAME TO exa_raw_entries;
  END IF;
END $$;

-- 2. Directorios compartidos del equipo.
CREATE TABLE IF NOT EXISTS directories (
  id UUID PRIMARY KEY,
  name VARCHAR(160) NOT NULL,
  description VARCHAR(1000),
  created_by_user_id UUID REFERENCES users (id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_directories_name ON directories (name);

-- 3. Steps dentro de cada directorio (flow custom).
CREATE TABLE IF NOT EXISTS directory_steps (
  id UUID PRIMARY KEY,
  directory_id UUID NOT NULL REFERENCES directories (id),
  name VARCHAR(120) NOT NULL,
  display_order INTEGER NOT NULL DEFAULT 0,
  is_terminal BOOLEAN NOT NULL DEFAULT FALSE,
  is_won BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_directory_steps_directory_id ON directory_steps (directory_id);
CREATE INDEX IF NOT EXISTS ix_directory_steps_display_order ON directory_steps (display_order);

-- 4. search_jobs ancla búsqueda a un directorio.
ALTER TABLE search_jobs ADD COLUMN IF NOT EXISTS directory_id UUID REFERENCES directories (id);
CREATE INDEX IF NOT EXISTS ix_search_jobs_directory_id ON search_jobs (directory_id);

-- 5. opportunities: FK a directorio + step + tracking de terminación.
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS directory_id UUID REFERENCES directories (id);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS current_step_id UUID REFERENCES directory_steps (id);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS terminated_at TIMESTAMPTZ;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS terminated_outcome VARCHAR(32);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS terminated_note VARCHAR(500);
CREATE INDEX IF NOT EXISTS ix_opportunities_directory_id ON opportunities (directory_id);
CREATE INDEX IF NOT EXISTS ix_opportunities_current_step_id ON opportunities (current_step_id);

-- 6. Seeder del directorio 'Sin clasificar' con los 6 steps legacy (se ejecuta también embebido en init_db).
