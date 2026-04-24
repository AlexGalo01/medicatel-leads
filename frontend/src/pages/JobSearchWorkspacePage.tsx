import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useParams } from "react-router-dom";
import { ChevronRight, Download, Loader2, Mail, Phone, Linkedin, MessageCircle } from "lucide-react";

import {
  clarifySearchJob,
  downloadLeadsCsvFile,
  getDirectory,
  getSearchJobStatus,
  listLeads,
  listOpportunities,
  loadMoreExaResults,
} from "../api";
import { Button } from "../components/ui/button";
import type { ExaCategoryChoice, SearchFocus } from "../types";

export interface JobSearchLocationState {
  searchLabel: string;
  contactChannels: string[];
  searchFocus: SearchFocus;
  notes?: string;
  exaCategory?: ExaCategoryChoice;
  exaCriteria?: string;
}

function formatRelative(iso: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const ts = d.getTime();
  if (Number.isNaN(ts)) return "";
  const diffSec = Math.max(1, Math.floor((Date.now() - ts) / 1000));
  if (diffSec < 60) return `hace ${diffSec} s`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `hace ${diffMin} min`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `hace ${diffH} h`;
  const diffD = Math.floor(diffH / 24);
  return `hace ${diffD} día${diffD > 1 ? "s" : ""}`;
}

interface RowData {
  id: string;
  title: string;
  subtitle: string | null;
  email: string | null;
  phone: string | null;
  whatsapp: string | null;
  linkedin: string | null;
  stepLabel: string | null;
  href: string;
  enriched: boolean;
}

function initial(text: string): string {
  const t = text.trim();
  return t ? t.charAt(0).toUpperCase() : "?";
}

