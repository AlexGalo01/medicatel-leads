import type {
  AdminUsersListResponse,
  DirectoryEntriesListResponse,
  ExaMoreResultsResponse,
  LeadCrmUpdateRequest,
  LeadDetailResponse,
  LeadsExportFilters,
  LeadsExportResponse,
  LeadsListResponse,
  LoginResponse,
  OpportunityCreateFromPreviewRequest,
  OpportunityListResponse,
  OpportunityProfileOverrides,
  OpportunityResponse,
  ProfileInterpretResponse,
  ProfileSummaryRequest,
  ProfileSummaryResponse,
  SearchJobCreateRequest,
  SearchJobCreateResponse,
  SearchJobsListResponse,
  SearchJobStatusResponse,
  UserPublic,
} from "./types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const TOKEN_STORAGE_KEY = "mle_access_token";

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setAccessToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_STORAGE_KEY, token);
  else localStorage.removeItem(TOKEN_STORAGE_KEY);
}

function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  const t = getAccessToken();
  if (t) headers.set("Authorization", `Bearer ${t}`);
  return fetch(input, { ...init, headers });
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const bodyText = await response.text();
    throw new Error(`Error API (${response.status}): ${bodyText || "Sin detalle"}`);
  }
  return (await response.json()) as T;
}

export async function createSearchJob(payload: SearchJobCreateRequest): Promise<SearchJobCreateResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/search-jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<SearchJobCreateResponse>(response);
}

export async function getSearchJobStatus(jobId: string): Promise<SearchJobStatusResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/search-jobs/${jobId}`);
  return parseJsonResponse<SearchJobStatusResponse>(response);
}

export async function listSearchJobs(params: { limit?: number; offset?: number; q?: string } = {}): Promise<SearchJobsListResponse> {
  const query = new URLSearchParams();
  if (typeof params.limit === "number") {
    query.set("limit", String(params.limit));
  }
  if (typeof params.offset === "number") {
    query.set("offset", String(params.offset));
  }
  if (params.q?.trim()) {
    query.set("q", params.q.trim());
  }
  const response = await apiFetch(`${apiBaseUrl}/api/v1/search-jobs${query.toString() ? `?${query}` : ""}`);
  return parseJsonResponse<SearchJobsListResponse>(response);
}

export async function loadMoreExaResults(jobId: string, numResults = 40): Promise<ExaMoreResultsResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/search-jobs/${jobId}/exa-more`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ num_results: numResults }),
  });
  return parseJsonResponse<ExaMoreResultsResponse>(response);
}

export async function interpretProfileTexts(texts: string[]): Promise<ProfileInterpretResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/profiles/interpret`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ texts }),
  });
  return parseJsonResponse<ProfileInterpretResponse>(response);
}

export async function summarizeProfile(payload: ProfileSummaryRequest): Promise<ProfileSummaryResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/profiles/summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<ProfileSummaryResponse>(response);
}

export interface ListDirectoryEntriesParams {
  page?: number;
  pageSize?: number;
}

export async function listDirectoryEntries(
  jobId: string,
  params: ListDirectoryEntriesParams = {},
): Promise<DirectoryEntriesListResponse> {
  const queryParams = new URLSearchParams();
  if (typeof params.page === "number") {
    queryParams.set("page", String(params.page));
  }
  if (typeof params.pageSize === "number") {
    queryParams.set("page_size", String(params.pageSize));
  }
  const qs = queryParams.toString();
  const url = `${apiBaseUrl}/api/v1/search-jobs/${jobId}/directory-entries${qs ? `?${qs}` : ""}`;
  const response = await apiFetch(url);
  return parseJsonResponse<DirectoryEntriesListResponse>(response);
}

export interface ListLeadsParams {
  minScore?: number;
  nameQuery?: string;
  contactFilter?: string;
  page?: number;
  pageSize?: number;
}

export async function listLeads(jobId: string, params: ListLeadsParams = {}): Promise<LeadsListResponse> {
  const queryParams = new URLSearchParams({ job_id: jobId });
  if (typeof params.minScore === "number") {
    queryParams.set("min_score", String(params.minScore));
  }
  const trimmedName = params.nameQuery?.trim();
  if (trimmedName) {
    queryParams.set("q", trimmedName);
  }
  const trimmedFilter = params.contactFilter?.trim();
  if (trimmedFilter && trimmedFilter !== "all") {
    queryParams.set("contact_filter", trimmedFilter);
  }
  if (typeof params.page === "number") {
    queryParams.set("page", String(params.page));
  }
  if (typeof params.pageSize === "number") {
    queryParams.set("page_size", String(params.pageSize));
  }
  const response = await apiFetch(`${apiBaseUrl}/api/v1/leads?${queryParams.toString()}`);
  return parseJsonResponse<LeadsListResponse>(response);
}

export async function getLeadDetail(leadId: string): Promise<LeadDetailResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/leads/${leadId}`);
  return parseJsonResponse<LeadDetailResponse>(response);
}

