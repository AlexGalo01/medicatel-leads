-- Soft-delete: directories y opportunities se marcan como eliminados en lugar de borrarlos físicamente.
ALTER TABLE directories
  ADD COLUMN IF NOT EXISTS deleted_by UUID REFERENCES users(id),
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

ALTER TABLE opportunities
  ADD COLUMN IF NOT EXISTS deleted_by UUID REFERENCES users(id),
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_directories_deleted_at ON directories (deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_opportunities_deleted_at ON opportunities (deleted_at) WHERE deleted_at IS NULL;
