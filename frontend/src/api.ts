import type {
  LeadCrmUpdateRequest,
  LeadDetailResponse,
  LeadsExportFilters,
  LeadsExportResponse,
  LeadsListResponse,
  SearchJobCreateRequest,
  SearchJobCreateResponse,
  SearchJobStatusResponse,
} from "./types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const bodyText = await response.text();
    throw new Error(`Error API (${response.status}): ${bodyText || "Sin detalle"}`);
  }
  return (await response.json()) as T;
}

export async function createSearchJob(payload: SearchJobCreateRequest): Promise<SearchJobCreateResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/search-jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<SearchJobCreateResponse>(response);
}

export async function getSearchJobStatus(jobId: string): Promise<SearchJobStatusResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/search-jobs/${jobId}`);
  return parseJsonResponse<SearchJobStatusResponse>(response);
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
  const response = await fetch(`${apiBaseUrl}/api/v1/leads?${queryParams.toString()}`);
  return parseJsonResponse<LeadsListResponse>(response);
}

export async function getLeadDetail(leadId: string): Promise<LeadDetailResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}`);
  return parseJsonResponse<LeadDetailResponse>(response);
}

export async function updateLeadCrm(
  leadId: string,
  payload: LeadCrmUpdateRequest,
): Promise<LeadDetailResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/crm`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<LeadDetailResponse>(response);
}

export async function deepEnrichLead(leadId: string): Promise<LeadDetailResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/deep-enrich`, {
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
  const response = await fetch(`${apiBaseUrl}/api/v1/leads/export`, {
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
  const response = await fetch(`${apiBaseUrl}/api/v1/leads/export/file?${queryParams.toString()}`);
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
