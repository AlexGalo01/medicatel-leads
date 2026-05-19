export type UserRole = "admin" | "user";

export type Permission = "use_search" | "manage_opportunities";

export interface UserPublic {
  user_id: string;
  email: string;
  display_name: string;
  role: UserRole;
  permissions: Permission[];
  is_active: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserPublic;
}

export interface RegisterRequest {
  email: string;
  password: string;
  display_name: string;
}

export interface AdminCreateUserRequest {
  email: string;
  password: string;
  display_name: string;
  role: UserRole;
  permissions: Permission[];
}

export interface AdminUpdateUserRequest {
  email?: string;
  display_name?: string;
  role?: UserRole;
  is_active?: boolean;
  permissions?: Permission[];
}

export interface AdminUsersListResponse {
  items: UserPublic[];
}

export interface AdminUserJobsResponse {
  items: SearchJobListItem[];
  total: number;
  user: UserPublic;
}

export type SearchFocus = "general" | "linkedin" | "instagram";

export type ExaCategoryChoice = "people" | "company" | "local_business";

export type LeadsContactFilter =
  | "all"
  | "linkedin"
  | "whatsapp"
  | "email"
  | "linkedin_and_whatsapp"
  | "has_any";

export interface SearchJobCreateRequest {
  query: string;
  directory_id: string;
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
  requires_clarification?: boolean;
}

export interface SearchJobListItem {
  job_id: string;
  query: string;
  status: string;
  created_at: string;
  exa_category?: string | null;
  directory_id?: string | null;
  directory_name?: string | null;
  error_message?: string | null;
}

