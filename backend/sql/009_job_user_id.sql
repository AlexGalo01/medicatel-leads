-- Migration 009: add user_id to search_jobs
-- Tracks which user created each search job.

ALTER TABLE search_jobs
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_search_jobs_user_id ON search_jobs(user_id);