export function JobSearchWorkspacePage(): JSX.Element {
  const { jobId = "" } = useParams();
  const location = useLocation();
  const passedState = location.state as JobSearchLocationState | null;
  const queryClient = useQueryClient();
  const [tablePage, setTablePage] = useState(1);
  const tablePageSize = 50;
  const [workspaceClarifyReply, setWorkspaceClarifyReply] = useState("");

  const downloadCsvMutation = useMutation({
    mutationFn: () => downloadLeadsCsvFile(jobId, {}),
  });

  const jobStatusQuery = useQuery({
    queryKey: ["job-status", jobId],
    queryFn: () => getSearchJobStatus(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "error" ? false : 2000;
    },
    enabled: Boolean(jobId),
    staleTime: 1000,
    placeholderData: keepPreviousData,
  });

  const [exaMoreMessage, setExaMoreMessage] = useState<string | null>(null);
  const exaMoreMutation = useMutation({
    mutationFn: () => loadMoreExaResults(jobId, 40),
    onSuccess: (data) => {
      if (!data.ok) {
        setExaMoreMessage(data.error || "No se pudieron cargar más resultados");
        return;
      }
      setExaMoreMessage(null);
      void queryClient.invalidateQueries({ queryKey: ["job-status", jobId] });
    },
    onError: (error: Error) => setExaMoreMessage(error.message),
  });

  const clarifyWorkspaceMutation = useMutation({
    mutationFn: (reply: string) => clarifySearchJob(jobId, { reply }),
    onSuccess: () => {
      setWorkspaceClarifyReply("");
      void queryClient.invalidateQueries({ queryKey: ["job-status", jobId] });
    },
  });

  const jobStatus = jobStatusQuery.data?.status;
  const awaitingClarification = Boolean(
    jobStatusQuery.data?.awaiting_clarification && jobStatus === "pending",
  );
  const isProcessing =
    (jobStatus === "pending" || jobStatus === "running") && !awaitingClarification;
  const pipelineMode = jobStatusQuery.data?.pipeline_mode ?? null;
  const searchOnlyDemo =
    pipelineMode === "presearch_and_search_only" ||
    (isProcessing && pipelineMode === null);
  const previewRows = searchOnlyDemo ? (jobStatusQuery.data?.exa_results_preview ?? []) : [];

  const leadsQuery = useQuery({
    queryKey: ["leads", jobId, "workspace"],
    queryFn: () => listLeads(jobId, { pageSize: 100 }),
    enabled: Boolean(jobId) && !isProcessing && !searchOnlyDemo,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });
  const persistedLeads = leadsQuery.data?.items ?? [];

  const jobOppsQuery = useQuery({
    queryKey: ["job-opportunities", jobId],
    queryFn: () => listOpportunities({ job_id: jobId }),
    enabled: Boolean(jobId) && !isProcessing,
    staleTime: 30_000,
  });

  const directoryId = (jobStatusQuery.data as unknown as { directory_id?: string })?.directory_id;
  const directoryQuery = useQuery({
    queryKey: ["directory", directoryId],
    queryFn: () => getDirectory(directoryId!),
    enabled: Boolean(directoryId),
    staleTime: 60_000,
  });

  const stepNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const s of directoryQuery.data?.steps ?? []) {
      map.set(s.id, s.name);
    }
    return map;
  }, [directoryQuery.data]);

  const oppByPreviewIndex = useMemo(() => {
    const map = new Map<number, { stepId: string | null }>();
    for (const opp of jobOppsQuery.data?.items ?? []) {
      if (opp.exa_preview_index != null) {
        map.set(opp.exa_preview_index, { stepId: opp.current_step_id });
      }
    }
    return map;
  }, [jobOppsQuery.data?.items]);

  // Normaliza filas (preview o persisted) a una shape única
  const rows: RowData[] = useMemo(() => {
    if (searchOnlyDemo) {
      return previewRows.map((row) => {
        type PreviewExt = typeof row & {
          email?: string | null;
          phone?: string | null;
          whatsapp?: string | null;
          linkedin_url?: string | null;
          enrichment_status?: string | null;
        };
        const r = row as PreviewExt;
        const idx = r.index;
        const opp = oppByPreviewIndex.get(idx);
        const stepName = opp?.stepId ? stepNameById.get(opp.stepId) : null;
        return {
          id: `preview-${idx}`,
          title: (r.title ?? "").trim() || "Sin título",
          subtitle: [r.specialty, r.city].filter(Boolean).join(" · ") || null,
          email: r.email ?? null,
          phone: r.phone ?? null,
          whatsapp: r.whatsapp ?? null,
          linkedin: r.linkedin_url ?? null,
          stepLabel: stepName ?? null,
          href: `/jobs/${jobId}/result/${idx}`,
          enriched: r.enrichment_status === "enriched",
        };
      });
    }
    return persistedLeads.map((lead) => {
      const hasAny = Boolean(lead.email || lead.whatsapp || lead.linkedin_url || lead.phone);
      return {
        id: lead.lead_id,
        title: lead.full_name || "Sin título",
        subtitle: [lead.specialty, lead.city].filter(Boolean).join(" · ") || null,
        email: lead.email,
        phone: lead.phone,
        whatsapp: lead.whatsapp,
        linkedin: lead.linkedin_url,
        stepLabel: null,
        href: `/leads/${lead.lead_id}`,
        enriched: hasAny,
      };
    });
  }, [searchOnlyDemo, previewRows, persistedLeads, jobId, oppByPreviewIndex, stepNameById]);

  const totalRows = rows.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / tablePageSize));
  const currentPage = Math.min(tablePage, totalPages);
  const offset = (currentPage - 1) * tablePageSize;
  const paginated = rows.slice(offset, offset + tablePageSize);

  useEffect(() => {
    setTablePage(1);
  }, [jobId, searchOnlyDemo]);

  useEffect(() => {
    setWorkspaceClarifyReply("");
  }, [jobId]);

  const searchLabel =
    jobStatusQuery.data?.query_text?.trim() || passedState?.searchLabel?.trim() || "Búsqueda";
  const createdAt = jobStatusQuery.data?.updated_at;

  const statusLabel =
    awaitingClarification ? "Aclaración pendiente" :
    jobStatus === "completed" ? "Completada" :
    jobStatus === "error" ? "Error" :
    "En vivo";

  const statusTone =
    awaitingClarification ? "running" :
    jobStatus === "completed" ? "completed" :
    jobStatus === "error" ? "error" : "running";

  return (
    <section className="workspace-v3">
      <nav className="workspace-v3-breadcrumb" aria-label="Navegación">
        {directoryQuery.data ? (
          <>
            <Link to="/directories" className="workspace-v3-crumb">Directorios</Link>
            <ChevronRight size={12} aria-hidden />
            <Link to={`/directories/${directoryQuery.data.id}`} className="workspace-v3-crumb">
              {directoryQuery.data.name}
            </Link>
            <ChevronRight size={12} aria-hidden />
            <span className="workspace-v3-crumb workspace-v3-crumb--current">Búsqueda</span>
          </>
        ) : (
          <Link to="/search" className="workspace-v3-crumb">Buscar</Link>
        )}
      </nav>

      <header className="workspace-v3-head">
        <h1 className="workspace-v3-query">{searchLabel}</h1>
        <div className="workspace-v3-status-row">
          <span className={`workspace-v3-dot workspace-v3-dot--${statusTone}`} aria-hidden />
          <span className="workspace-v3-status-label">{statusLabel}</span>
          <span className="workspace-v3-sep">·</span>
          <span className="workspace-v3-count">{totalRows} resultado{totalRows === 1 ? "" : "s"}</span>
          {createdAt ? (
            <>
              <span className="workspace-v3-sep">·</span>
              <span className="muted-text">{formatRelative(createdAt)}</span>
            </>
          ) : null}
          <div className="workspace-v3-actions">
            {jobStatus === "completed" && searchOnlyDemo && previewRows.length > 0 ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={exaMoreMutation.isPending}
                onClick={() => {
                  setExaMoreMessage(null);
                  exaMoreMutation.mutate();
                }}
              >
                {exaMoreMutation.isPending ? "Cargando…" : "Cargar más"}
              </Button>
            ) : null}
            {jobStatus === "completed" && !searchOnlyDemo ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={downloadCsvMutation.isPending}
                onClick={() => downloadCsvMutation.mutate()}
              >
                <Download size={13} aria-hidden />
                {downloadCsvMutation.isPending ? "Generando…" : "Exportar"}
              </Button>
            ) : null}
          </div>
        </div>
      </header>

      <div
        className={`workspace-v3-progress${
          (isProcessing || jobStatusQuery.isFetching) && !awaitingClarification ? " is-active" : ""
        }`}
        aria-hidden
      />

      {jobStatusQuery.isError ? (
        <p className="error-text workspace-v3-inline-error" role="alert">
          {jobStatusQuery.error instanceof Error
            ? jobStatusQuery.error.message
            : "No se pudo consultar el estado del trabajo."}
        </p>
      ) : null}

      {exaMoreMessage ? <p className="error-text workspace-v3-inline-error">{exaMoreMessage}</p> : null}

      <div className="workspace-v3-list-wrap">
        {awaitingClarification ? (
          <div className="workspace-v3-empty workspace-v3-clarify-panel" role="region" aria-label="Aclaración">
            <p className="muted-text" style={{ marginBottom: "0.5rem" }}>
              <strong style={{ color: "var(--color-text, #1c2b33)" }}>El plan de búsqueda necesita un dato más.</strong>
            </p>
            <p className="muted-text">{jobStatusQuery.data?.clarifying_question}</p>
            <label className="search-clarify-label" htmlFor="workspace-clarify-reply" style={{ marginTop: "0.5rem" }}>
              Tu respuesta
            </label>
            <textarea
              id="workspace-clarify-reply"
              className="search-clarify-textarea workspace-v3-clarify-textarea"
              value={workspaceClarifyReply}
              onChange={(e) => setWorkspaceClarifyReply(e.target.value)}
              rows={4}
              maxLength={500}
              placeholder="Escribe la aclaración y continúa la búsqueda."
            />
            {clarifyWorkspaceMutation.isError ? (
              <p className="error-text" role="alert">
                {clarifyWorkspaceMutation.error instanceof Error
                  ? clarifyWorkspaceMutation.error.message
                  : "No se pudo enviar la aclaración."}
              </p>
            ) : null}
            <Button
              type="button"
              className="cta-button"
              disabled={
                clarifyWorkspaceMutation.isPending || workspaceClarifyReply.trim().length < 1
              }
              onClick={() => clarifyWorkspaceMutation.mutate(workspaceClarifyReply.trim())}
            >
              {clarifyWorkspaceMutation.isPending ? (
                <>
                  <Loader2 className="spin" size={16} aria-hidden />
                  Enviando…
                </>
              ) : (
                "Continuar búsqueda"
              )}
            </Button>
          </div>
        ) : jobStatus === "error" ? (
          <div className="workspace-v3-empty workspace-v3-failure" role="alert">
            <p className="error-text">
              <strong>No se pudo completar la búsqueda.</strong>
            </p>
            {jobStatusQuery.data?.error_message ? (
              <p className="muted-text workspace-v3-failure-detail">{jobStatusQuery.data.error_message}</p>
            ) : (
              <p className="muted-text">Revisa los logs del backend o vuelve a intentar más tarde.</p>
            )}
          </div>
        ) : isProcessing && rows.length === 0 ? (
          <p className="workspace-v3-empty muted-text">Esperando resultados…</p>
        ) : rows.length === 0 ? (
          <p className="workspace-v3-empty muted-text">Sin coincidencias.</p>
        ) : (
          <ul className="workspace-v3-list">
            {paginated.map((row) => (
              <li key={row.id} className="workspace-v3-row">
                <Link to={row.href} className="workspace-v3-row-link">
                  <span className="workspace-v3-avatar" aria-hidden>{initial(row.title)}</span>
                  <div className="workspace-v3-row-main">
                    <div className="workspace-v3-row-title-line">
                      <strong className="workspace-v3-row-title">{row.title}</strong>
                      {row.enriched ? (
                        <span className="workspace-v3-enriched" aria-label="Enriquecido" title="Enriquecido">
                          ✓
                        </span>
                      ) : null}
                    </div>
                    {row.subtitle ? (
                      <span className="workspace-v3-row-sub muted-text">{row.subtitle}</span>
                    ) : null}
                  </div>
                  <div className="workspace-v3-row-chips" onClick={(e) => e.preventDefault()}>
                    <span
                      className={`workspace-v3-chip${row.email ? " is-on" : ""}`}
                      title={row.email || "Sin correo"}
                      aria-label={row.email ? `Correo: ${row.email}` : "Sin correo"}
                    >
                      <Mail size={13} aria-hidden />
                    </span>
                    <span
                      className={`workspace-v3-chip${row.phone ? " is-on" : ""}`}
                      title={row.phone || "Sin teléfono"}
                      aria-label={row.phone ? `Teléfono: ${row.phone}` : "Sin teléfono"}
                    >
                      <Phone size={13} aria-hidden />
                    </span>
                    <span
                      className={`workspace-v3-chip${row.whatsapp ? " is-on" : ""}`}
                      title={row.whatsapp || "Sin WhatsApp"}
                      aria-label={row.whatsapp ? `WhatsApp: ${row.whatsapp}` : "Sin WhatsApp"}
                    >
                      <MessageCircle size={13} aria-hidden />
                    </span>
                    <span
                      className={`workspace-v3-chip${row.linkedin ? " is-on" : ""}`}
                      title={row.linkedin || "Sin LinkedIn"}
                      aria-label={row.linkedin ? "LinkedIn disponible" : "Sin LinkedIn"}
                    >
                      <Linkedin size={13} aria-hidden />
                    </span>
                  </div>
                  {row.stepLabel ? (
                    <span className="workspace-v3-row-step">{row.stepLabel}</span>
                  ) : null}
                  <ChevronRight size={14} aria-hidden className="workspace-v3-row-chevron" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      {totalRows > tablePageSize ? (
        <div className="workspace-v3-pagination">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={currentPage <= 1}
            onClick={() => setTablePage((v) => Math.max(1, v - 1))}
          >
            Anterior
          </Button>
          <span className="muted-text workspace-v3-pagination-label">
            {currentPage} / {totalPages}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={currentPage >= totalPages}
            onClick={() => setTablePage((v) => Math.min(totalPages, v + 1))}
          >
            Siguiente
          </Button>
        </div>
      ) : null}
    </section>
  );
}
