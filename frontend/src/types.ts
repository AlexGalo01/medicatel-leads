export interface SearchJobCreateRequest {
  specialty: string;
  country: string;
  city: string;
  contact_channels: string[];
  notes?: string;
}

export interface SearchJobCreateResponse {
  job_id: string;
  status: string;
  created_at: string;
}

export interface SearchJobStatusResponse {
  job_id: string;
  status: string;
  progress: number;
  current_stage: string;
  metrics: {
    sources_visited: number;
    leads_extracted: number;
    leads_scored: number;
  };
  updated_at: string;
}

export interface LeadItem {
  lead_id: string;
  full_name: string;
  specialty: string;
  city: string;
  score: number | null;
  email: string | null;
  whatsapp: string | null;
  linkedin_url: string | null;
  primary_source_url: string | null;
}

export interface LeadsListResponse {
  items: LeadItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface LeadDetailResponse extends LeadItem {
  country: string;
  score_reasoning: string | null;
  validation_status: string;
  source_citations: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
}

export interface LeadsExportResponse {
  download_path: string;
  generated_at: string;
}

