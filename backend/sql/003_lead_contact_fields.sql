-- Columnas de contacto extendido para leads (auto-enrich desde pipeline de búsqueda).
-- Alimentado por auto_enrich_node (Exa /contents + OpenCLI Google/Maps/Doctoralia).

ALTER TABLE leads ADD COLUMN IF NOT EXISTS phone VARCHAR(40);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS address VARCHAR(500);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS schedule_text VARCHAR(500);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS enriched_sources JSONB NOT NULL DEFAULT '{}'::jsonb;
