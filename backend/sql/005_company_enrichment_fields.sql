-- Campos de enriquecimiento para búsquedas de negocios (Google Maps + redes sociales).
-- Alimentado por auto_enrich_node (OpenCLI google-maps, facebook, instagram).

ALTER TABLE leads ADD COLUMN IF NOT EXISTS website VARCHAR(500);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS facebook_url VARCHAR(500);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS instagram_url VARCHAR(500);
