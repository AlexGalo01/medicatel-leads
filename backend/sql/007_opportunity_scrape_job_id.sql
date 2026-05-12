-- Agrega referencia al job de URL scraping que originó cada oportunidad

ALTER TABLE opportunities
    ADD COLUMN IF NOT EXISTS scrape_job_id UUID REFERENCES url_scrape_jobs(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_opportunities_scrape_job ON opportunities(scrape_job_id);
