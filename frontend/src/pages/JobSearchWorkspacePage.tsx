import { useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  Bookmark,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Download,
  FileSpreadsheet,
  Filter,
  Globe,
  Lightbulb,
  Linkedin,
  Loader2,
  Mail,
  MapPin,
  MessageCircle,
  Phone,
  Plus,
  Satellite,
  Search,
  Star,
} from "lucide-react";

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
  address?: string | null;
  website?: string | null;
  hours?: string | null;
  rating?: number | null;
  review_count?: number | null;
  source_type?: string | null;
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

const AVATAR_PALETTE = [
  { bg: "#DBEAFE", color: "#1D4ED8" },
  { bg: "#FEF3C7", color: "#D97706" },
  { bg: "#D1FAE5", color: "#059669" },
  { bg: "#EDE9FE", color: "#7C3AED" },
  { bg: "#FCE7F3", color: "#DB2777" },
  { bg: "#FEE2E2", color: "#DC2626" },
];

function getAvatarStyle(text: string) {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = ((h << 5) - h + text.charCodeAt(i)) | 0;
  return AVATAR_PALETTE[Math.abs(h) % AVATAR_PALETTE.length];
}

const LOADING_MESSAGES = [
  "Buscando en la web…",
  "Enriqueciendo datos…",
  "Verificando contactos…",
  "Analizando resultados…",
  "Casi listo…",
];

