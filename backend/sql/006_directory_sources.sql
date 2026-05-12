-- Directory sources: URLs guardadas como referencia o para scrapear dentro de un directorio

CREATE TABLE IF NOT EXISTS directory_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    directory_id UUID NOT NULL REFERENCES directories(id) ON DELETE CASCADE,
    url VARCHAR(2000) NOT NULL,
    title VARCHAR(500) NOT NULL DEFAULT '',
    notes TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    scrape_job_id UUID REFERENCES url_scrape_jobs(id) ON DELETE SET NULL,
    source_search_job_id UUID REFERENCES search_jobs(id) ON DELETE SET NULL,
    created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_directory_sources_directory ON directory_sources(directory_id);
CREATE INDEX IF NOT EXISTS idx_directory_sources_status ON directory_sources(status);
CREATE INDEX IF NOT EXISTS idx_directory_sources_scrape_job ON directory_sources(scrape_job_id);
