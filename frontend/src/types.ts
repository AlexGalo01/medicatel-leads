export type UserRole = "admin" | "user";

export interface UserPublic {
  user_id: string;
  email: string;
  display_name: string;
  role: UserRole;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserPublic;
}

export interface AdminUsersListResponse {
  items: UserPublic[];
}

export type SearchFocus = "general" | "linkedin" | "instagram";

export type ExaCategoryChoice = "people" | "company";

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
  exa_category?: ExaCategoryChoice;
  exa_criteria?: string;
}

export interface SearchJobCreateResponse {
  job_id: string;
  status: string;
  created_at: string;
  clarifying_question?: string | null;
}

export interface SearchJobListItem {
  job_id: string;
  query: string;
  status: string;
  created_at: string;
  exa_category?: string | null;
}

export interface SearchJobsListResponse {
  items: SearchJobListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ProfileInterpretItem {
  source_text: string;
  normalized_name?: string | null;
  normalized_company?: string | null;
  normalized_specialty?: string | null;
}

export interface ProfileInterpretResponse {
  items: ProfileInterpretItem[];
}

export interface ProfileSummaryRequest {
  title: string;
  specialty?: string | null;
  city?: string | null;
  snippet?: string | null;
}

export interface ProfileSummaryResponse {
  professional_summary?: string | null;
  about?: string | null;
  experiences?: Array<{
    role: string;
    organization?: string | null;
    period?: string | null;
  }>;
  company?: string | null;
  location?: string | null;
  confidence: "high" | "medium" | "low";
  notes?: string | null;
}

export interface ExaResultPreviewItem {
  index: number;
  title: string;
  url: string;
  snippet: string | null;
  specialty?: string | null;
  city?: string | null;
}

export interface ExaMoreResultsResponse {
  ok: boolean;
  added_count: number;
  total_count: number;
  preview_count: number;
  query_used?: string | null;
  error?: string | null;
}

export type OpportunityStageKey =
  | "first_contact"
  | "presentation"
  | "response"
  | "documents_wait"
  | "agreement_sign"
  | "medicatel_profile";

export type OpportunityResponseOutcome = "pending" | "positive" | "negative";

export type OpportunityContactKind = "email" | "phone" | "whatsapp" | "linkedin" | "other";

export interface OpportunityContact {
  id: string;
  kind: OpportunityContactKind;
  value: string;
  note?: string | null;
  role?: string | null;
  is_primary: boolean;
}

export interface OpportunityActivityEntry {
  at: string;
  stage: string;
  author: string;
  text: string;
}

/** Overrides guardados en oportunidad (About, ubicación, experiencia); ausente = usar resumen generado. */
export interface OpportunityProfileOverrides {
  about?: string | null;
  location?: string | null;
  experiences?: Array<{
    role: string;
    organization?: string | null;
    period?: string | null;
  }> | null;
}

export interface OpportunityOwnerSnippet {
  user_id: string;
  display_name: string;
  email: string;
}

export interface OpportunityResponse {
  opportunity_id: string;
  job_id: string;
  exa_preview_index: number;
  title: string;
  source_url: string;
  snippet: string | null;
  specialty: string;
  city: string;
  stage: OpportunityStageKey;
  response_outcome: OpportunityResponseOutcome | null;
  contacts: OpportunityContact[];
  activity_timeline: OpportunityActivityEntry[];
  profile_overrides?: OpportunityProfileOverrides;
  created_at: string;
  updated_at: string;
  created: boolean;
  owner: OpportunityOwnerSnippet | null;
}

export interface OpportunityListItem {
  opportunity_id: string;
  job_id: string;
  exa_preview_index: number;
  title: string;
  city: string;
  stage: OpportunityStageKey;
  response_outcome: OpportunityResponseOutcome | null;
  updated_at: string;
  owner: OpportunityOwnerSnippet | null;
}

export interface OpportunityListResponse {
  items: OpportunityListItem[];
}

export interface OpportunityCreateFromPreviewRequest {
  job_id: string;
  exa_preview_index: number;
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
  pipeline_mode?: string | null;
  exa_results_preview?: ExaResultPreviewItem[];
  notes?: string | null;
  exa_category?: string | null;
  exa_criteria?: string | null;
  query_text?: string | null;
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

export interface DirectoryEntryItem {
  entry_id: string;
  display_title: string;
  primary_url: string;
  snippet: string | null;
  entity_type: string;
  city: string;
  country: string;
  created_at: string;
}

export interface DirectoryEntriesListResponse {
  items: DirectoryEntryItem[];
  page: number;
  page_size: number;
  total: number;
}