const TABLE_COLS = "48px minmax(220px,1fr) 150px 170px 110px";

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
  const [activeTab, setActiveTab] = useState<"results" | "dropped">("results");
  const [loadingMessageIndex, setLoadingMessageIndex] = useState(0);
  const [msgVisible, setMsgVisible] = useState(true);
  const [filterText, setFilterText] = useState("");
  const [lpaOpen, setLpaOpen] = useState(false);

  const downloadCsvMutation = useMutation({ mutationFn: () => downloadLeadsCsvFile(jobId, {}) });
  const downloadXlsxMutation = useMutation({ mutationFn: () => downloadLeadsXlsxFile(jobId, {}) });
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
      if (!data.ok) { setExaMoreMessage(data.error || "No se pudieron cargar más resultados"); return; }
      setExaMoreMessage(null);
      void queryClient.invalidateQueries({ queryKey: ["job-status", jobId] });
    },
    onError: (error: Error) => setExaMoreMessage(error.message),
  });

  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
  const [selectedSourceIndices, setSelectedSourceIndices] = useState<Set<number>>(new Set());
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [selectedDirectoryId, setSelectedDirectoryId] = useState<string | null>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savingAllSources, setSavingAllSources] = useState(false);
  const [allSourcesDirPickerOpen, setAllSourcesDirPickerOpen] = useState(false);
  const [allSourcesDirId, setAllSourcesDirId] = useState("");
  const [scraperOpen, setScraperOpen] = useState(false);
  const [scraperUrl, setScraperUrl] = useState<string | undefined>(undefined);
  const [scraperTitle, setScraperTitle] = useState<string | undefined>(undefined);
  const [sourcePickerUrl, setSourcePickerUrl] = useState<string | null>(null);
  const [sourcePickerDirId, setSourcePickerDirId] = useState<string>("");
  const [savedSourceUrls, setSavedSourceUrls] = useState<Set<string>>(new Set());

  const clarifyWorkspaceMutation = useMutation({
    mutationFn: (reply: string) => clarifySearchJob(jobId, { reply }),
    onSuccess: () => {
      setWorkspaceClarifyReply("");
      void queryClient.invalidateQueries({ queryKey: ["job-status", jobId] });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelSearchJob(jobId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["job-status", jobId] }),
  });

  const jobStatus = jobStatusQuery.data?.status;
  const awaitingClarification = Boolean(
    jobStatusQuery.data?.awaiting_clarification && jobStatus === "pending",
  );
  const isProcessing = (jobStatus === "pending" || jobStatus === "running") && !awaitingClarification;

  useEffect(() => {
    if (!isProcessing) return;
    const timer = setInterval(() => {
      setMsgVisible(false);
      setTimeout(() => {
        setLoadingMessageIndex((prev) => (prev + 1) % LOADING_MESSAGES.length);
        setMsgVisible(true);
      }, 500);
    }, 2500);
    return () => clearInterval(timer);
  }, [isProcessing]);

  const pipelineMode = jobStatusQuery.data?.pipeline_mode ?? null;
  const searchOnlyDemo =
    pipelineMode === "presearch_and_search_only" || (isProcessing && pipelineMode === null);
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
    for (const s of directoryQuery.data?.steps ?? []) map.set(s.id, s.name);
    return map;
  }, [directoryQuery.data]);

  const oppByPreviewIndex = useMemo(() => {
    const map = new Map<number, { stepId: string | null }>();
    for (const opp of jobOppsQuery.data?.items ?? []) {
      if (opp.exa_preview_index != null) map.set(opp.exa_preview_index, { stepId: opp.current_step_id });
    }
    return map;
  }, [jobOppsQuery.data?.items]);

  const rows: RowData[] = useMemo(() => {
    if (searchOnlyDemo) {
      return previewRows.map((row) => {
        type PreviewExt = typeof row & {
          email?: string | null;
          phone?: string | null;
          whatsapp?: string | null;
          linkedin_url?: string | null;
          enrichment_status?: string | null;
          address?: string | null;
          website?: string | null;
          hours?: string | null;
          rating?: number | null;
          review_count?: number | null;
          source_type?: string | null;
        };
        const r = row as PreviewExt;
        const idx = r.index;
        const opp = oppByPreviewIndex.get(idx);
        const stepName = opp?.stepId ? stepNameById.get(opp.stepId) : null;
        const rawLabel = (r as PreviewExt & { label?: string }).label;
        const label = LABEL_OPTIONS.some((o) => o.value === rawLabel) ? (rawLabel as PreviewLabel) : null;
        const isLocalBiz = r.source_type === "google_places" || r.source_type === "brave_local";
        return {
          id: `preview-${idx}`,
          title: (r.title ?? "").trim() || "Sin título",
          subtitle: isLocalBiz
            ? (r.address ?? null)
            : [r.specialty, r.city].filter(Boolean).join(" · ") || null,
          email: r.email ?? null,
          phone: r.phone ?? null,
          whatsapp: r.whatsapp ?? null,
          linkedin: r.linkedin_url ?? null,
          stepLabel: stepName ?? null,
          href: `/jobs/${jobId}/result/${idx}`,
          enriched: r.enrichment_status === "enriched",
          previewIndex: idx,
          label,
          address: r.address ?? null,
          website: r.website ?? null,
          hours: r.hours ?? null,
          rating: r.rating ?? null,
          review_count: r.review_count ?? null,
          source_type: r.source_type ?? null,
        };
      });
    }
    return persistedLeads.map((lead) => ({
      id: lead.lead_id,
      title: lead.full_name || "Sin título",
      subtitle: [lead.specialty, lead.city].filter(Boolean).join(" · ") || null,
      email: lead.email,
      phone: lead.phone,
      whatsapp: lead.whatsapp,
      linkedin: lead.linkedin_url,
      stepLabel: null,
      href: `/leads/${lead.lead_id}`,
      enriched: Boolean(lead.email || lead.whatsapp || lead.linkedin_url || lead.phone),
      previewIndex: null,
      label: null,
    }));
  }, [searchOnlyDemo, previewRows, persistedLeads, jobId, oppByPreviewIndex, stepNameById]);

  const filteredRows = useMemo(() => {
    if (!filterText.trim()) return rows;
    const q = filterText.toLowerCase();
    return rows.filter(
      (r) => r.title.toLowerCase().includes(q) || (r.subtitle ?? "").toLowerCase().includes(q),
    );
  }, [rows, filterText]);

  const totalRows = rows.length;
  const totalPages = Math.max(1, Math.ceil(filteredRows.length / tablePageSize));
  const currentPage = Math.min(tablePage, totalPages);
  const offset = (currentPage - 1) * tablePageSize;
  const paginated = filteredRows.slice(offset, offset + tablePageSize);

  useEffect(() => {
    if (prevJobIdRef.current !== jobId) {
      prevJobIdRef.current = jobId;
      setSearchParams(
        (prev: URLSearchParams) => { const n = new URLSearchParams(prev); n.delete("page"); return n; },
        { replace: true },
      );
    }
  }, [jobId, searchOnlyDemo, setSearchParams]);

  const handleSaveSelected = async () => {
    if (selectedIndices.size > 0 && !selectedStepId) return;
    const dirId = directoryId || selectedDirectoryId;
    if (selectedSourceIndices.size > 0 && !dirId) return;
    setSaving(true);
    for (const previewIndex of Array.from(selectedIndices)) {
      await createOpportunityFromPreview({
        job_id: jobId,
        exa_preview_index: previewIndex,
        step_id: selectedStepId || undefined,
      });
    }
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
    if (saved.length > 0) setSavedSourceUrls((prev) => new Set([...prev, ...saved]));
    setSavingAllSources(false);
    setAllSourcesDirPickerOpen(false);
    setAllSourcesDirId("");
  };

  const unsavedRows = rows.filter(
    (r) => r.previewIndex != null && !oppByPreviewIndex.has(r.previewIndex),
  );
  const unsavedCount = unsavedRows.length;
  const totalSelected = selectedIndices.size + selectedSourceIndices.size;

  useEffect(() => { setWorkspaceClarifyReply(""); }, [jobId]);

  const searchLabel =
    jobStatusQuery.data?.query_text?.trim() || passedState?.searchLabel?.trim() || "Búsqueda";
  const createdAt = jobStatusQuery.data?.created_at ?? jobStatusQuery.data?.updated_at;

  const statusLabel =
    awaitingClarification ? "Aclaración" :
    jobStatus === "completed" ? "Completado" :
    jobStatus === "error" ? "Error" :
    jobStatus === "cancelled" ? "Cancelada" : "En vivo";

  const statusColor =
    awaitingClarification ? "#D97706" :
    jobStatus === "completed" ? "#059669" :
    jobStatus === "error" || jobStatus === "cancelled" ? "#DC2626" : "#3B82F6";

  const statusBg =
    awaitingClarification ? "#FEF3C7" :
    jobStatus === "completed" ? "#D1FAE5" :
    jobStatus === "error" || jobStatus === "cancelled" ? "#FEE2E2" : "#DBEAFE";

  const suggestedSources = jobStatusQuery.data?.suggested_source_urls ?? [];
  const lpaItems = jobStatusQuery.data?.lpa_preview ?? [];
  const hasSidebar = !isProcessing && (suggestedSources.length > 0 || lpaItems.length > 0);
  const filterStats = jobStatusQuery.data?.filter_stats;

  const warnings = jobStatusQuery.data?.warnings ?? [];
  const placesError = warnings.find((w) => w.startsWith("PLACES_API_ERROR:"));
  const otherWarnings = warnings.filter((w) => !w.startsWith("PLACES_API_ERROR:"));

  return (
    <section className="workspace-v4">

      {/* ── TOP HEADER BAR ── */}
      <header style={{
        height: 72, background: "white", borderBottom: "1px solid #D3D3D3",
        padding: "0 32px", display: "flex", alignItems: "center",
        justifyContent: "space-between", flexShrink: 0, zIndex: 10,
      }}>
        <div>
          <nav style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#808080", marginBottom: 4 }}>
            {directoryQuery.data ? (
              <>
                <Link to="/lists" style={{ color: "#808080", textDecoration: "none" }}>
                  Listas
                </Link>
                <ChevronRight size={10} aria-hidden />
                <Link to={`/lists/${directoryQuery.data.id}`} style={{ color: "#808080", textDecoration: "none" }}>
                  {directoryQuery.data.name}
                </Link>
                <ChevronRight size={10} aria-hidden />
                <span style={{ color: "#0F172A" }}>Búsqueda</span>
              </>
            ) : (
              <>
                <Link to="/search" style={{ color: "#808080", textDecoration: "none" }}>
                  Prospecciones
                </Link>
                <ChevronRight size={10} aria-hidden />
                <span style={{ color: "#0F172A" }}>Búsqueda: {searchLabel}</span>
              </>
            )}
          </nav>
          <h1 style={{ fontSize: 15, fontWeight: 600, color: "#374151", margin: 0, lineHeight: 1.4, maxWidth: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {searchLabel}
          </h1>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ position: "relative" }}>
            <Search size={14} aria-hidden style={{
              position: "absolute", left: 10, top: "50%",
              transform: "translateY(-50%)", color: "#808080", pointerEvents: "none",
            }} />
            <input
              type="text"
              placeholder="Buscar en resultados..."
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              style={{
                width: 220, paddingLeft: 32, paddingRight: 12, paddingTop: 8, paddingBottom: 8,
                background: "#F8FAFC", border: "1px solid #D3D3D3", borderRadius: 8,
                fontSize: 13, outline: "none", fontFamily: "inherit", color: "#0F172A",
              }}
            />
          </div>
          <button
            type="button"
            style={{
              width: 36, height: 36, borderRadius: 8, border: "1px solid #D3D3D3",
              background: "white", display: "flex", alignItems: "center", justifyContent: "center",
              cursor: "pointer", color: "#808080",
            }}
            title="Filtrar"
          >
            <Filter size={14} aria-hidden />
          </button>
        </div>
      </header>

      {/* ── CONTENT ROW ── */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* LEFT: RESULTS COLUMN */}
        <div style={{
          flex: 1, display: "flex", flexDirection: "column", minWidth: 0,
          borderRight: hasSidebar ? "1px solid #D3D3D3" : "none",
          background: "#F8FAFC", overflow: "hidden",
        }}>

          {/* STATUS + ACTIONS BAR */}
          <div style={{
            padding: "16px 24px", background: "white",
            borderBottom: "1px solid #D3D3D3", flexShrink: 0,
          }}>
            <div style={{
              display: "flex", alignItems: "flex-start",
              justifyContent: "space-between", marginBottom: 14,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{
                  display: "inline-flex", alignItems: "center", gap: 6,
                  padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 500,
                  background: statusBg, color: statusColor, border: `1px solid ${statusColor}40`,
                }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: statusColor, flexShrink: 0 }} />
                  {statusLabel}
                </span>
                <span style={{ fontSize: 13, color: "#808080", fontWeight: 500 }}>
                  {totalRows} resultado{totalRows === 1 ? "" : "s"} encontrados
                </span>
                {createdAt ? (
                  <span style={{ fontSize: 12, color: "#9CA3AF" }}>· {formatRelative(createdAt)}</span>
                ) : null}
              </div>
              <div style={{ textAlign: "right" }}>
                <p style={{ fontSize: 11, color: "#9CA3AF", margin: "0 0 5px" }}>Progreso del Job</p>
                <div style={{
                  width: 120, height: 6, background: "#F3F4F6",
                  borderRadius: 999, overflow: "hidden", border: "1px solid #E5E7EB",
                }}>
                  <div style={{
                    height: "100%",
                    background: isProcessing ? "#3B82F6" : statusColor,
                    borderRadius: 999,
                    width: isProcessing ? "60%" : jobStatus === "completed" ? "100%" : "0%",
                    transition: "width 0.3s ease",
                  }} />
                </div>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {null}

                {jobStatus === "completed" && searchOnlyDemo && previewRows.length > 0 ? (
                  <>
                    <button
                      type="button"
                      disabled={unsavedCount === 0 || saving}
                      onClick={() => {
                        const notSaved = unsavedRows.map((r) => r.previewIndex!);
                        setSelectedIndices(new Set(notSaved));
                        setSelectedSourceIndices(new Set());
                        setSaveModalOpen(true);
                      }}
                      className="cta-button"
                      style={{
                        display: "flex", alignItems: "center", gap: 6,
                        fontSize: 13, padding: "7px 16px",
                        opacity: unsavedCount === 0 ? 0.45 : 1,
                        cursor: unsavedCount === 0 ? "not-allowed" : "pointer",
                      }}
                    >
                      <Bookmark size={13} aria-hidden />
                      {saving ? "Guardando…" : `Guardar todos (${unsavedCount})`}
                    </button>
                    {totalSelected > 0 && (
                      <button
                        type="button"
                        onClick={() => setSaveModalOpen(true)}
                        style={{
                          display: "flex", alignItems: "center", gap: 7,
                          padding: "7px 14px", background: "white",
                          border: "1px solid #D3D3D3", borderRadius: 8,
                          fontSize: 13, fontWeight: 500, cursor: "pointer",
                          fontFamily: "inherit", color: "#0F172A",
                        }}
                      >
                        <Bookmark size={13} aria-hidden />
                        Guardar seleccionados ({totalSelected})
                      </button>
                    )}
                  </>
                ) : null}
              </div>

              <div style={{ display: "flex", gap: 8 }}>
                {jobStatus === "completed" && searchOnlyDemo && (
                  <button
                    type="button"
                    disabled={downloadPreviewXlsxMutation.isPending}
                    onClick={() => downloadPreviewXlsxMutation.mutate()}
                    style={{
                      display: "flex", alignItems: "center", gap: 6,
                      padding: "7px 14px", background: "white",
                      border: "1px solid #D3D3D3", borderRadius: 8,
                      fontSize: 13, fontWeight: 500, cursor: "pointer",
                      fontFamily: "inherit", color: "#0F172A",
                    }}
                  >
                    <FileSpreadsheet size={14} style={{ color: "#059669" }} aria-hidden />
                    {downloadPreviewXlsxMutation.isPending ? "Generando…" : "Exportar Excel"}
                  </button>
                )}
                {jobStatus === "completed" && !searchOnlyDemo && (
                  <>
                    <Button
                      type="button" variant="secondary" size="sm"
                      disabled={downloadCsvMutation.isPending}
                      onClick={() => downloadCsvMutation.mutate()}
                    >
                      <Download size={13} aria-hidden />
                      {downloadCsvMutation.isPending ? "Generando…" : "Exportar"}
                    </Button>
                    <Button
                      type="button" variant="secondary" size="sm"
                      disabled={downloadXlsxMutation.isPending}
                      onClick={() => downloadXlsxMutation.mutate()}
                    >
                      <FileSpreadsheet size={13} aria-hidden />
                      {downloadXlsxMutation.isPending ? "Generando…" : "Excel"}
                    </Button>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* FILTER EVALUATION PANEL */}
          {filterStats && (filterStats.relevance_filter_kept != null || filterStats.relevance_filter_dropped != null) && (
            <div style={{
              padding: "12px 24px", background: "#FAFAFA",
              borderBottom: "1px solid #E5E7EB", flexShrink: 0,
              display: "flex", alignItems: "flex-start", gap: 24, flexWrap: "wrap",
            }}>
              {/* Pill stats */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#6B7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  Filtrado IA
                </span>
                {filterStats.relevance_filter_kept != null && (
                  <span style={{
                    display: "inline-flex", alignItems: "center", gap: 4,
                    padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600,
                    background: "#D1FAE5", color: "#065F46", border: "1px solid #A7F3D0",
                  }}>
                    ✓ {filterStats.relevance_filter_kept} aceptados
                  </span>
                )}
                {filterStats.relevance_filter_dropped != null && filterStats.relevance_filter_dropped > 0 && (
                  <span style={{
                    display: "inline-flex", alignItems: "center", gap: 4,
                    padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600,
                    background: "#FEE2E2", color: "#991B1B", border: "1px solid #FECACA",
                  }}>
                    ✕ {filterStats.relevance_filter_dropped} descartados
                  </span>
                )}
                {filterStats.relevance_filter_heuristic_drops != null && filterStats.relevance_filter_heuristic_drops > 0 && (
                  <span style={{
                    display: "inline-flex", alignItems: "center", gap: 4,
                    padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600,
                    background: "#FEF3C7", color: "#92400E", border: "1px solid #FDE68A",
                  }}>
                    ⚡ {filterStats.relevance_filter_heuristic_drops} por heurística
                  </span>
                )}
                {filterStats.relevance_filter_mode === "degraded_exception" && (
                  <span style={{
                    display: "inline-flex", alignItems: "center", gap: 4,
                    padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600,
                    background: "#FFF7ED", color: "#C2410C", border: "1px solid #FDBA74",
                  }}>
                    ⚠ Filtro degradado
                  </span>
                )}
              </div>

              {/* Sample drop reasons */}
              {filterStats.relevance_filter_discarded_sample && filterStats.relevance_filter_discarded_sample.length > 0 && (
                <div style={{ display: "flex", alignItems: "flex-start", gap: 6, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 11, color: "#9CA3AF", flexShrink: 0, paddingTop: 3 }}>Razones:</span>
                  <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                    {(() => {
                      const reasons = filterStats.relevance_filter_discarded_sample!;
                      const counted = reasons.reduce<Record<string, number>>((acc, r) => {
                        const key = r.reason_es || "Sin razón";
                        acc[key] = (acc[key] || 0) + 1;
                        return acc;
                      }, {});
                      return Object.entries(counted)
                        .sort(([, a], [, b]) => b - a)
                        .slice(0, 5)
                        .map(([reason, count]) => (
                          <span key={reason} style={{
                            fontSize: 11, padding: "2px 8px", borderRadius: 5,
                            background: "#F3F4F6", color: "#6B7280",
                            border: "1px solid #E5E7EB",
                          }}>
                            {count > 1 ? `${count}× ` : ""}{reason}
                          </span>
                        ));
                    })()}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB SWITCHER */}
          {filterStats?.relevance_filter_discarded_sample && filterStats.relevance_filter_discarded_sample.length > 0 && (
            <div style={{ display: "flex", borderBottom: "1px solid #E5E7EB", background: "white", flexShrink: 0, paddingLeft: 24 }}>
              <button
                type="button"
                onClick={() => setActiveTab("results")}
                style={{
                  padding: "10px 16px", fontSize: 13, fontWeight: 500,
                  border: "none", background: "none", cursor: "pointer",
                  borderBottom: activeTab === "results" ? "2px solid #4F46E5" : "2px solid transparent",
                  color: activeTab === "results" ? "#4F46E5" : "#6B7280",
                }}
              >
                Resultados ({totalRows})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("dropped")}
                style={{
                  padding: "10px 16px", fontSize: 13, fontWeight: 500,
                  border: "none", background: "none", cursor: "pointer",
                  borderBottom: activeTab === "dropped" ? "2px solid #EF4444" : "2px solid transparent",
                  color: activeTab === "dropped" ? "#EF4444" : "#6B7280",
                }}
              >
                Descartados ({filterStats.relevance_filter_discarded_sample.length})
              </button>
            </div>
          )}

          {/* SCROLLABLE RESULTS AREA */}
          <div style={{ flex: 1, overflowY: "auto", padding: 24 }}>

            {/* Errors / Warnings */}
            {jobStatusQuery.isError && (
              <p className="error-text" role="alert" style={{ marginBottom: 16 }}>
                {jobStatusQuery.error instanceof Error
                  ? jobStatusQuery.error.message
                  : "No se pudo consultar el estado del trabajo."}
              </p>
            )}
            {exaMoreMessage && (
              <p className="error-text" style={{ marginBottom: 16 }}>{exaMoreMessage}</p>
            )}
            {placesError && (
              <div role="alert" style={{
                background: "#FFF7ED", border: "2px solid #F97316", borderRadius: 12,
                padding: "16px 20px", marginBottom: 16, display: "flex", gap: 14, alignItems: "flex-start",
              }}>
                <span style={{ fontSize: 22, flexShrink: 0 }}>⚠️</span>
                <div>
                  <p style={{ fontWeight: 700, color: "#C2410C", margin: "0 0 6px", fontSize: 15 }}>
                    Google Places API no está habilitada
                  </p>
                  <p style={{ color: "#9A3412", fontSize: 13, margin: "0 0 10px" }}>
                    {placesError.replace("PLACES_API_ERROR:", "").trim()}
                  </p>
                  <p style={{ color: "#7C2D12", fontSize: 12, margin: 0, lineHeight: 1.5 }}>
                    <strong>Para activarla:</strong> ve a{" "}
                    <strong>Google Cloud Console → APIs y servicios → Habilitar APIs</strong>{" "}
                    → busca <em>"Places API (New)"</em> → Habilitar.
                  </p>
                </div>
              </div>
            )}
            {otherWarnings.length > 0 && (
              <div className="workspace-v3-warnings" role="status" style={{ marginBottom: 16 }}>
                {otherWarnings.map((w, i) => (
                  <p key={i} className="workspace-v3-warning-text">{w}</p>
                ))}
              </div>
            )}

            {/* MAIN CONTENT */}
            {activeTab === "dropped" && filterStats?.relevance_filter_discarded_sample && filterStats.relevance_filter_discarded_sample.length > 0 ? (
              <div style={{
                background: "white", border: "1px solid #D3D3D3",
                borderRadius: 12, overflow: "hidden",
                boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
              }}>
                <div style={{
                  display: "grid", gridTemplateColumns: "1fr 220px",
                  gap: "0 12px", padding: "10px 16px",
                  borderBottom: "1px solid #D3D3D3", background: "#F8FAFC",
                  fontSize: 11, fontWeight: 600, color: "#808080",
                  textTransform: "uppercase", letterSpacing: "0.05em",
                }}>
                  <div>URL descartada</div>
                  <div>Razón</div>
                </div>
                {filterStats.relevance_filter_discarded_sample.map((item, i) => (
                  <div key={i} style={{
                    display: "grid", gridTemplateColumns: "1fr 220px",
                    gap: "0 12px", padding: "9px 16px",
                    borderBottom: "1px solid #F3F4F6", alignItems: "center",
                  }}>
                    <a
                      href={item.url.startsWith("http") ? item.url : `https://${item.url}`}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        fontSize: 12, color: "#4F46E5", textDecoration: "none",
                        overflow: "hidden", textOverflow: "ellipsis",
                        whiteSpace: "nowrap", display: "block",
                      }}
                    >
                      {item.url}
                    </a>
                    <span style={{ fontSize: 12, color: "#6B7280" }}>{item.reason_es || "—"}</span>
                  </div>
                ))}
              </div>
            ) : awaitingClarification ? (
              <div style={{
                background: "white", border: "1px solid #D3D3D3",
                borderRadius: 12, padding: 24, maxWidth: 560,
              }}>
                <p style={{ fontWeight: 600, color: "#0F172A", marginBottom: 8 }}>
                  El plan de búsqueda necesita un dato más.
                </p>
                <p style={{ color: "#808080", fontSize: 14, marginBottom: 16 }}>
                  {jobStatusQuery.data?.clarifying_question}
                </p>
                <label className="search-clarify-label" htmlFor="workspace-clarify-reply">
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
                {clarifyWorkspaceMutation.isError && (
                  <p className="error-text" role="alert">
                    {clarifyWorkspaceMutation.error instanceof Error
                      ? clarifyWorkspaceMutation.error.message
                      : "No se pudo enviar la aclaración."}
                  </p>
                )}
                <Button
                  type="button"
                  className="cta-button"
                  style={{ marginTop: 12 }}
                  disabled={clarifyWorkspaceMutation.isPending || workspaceClarifyReply.trim().length < 1}
                  onClick={() => clarifyWorkspaceMutation.mutate(workspaceClarifyReply.trim())}
                >
                  {clarifyWorkspaceMutation.isPending ? (
                    <><Loader2 className="spin" size={16} aria-hidden /> Enviando…</>
                  ) : "Continuar búsqueda"}
                </Button>
              </div>
            ) : jobStatus === "error" ? (
              <div style={{
                background: "white", border: "1px solid #FCA5A5",
                borderRadius: 12, padding: 24,
              }}>
                <p className="error-text" style={{ marginBottom: 8 }}>
                  <strong>No se pudo completar la búsqueda.</strong>
                </p>
                <p style={{ color: "#808080", fontSize: 14 }}>
                  {jobStatusQuery.data?.error_message || "Revisa los logs del backend o vuelve a intentar."}
                </p>
              </div>
            ) : isProcessing && rows.length === 0 ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", flex: 1, padding: "40px 24px" }}>
                <div className="loading-card">
                  <div className="loading-card__glow" />
                  <div className="loading-card__radar">
                    <div className="loading-card__ring loading-card__ring--1" />
                    <div className="loading-card__ring loading-card__ring--2" />
                    <div className="loading-card__ring loading-card__ring--3" />
                    <div className="loading-card__node">
                      <Satellite size={28} className="loading-card__node-icon" aria-hidden />
                    </div>
                    <div className="loading-card__orbit">
                      <div className="loading-card__orbit-dot" />
                    </div>
                    <div className="loading-card__orbit loading-card__orbit--slow">
                      <div className="loading-card__orbit-dot loading-card__orbit-dot--gray" />
                    </div>
                  </div>
                  <div className="loading-card__status-wrap">
                    <p className="loading-card__status" style={{ opacity: msgVisible ? 1 : 0 }}>
                      {LOADING_MESSAGES[loadingMessageIndex]}
                    </p>
                  </div>
                  <div className="loading-card__bar-track">
                    <div className="loading-card__bar-fill" />
                  </div>

                  {/* ACTIVITY FEED */}
                  {jobStatusQuery.data?.activity_log && jobStatusQuery.data.activity_log.length > 0 && (
                    <div style={{
                      marginTop: 16, background: "#F8FAFC", borderRadius: 8,
                      border: "1px solid #E5E7EB", padding: "10px 14px",
                      fontFamily: "monospace", fontSize: 11, color: "#6B7280",
                      maxHeight: 130, overflowY: "auto", textAlign: "left",
                    }}>
                      {jobStatusQuery.data.activity_log.slice(-6).map((entry, i) => (
                        <div key={i} style={{ marginBottom: 3 }}>
                          <span style={{ color: "#9CA3AF" }}>{entry.t.slice(11, 19)}</span>
                          {" "}{entry.msg}
                          {entry.found !== undefined && (
                            <span style={{ color: "#4F46E5" }}> → {entry.found} nuevos</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  <button
                    type="button"
                    className="loading-card__cancel"
                    disabled={cancelMutation.isPending}
                    onClick={() => cancelMutation.mutate()}
                  >
                    {cancelMutation.isPending ? "Cancelando…" : "Detener búsqueda"}
                  </button>
                </div>
              </div>
            ) : rows.length === 0 ? (
              <p style={{ color: "#808080", textAlign: "center", padding: "60px 0" }}>
                Sin coincidencias.
              </p>
            ) : (
              <>
                {/* RESULTS TABLE */}
                <div style={{
                  background: "white", border: "1px solid #D3D3D3",
                  borderRadius: 12, overflow: "hidden",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                }}>

                  {/* Table header row */}
                  <div style={{
                    display: "grid", gridTemplateColumns: TABLE_COLS, gap: "0 12px",
                    padding: "10px 16px", borderBottom: "1px solid #D3D3D3",
                    background: "#F8FAFC", fontSize: 11, fontWeight: 600,
                    color: "#808080", textTransform: "uppercase", letterSpacing: "0.05em",
                    alignItems: "center",
                  }}>
                    <div style={{ display: "flex", justifyContent: "center" }}>
                      <input
                        type="checkbox"
                        style={{ width: 15, height: 15, cursor: "pointer" }}
                        checked={
                          searchOnlyDemo &&
                          unsavedRows.length > 0 &&
                          unsavedRows.every((r) => selectedIndices.has(r.previewIndex!))
                        }
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedIndices(new Set(unsavedRows.map((r) => r.previewIndex!)));
                            setSelectedSourceIndices(new Set());
                          } else {
                            setSelectedIndices(new Set());
                          }
                        }}
                        readOnly={!searchOnlyDemo}
                      />
                    </div>
                    <div>Perfil</div>
                    <div>Contacto</div>
                    <div>Acción</div>
                    <div style={{ textAlign: "right" }}>Estado</div>
                  </div>

                  {/* Data rows */}
                  {paginated.map((row) => {
                    const isLocalBiz =
                      row.source_type === "google_places" || row.source_type === "brave_local";
                    const isSaved = oppByPreviewIndex.has(row.previewIndex ?? -1);
                    const avStyle = getAvatarStyle(row.title);

                    return (
                      <div
                        key={row.id}
                        className="ws-result-row"
                        style={{
                          display: "grid", gridTemplateColumns: TABLE_COLS, gap: "0 12px",
                          padding: "12px 16px", borderBottom: "1px solid #F3F4F6",
                          alignItems: "center",
                        }}
                      >
                        {/* Checkbox */}
                        <div style={{ display: "flex", justifyContent: "center" }}>
                          {searchOnlyDemo && row.previewIndex != null && !isSaved ? (
                            <input
                              type="checkbox"
                              style={{ width: 15, height: 15, cursor: "pointer" }}
                              checked={selectedIndices.has(row.previewIndex)}
                              onChange={() => {
                                const idx = row.previewIndex!;
                                setSelectedIndices((prev) => {
                                  const next = new Set(prev);
                                  next.has(idx) ? next.delete(idx) : next.add(idx);
                                  return next;
                                });
                                setSelectedSourceIndices((prev) => {
                                  const next = new Set(prev); next.delete(idx); return next;
                                });
                              }}
                            />
                          ) : null}
                        </div>

                        {/* Profile */}
                        <Link
                          to={row.href}
                          style={{ display: "flex", alignItems: "center", gap: 12, textDecoration: "none", overflow: "hidden" }}
                        >
                          <div style={{
                            width: 38, height: 38, borderRadius: "50%", flexShrink: 0,
                            background: avStyle.bg, color: avStyle.color,
                            display: "flex", alignItems: "center", justifyContent: "center",
                            fontWeight: 700, fontSize: 13,
                            border: `1px solid ${avStyle.color}30`,
                          }}>
                            {isLocalBiz ? <MapPin size={15} /> : initial(row.title)}
                          </div>
                          <div style={{ overflow: "hidden" }}>
                            <p style={{
                              fontWeight: 600, fontSize: 13, color: "#0F172A",
                              margin: 0, display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap",
                            }}>
                              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {stripEmojis(row.title)}
                              </span>
                              {row.rating != null && row.rating > 0 && (
                                <span style={{
                                  display: "inline-flex", alignItems: "center", gap: 2,
                                  fontSize: 11, color: "#F59E0B", flexShrink: 0,
                                }}>
                                  <Star size={10} fill="#F59E0B" />
                                  {row.rating.toFixed(1)}
                                  {row.review_count ? (
                                    <span style={{ color: "#9CA3AF" }}>({row.review_count})</span>
                                  ) : null}
                                </span>
                              )}
                            </p>
                            {row.subtitle ? (
                              <p style={{
                                fontSize: 11, color: "#808080",
                                margin: "2px 0 0", overflow: "hidden",
                                textOverflow: "ellipsis", whiteSpace: "nowrap",
                              }}>
                                {row.subtitle}
                              </p>
                            ) : null}
                          </div>
                        </Link>

                        {/* Contact icons */}
                        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                          {row.email && (
                            <a
                              href={`mailto:${row.email}`}
                              className="ws-contact-btn"
                              title={row.email}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <Mail size={12} />
                            </a>
                          )}
                          {row.whatsapp && (
                            <a
                              href={`https://wa.me/${row.whatsapp.replace(/\D/g, "")}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="ws-contact-btn ws-contact-btn--wa"
                              title={`WhatsApp: ${row.whatsapp}`}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <MessageCircle size={12} />
                            </a>
                          )}
                          {row.linkedin && (
                            <a
                              href={row.linkedin}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="ws-contact-btn ws-contact-btn--li"
                              title="LinkedIn"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <Linkedin size={12} />
                            </a>
                          )}
                          {row.phone && !row.whatsapp && (
                            <a
                              href={`tel:${row.phone}`}
                              className="ws-contact-btn"
                              title={row.phone}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <Phone size={12} />
                            </a>
                          )}
                          {row.website && (
                            <a
                              href={row.website}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="ws-contact-btn"
                              title="Web"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <Globe size={12} />
                            </a>
                          )}
                          {!row.email && !row.whatsapp && !row.linkedin && !row.phone && !row.website && (
                            <span style={{ fontSize: 11, color: "#D1D5DB" }}>—</span>
                          )}
                        </div>

                        {/* Action / label */}
                        <div>
                          {searchOnlyDemo && row.previewIndex != null ? (
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
                              <option value="">Marcar como...</option>
                              {LABEL_OPTIONS.map((o) => (
                                <option key={o.value} value={o.value}>{o.label}</option>
                              ))}
                            </select>
                          ) : row.stepLabel ? (
                            <span className="workspace-v3-row-step">{row.stepLabel}</span>
                          ) : null}
                        </div>

                        {/* Status badge */}
                        <div style={{ textAlign: "right" }}>
                          {isSaved ? (
                            <span style={{
                              display: "inline-flex", alignItems: "center", gap: 5,
                              padding: "4px 10px", borderRadius: 20, fontSize: 11, fontWeight: 500,
                              background: "#D1FAE5", color: "#059669",
                            }}>
                              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#059669", flexShrink: 0 }} />
                              Guardado
                            </span>
                          ) : null}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Pagination */}
                {filteredRows.length > tablePageSize && (
                  <div style={{
                    marginTop: 20, display: "flex",
                    justifyContent: "center", alignItems: "center", gap: 12,
                  }}>
                    <Button
                      type="button" variant="ghost" size="sm"
                      disabled={currentPage <= 1}
                      onClick={() => setTablePage(Math.max(1, currentPage - 1))}
                    >
                      Anterior
                    </Button>
                    <span style={{ fontSize: 13, color: "#808080" }}>
                      {currentPage} / {totalPages}
                    </span>
                    <Button
                      type="button" variant="ghost" size="sm"
                      disabled={currentPage >= totalPages}
                      onClick={() => setTablePage(Math.min(totalPages, currentPage + 1))}
                    >
                      Siguiente
                    </Button>
                  </div>
                )}

                {/* Load more from API */}
                {jobStatus === "completed" && searchOnlyDemo && (
                  <div style={{ marginTop: 20, display: "flex", justifyContent: "center" }}>
                    <button
                      type="button"
                      disabled={exaMoreMutation.isPending}
                      onClick={() => { setExaMoreMessage(null); exaMoreMutation.mutate(); }}
                      style={{
                        display: "flex", alignItems: "center", gap: 8,
                        padding: "9px 20px", background: "white",
                        border: "1px solid #D3D3D3", borderRadius: 8,
                        fontSize: 13, fontWeight: 500,
                        cursor: exaMoreMutation.isPending ? "not-allowed" : "pointer",
                        fontFamily: "inherit", color: "#0F172A",
                      }}
                    >
                      {exaMoreMutation.isPending ? (
                        <><Loader2 size={14} className="spin" aria-hidden /> Cargando…</>
                      ) : (
                        <>Cargar más resultados <ChevronDown size={14} aria-hidden /></>
                      )}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* RIGHT: INSIGHTS SIDEBAR */}
        {hasSidebar && (
          <aside style={{
            width: 310, background: "white", flexShrink: 0,
            overflowY: "auto",
          }}>

            {/* Fuentes Sugeridas */}
            {suggestedSources.length > 0 && (
              <div style={{
                padding: "20px 18px 16px",
                borderBottom: lpaItems.length > 0 ? "1px solid #D3D3D3" : "none",
              }}>
                <h3 style={{
                  margin: "0 0 14px", fontSize: 11, fontWeight: 700, color: "#0F172A",
                  textTransform: "uppercase", letterSpacing: "0.06em",
                  display: "flex", alignItems: "center", gap: 7,
                }}>
                  <Lightbulb size={14} style={{ color: "#F59E0B" }} aria-hidden />
                  Fuentes Sugeridas
                </h3>

                {/* Save-all header */}
                {(() => {
                  const unsavedSources = suggestedSources.filter((s) => !savedSourceUrls.has(s.url));
                  if (unsavedSources.length === 0) return null;
                  return (
                    <div style={{ marginBottom: 12 }}>
                      {directoryId ? (
                        <Button
                          type="button" variant="ghost" size="sm"
                          className="workspace-v3-sources-btn"
                          disabled={savingAllSources}
                          onClick={() => handleSaveAllSources(directoryId)}
                        >
                          {savingAllSources
                            ? <><Loader2 className="spin" size={12} aria-hidden /> Guardando…</>
                            : `Guardar todas (${unsavedSources.length})`}
                        </Button>
                      ) : allSourcesDirPickerOpen ? (
                        <div className="sources-dir-picker">
                          <div className="sources-dir-picker-list">
                            {directoriesQuery.isLoading
                              ? <span className="muted-text" style={{ fontSize: 12, padding: "6px 10px", display: "block" }}>
                                  <Loader2 className="spin" size={12} aria-hidden /> Cargando…
                                </span>
                              : (directoriesQuery.data?.items ?? []).map((d) => (
                                <button
                                  key={d.id} type="button"
                                  className={`sources-dir-picker-opt${allSourcesDirId === d.id ? " is-selected" : ""}`}
                                  onClick={() => setAllSourcesDirId(d.id)}
                                >
                                  {d.name}
                                </button>
                              ))}
                          </div>
                          <div className="sources-dir-picker-actions">
                            <Button
                              type="button" variant="default" size="sm"
                              disabled={!allSourcesDirId || savingAllSources}
                              onClick={() => handleSaveAllSources(allSourcesDirId)}
                            >
                              {savingAllSources
                                ? <><Loader2 className="spin" size={12} aria-hidden /> Guardando…</>
                                : "Guardar"}
                            </Button>
                            <Button
                              type="button" variant="ghost" size="sm"
                              onClick={() => { setAllSourcesDirPickerOpen(false); setAllSourcesDirId(""); }}
                            >
                              Cancelar
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <Button
                          type="button" variant="ghost" size="sm"
                          className="workspace-v3-sources-btn"
                          onClick={() => setAllSourcesDirPickerOpen(true)}
                        >
                          Guardar todas ({unsavedSources.length})
                        </Button>
                      )}
                    </div>
                  );
                })()}

                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {suggestedSources.map((s) => (
                    <div key={s.url} style={{
                      padding: "10px 12px", background: "#F8FAFC",
                      border: "1px solid #E5E7EB", borderRadius: 10,
                    }}>
                      <div style={{
                        display: "flex", justifyContent: "space-between",
                        alignItems: "flex-start", marginBottom: 5, gap: 6,
                      }}>
                        <span style={{
                          fontSize: 11, fontWeight: 600, color: "#0000FF",
                          background: "rgba(0,0,255,0.08)", padding: "2px 7px",
                          borderRadius: 4, flexShrink: 1, overflow: "hidden",
                          textOverflow: "ellipsis", whiteSpace: "nowrap",
                        }}>
                          {stripEmojis(s.title || "Fuente")}
                        </span>
                        <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                          {directoryId && (
                            <button
                              type="button"
                              className="ws-contact-btn"
                              title="Buscar por URL"
                              onClick={() => {
                                setScraperUrl(s.url);
                                setScraperTitle(s.title);
                                setScraperOpen(true);
                              }}
                            >
                              <Search size={11} />
                            </button>
                          )}
                          {savedSourceUrls.has(s.url) ? (
                            <span style={{ fontSize: 11, color: "#059669", padding: "2px 4px" }}>✓</span>
                          ) : (
                            <button
                              type="button"
                              className="ws-contact-btn"
                              title="Guardar en lista"
                              onClick={async () => {
                                if (directoryId) {
                                  try {
                                    await createDirectorySource(directoryId, {
                                      url: s.url, title: s.title, source_search_job_id: jobId,
                                    });
                                    setSavedSourceUrls((prev) => new Set([...prev, s.url]));
                                  } catch { /* silent */ }
                                } else {
                                  setSourcePickerUrl(s.url);
                                  setSourcePickerDirId("");
                                }
                              }}
                            >
                              <Plus size={11} />
                            </button>
                          )}
                        </div>
                      </div>
                      <p style={{
                        fontSize: 11, color: "#374151", margin: 0,
                        wordBreak: "break-all", lineHeight: 1.4,
                      }}>
                        {s.url.replace(/^https?:\/\//, "").slice(0, 52)}
                        {s.url.replace(/^https?:\/\//, "").length > 52 ? "…" : ""}
                      </p>
                      {sourcePickerUrl === s.url && (
                        <div className="sources-dir-picker sources-dir-picker--inline" style={{ marginTop: 8 }}>
                          <div className="sources-dir-picker-list">
                            {(directoriesQuery.data?.items ?? []).map((d) => (
                              <button
                                key={d.id} type="button"
                                className={`sources-dir-picker-opt${sourcePickerDirId === d.id ? " is-selected" : ""}`}
                                onClick={() => setSourcePickerDirId(d.id)}
                              >
                                {d.name}
                              </button>
                            ))}
                          </div>
                          <div className="sources-dir-picker-actions">
                            <Button
                              type="button" variant="default" size="sm"
                              disabled={!sourcePickerDirId}
                              onClick={async () => {
                                if (!sourcePickerDirId) return;
                                try {
                                  await createDirectorySource(sourcePickerDirId, {
                                    url: s.url, title: s.title, source_search_job_id: jobId,
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
                              type="button" variant="ghost" size="sm"
                              onClick={() => { setSourcePickerUrl(null); setSourcePickerDirId(""); }}
                            >
                              Cancelar
                            </Button>
                          </div>
                        </div>
                      )}
                      <a
                        href={s.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: 11, color: "#0000FF", textDecoration: "none", display: "inline-block", marginTop: 5 }}
                      >
                        Abrir →
                      </a>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Alternativas Bajas (LPA) */}
            {lpaItems.length > 0 && (
              <div style={{ padding: "16px 18px" }}>
                <button
                  type="button"
                  onClick={() => setLpaOpen((o) => !o)}
                  style={{
                    width: "100%", display: "flex", alignItems: "center",
                    justifyContent: "space-between", background: "none",
                    border: "none", cursor: "pointer", padding: 0, marginBottom: lpaOpen ? 12 : 0,
                    fontSize: 11, fontWeight: 700, color: "#0F172A",
                    textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "inherit",
                  }}
                  aria-expanded={lpaOpen}
                >
                  <span style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    <AlertTriangle size={13} style={{ color: "#FF0000" }} aria-hidden />
                    Alternativas Bajas ({lpaItems.length})
                  </span>
                  {lpaOpen
                    ? <ChevronUp size={13} style={{ color: "#808080" }} />
                    : <ChevronDown size={13} style={{ color: "#808080" }} />}
                </button>

                {lpaOpen && (
                  <>
                    <p style={{ fontSize: 12, color: "#808080", marginBottom: 10 }}>
                      Clínicas, centros o profesionales adyacentes. No son leads directos pero vale la pena explorarlos.
                    </p>
                    <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                      {lpaItems.map((row) => (
                        <Link
                          key={row.url}
                          to={`/jobs/${jobId}/result/${row.index}`}
                          style={{
                            display: "flex", alignItems: "center", gap: 10,
                            padding: "8px 10px", background: "#FFF7ED",
                            border: "1px solid #FED7AA", borderRadius: 8,
                            textDecoration: "none",
                          }}
                        >
                          <div style={{
                            width: 26, height: 26, borderRadius: "50%", background: "#FEF3C7",
                            color: "#D97706", display: "flex", alignItems: "center",
                            justifyContent: "center", fontSize: 11, fontWeight: 700, flexShrink: 0,
                          }}>
                            {row.title.charAt(0).toUpperCase() || "?"}
                          </div>
                          <div style={{ overflow: "hidden", flex: 1 }}>
                            <p style={{
                              fontSize: 12, fontWeight: 600, color: "#92400E",
                              margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                            }}>
                              {row.title || row.url}
                            </p>
                            {row.snippet && (
                              <p style={{
                                fontSize: 11, color: "#B45309", margin: "2px 0 0",
                                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                              }}>
                                {row.snippet}
                              </p>
                            )}
                          </div>
                          <ChevronRight size={12} style={{ color: "#D97706", flexShrink: 0 }} />
                        </Link>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
          </aside>
        )}
      </div>

      {/* ── MODALS ── */}
      {scraperOpen && directoryId && directoryQuery.data && (
        <UrlScraperModal
          isOpen={scraperOpen}
          onClose={() => setScraperOpen(false)}
          directoryId={directoryId}
          steps={directoryQuery.data.steps}
          prefillUrl={scraperUrl}
          prefillTitle={scraperTitle}
        />
      )}

      {saveModalOpen && (
        <div className="modal-overlay-save-opp" onClick={() => setSaveModalOpen(false)}>
          <div className="modal-save-opp" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-save-opp-title">
              {directoryId && directoryQuery.data
                ? `Enviar a: ${directoryQuery.data.name}`
                : "¿A qué lista enviar?"}
            </h3>
            <p className="modal-save-opp-subtitle">
              {selectedIndices.size > 0 && `${selectedIndices.size} oportunidad${selectedIndices.size !== 1 ? "es" : ""}`}
              {selectedIndices.size > 0 && selectedSourceIndices.size > 0 && " · "}
              {selectedSourceIndices.size > 0 && `${selectedSourceIndices.size} fuente${selectedSourceIndices.size !== 1 ? "s" : ""}`}
            </p>

            {directoryId && directoryQuery.data ? (
              selectedIndices.size > 0 ? (
                <div className="modal-save-opp-steps" style={{ marginTop: 16 }}>
                  <p style={{ marginBottom: 8, fontSize: 13, color: "var(--text-muted)" }}>Selecciona la fase:</p>
                  {directoryQuery.data.steps.filter((s) => !s.is_terminal).length === 0 ? (
                    <p className="modal-save-opp-empty muted-text">Sin steps disponibles</p>
                  ) : (
                    directoryQuery.data.steps
                      .filter((s) => !s.is_terminal)
                      .map((step) => (
                        <button
                          key={step.id} type="button"
                          className={`modal-save-opp-step-btn${selectedStepId === step.id ? " is-selected" : ""}`}
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
                    <Loader2 className="spin" size={16} aria-hidden /> Cargando directorios…
                  </div>
                )}
                {directoriesQuery.data?.items?.length === 0 && (
                  <p className="modal-save-opp-empty muted-text">Sin directorios disponibles</p>
                )}
                {directoriesQuery.data?.items.map((dir) => (
                  <div key={dir.id} className="modal-save-opp-directory">
                    <button
                      type="button"
                      className={`modal-save-opp-dir-btn${selectedDirectoryId === dir.id ? " is-selected" : ""}`}
                      onClick={() => setSelectedDirectoryId((d) => (d === dir.id ? null : dir.id))}
                    >
                      {dir.name}
                    </button>
                    {selectedDirectoryId === dir.id && (
                      <div className="modal-save-opp-steps">
                        {dir.steps.filter((s) => !s.is_terminal).length === 0 ? (
                          <p className="modal-save-opp-empty muted-text">Sin steps disponibles</p>
                        ) : (
                          dir.steps.filter((s) => !s.is_terminal).map((step) => (
                            <button
                              key={step.id} type="button"
                              className={`modal-save-opp-step-btn${selectedStepId === step.id ? " is-selected" : ""}`}
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
              <Button type="button" variant="ghost" size="sm" onClick={() => setSaveModalOpen(false)}>
                Cancelar
              </Button>
              <Button
                type="button" variant="default" size="sm"
                onClick={handleSaveSelected}
                disabled={(selectedIndices.size > 0 && !selectedStepId) || saving}
              >
                {saving ? (
                  <><Loader2 className="spin" size={13} aria-hidden /> Guardando…</>
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
