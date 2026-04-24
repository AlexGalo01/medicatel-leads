import type {
  AdminCreateUserRequest,
  AdminUpdateUserRequest,
  AdminUsersListResponse,
  Directory,
  DirectoryCreateRequest,
  DirectoryEntriesListResponse,
  DirectoryListResponse,
  DirectoryStep,
  DirectoryStepCreate,
  DirectoryStepUpdate,
  DirectoryUpdateRequest,
  ExaMoreResultsResponse,
  LeadCrmUpdateRequest,
  LeadDetailResponse,
  LeadsExportFilters,
  LeadsExportResponse,
  LeadsListResponse,
  LoginResponse,
  RegisterRequest,
  OpportunityCreateFromPreviewRequest,
  OpportunityListResponse,
  OpportunityProfileOverrides,
  OpportunityResponse,
  OpportunityTerminatedOutcome,
  ProfileInterpretResponse,
  ProfileSummaryRequest,
  ProfileSummaryResponse,
  SearchJobCreateRequest,
  SearchJobCreateResponse,
  SearchJobsListResponse,
  SearchJobStatusResponse,
  UserPublic,
} from "./types";

const DEFAULT_API_ORIGIN = "http://localhost:8000";

/**
 * VITE_API_BASE_URL debe ser solo el origen (p. ej. `http://localhost:8000`).
 * Si alguien pone el prefijo de API entero, evitamos `/api/v1/api/v1/...` (404 en FastAPI).
 */
function normalizeApiOrigin(envValue: string | undefined): string {
  const raw = (envValue ?? DEFAULT_API_ORIGIN).trim();
  if (!raw) {
    return DEFAULT_API_ORIGIN;
  }
  const noTrailing = raw.replace(/\/+$/, "");
  if (/\/api\/v1$/i.test(noTrailing)) {
    return noTrailing.replace(/\/api\/v1$/i, "");
  }
  return noTrailing;
}

const apiBaseUrl = normalizeApiOrigin(import.meta.env.VITE_API_BASE_URL);

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
  // Auto Content-Type: application/json cuando mandamos un string como body (siempre JSON.stringify).
  if (init?.body && typeof init.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(input, { ...init, headers });
}

function formatApiErrorMessage(status: number, bodyText: string): string {
  const trimmed = bodyText.trim();
  if (!trimmed) {
    return `Error del servidor (${status}).`;
  }
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown };
    const d = parsed.detail;
    if (typeof d === "string") {
      return d;
    }
    if (Array.isArray(d)) {
      const msgs = d
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) {
            return String((item as { msg?: string }).msg ?? "");
          }
          return typeof item === "string" ? item : JSON.stringify(item);
        })
        .filter(Boolean);
      if (msgs.length) {
        return msgs.join(" · ");
      }
    }
    if (d && typeof d === "object" && d !== null && "message" in d) {
      return String((d as { message?: string }).message);
    }
  } catch {
    /* cuerpo no JSON */
  }
  if (trimmed.length > 400) {
    return `${trimmed.slice(0, 397)}…`;
  }
  return trimmed;
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const bodyText = await response.text();
    throw new Error(formatApiErrorMessage(response.status, bodyText));
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

export async function clarifySearchJob(
  jobId: string,
  payload: { reply: string },
): Promise<{ job_id: string; status: string }> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/search-jobs/${jobId}/clarify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<{ job_id: string; status: string }>(response);
}

