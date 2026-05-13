import { useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Bookmark, ChevronRight, Download, FileSpreadsheet, Loader2, Mail, Phone, Linkedin, MessageCircle } from "lucide-react";

import { UrlScraperModal } from "../features/directories/components/UrlScraperModal";
import {
  cancelSearchJob,
  clarifySearchJob,
  createDirectorySource,
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
  setPreviewItemLabel,
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
  if (diffMin < 60) return `hace ${diffMin} minuto${diffMin !== 1 ? "s" : ""}`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `hace ${diffH} hora${diffH !== 1 ? "s" : ""}`;
  const diffD = Math.floor(diffH / 24);
  return `hace ${diffD} día${diffD !== 1 ? "s" : ""}`;
}

type PreviewLabel = "no_relevante" | "duplicado" | "ya_contactado" | "fuente";

const LABEL_OPTIONS: { value: PreviewLabel; label: string }[] = [
  { value: "no_relevante", label: "No relevante" },
  { value: "duplicado", label: "Duplicado" },
  { value: "ya_contactado", label: "Ya contactado" },
  { value: "fuente", label: "Fuente" },
];

const LABEL_STYLE: Record<PreviewLabel, { bg: string; color: string }> = {
  no_relevante: { bg: "rgba(239,68,68,0.10)", color: "#DC2626" },
  duplicado: { bg: "rgba(245,158,11,0.12)", color: "#B45309" },
  ya_contactado: { bg: "rgba(59,130,246,0.10)", color: "#1D4ED8" },
  fuente: { bg: "rgba(139,92,246,0.10)", color: "#7C3AED" },
};

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
  label: PreviewLabel | null;
}

