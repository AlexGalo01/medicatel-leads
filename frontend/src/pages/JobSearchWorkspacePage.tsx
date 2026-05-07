import { useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ChevronRight, Download, FileSpreadsheet, Loader2, Mail, Phone, Linkedin, MessageCircle } from "lucide-react";

import {
  cancelSearchJob,
  clarifySearchJob,
  createOpportunityFromPreview,
  downloadLeadsCsvFile,
  downloadLeadsXlsxFile,
  downloadPreviewXlsxFile,
  getDirectory,
  getSearchJobStatus,
  listDirectories,
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
  previewIndex: number | null;
}

function initial(text: string): string {
  const t = text.trim();
  return t ? t.charAt(0).toUpperCase() : "?";
}

const LOADING_MESSAGES = [
  "Buscando en la web…",
  "Enriqueciendo datos…",
  "Verificando contactos…",
  "Analizando resultados…",
  "Casi listo…",
];

export function JobSearchWorkspacePage(): JSX.Element {
  const { jobId = "" } = useParams();
  const location = useLocation();
  const passedState = location.state as JobSearchLocationState | null;
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tablePage = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10));
  const setTablePage = (newPage: number) => {
    setSearchParams(
      (prev: URLSearchParams) => { const n = new URLSearchParams(prev); n.set("page", String(newPage)); return n; },
      { replace: true }
    );
  };
  const tablePageSize = 50;
  const prevJobIdRef = useRef<string>("");
  const [workspaceClarifyReply, setWorkspaceClarifyReply] = useState("");
  const [loadingMessageIndex, setLoadingMessageIndex] = useState(0);

  const downloadCsvMutation = useMutation({
    mutationFn: () => downloadLeadsCsvFile(jobId, {}),
  });

  const downloadXlsxMutation = useMutation({
    mutationFn: () => downloadLeadsXlsxFile(jobId, {}),
  });

  const downloadPreviewXlsxMutation = useMutation({
    mutationFn: () => downloadPreviewXlsxFile(jobId),
  });

  const jobStatusQuery = useQuery({
    queryKey: ["job-status", jobId],
    queryFn: () => getSearchJobStatus(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "error" || status === "cancelled" ? false : 2000;
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

  // Opportunity selection and modal state
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [selectedDirectoryId, setSelectedDirectoryId] = useState<string | null>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const directoriesQuery = useQuery({
    queryKey: ["directories"],
    queryFn: listDirectories,
    staleTime: 60_000,
    enabled: saveModalOpen,
  });

  const saveAsOppMutation = useMutation({
    mutationFn: (previewIndex: number) =>
      createOpportunityFromPreview({
        job_id: jobId,
        exa_preview_index: previewIndex,
        step_id: selectedStepId || undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["job-opportunities", jobId] });
    },
  });

  const clarifyWorkspaceMutation = useMutation({
    mutationFn: (reply: string) => clarifySearchJob(jobId, { reply }),
    onSuccess: () => {
      setWorkspaceClarifyReply("");
      void queryClient.invalidateQueries({ queryKey: ["job-status", jobId] });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelSearchJob(jobId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["job-status", jobId] });
    },
  });

  const jobStatus = jobStatusQuery.data?.status;
  const awaitingClarification = Boolean(
    jobStatusQuery.data?.awaiting_clarification && jobStatus === "pending",
  );
  const isProcessing =
    (jobStatus === "pending" || jobStatus === "running") && !awaitingClarification;

  useEffect(() => {
    if (!isProcessing) return;
    const timer = setInterval(() => {
      setLoadingMessageIndex((prev) => (prev + 1) % LOADING_MESSAGES.length);
    }, 2500);
    return () => clearInterval(timer);
  }, [isProcessing]);

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
          previewIndex: idx,
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
        previewIndex: null,
      };
    });
  }, [searchOnlyDemo, previewRows, persistedLeads, jobId, oppByPreviewIndex, stepNameById]);

  const totalRows = rows.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / tablePageSize));
  const currentPage = Math.min(tablePage, totalPages);
  const offset = (currentPage - 1) * tablePageSize;
  const paginated = rows.slice(offset, offset + tablePageSize);

  useEffect(() => {
    if (prevJobIdRef.current !== jobId) {
      prevJobIdRef.current = jobId;
      setSearchParams((prev: URLSearchParams) => {
        const n = new URLSearchParams(prev);
        n.delete("page");
        return n;
      }, { replace: true });
    }
  }, [jobId, searchOnlyDemo, setSearchParams]);

  const handleSaveSelected = async () => {
    if (!selectedStepId) return;
    setSaving(true);
    const toSave = Array.from(selectedIndices);
    for (const previewIndex of toSave) {
      await createOpportunityFromPreview({
        job_id: jobId,
        exa_preview_index: previewIndex,
        step_id: selectedStepId,
      });
    }
    void queryClient.invalidateQueries({ queryKey: ["job-opportunities", jobId] });
    setSelectedIndices(new Set());
    setSaveModalOpen(false);
    setSelectedDirectoryId(null);
    setSelectedStepId(null);
    setSaving(false);
  };

  const unsavedCount = rows.filter(
    (r) => r.previewIndex != null && !oppByPreviewIndex.has(r.previewIndex),
  ).length;

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
    jobStatus === "cancelled" ? "Cancelada" :
    "En vivo";

  const statusTone =
    awaitingClarification ? "running" :
    jobStatus === "completed" ? "completed" :
    jobStatus === "error" ? "error" :
    jobStatus === "cancelled" ? "error" : "running";

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
            {isProcessing ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={cancelMutation.isPending}
                onClick={() => cancelMutation.mutate()}
              >
                {cancelMutation.isPending ? "Cancelando…" : "Detener búsqueda"}
              </Button>
            ) : null}
            {jobStatus === "completed" && searchOnlyDemo && previewRows.length > 0 ? (
              <>
                <Button
                  type="button"
                  variant="default"
                  size="sm"
                  disabled={unsavedCount === 0 || saving}
                  onClick={() => {
                    const notSaved = rows
                      .filter((r) => r.previewIndex != null && !oppByPreviewIndex.has(r.previewIndex!))
                      .map((r) => r.previewIndex!);
                    setSelectedIndices(new Set(notSaved));
                    setSaveModalOpen(true);
                  }}
                  className="btn-save-all-opp"
                >
                  {saving ? "Guardando…" : `Guardar todos (${unsavedCount})`}
                </Button>
                {selectedIndices.size > 0 && (
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={selectedIndices.size === 0 || saving}
                    onClick={() => setSaveModalOpen(true)}
                  >
                    Crear Oportunidades ({selectedIndices.size})
                  </Button>
                )}
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={downloadPreviewXlsxMutation.isPending}
                  onClick={() => downloadPreviewXlsxMutation.mutate()}
                >
                  <FileSpreadsheet size={13} aria-hidden />
                  {downloadPreviewXlsxMutation.isPending ? "Generando…" : "Excel"}
                </Button>
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
              </>
            ) : null}
            {jobStatus === "completed" && !searchOnlyDemo ? (
              <>
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
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={downloadXlsxMutation.isPending}
                  onClick={() => downloadXlsxMutation.mutate()}
                >
                  <FileSpreadsheet size={13} aria-hidden />
                  {downloadXlsxMutation.isPending ? "Generando…" : "Excel"}
                </Button>
              </>
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
          <div className="workspace-v3-empty">
            <div className="workspace-v3-loading-spinner" />
            <p className="workspace-v3-loading-message">{LOADING_MESSAGES[loadingMessageIndex]}</p>
          </div>
        ) : rows.length === 0 ? (
          <p className="workspace-v3-empty muted-text">Sin coincidencias.</p>
        ) : (
          <ul className="workspace-v3-list">
            {paginated.map((row) => (
              <li key={row.id} className="workspace-v3-row">
                {/* Checkbox for search-only mode */}
                {searchOnlyDemo && row.previewIndex != null && !oppByPreviewIndex.has(row.previewIndex) && (
                  <input
                    type="checkbox"
                    checked={selectedIndices.has(row.previewIndex)}
                    onChange={() => {
                      setSelectedIndices((prev) => {
                        const next = new Set(prev);
                        next.has(row.previewIndex!) ? next.delete(row.previewIndex!) : next.add(row.previewIndex!);
                        return next;
                      });
                    }}
                    onClick={(e) => e.stopPropagation()}
                    style={{ marginRight: "8px" }}
                  />
                )}
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
                  {/* Show saved badge if already has an opportunity */}
                  {oppByPreviewIndex.has(row.previewIndex ?? -1) && (
                    <span className="workspace-v3-saved-badge" style={{ marginRight: "8px" }}>
                      ✓ Oportunidad
                    </span>
                  )}
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
            onClick={() => setTablePage(Math.max(1, currentPage - 1))}
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
            onClick={() => setTablePage(Math.min(totalPages, currentPage + 1))}
          >
            Siguiente
          </Button>
        </div>
      ) : null}

      {(jobStatusQuery.data?.suggested_source_urls ?? []).length > 0 ? (
        <section className="workspace-v3-sources">
          <h3>Fuentes para explorar</h3>
          <p className="muted-text">
            {directoryId
              ? "Estas páginas de directorio pueden contener más contactos. Impórtalas con el URL scraper."
              : "Estos son directorios y páginas de listado que pueden contener más contactos del sector."}
          </p>
          <ul className="workspace-v3-sources-list">
            {(jobStatusQuery.data?.suggested_source_urls ?? []).map((s) => (
              <li key={s.url} className="workspace-v3-sources-item">
                <span className="workspace-v3-sources-title">{s.title || s.url}</span>
                {directoryId ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="workspace-v3-sources-btn"
                    onClick={() => {
                      navigate(`/directories/${directoryId}`, {
                        state: { openUrlScraper: true, prefillUrl: s.url }
                      });
                    }}
                  >
                    Importar →
                  </Button>
                ) : (
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="link-button">
                    Abrir →
                  </a>
                )}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Modal de selección de directorio */}
      {saveModalOpen && (
        <div
          className="modal-overlay"
          onClick={() => setSaveModalOpen(false)}
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0, 0, 0, 0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            className="modal-card"
            onClick={(e) => e.stopPropagation()}
            style={{
              backgroundColor: "white",
              borderRadius: "8px",
              padding: "24px",
              maxWidth: "500px",
              maxHeight: "80vh",
              overflowY: "auto",
              boxShadow: "0 10px 25px rgba(0, 0, 0, 0.1)",
            }}
          >
            <h3 style={{ marginTop: 0, marginBottom: "8px" }}>¿A qué directorio enviar?</h3>
            <p style={{ marginBottom: "16px", color: "#666", fontSize: "14px" }}>
              {selectedIndices.size} resultado(s) seleccionado(s)
            </p>

            {directoriesQuery.isLoading && (
              <div style={{ textAlign: "center", padding: "20px" }}>Cargando directorios...</div>
            )}

            {directoriesQuery.data?.items.map((dir) => (
              <div key={dir.id} style={{ marginBottom: "12px" }}>
                <button
                  type="button"
                  onClick={() =>
                    setSelectedDirectoryId((d) => (d === dir.id ? null : dir.id))
                  }
                  style={{
                    width: "100%",
                    padding: "10px 12px",
                    textAlign: "left",
                    border: selectedDirectoryId === dir.id ? "2px solid #6366f1" : "1px solid #ddd",
                    borderRadius: "6px",
                    backgroundColor: selectedDirectoryId === dir.id ? "#f0f4ff" : "white",
                    cursor: "pointer",
                    fontWeight: selectedDirectoryId === dir.id ? "600" : "normal",
                  }}
                >
                  {dir.name}
                </button>
                {selectedDirectoryId === dir.id && (
                  <div style={{ marginTop: "8px", paddingLeft: "8px" }}>
                    {dir.steps
                      .filter((s) => !s.is_terminal)
                      .map((step) => (
                        <button
                          key={step.id}
                          type="button"
                          onClick={() => setSelectedStepId(step.id)}
                          style={{
                            display: "block",
                            width: "100%",
                            padding: "8px 12px",
                            marginBottom: "6px",
                            textAlign: "left",
                            border:
                              selectedStepId === step.id
                                ? "2px solid #6366f1"
                                : "1px solid #e5e7eb",
                            borderRadius: "4px",
                            backgroundColor:
                              selectedStepId === step.id ? "#f0f4ff" : "white",
                            cursor: "pointer",
                            fontSize: "14px",
                            fontWeight: selectedStepId === step.id ? "600" : "normal",
                          }}
                        >
                          {step.name}
                        </button>
                      ))}
                  </div>
                )}
              </div>
            ))}

            <div
              style={{
                marginTop: "20px",
                display: "flex",
                gap: "8px",
                justifyContent: "flex-end",
              }}
            >
              <button
                type="button"
                onClick={() => setSaveModalOpen(false)}
                style={{
                  padding: "8px 16px",
                  border: "1px solid #ddd",
                  borderRadius: "4px",
                  backgroundColor: "white",
                  cursor: "pointer",
                  fontSize: "14px",
                }}
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleSaveSelected}
                disabled={!selectedStepId || saving}
                style={{
                  padding: "8px 16px",
                  border: "none",
                  borderRadius: "4px",
                  backgroundColor: !selectedStepId || saving ? "#ccc" : "#6366f1",
                  color: "white",
                  cursor: !selectedStepId || saving ? "not-allowed" : "pointer",
                  fontSize: "14px",
                  fontWeight: "600",
                }}
              >
                {saving ? "Guardando…" : `Guardar ${selectedIndices.size} oportunidades`}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
