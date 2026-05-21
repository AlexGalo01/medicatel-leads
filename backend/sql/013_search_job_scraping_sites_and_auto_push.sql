-- Add scraping_site_ids to search_jobs and auto_push to url_scrape_jobs
ALTER TABLE search_jobs
ADD COLUMN scraping_site_ids JSONB NOT NULL DEFAULT '[]';

ALTER TABLE url_scrape_jobs
ADD COLUMN auto_push BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX idx_search_jobs_scraping_site_ids ON search_jobs USING GIN (scraping_site_ids);