export interface SearchJobsListResponse {
  items: SearchJobListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
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
  organization?: string | null;
  email?: string | null;
  whatsapp?: string | null;
  phone?: string | null;
  address?: string | null;
  schedule_text?: string | null;
  linkedin_url?: string | null;
  description?: string | null;
  enrichment_status?: string | null;
  enrichment_message?: string | null;
  enriched_sources?: Record<string, unknown> | null;
  saved_source_urls?: string[] | null;
  // Local business fields (Google Places)
  source_type?: string | null;
  website?: string | null;
  hours?: string | null;
  rating?: number | null;
  review_count?: number | null;
  place_id?: string | null;
  lat?: number | null;
  lng?: number | null;
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
  company?: string | null;
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

export type OpportunityTerminatedOutcome = "won" | "lost" | "no_response" | "no_valida";

export interface OpportunityResponse {
  opportunity_id: string;
  job_id: string | null;
  scrape_job_id: string | null;
  exa_preview_index: number | null;
  directory_id: string | null;
  current_step_id: string | null;
  title: string;
  source_url: string;
  snippet: string | null;
  specialty: string;
  city: string;
  stage: OpportunityStageKey;
  response_outcome: OpportunityResponseOutcome | null;
  terminated_at: string | null;
  terminated_outcome: OpportunityTerminatedOutcome | null;
  terminated_note: string | null;
  contacts: OpportunityContact[];
  activity_timeline: OpportunityActivityEntry[];
  profile_overrides?: OpportunityProfileOverrides;
  contact_type: "employee" | "company" | null;
  created_at: string;
  updated_at: string;
  created: boolean;
  owner: OpportunityOwnerSnippet | null;
}

export interface OpportunityListItem {
  opportunity_id: string;
  job_id: string | null;
  scrape_job_id: string | null;
  scrape_target_url: string | null;
  exa_preview_index: number | null;
  directory_id: string | null;
  current_step_id: string | null;
  title: string;
  city: string;
  stage: OpportunityStageKey;
  response_outcome: OpportunityResponseOutcome | null;
  terminated_at: string | null;
  terminated_outcome: OpportunityTerminatedOutcome | null;
  updated_at: string;
  owner: OpportunityOwnerSnippet | null;
}

export interface DirectoryStep {
  id: string;
  name: string;
  display_order: number;
  is_terminal: boolean;
  is_won: boolean;
  created_at: string;
}

export interface Directory {
  id: string;
  name: string;
  description: string | null;
  created_by_user_id: string | null;
  steps: DirectoryStep[];
  item_count: number;
  created_at: string;
  updated_at: string;
}

export interface DirectoryListResponse {
  items: Directory[];
}

export interface DirectoryStepCreate {
  name: string;
  is_terminal: boolean;
  is_won: boolean;
}

export interface DirectoryCreateRequest {
  name: string;
  description?: string | null;
  steps: DirectoryStepCreate[];
}

export interface DirectoryUpdateRequest {
  name?: string;
  description?: string | null;
}

export interface DirectoryStepUpdate {
  name?: string;
  is_terminal?: boolean;
  is_won?: boolean;
  display_order?: number;
}

export interface OpportunityListResponse {
  items: OpportunityListItem[];
}

export interface OpportunityCreateFromPreviewRequest {
  job_id: string;
  exa_preview_index: number;
  step_id?: string;
  contact_overrides?: Record<string, string>;
}

export interface OpportunityCreateManualRequest {
  title: string;
  specialty?: string;
  city?: string;
  source_url?: string;
  snippet?: string | null;
  directory_id?: string | null;
  step_id?: string | null;
  contacts?: Array<{
    id?: string;
    kind: string;
    value: string;
    note?: string | null;
    role?: string | null;
    is_primary?: boolean;
  }>;
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
  created_at?: string | null;
  updated_at: string;
  pipeline_mode?: string | null;
  exa_results_preview?: ExaResultPreviewItem[];
  notes?: string | null;
  exa_category?: string | null;
  exa_criteria?: string | null;
  query_text?: string | null;
  error_message?: string | null;
  awaiting_clarification?: boolean;
  clarifying_question?: string | null;
  suggested_source_urls?: Array<{ url: string; title: string }>;
  lpa_preview?: ExaResultPreviewItem[];
  warnings?: string[];
  filter_stats?: {
    relevance_filter_kept?: number;
    relevance_filter_dropped?: number;
    relevance_filter_heuristic_drops?: number;
    relevance_filter_mode?: string;
    relevance_filter_error?: string;
    relevance_filter_discarded_sample?: Array<{ index: number; url: string; reason_es: string }>;
  };
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
  phone: string | null;
  address: string | null;
  schedule_text: string | null;
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
  enriched_sources?: Record<string, unknown> | null;
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

// ---- URL Scraper ----

export interface UrlScrapeJobCreateRequest {
  target_url: string;
  user_prompt: string;
  directory_id?: string | null;
}

export interface UrlScrapeResultPreviewItem {
  index: number;
  title: string;
  url: string;
  snippet: string | null;
  city: string;
  phones: string[];
  emails: string[];
}

export interface UrlScrapeJobStatusResponse {
  job_id: string;
  status: string;
  progress: number;
  target_url: string;
  directory_id: string | null;
  entries_count: number;
  scrape_results_preview: UrlScrapeResultPreviewItem[];
  error_message: string | null;
  created_at: string;
  updated_at: string;
  pages_scraped?: number;
  pages_total?: number;
}

export interface UrlScrapeJobListItem {
  job_id: string;
  target_url: string;
  status: string;
  entries_count: number;
  created_at: string;
}

export interface UrlScrapeJobsListResponse {
  items: UrlScrapeJobListItem[];
}

// ---- Directory Sources (referencias guardadas) ----

export type DirectorySourceStatus = "pending" | "scraping" | "scraped" | "discarded";

export interface DirectorySourceCreateRequest {
  url: string;
  title?: string;
  notes?: string | null;
  source_search_job_id?: string | null;
}

export interface DirectorySourceUpdateRequest {
  title?: string;
  notes?: string | null;
  status?: DirectorySourceStatus;
}

export interface DirectorySourceItem {
  source_id: string;
  directory_id: string;
  url: string;
  title: string;
  notes: string | null;
  status: DirectorySourceStatus;
  scrape_job_id: string | null;
  source_search_job_id: string | null;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface DirectorySourcesListResponse {
  items: DirectorySourceItem[];
}
