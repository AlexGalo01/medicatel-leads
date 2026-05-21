-- Create scraping_sites table for global scraping source management
CREATE TABLE scraping_sites (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url         VARCHAR(2000) NOT NULL,
  title       VARCHAR(500) NOT NULL DEFAULT '',
  notes       TEXT,
  scrape_prompt TEXT,
  last_scrape_job_id UUID REFERENCES url_scrape_jobs(id) ON DELETE SET NULL,
  created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_scraping_sites_last_job ON scraping_sites(last_scrape_job_id);
CREATE INDEX idx_scraping_sites_created_by ON scraping_sites(created_by_user_id);
CREATE INDEX idx_scraping_sites_created_at ON scraping_sites(created_at DESC);
