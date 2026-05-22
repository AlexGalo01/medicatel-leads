-- Add soft delete columns to users, directory_steps, directory_sources
-- Pattern: deleted_by (FK users), deleted_at (TIMESTAMPTZ), partial index on deleted_at IS NULL

-- users
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS deleted_by UUID REFERENCES users(id),
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS ix_users_deleted_at ON users (deleted_at) WHERE deleted_at IS NULL;

-- directory_steps
ALTER TABLE directory_steps
  ADD COLUMN IF NOT EXISTS deleted_by UUID REFERENCES users(id),
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS ix_directory_steps_deleted_at ON directory_steps (deleted_at) WHERE deleted_at IS NULL;

-- directory_sources
ALTER TABLE directory_sources
  ADD COLUMN IF NOT EXISTS deleted_by UUID REFERENCES users(id),
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS ix_directory_sources_deleted_at ON directory_sources (deleted_at) WHERE deleted_at IS NULL;