export async function getSearchJobStatus(jobId: string): Promise<SearchJobStatusResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/search-jobs/${jobId}`);
  return parseJsonResponse<SearchJobStatusResponse>(response);
}

export async function listSearchJobs(params: {
  limit?: number;
  offset?: number;
  q?: string;
  directory_id?: string;
} = {}): Promise<SearchJobsListResponse> {
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
  if (params.directory_id) {
    query.set("directory_id", params.directory_id);
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

export async function summarizeProfile(
  payload: ProfileSummaryRequest,
  options?: { signal?: AbortSignal },
): Promise<ProfileSummaryResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/profiles/summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: options?.signal,
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

export async function listOpportunities(params: {
  stage?: string;
  job_id?: string;
  directory_id?: string;
  limit?: number;
} = {}): Promise<OpportunityListResponse> {
  const query = new URLSearchParams();
  if (params.stage) {
    query.set("stage", params.stage);
  }
  if (params.job_id) {
    query.set("job_id", params.job_id);
  }
  if (params.directory_id) {
    query.set("directory_id", params.directory_id);
  }
  if (typeof params.limit === "number") {
    query.set("limit", String(params.limit));
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

export async function authRegister(body: RegisterRequest): Promise<LoginResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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

export async function createAdminUser(body: AdminCreateUserRequest): Promise<UserPublic> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/admin/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseJsonResponse<UserPublic>(response);
}

export async function updateAdminUser(
  userId: string,
  body: AdminUpdateUserRequest,
): Promise<UserPublic> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/admin/users/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseJsonResponse<UserPublic>(response);
}

export async function deleteAdminUser(userId: string): Promise<void> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/admin/users/${userId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Error al eliminar usuario" }));
    throw new Error(err.detail || "Error al eliminar usuario");
  }
}

export async function createManualOpportunity(body: {
  title: string;
  specialty?: string;
  city?: string;
  source_url?: string;
  snippet?: string | null;
}): Promise<OpportunityResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/opportunities/manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseJsonResponse<OpportunityResponse>(response);
}

export async function deleteOpportunity(opportunityId: string): Promise<void> {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/opportunities/${opportunityId}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Error al eliminar oportunidad" }));
    throw new Error(err.detail || "Error al eliminar oportunidad");
  }
}

// ============================================================================
// DIRECTORIES
// ============================================================================

export async function listDirectories(): Promise<DirectoryListResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/directories`);
  return parseJsonResponse<DirectoryListResponse>(response);
}

export async function getDirectory(directoryId: string): Promise<Directory> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/directories/${directoryId}`);
  return parseJsonResponse<Directory>(response);
}

export async function createDirectory(payload: DirectoryCreateRequest): Promise<Directory> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/directories`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<Directory>(response);
}

export async function updateDirectory(
  directoryId: string,
  payload: DirectoryUpdateRequest,
): Promise<Directory> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/directories/${directoryId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<Directory>(response);
}

export async function deleteDirectory(directoryId: string): Promise<void> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/directories/${directoryId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Error al eliminar directorio" }));
    throw new Error(err.detail || "Error al eliminar directorio");
  }
}

export async function addDirectoryStep(
  directoryId: string,
  payload: DirectoryStepCreate,
): Promise<DirectoryStep> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/directories/${directoryId}/steps`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<DirectoryStep>(response);
}

export async function updateDirectoryStep(
  directoryId: string,
  stepId: string,
  payload: DirectoryStepUpdate,
): Promise<DirectoryStep> {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/directories/${directoryId}/steps/${stepId}`,
    { method: "PATCH", body: JSON.stringify(payload) },
  );
  return parseJsonResponse<DirectoryStep>(response);
}

export async function reorderDirectorySteps(
  directoryId: string,
  stepIds: string[],
): Promise<DirectoryStep[]> {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/directories/${directoryId}/steps/reorder`,
    { method: "POST", body: JSON.stringify({ step_ids: stepIds }) },
  );
  return parseJsonResponse<DirectoryStep[]>(response);
}

export async function deleteDirectoryStep(
  directoryId: string,
  stepId: string,
  moveItemsToStepId?: string,
): Promise<void> {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/directories/${directoryId}/steps/${stepId}`,
    {
      method: "DELETE",
      body: JSON.stringify({ move_items_to_step_id: moveItemsToStepId ?? null }),
    },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Error al eliminar step" }));
    throw new Error(err.detail || "Error al eliminar step");
  }
}

export async function moveOpportunityStep(
  opportunityId: string,
  direction: "forward" | "backward",
): Promise<OpportunityResponse> {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/opportunities/${opportunityId}/step`,
    { method: "PATCH", body: JSON.stringify({ direction }) },
  );
  return parseJsonResponse<OpportunityResponse>(response);
}

export async function terminateOpportunity(
  opportunityId: string,
  outcome: OpportunityTerminatedOutcome,
  note?: string | null,
): Promise<OpportunityResponse> {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/opportunities/${opportunityId}/terminate`,
    { method: "POST", body: JSON.stringify({ outcome, note: note ?? null }) },
  );
  return parseJsonResponse<OpportunityResponse>(response);
}

export async function reopenOpportunity(opportunityId: string): Promise<OpportunityResponse> {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/opportunities/${opportunityId}/reopen`,
    { method: "POST", body: JSON.stringify({}) },
  );
  return parseJsonResponse<OpportunityResponse>(response);
}
