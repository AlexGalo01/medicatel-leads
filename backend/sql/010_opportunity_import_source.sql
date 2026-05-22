-- Add import_source column to opportunities to track origin
-- Values: 'search', 'url_scrape', 'excel', 'manual'
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS import_source VARCHAR(32) NULL;

-- Backfill existing rows based on available foreign keys
UPDATE opportunities SET import_source = 'search' WHERE job_id IS NOT NULL AND import_source IS NULL;
UPDATE opportunities SET import_source = 'url_scrape' WHERE scrape_job_id IS NOT NULL AND import_source IS NULL;
-- Remaining rows (no job_id, no scrape_job_id) stay NULL — treated as 'manual' in the app