export async function updateLeadCrm(
  leadId: string,
  payload: LeadCrmUpdateRequest,
): Promise<LeadDetailResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/leads/${leadId}/crm`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<LeadDetailResponse>(response);
}

export async function deepEnrichLead(leadId: string): Promise<LeadDetailResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/leads/${leadId}/deep-enrich`, {
    method: "POST",
  });
  return parseJsonResponse<LeadDetailResponse>(response);
}

export async function exportLeads(jobId: string, filters: LeadsExportFilters = {}): Promise<LeadsExportResponse> {
  const payloadFilters: Record<string, string | number> = {};
  if (typeof filters.min_score === "number") {
    payloadFilters.min_score = filters.min_score;
  }
  if (filters.q?.trim()) {
    payloadFilters.q = filters.q.trim();
  }
  if (filters.contact_filter?.trim() && filters.contact_filter.trim() !== "all") {
    payloadFilters.contact_filter = filters.contact_filter.trim();
  }
  const response = await apiFetch(`${apiBaseUrl}/api/v1/leads/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: jobId,
      format: "csv",
      filters: payloadFilters,
    }),
  });
  return parseJsonResponse<LeadsExportResponse>(response);
}

export async function downloadLeadsCsvFile(jobId: string, filters: LeadsExportFilters = {}): Promise<void> {
  const queryParams = new URLSearchParams({ job_id: jobId });
  if (typeof filters.min_score === "number") {
    queryParams.set("min_score", String(filters.min_score));
  }
  if (filters.q?.trim()) {
    queryParams.set("q", filters.q.trim());
  }
  if (filters.contact_filter?.trim() && filters.contact_filter.trim() !== "all") {
    queryParams.set("contact_filter", filters.contact_filter.trim());
  }
  const response = await apiFetch(`${apiBaseUrl}/api/v1/leads/export/file?${queryParams.toString()}`);
  if (!response.ok) {
    const bodyText = await response.text();
    throw new Error(`Error al descargar CSV (${response.status}): ${bodyText || "Sin detalle"}`);
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = `leads_${jobId}.csv`;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

export async function getOpportunityByPreview(
  jobId: string,
  exaPreviewIndex: number,
): Promise<OpportunityResponse | null> {
  const query = new URLSearchParams({
    job_id: jobId,
    exa_preview_index: String(exaPreviewIndex),
  });
  const response = await apiFetch(`${apiBaseUrl}/api/v1/opportunities/by-preview?${query}`);
  if (response.status === 404) {
    return null;
  }
  return parseJsonResponse<OpportunityResponse>(response);
}

export async function createOpportunityFromPreview(
  payload: OpportunityCreateFromPreviewRequest,
): Promise<OpportunityResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/opportunities/from-preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: payload.job_id,
      exa_preview_index: payload.exa_preview_index,
    }),
  });
  return parseJsonResponse<OpportunityResponse>(response);
}

export async function listOpportunities(params: { stage?: string } = {}): Promise<OpportunityListResponse> {
  const query = new URLSearchParams();
  if (params.stage) {
    query.set("stage", params.stage);
  }
  const response = await apiFetch(`${apiBaseUrl}/api/v1/opportunities?${query}`);
  return parseJsonResponse<OpportunityListResponse>(response);
}

export async function getOpportunity(opportunityId: string): Promise<OpportunityResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/opportunities/${opportunityId}`);
  return parseJsonResponse<OpportunityResponse>(response);
}

export async function patchOpportunity(
  opportunityId: string,
  body: {
    stage?: string;
    response_outcome?: string | null;
    note?: string | null;
    profile_cv?: OpportunityProfileOverrides;
  },
): Promise<OpportunityResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/opportunities/${opportunityId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseJsonResponse<OpportunityResponse>(response);
}

export async function postOpportunityBitacora(
  opportunityId: string,
  text: string,
  author?: string,
): Promise<OpportunityResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/opportunities/${opportunityId}/bitacora`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, ...(author ? { author } : {}) }),
  });
  return parseJsonResponse<OpportunityResponse>(response);
}

export async function putOpportunityContacts(
  opportunityId: string,
  contacts: Array<{
    id?: string | null;
    kind: string;
    value: string;
    note?: string | null;
    role?: string | null;
    is_primary: boolean;
  }>,
): Promise<OpportunityResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/opportunities/${opportunityId}/contacts`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contacts }),
  });
  return parseJsonResponse<OpportunityResponse>(response);
}

export async function authLogin(email: string, password: string): Promise<LoginResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return parseJsonResponse<LoginResponse>(response);
}

export async function authMe(): Promise<UserPublic> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/auth/me`);
  return parseJsonResponse<UserPublic>(response);
}

export async function listAdminUsers(): Promise<AdminUsersListResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/admin/users`);
  return parseJsonResponse<AdminUsersListResponse>(response);
}

export async function createAdminUser(body: {
  email: string;
  password: string;
  display_name: string;
  role: "admin" | "user";
}): Promise<UserPublic> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/admin/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseJsonResponse<UserPublic>(response);
}
