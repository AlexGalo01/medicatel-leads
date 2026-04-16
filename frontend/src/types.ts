export type SearchFocus = "general" | "linkedin" | "instagram";

export type LeadsContactFilter =
  | "all"
  | "linkedin"
  | "whatsapp"
  | "email"
  | "linkedin_and_whatsapp"
  | "has_any";

export interface SearchJobCreateRequest {
  query: string;
  contact_channels: string[];
  notes?: string;
  search_focus?: SearchFocus;
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
  quality_metrics?: {
    contact_coverage: number;
    missing_contact_count: number;
    retry_used: boolean;
    discarded_leads_count: number;
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

export interface LeadSourceCitation {
  url: string;
  title: string;
  confidence?: string;
}

export interface LeadDetailResponse extends LeadItem {
  country: string;
  score_reasoning: string | null;
  validation_status: string;
  source_citations: LeadSourceCitation[];
  crm_stage: string;
  crm_notes: string | null;
  activity_timeline: Array<Record<string, string>>;
  created_at: string;
  updated_at: string;
  enrichment_status?: string | null;
  enrichment_message?: string | null;
}

export interface LeadCrmUpdateRequest {
  crm_stage?: string;
  crm_notes?: string;
  activity_note?: string;
}

export interface LeadsExportFilters {
  min_score?: number;
  q?: string;
  contact_filter?: string;
}

export interface LeadsExportResponse {
  download_path: string;
  generated_at: string;
}
