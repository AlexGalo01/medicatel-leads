import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ExternalLink, Globe, Loader, MapPin, Phone, Mail, Sparkles } from "lucide-react";

const SCRAPE_TABLE_COLS = "48px minmax(150px,1fr) minmax(150px,1fr) 100px";

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

function initial(text: string): string {
  const t = text.trim();
  return t ? t.charAt(0).toUpperCase() : "?";
}

import { cancelUrlScrapeJob, enrichUrlScrapeProfiles, getDirectory, getUrlScrapeJobStatus, pushScrapeEntriesToDirectory } from "../api";
import { Button } from "../components/ui/button";

const ITEMS_PER_PAGE = 30;

export function UrlScrapeJobPage(): JSX.Element {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const stepIdFromUrl = searchParams.get("stepId") ?? undefined;
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
  const [pushed, setPushed] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [enrichingRows, setEnrichingRows] = useState<Set<number>>(new Set());

  const jobQuery = useQuery({
    queryKey: ["url-scrape-job", jobId],
    queryFn: () => getUrlScrapeJobStatus(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "error" || status === "cancelled" ? false : 2000;
    },
  });

  const job = jobQuery.data;
  const directoryId = job?.directory_id ?? null;

  const directoryQuery = useQuery({
    queryKey: ["directory", directoryId],
    queryFn: () => getDirectory(directoryId!),
    enabled: Boolean(directoryId),
  });

  const pushMutation = useMutation({
    mutationFn: () =>
      pushScrapeEntriesToDirectory(
        jobId!,
        directoryId!,
        selectedIndices.size > 0 ? Array.from(selectedIndices) : [],
        stepIdFromUrl,
      ),
    onSuccess: () => {
      setPushed(true);
      void queryClient.invalidateQueries({ queryKey: ["directory-items", directoryId] });
      setTimeout(() => navigate(`/lists/${directoryId}`), 1500);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelUrlScrapeJob(jobId!),
    onSuccess: () => {
      void jobQuery.refetch();
    },
  });

  const enrichMutation = useMutation({
    mutationFn: () =>
      enrichUrlScrapeProfiles(jobId!, selectedIndices.size > 0 ? Array.from(selectedIndices) : undefined),
    onSuccess: () => {
      void jobQuery.refetch();
    },
  });

  // Clear per-row enriching state when job returns to completed
  useEffect(() => {
    if (job?.status === "completed" && enrichingRows.size > 0) {
      setEnrichingRows(new Set());
    }
  }, [job?.status, enrichingRows.size]);

  const enrichRow = async (index: number) => {
    if (enrichingRows.has(index) || job?.status !== "completed") return;
    setEnrichingRows((prev) => new Set([...prev, index]));
    try {
      await enrichUrlScrapeProfiles(jobId!, [index]);
      void jobQuery.refetch();
    } catch {
      setEnrichingRows((prev) => {
        const next = new Set(prev);
        next.delete(index);
        return next;
      });
    }
  };

  const preview = job?.scrape_results_preview ?? [];
  const isRunning = jobQuery.isLoading || job?.status === "running" || job?.status === "pending";
  const isCompleted = job?.status === "completed";
  const isError = job?.status === "error";
  const isCancelled = job?.status === "cancelled";

  // Check if there are entries that need enrichment (have URL but no phones/emails)
  const needsEnrichment = preview.some(
    (item) =>
      item.url &&
      item.url.trim().length > 0 &&
      (!item.phones || item.phones.length === 0) &&
      (!item.emails || item.emails.length === 0),
  );
  const isEnriching = job?.status === "running" && job?.stage === "enriching";

  const totalPages = Math.ceil(preview.length / ITEMS_PER_PAGE);
  const startIdx = (currentPage - 1) * ITEMS_PER_PAGE;
  const endIdx = startIdx + ITEMS_PER_PAGE;
  const paginatedItems = preview.slice(startIdx, endIdx);

  const togglePageItems = () => {
    const allPageItemsSelected = paginatedItems.every((item) =>
      selectedIndices.has(item.index)
    );

    const next = new Set(selectedIndices);
    if (allPageItemsSelected) {
      paginatedItems.forEach((item) => next.delete(item.index));
    } else {
      paginatedItems.forEach((item) => next.add(item.index));
    }
    setSelectedIndices(next);
  };

  const dirName = directoryQuery.data?.name ?? "Lista";

  return (
    <div className="url-scrape-job-page">
      {/* Breadcrumb */}
      <nav className="url-scrape-job-breadcrumb">
        {directoryId ? (
          <Link to={`/lists/${directoryId}`} className="url-scrape-job-back">
            <ChevronLeft size={15} aria-hidden /> {dirName}
          </Link>
        ) : (
          <Link to="/lists" className="url-scrape-job-back">
            <ChevronLeft size={15} aria-hidden /> Listas
          </Link>
        )}
        <span className="url-scrape-job-breadcrumb-sep">/</span>
        <span className="url-scrape-job-breadcrumb-current">Importar URL</span>
      </nav>

      {/* Header */}
      <header className="url-scrape-job-header">
        <div>
          <h1 className="url-scrape-job-title">
            {isError
              ? "Error en extracción"
              : isRunning && preview.length === 0
                ? "Extrayendo…"
                : isRunning
                  ? `${preview.length} entradas hasta ahora…`
                  : `${preview.length} entradas encontradas`}
          </h1>
          <p className="url-scrape-job-url muted-text">
            <a href={job?.target_url} target="_blank" rel="noreferrer" className="url-scrape-job-source-link">
              {job?.target_url} <ExternalLink size={11} aria-hidden />
            </a>
          </p>
        </div>

        {isCompleted && preview.length > 0 && !pushed && (
          <div className="url-scrape-job-actions">
            <span className="muted-text url-scrape-job-sel-count">
              {selectedIndices.size > 0 ? `${selectedIndices.size} seleccionadas` : "Todas seleccionadas"}
            </span>
            {needsEnrichment && (
              <Button
                type="button"
                onClick={() => enrichMutation.mutate()}
                disabled={enrichMutation.isPending || isEnriching}
                variant="outline"
              >
                {enrichMutation.isPending || isEnriching
                  ? "Enriqueciendo…"
                  : "Enriquecer perfiles"}
              </Button>
            )}
            <Button
              type="button"
              onClick={() => pushMutation.mutate()}
              disabled={pushMutation.isPending}
              className="cta-button"
            >
              {pushMutation.isPending
                ? "Agregando…"
                : `Agregar ${selectedIndices.size > 0 ? selectedIndices.size : preview.length} al lista`}
            </Button>
          </div>
        )}

        {isEnriching && (
          <div className="url-scrape-job-actions">
            <span className="muted-text">
              {job?.progress ?? 0}% — Enriqueciendo perfiles…
            </span>
          </div>
        )}
      </header>

      {/* Loading card while running with no results yet */}
      {isRunning && preview.length === 0 && (
        <div style={{ display: "flex", justifyContent: "center", padding: "32px 0" }}>
          <div className="loading-card">
            <div className="loading-card__glow" />
            <div className="loading-card__radar">
              <div className="loading-card__ring loading-card__ring--1" />
              <div className="loading-card__ring loading-card__ring--2" />
              <div className="loading-card__ring loading-card__ring--3" />
              <div className="loading-card__node">
                <Globe size={28} className="loading-card__node-icon" aria-hidden />
              </div>
              <div className="loading-card__orbit">
                <div className="loading-card__orbit-dot" />
              </div>
              <div className="loading-card__orbit loading-card__orbit--slow">
                <div className="loading-card__orbit-dot loading-card__orbit-dot--gray" />
              </div>
            </div>
            <div className="loading-card__status-wrap">
              <p className="loading-card__status">
                {(job?.progress ?? 0) <= 10
                  ? "Navegando la URL…"
                  : job?.pages_scraped != null && job?.pages_total != null
                    ? `Procesando página ${job.pages_scraped} de ${job.pages_total}…`
                    : "Procesando con IA…"}
              </p>
            </div>
            <div className="loading-card__bar-track">
              <div
                className="loading-card__bar-fill--real"
                style={{ width: `${job?.progress ?? 0}%` }}
              />
            </div>
            <span className="loading-card__percent">{job?.progress ?? 0}%</span>
            <button
              type="button"
              className="loading-card__cancel"
              disabled={cancelMutation.isPending}
              onClick={() => cancelMutation.mutate()}
            >
              {cancelMutation.isPending ? "Cancelando…" : "Cancelar"}
            </button>
          </div>
        </div>
      )}

      {/* Compact progress bar while running with partial results */}
      {isRunning && preview.length > 0 && (
        <div className="url-scrape-job-progress-wrap">
          <div
            className="url-scrape-job-progress-bar"
            style={{ width: `${job?.progress ?? 0}%` }}
          />
          <p className="muted-text url-scrape-job-progress-label">
            {job?.progress != null && job.progress <= 10
              ? "Navegando la URL…"
              : job?.pages_scraped != null && job?.pages_total != null
                ? `Procesando página ${job.pages_scraped} de ${job.pages_total}…`
                : "Procesando con IA…"} {job?.progress}%
          </p>
          <Button
            type="button"
            variant="ghost"
            onClick={() => cancelMutation.mutate()}
            disabled={cancelMutation.isPending}
            className="url-scrape-job-cancel-btn"
          >
            {cancelMutation.isPending ? "Cancelando…" : "Cancelar"}
          </Button>
        </div>
      )}

      {/* Cancelled */}
      {isCancelled && (
        <div className="url-scrape-job-error">
          <p className="muted-text">Búsqueda cancelada.</p>
          {directoryId && (
            <Button type="button" onClick={() => navigate(`/lists/${directoryId}`)}>
              Volver al lista
            </Button>
          )}
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="url-scrape-job-error">
          <p className="error-text">{job?.error_message ?? "Ocurrió un error durante la extracción."}</p>
          {directoryId && (
            <Button type="button" onClick={() => navigate(`/lists/${directoryId}`)}>
              Volver al lista
            </Button>
          )}
        </div>
      )}

      {/* Success banner */}
      {pushed && (
        <div className="url-scrape-job-success">
          Entradas agregadas al lista. Redirigiendo…
        </div>
      )}

      {/* Results table */}
      {preview.length > 0 && (
        <div style={{
          background: "var(--c-card-bg)", border: "1px solid var(--color-border)",
          borderRadius: 12, overflow: "hidden",
          boxShadow: "var(--c-card-shadow)",
          margin: "16px 0",
        }}>
          {/* Table header */}
          <div style={{
            display: "grid", gridTemplateColumns: SCRAPE_TABLE_COLS, gap: "0 12px",
            padding: "10px 16px", borderBottom: "1px solid var(--color-border)",
            background: "var(--color-surface-alt)", fontSize: 11, fontWeight: 600,
            color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em",
            alignItems: "center",
          }}>
            <div style={{ display: "flex", justifyContent: "center" }}>
              <input
                type="checkbox"
                style={{ width: 15, height: 15, cursor: "pointer" }}
                checked={paginatedItems.length > 0 && paginatedItems.every((item) => selectedIndices.has(item.index))}
                onChange={togglePageItems}
              />
            </div>
            <div>Perfil</div>
            <div>URL</div>
            <div>Contacto</div>
          </div>

          {/* Data rows */}
          {paginatedItems.map((item) => {
            const avStyle = getAvatarStyle(item.title || "?");
            let hostname = "";
            try { hostname = new URL(item.url).hostname.replace(/^www\./, ""); } catch { hostname = item.url; }

            return (
              <div
                key={item.index}
                className="ws-result-row"
                style={{
                  display: "grid", gridTemplateColumns: SCRAPE_TABLE_COLS, gap: "0 12px",
                  padding: "12px 16px", borderBottom: "1px solid var(--color-border)",
                  alignItems: "center",
                }}
              >
                {/* Checkbox */}
                <div style={{ display: "flex", justifyContent: "center" }}>
                  <input
                    type="checkbox"
                    style={{ width: 15, height: 15, cursor: "pointer" }}
                    checked={selectedIndices.has(item.index)}
                    onChange={(e) => {
                      const next = new Set(selectedIndices);
                      if (e.target.checked) next.add(item.index);
                      else next.delete(item.index);
                      setSelectedIndices(next);
                    }}
                  />
                </div>

                {/* Profile */}
                <div style={{ display: "flex", alignItems: "center", gap: 12, overflow: "hidden" }}>
                  <div style={{
                    width: 38, height: 38, borderRadius: "50%", flexShrink: 0,
                    background: avStyle.bg, color: avStyle.color,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontWeight: 700, fontSize: 13,
                    border: `1px solid ${avStyle.color}30`,
                  }}>
                    {initial(item.title || "?")}
                  </div>
                  <div style={{ overflow: "hidden" }}>
                    <p style={{
                      fontWeight: 600, fontSize: 13, color: "var(--color-text)",
                      margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    }}>
                      {item.title || <span style={{ color: "var(--color-text-secondary)" }}>(sin título)</span>}
                    </p>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
                      {item.city && (
                        <span style={{ fontSize: 11, color: "var(--color-text-secondary)", display: "flex", alignItems: "center", gap: 3 }}>
                          <MapPin size={10} aria-hidden /> {item.city}
                        </span>
                      )}
                    </div>
                    {item.snippet && (
                      <p style={{ fontSize: 11, color: "var(--color-text-secondary)", margin: "3px 0 0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {item.snippet.slice(0, 120)}
                      </p>
                    )}
                  </div>
                </div>

                {/* URL */}
                <div style={{ overflow: "hidden" }}>
                  {item.url ? (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        fontSize: 12, color: "var(--color-primary)", textDecoration: "none",
                        display: "inline-flex", alignItems: "center", gap: 4, overflow: "hidden",
                      }}
                      onClick={(e) => e.stopPropagation()}
                      title={item.url}
                    >
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {hostname}
                      </span>
                      <ExternalLink size={11} aria-hidden style={{ flexShrink: 0 }} />
                    </a>
                  ) : (
                    <span style={{ fontSize: 11, color: "var(--color-neutral)" }}>—</span>
                  )}
                </div>

                {/* Contact icons */}
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  {item.emails[0] && (
                    <a
                      href={`mailto:${item.emails[0]}`}
                      className="ws-contact-btn"
                      title={item.emails[0]}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Mail size={12} />
                    </a>
                  )}
                  {item.phones[0] && (
                    <a
                      href={`tel:${item.phones[0]}`}
                      className="ws-contact-btn"
                      title={item.phones[0]}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Phone size={12} />
                    </a>
                  )}
                  {!item.emails[0] && !item.phones[0] && item.url && (
                    <button
                      className="ws-contact-btn"
                      title="Enriquecer perfil"
                      disabled={enrichingRows.has(item.index) || job?.status !== "completed"}
                      onClick={(e) => { e.stopPropagation(); void enrichRow(item.index); }}
                    >
                      {enrichingRows.has(item.index)
                        ? <Loader size={12} style={{ animation: "spin 1s linear infinite" }} />
                        : <Sparkles size={12} />}
                    </button>
                  )}
                  {!item.emails[0] && !item.phones[0] && !item.url && (
                    <span style={{ fontSize: 11, color: "var(--color-neutral)" }}>—</span>
                  )}
                </div>
              </div>
            );
          })}

          {/* Pagination inside table */}
          {totalPages > 1 && (
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8,
              padding: "10px 16px", borderTop: "1px solid var(--color-border)", background: "var(--color-surface-alt)",
            }}>
              <Button
                type="button" variant="ghost"
                disabled={currentPage === 1}
                onClick={() => setCurrentPage(currentPage - 1)}
                className="url-scrape-job-pagination-btn"
              >
                <ChevronLeft size={16} aria-hidden /> Anterior
              </Button>
              <span style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>
                Página {currentPage} de {totalPages}
              </span>
              <Button
                type="button" variant="ghost"
                disabled={currentPage === totalPages}
                onClick={() => setCurrentPage(currentPage + 1)}
                className="url-scrape-job-pagination-btn"
              >
                Siguiente <ChevronRight size={16} aria-hidden />
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Empty state when completed but no entries */}
      {isCompleted && preview.length === 0 && (
        <div className="url-scrape-job-empty">
          <p>No se encontraron entradas en esta página.</p>
          <p className="muted-text">
            Intenta con un prompt más específico o verifica que la URL contenga un listado visible.
          </p>
          {directoryId && (
            <Button type="button" onClick={() => navigate(`/lists/${directoryId}`)}>
              Volver al lista
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
