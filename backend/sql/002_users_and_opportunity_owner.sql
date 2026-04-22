-- Usuarios CRM y responsable de oportunidad (PostgreSQL).
-- También se aplica al iniciar la app vía init_db.

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  display_name VARCHAR(160) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'user',
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);
CREATE INDEX IF NOT EXISTS ix_users_is_active ON users (is_active);

ALTER TABLE opportunities
  ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users (id);
CREATE INDEX IF NOT EXISTS ix_opportunities_owner_user_id ON opportunities (owner_user_id);
