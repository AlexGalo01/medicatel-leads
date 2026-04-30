import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ExternalLink, MapPin, Phone, Mail } from "lucide-react";

import { getDirectory, getUrlScrapeJobStatus, pushScrapeEntriesToDirectory } from "../api";
import { Button } from "../components/ui/button";

const ITEMS_PER_PAGE = 30;

export function UrlScrapeJobPage(): JSX.Element {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
  const [pushed, setPushed] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);

  const jobQuery = useQuery({
    queryKey: ["url-scrape-job", jobId],
    queryFn: () => getUrlScrapeJobStatus(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "error" ? false : 2000;
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
      ),
    onSuccess: (result) => {
      setPushed(true);
      void queryClient.invalidateQueries({ queryKey: ["directory-items", directoryId] });
      setTimeout(() => navigate(`/directories/${directoryId}`), 1500);
    },
  });

  const preview = job?.scrape_results_preview ?? [];
  const isRunning = job?.status === "running" || job?.status === "pending";
  const isCompleted = job?.status === "completed";
  const isError = job?.status === "error";

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

  const dirName = directoryQuery.data?.name ?? "Directorio";

  return (
    <div className="url-scrape-job-page">
      {/* Breadcrumb */}
      <nav className="url-scrape-job-breadcrumb">
        {directoryId ? (
          <Link to={`/directories/${directoryId}`} className="url-scrape-job-back">
            <ChevronLeft size={15} aria-hidden /> {dirName}
          </Link>
        ) : (
          <Link to="/directories" className="url-scrape-job-back">
            <ChevronLeft size={15} aria-hidden /> Directorios
          </Link>
        )}
        <span className="url-scrape-job-breadcrumb-sep">/</span>
        <span className="url-scrape-job-breadcrumb-current">Importar URL</span>
      </nav>

      {/* Header */}
      <header className="url-scrape-job-header">
        <div>
          <h1 className="url-scrape-job-title">
            {isRunning ? "Extrayendo…" : isError ? "Error en extracción" : `${preview.length} entradas encontradas`}
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
            <Button
              type="button"
              onClick={() => pushMutation.mutate()}
              disabled={pushMutation.isPending}
              className="cta-button"
            >
              {pushMutation.isPending
                ? "Agregando…"
                : `Agregar ${selectedIndices.size > 0 ? selectedIndices.size : preview.length} al directorio`}
            </Button>
          </div>
        )}
      </header>

      {/* Progress bar while running */}
      {isRunning && (
        <div className="url-scrape-job-progress-wrap">
          <div
            className="url-scrape-job-progress-bar"
            style={{ width: `${job?.progress ?? 0}%` }}
          />
          <p className="muted-text url-scrape-job-progress-label">
            {job?.progress === 10 ? "Navegando la URL…" : "Procesando con IA…"} {job?.progress}%
          </p>
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="url-scrape-job-error">
          <p className="error-text">{job?.error_message ?? "Ocurrió un error durante la extracción."}</p>
          {directoryId && (
            <Button type="button" onClick={() => navigate(`/directories/${directoryId}`)}>
              Volver al directorio
            </Button>
          )}
        </div>
      )}

      {/* Success banner */}
      {pushed && (
        <div className="url-scrape-job-success">
          Entradas agregadas al directorio. Redirigiendo…
        </div>
      )}

      {/* Select all toggle and pagination */}
      {isCompleted && preview.length > 0 && !pushed && (
        <div className="url-scrape-job-select-bar">
          <div className="url-scrape-job-select-bar-left">
            <label className="url-scrape-job-check-all">
              <input
                type="checkbox"
                checked={paginatedItems.length > 0 && paginatedItems.every((item) =>
                  selectedIndices.has(item.index)
                )}
                onChange={togglePageItems}
              />
              Seleccionar página
            </label>
          </div>
          {totalPages > 1 && (
            <div className="url-scrape-job-pagination">
              <Button
                type="button"
                variant="ghost"
                disabled={currentPage === 1}
                onClick={() => setCurrentPage(currentPage - 1)}
                className="url-scrape-job-pagination-btn"
              >
                <ChevronLeft size={16} aria-hidden /> Anterior
              </Button>
              <span className="url-scrape-job-pagination-info">
                Página {currentPage} de {totalPages}
              </span>
              <Button
                type="button"
                variant="ghost"
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

      {/* Results grid */}
      {preview.length > 0 && (
        <ul className="url-scrape-job-results">
          {paginatedItems.map((item) => (
            <li key={item.index} className="url-scrape-job-card">
              <label className="url-scrape-job-card-inner">
                <input
                  type="checkbox"
                  className="url-scrape-job-card-check"
                  checked={selectedIndices.has(item.index)}
                  onChange={(e) => {
                    const next = new Set(selectedIndices);
                    if (e.target.checked) next.add(item.index);
                    else next.delete(item.index);
                    setSelectedIndices(next);
                  }}
                />
                <div className="url-scrape-job-card-body">
                  <p className="url-scrape-job-card-title">
                    {item.title || <span className="muted-text">(sin título)</span>}
                  </p>

                  {item.url && (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      className="url-scrape-job-card-link muted-text"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {item.url.length > 60 ? item.url.slice(0, 60) + "…" : item.url}
                      <ExternalLink size={10} aria-hidden />
                    </a>
                  )}

                  {item.snippet && (
                    <p className="url-scrape-job-card-snippet muted-text">{item.snippet.slice(0, 140)}</p>
                  )}

                  <div className="url-scrape-job-card-meta">
                    {item.city && (
                      <span className="url-scrape-job-card-tag">
                        <MapPin size={11} aria-hidden /> {item.city}
                      </span>
                    )}
                    {item.phones[0] && (
                      <span className="url-scrape-job-card-tag">
                        <Phone size={11} aria-hidden /> {item.phones[0]}
                      </span>
                    )}
                    {item.emails[0] && (
                      <span className="url-scrape-job-card-tag">
                        <Mail size={11} aria-hidden /> {item.emails[0]}
                      </span>
                    )}
                  </div>
                </div>
              </label>
            </li>
          ))}
        </ul>
      )}

      {/* Empty state when completed but no entries */}
      {isCompleted && preview.length === 0 && (
        <div className="url-scrape-job-empty">
          <p>No se encontraron entradas en esta página.</p>
          <p className="muted-text">
            Intenta con un prompt más específico o verifica que la URL contenga un listado visible.
          </p>
          {directoryId && (
            <Button type="button" onClick={() => navigate(`/directories/${directoryId}`)}>
              Volver al directorio
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
