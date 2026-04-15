import type {
  LeadDetailResponse,
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

export async function listLeads(jobId: string, minScore?: number): Promise<LeadsListResponse> {
  const queryParams = new URLSearchParams({ job_id: jobId });
  if (typeof minScore === "number") {
    queryParams.set("min_score", String(minScore));
  }
  const response = await fetch(`${apiBaseUrl}/api/v1/leads?${queryParams.toString()}`);
  return parseJsonResponse<LeadsListResponse>(response);
}

export async function getLeadDetail(leadId: string): Promise<LeadDetailResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}`);
  return parseJsonResponse<LeadDetailResponse>(response);
}

export async function exportLeads(jobId: string, minScore?: number): Promise<LeadsExportResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/leads/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: jobId,
      format: "csv",
      filters: minScore ? { min_score: minScore } : {},
    }),
  });
  return parseJsonResponse<LeadsExportResponse>(response);
}