function stripEmojis(text: string): string {
  return text
    .replace(/[\u{1F000}-\u{1FFFF}]/gu, "")
    .replace(/[\u{2600}-\u{27BF}]/gu, "")
    .replace(/[\u{1F300}-\u{1F9FF}]/gu, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function initial(text: string): string {
  const t = stripEmojis(text).trim();
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
    mutationFn: () => downloadPreviewXlsxFile(jobId, searchLabel),
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
  const [selectedSourceIndices, setSelectedSourceIndices] = useState<Set<number>>(new Set());
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [selectedDirectoryId, setSelectedDirectoryId] = useState<string | null>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Bulk save de fuentes del panel
  const [savingAllSources, setSavingAllSources] = useState(false);
  const [allSourcesDirPickerOpen, setAllSourcesDirPickerOpen] = useState(false);
  const [allSourcesDirId, setAllSourcesDirId] = useState("");

  const [lpaOpen, setLpaOpen] = useState(false);

  // Estado para scraper modal inline
  const [scraperOpen, setScraperOpen] = useState(false);
  const [scraperUrl, setScraperUrl] = useState<string | undefined>(undefined);
  const [scraperTitle, setScraperTitle] = useState<string | undefined>(undefined);

  // Estado para guardar fuentes en directorio (cuando no hay directoryId)
  const [sourcePickerUrl, setSourcePickerUrl] = useState<string | null>(null);
  const [sourcePickerDirId, setSourcePickerDirId] = useState<string>("");
  const [savedSourceUrls, setSavedSourceUrls] = useState<Set<string>>(new Set());

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

  const directoriesQuery = useQuery({
    queryKey: ["directories"],
    queryFn: listDirectories,
    staleTime: 60_000,
    enabled: saveModalOpen || !directoryId,
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
        const rawLabel = (r as PreviewExt & { label?: string }).label;
        const label = LABEL_OPTIONS.some((o) => o.value === rawLabel)
          ? (rawLabel as PreviewLabel)
          : null;
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
          label,
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
        label: null,
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
    if (selectedIndices.size > 0 && !selectedStepId) return;
    const dirId = directoryId || selectedDirectoryId;
    if (selectedSourceIndices.size > 0 && !dirId) return;
    setSaving(true);

    // Guardar como oportunidades
    for (const previewIndex of Array.from(selectedIndices)) {
      await createOpportunityFromPreview({
        job_id: jobId,
        exa_preview_index: previewIndex,
        step_id: selectedStepId || undefined,
      });
    }

    // Guardar como fuentes
    if (dirId) {
      for (const previewIndex of Array.from(selectedSourceIndices)) {
        const previewRow = previewRows.find((r) => r.index === previewIndex);
        if (previewRow) {
          try {
            await createDirectorySource(dirId, {
              url: previewRow.url,
              title: previewRow.title,
              source_search_job_id: jobId,
            });
            setSavedSourceUrls((prev) => new Set([...prev, previewRow.url]));
          } catch { /* silent */ }
        }
      }
    }

    void queryClient.invalidateQueries({ queryKey: ["job-opportunities", jobId] });
    setSelectedIndices(new Set());
    setSelectedSourceIndices(new Set());
    setSaveModalOpen(false);
    setSelectedDirectoryId(null);
    setSelectedStepId(null);
    setSaving(false);
  };

  const handleSaveAllSources = async (dirId: string) => {
    setSavingAllSources(true);
    const unsaved = (jobStatusQuery.data?.suggested_source_urls ?? []).filter(
      (s) => !savedSourceUrls.has(s.url),
    );
    const results = await Promise.allSettled(
      unsaved.map((s) =>
        createDirectorySource(dirId, {
          url: s.url,
          title: s.title,
          source_search_job_id: jobId,
        }).then(() => s.url),
      ),
    );
    const saved = results
      .filter((r): r is PromiseFulfilledResult<string> => r.status === "fulfilled")
      .map((r) => r.value);
    if (saved.length > 0) {
      setSavedSourceUrls((prev) => new Set([...prev, ...saved]));
    }
    setSavingAllSources(false);
    setAllSourcesDirPickerOpen(false);
    setAllSourcesDirId("");
  };

  const unsavedRows = rows.filter(
    (r) => r.previewIndex != null && !oppByPreviewIndex.has(r.previewIndex),
  );
  const unsavedCount = unsavedRows.length;
  const totalSelected = selectedIndices.size + selectedSourceIndices.size;

  useEffect(() => {
    setWorkspaceClarifyReply("");
  }, [jobId]);

  const searchLabel =
    jobStatusQuery.data?.query_text?.trim() || passedState?.searchLabel?.trim() || "Búsqueda";
  const createdAt = jobStatusQuery.data?.created_at ?? jobStatusQuery.data?.updated_at;

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
                    const notSaved = unsavedRows.map((r) => r.previewIndex!);
                    setSelectedIndices(new Set(notSaved));
                    setSelectedSourceIndices(new Set());
                    setSaveModalOpen(true);
                  }}
                  className="btn-save-all-opp"
                >
                  {saving ? "Guardando…" : `Guardar todos (${unsavedCount})`}
                </Button>
                {totalSelected > 0 && (
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={totalSelected === 0 || saving}
                    onClick={() => setSaveModalOpen(true)}
                  >
                    Guardar seleccionados ({totalSelected})
                  </Button>
                )}
                <Button
                  type="button"
                  size="sm"
                  disabled={downloadPreviewXlsxMutation.isPending}
                  onClick={() => downloadPreviewXlsxMutation.mutate()}
                  className="btn-excel"
                >
                  <FileSpreadsheet size={14} aria-hidden />
                  {downloadPreviewXlsxMutation.isPending ? "Generando…" : "Exportar Excel"}
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

      {(jobStatusQuery.data?.warnings ?? []).length > 0 ? (
        <div className="workspace-v3-warnings" role="status">
          {jobStatusQuery.data!.warnings!.map((w, i) => (
            <p key={i} className="workspace-v3-warning-text">{w}</p>
          ))}
        </div>
      ) : null}

      <div className="workspace-v3-split">
      <div className="workspace-v3-split-main">
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
                {/* Checkboxes: Resultado / Fuente */}
                {searchOnlyDemo && row.previewIndex != null && !oppByPreviewIndex.has(row.previewIndex) && (
                  <div className="workspace-v3-row-selectors">
                    <label className="workspace-v3-checkbox-label" title="Guardar como oportunidad">
                      <input
                        type="checkbox"
                        className="workspace-v3-checkbox-input"
                        checked={selectedIndices.has(row.previewIndex)}
                        onChange={() => {
                          const idx = row.previewIndex!;
                          setSelectedIndices((prev) => {
                            const next = new Set(prev);
                            next.has(idx) ? next.delete(idx) : next.add(idx);
                            return next;
                          });
                          setSelectedSourceIndices((prev) => { const next = new Set(prev); next.delete(idx); return next; });
                        }}
                      />
                    </label>
                    <button
                      type="button"
                      className={`workspace-v3-source-toggle${selectedSourceIndices.has(row.previewIndex) ? " is-active" : ""}`}
                      title={selectedSourceIndices.has(row.previewIndex) ? "Marcado como fuente" : "Marcar como fuente"}
                      onClick={(e) => {
                        e.preventDefault();
                        const idx = row.previewIndex!;
                        setSelectedSourceIndices((prev) => {
                          const next = new Set(prev);
                          next.has(idx) ? next.delete(idx) : next.add(idx);
                          return next;
                        });
                        setSelectedIndices((prev) => { const next = new Set(prev); next.delete(idx); return next; });
                      }}
                    >
                      <Bookmark size={14} />
                    </button>
                  </div>
                )}
                <Link to={row.href} className="workspace-v3-row-link">
                  <span className="workspace-v3-avatar" aria-hidden>
                    {initial(row.title)}
                  </span>
                  <div className="workspace-v3-row-content">
                    <div className="workspace-v3-row-title-line">
                      <strong className="workspace-v3-row-title">{stripEmojis(row.title)}</strong>
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
                  <div className="workspace-v3-row-actions">
                    {/* Show saved badge if already has an opportunity */}
                    {oppByPreviewIndex.has(row.previewIndex ?? -1) && (
                      <span className="workspace-v3-saved-badge">
                        ✓ Oportunidad
                      </span>
                    )}
                    {row.stepLabel ? (
                      <span className="workspace-v3-row-step">{row.stepLabel}</span>
                    ) : null}
                    {searchOnlyDemo && row.previewIndex != null && (
                      <select
                        className="preview-label-select"
                        value={row.label ?? ""}
                        style={row.label ? {
                          background: LABEL_STYLE[row.label].bg,
                          color: LABEL_STYLE[row.label].color,
                          borderColor: LABEL_STYLE[row.label].color,
                        } : undefined}
                        onClick={(e) => e.preventDefault()}
                        onChange={async (e) => {
                          e.stopPropagation();
                          const val = e.target.value || null;
                          try {
                            await setPreviewItemLabel(jobId, row.previewIndex!, val);
                            void queryClient.invalidateQueries({ queryKey: ["job-status", jobId] });
                          } catch { /* silent */ }
                        }}
                      >
                        <option value="">Etiquetar…</option>
                        {LABEL_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    )}
                  </div>
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
      </div>

      {!isProcessing && (jobStatusQuery.data?.suggested_source_urls ?? []).length > 0 ? (
        <section className="workspace-v3-sources workspace-v3-split-sidebar">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 4 }}>
            <h3 style={{ margin: 0 }}>Fuentes para explorar</h3>
            {(() => {
              const unsavedSources = (jobStatusQuery.data?.suggested_source_urls ?? []).filter(
                (s) => !savedSourceUrls.has(s.url),
              );
              if (unsavedSources.length === 0) return null;
              return directoryId ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="workspace-v3-sources-btn"
                  disabled={savingAllSources}
                  onClick={() => handleSaveAllSources(directoryId)}
                >
                  {savingAllSources ? <Loader2 className="spin" size={12} aria-hidden /> : null}
                  {savingAllSources ? "Guardando…" : `Guardar todas (${unsavedSources.length})`}
                </Button>
              ) : allSourcesDirPickerOpen ? (
                <div className="sources-dir-picker">
                  <div className="sources-dir-picker-list">
                    {directoriesQuery.isLoading ? (
                      <span className="muted-text" style={{ fontSize: 12, padding: "6px 10px", display: "block" }}>
                        <Loader2 className="spin" size={12} aria-hidden /> Cargando…
                      </span>
                    ) : (directoriesQuery.data?.items ?? []).map((d) => (
                      <button
                        key={d.id}
                        type="button"
                        className={`sources-dir-picker-opt${allSourcesDirId === d.id ? " is-selected" : ""}`}
                        onClick={() => setAllSourcesDirId(d.id)}
                      >
                        {d.name}
                      </button>
                    ))}
                  </div>
                  <div className="sources-dir-picker-actions">
                    <Button
                      type="button"
                      variant="default"
                      size="sm"
                      disabled={!allSourcesDirId || savingAllSources}
                      onClick={() => handleSaveAllSources(allSourcesDirId)}
                    >
                      {savingAllSources ? <><Loader2 className="spin" size={12} aria-hidden /> Guardando…</> : "Guardar"}
                    </Button>
                    <Button type="button" variant="ghost" size="sm" onClick={() => { setAllSourcesDirPickerOpen(false); setAllSourcesDirId(""); }}>
                      Cancelar
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="workspace-v3-sources-btn"
                  onClick={() => setAllSourcesDirPickerOpen(true)}
                >
                  Guardar todas ({unsavedSources.length})
                </Button>
              );
            })()}
          </div>
          <p className="muted-text">
            Directorios y páginas de listado que pueden contener más contactos del sector.
          </p>
          <ul className="workspace-v3-sources-list">
            {(jobStatusQuery.data?.suggested_source_urls ?? []).map((s) => (
              <li key={s.url} className="workspace-v3-sources-item">
                <span className="workspace-v3-sources-title">{stripEmojis(s.title || s.url)}</span>
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center" }}>
                  {directoryId ? (
                    <>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="workspace-v3-sources-btn"
                        onClick={() => {
                          setScraperUrl(s.url);
                          setScraperTitle(s.title);
                          setScraperOpen(true);
                        }}
                      >
                        Buscar por URL
                      </Button>
                      {savedSourceUrls.has(s.url) ? (
                        <span className="workspace-v3-sources-saved">✓ Guardado</span>
                      ) : (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="workspace-v3-sources-btn"
                          onClick={async () => {
                            try {
                              await createDirectorySource(directoryId!, {
                                url: s.url,
                                title: s.title,
                                source_search_job_id: jobId,
                              });
                              setSavedSourceUrls((prev) => new Set([...prev, s.url]));
                            } catch {
                              // silent
                            }
                          }}
                        >
                          Guardar en directorio
                        </Button>
                      )}
                    </>
                  ) : (
                    // Sin directoryId: mostrar selector inline
                    savedSourceUrls.has(s.url) ? (
                      <span className="workspace-v3-sources-saved">✓ Guardado</span>
                    ) : sourcePickerUrl === s.url ? (
                      <div className="sources-dir-picker sources-dir-picker--inline">
                        <div className="sources-dir-picker-list">
                          {(directoriesQuery.data?.items ?? []).map((d) => (
                            <button
                              key={d.id}
                              type="button"
                              className={`sources-dir-picker-opt${sourcePickerDirId === d.id ? " is-selected" : ""}`}
                              onClick={() => setSourcePickerDirId(d.id)}
                            >
                              {d.name}
                            </button>
                          ))}
                        </div>
                        <div className="sources-dir-picker-actions">
                          <Button
                            type="button"
                            variant="default"
                            size="sm"
                            disabled={!sourcePickerDirId}
                            onClick={async () => {
                              if (!sourcePickerDirId) return;
                              try {
                                await createDirectorySource(sourcePickerDirId, {
                                  url: s.url,
                                  title: s.title,
                                  source_search_job_id: jobId,
                                });
                                setSavedSourceUrls((prev) => new Set([...prev, s.url]));
                                setSourcePickerUrl(null);
                                setSourcePickerDirId("");
                              } catch { /* silent */ }
                            }}
                          >
                            Guardar
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => { setSourcePickerUrl(null); setSourcePickerDirId(""); }}
                          >
                            Cancelar
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="workspace-v3-sources-btn"
                        onClick={() => {
                          setSourcePickerUrl(s.url);
                          setSourcePickerDirId("");
                        }}
                      >
                        Guardar en directorio
                      </Button>
                    )
                  )}
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="link-button" style={{ fontSize: 13 }}>
                    Abrir →
                  </a>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      </div>

      {/* Sección LPA */}
      {!isProcessing && (jobStatusQuery.data?.lpa_preview ?? []).length > 0 ? (
        <section className="workspace-v3-lpa">
          <button
            type="button"
            className="workspace-v3-lpa-toggle"
            onClick={() => setLpaOpen((o) => !o)}
            aria-expanded={lpaOpen}
          >
            <span className="workspace-v3-lpa-badge">LPA</span>
            Por averiguar ({jobStatusQuery.data!.lpa_preview!.length})
            <span className="workspace-v3-lpa-chevron" aria-hidden>{lpaOpen ? "▲" : "▼"}</span>
          </button>
          {lpaOpen ? (
            <>
              <p className="muted-text workspace-v3-lpa-desc">
                Clínicas, centros o profesionales adyacentes que pueden contener contactos útiles. No son leads directos pero vale la pena explorarlos.
              </p>
              <ul className="workspace-v3-list">
                {jobStatusQuery.data!.lpa_preview!.map((row) => (
                  <li key={row.url} className="workspace-v3-row workspace-v3-row--lpa">
                    <Link to={`/jobs/${jobId}/result/${row.index}`} className="workspace-v3-row-link">
                      <span className="workspace-v3-avatar workspace-v3-avatar--lpa" aria-hidden>
                        {row.title.charAt(0).toUpperCase() || "?"}
                      </span>
                      <div className="workspace-v3-row-content">
                        <div className="workspace-v3-row-title-line">
                          <strong className="workspace-v3-row-title">{row.title || row.url}</strong>
                          <span className="workspace-v3-lpa-badge workspace-v3-lpa-badge--inline">LPA</span>
                        </div>
                        {row.snippet ? (
                          <span className="workspace-v3-row-sub muted-text">{row.snippet}</span>
                        ) : null}
                      </div>
                      <ChevronRight size={14} aria-hidden className="workspace-v3-row-chevron" />
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </section>
      ) : null}

      {scraperOpen && directoryId && directoryQuery.data ? (
        <UrlScraperModal
          isOpen={scraperOpen}
          onClose={() => setScraperOpen(false)}
          directoryId={directoryId}
          steps={directoryQuery.data.steps}
          prefillUrl={scraperUrl}
          prefillTitle={scraperTitle}
        />
      ) : null}

      {/* Modal de selección de directorio */}
      {saveModalOpen && (
        <div className="modal-overlay-save-opp" onClick={() => setSaveModalOpen(false)}>
          <div className="modal-save-opp" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-save-opp-title">
              {directoryId && directoryQuery.data
                ? `Enviar a: ${directoryQuery.data.name}`
                : "¿A qué directorio enviar?"}
            </h3>
            <p className="modal-save-opp-subtitle">
              {selectedIndices.size > 0 && `${selectedIndices.size} oportunidad${selectedIndices.size !== 1 ? "es" : ""}`}
              {selectedIndices.size > 0 && selectedSourceIndices.size > 0 && " · "}
              {selectedSourceIndices.size > 0 && `${selectedSourceIndices.size} fuente${selectedSourceIndices.size !== 1 ? "s" : ""}`}
            </p>

            {directoryId && directoryQuery.data ? (
              selectedIndices.size > 0 ? (
                <div className="modal-save-opp-steps" style={{ marginTop: "16px" }}>
                  <p style={{ marginBottom: "8px", fontSize: "13px", color: "var(--text-muted)" }}>Selecciona la fase:</p>
                  {directoryQuery.data.steps.filter((s) => !s.is_terminal).length === 0 ? (
                    <p className="modal-save-opp-empty muted-text">Sin steps disponibles</p>
                  ) : (
                    directoryQuery.data.steps
                      .filter((s) => !s.is_terminal)
                      .map((step) => (
                        <button
                          key={step.id}
                          type="button"
                          className={`modal-save-opp-step-btn${
                            selectedStepId === step.id ? " is-selected" : ""
                          }`}
                          onClick={() => setSelectedStepId(step.id)}
                        >
                          {step.name}
                        </button>
                      ))
                  )}
                </div>
              ) : (
                <p className="muted-text" style={{ marginTop: 12, fontSize: 13 }}>
                  Se guardarán en <strong>{directoryQuery.data.name}</strong>.
                </p>
              )
            ) : (
              <>
                {directoriesQuery.isLoading && (
                  <div className="modal-save-opp-loading">
                    <Loader2 className="spin" size={16} aria-hidden />
                    Cargando directorios…
                  </div>
                )}

                {directoriesQuery.data?.items && directoriesQuery.data.items.length === 0 && (
                  <p className="modal-save-opp-empty muted-text">Sin directorios disponibles</p>
                )}

                {directoriesQuery.data?.items.map((dir) => (
                  <div key={dir.id} className="modal-save-opp-directory">
                    <button
                      type="button"
                      className={`modal-save-opp-dir-btn${
                        selectedDirectoryId === dir.id ? " is-selected" : ""
                      }`}
                      onClick={() =>
                        setSelectedDirectoryId((d) => (d === dir.id ? null : dir.id))
                      }
                    >
                      {dir.name}
                    </button>
                    {selectedDirectoryId === dir.id && (
                      <div className="modal-save-opp-steps">
                        {dir.steps.filter((s) => !s.is_terminal).length === 0 ? (
                          <p className="modal-save-opp-empty muted-text">Sin steps disponibles</p>
                        ) : (
                          dir.steps
                            .filter((s) => !s.is_terminal)
                            .map((step) => (
                              <button
                                key={step.id}
                                type="button"
                                className={`modal-save-opp-step-btn${
                                  selectedStepId === step.id ? " is-selected" : ""
                                }`}
                                onClick={() => setSelectedStepId(step.id)}
                              >
                                {step.name}
                              </button>
                            ))
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </>
            )}

            <div className="modal-save-opp-actions">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setSaveModalOpen(false)}
              >
                Cancelar
              </Button>
              <Button
                type="button"
                variant="default"
                size="sm"
                onClick={handleSaveSelected}
                disabled={(selectedIndices.size > 0 && !selectedStepId) || saving}
              >
                {saving ? (
                  <>
                    <Loader2 className="spin" size={13} aria-hidden />
                    Guardando…
                  </>
                ) : (
                  `Guardar ${totalSelected}`
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
