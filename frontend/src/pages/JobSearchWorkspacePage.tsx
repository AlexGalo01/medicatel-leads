import { useEffect, useMemo, useState } from "react";

const WORKSPACE_PROCESSING_TIPS = [
  "Buscando perfiles que coincidan con tu consulta…",
  "Filtrando resultados por ubicación y rol…",
  "Esto puede tardar un poco si pedimos mucha calidad; no cierres la pestaña.",
  "Sincronizando con el motor de búsqueda…",
];
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useParams } from "react-router-dom";
import { Loader2 } from "lucide-react";

import {
  downloadLeadsCsvFile,
  getSearchJobStatus,
  interpretProfileTexts,
  listLeads,
  loadMoreExaResults,
} from "../api";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import type { ExaCategoryChoice, SearchFocus } from "../types";

export interface JobSearchLocationState {
  searchLabel: string;
  contactChannels: string[];
  searchFocus: SearchFocus;
  notes?: string;
  exaCategory?: ExaCategoryChoice;
  exaCriteria?: string;
}

interface ParsedProfile {
  normalized_name?: string | null;
  normalized_company?: string | null;
  normalized_specialty?: string | null;
}

/** Evita salto de layout al cambiar de página: mientras llega interpret, no mezclar fallback corto con texto normalizado largo. */
function WorkspaceInterpretCellSkeleton({ variant }: { variant: "profile" | "line" | "block" }): JSX.Element {
  if (variant === "profile") {
    return (
      <div className="workspace-table-cell-skeleton workspace-table-cell-skeleton--profile" aria-hidden>
        <span className="workspace-skeleton-line workspace-skeleton-line--fluid" />
        <span className="workspace-skeleton-line workspace-skeleton-line--fluid workspace-skeleton-line--narrow" />
      </div>
    );
  }
  if (variant === "block") {
    return (
      <div className="workspace-table-cell-skeleton workspace-table-cell-skeleton--block" aria-hidden>
        <span className="workspace-skeleton-line workspace-skeleton-line--fluid" />
        <span className="workspace-skeleton-line workspace-skeleton-line--fluid workspace-skeleton-line--mid" />
      </div>
    );
  }
  return (
    <div className="workspace-table-cell-skeleton workspace-table-cell-skeleton--single" aria-hidden>
      <span className="workspace-skeleton-line workspace-skeleton-line--fluid" />
    </div>
  );
}

export function JobSearchWorkspacePage(): JSX.Element {
  const { jobId = "" } = useParams();
  const location = useLocation();
  const passedState = location.state as JobSearchLocationState | null;
  const queryClient = useQueryClient();
  const [tablePage, setTablePage] = useState(1);
  const tablePageSize = 12;

  const downloadCsvMutation = useMutation({
    mutationFn: () => downloadLeadsCsvFile(jobId, {}),
  });

  const jobStatusQuery = useQuery({
    queryKey: ["job-status", jobId],
    queryFn: () => getSearchJobStatus(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "error" ? false : 1500;
    },
    enabled: Boolean(jobId),
  });

  const [exaMoreMessage, setExaMoreMessage] = useState<string | null>(null);
  const [processingTipIndex, setProcessingTipIndex] = useState(0);
  const exaMoreMutation = useMutation({
    mutationFn: () => loadMoreExaResults(jobId, 40),
    onSuccess: (data) => {
      if (!data.ok) {
        setExaMoreMessage(data.error || "No se pudieron cargar más resultados");
        return;
      }
      setExaMoreMessage(
        data.added_count > 0
          ? `Se añadieron ${data.added_count} resultado(s) nuevos (${data.total_count} en total).`
          : "No hubo URLs nuevas; Exa devolvió solo resultados ya listados.",
      );
      void queryClient.invalidateQueries({ queryKey: ["job-status", jobId] });
    },
    onError: (error: Error) => setExaMoreMessage(error.message),
  });

  const jobStatus = jobStatusQuery.data?.status;
  const isProcessing = jobStatus === "pending" || jobStatus === "running";
  const pipelineMode = jobStatusQuery.data?.pipeline_mode ?? null;
  const searchOnlyDemo =
    pipelineMode === "presearch_and_search_only" ||
    (isProcessing && pipelineMode === null);
  const previewRows = searchOnlyDemo ? (jobStatusQuery.data?.exa_results_preview ?? []) : [];

  const leadsQuery = useQuery({
    queryKey: ["leads", jobId, "workspace"],
    queryFn: () => listLeads(jobId, { pageSize: 100 }),
    enabled: Boolean(jobId),
    refetchInterval: isProcessing ? 2500 : false,
  });

  useEffect(() => {
    if (jobStatus === "completed") void leadsQuery.refetch();
  }, [jobStatus, leadsQuery]);

  const persistedLeads = leadsQuery.data?.items ?? [];

  const awaitingJobPayload = jobStatusQuery.isLoading || (!jobStatusQuery.data && jobStatusQuery.isFetching);
  const showTableSkeleton =
    awaitingJobPayload ||
    (searchOnlyDemo && isProcessing) ||
    (jobStatus === "completed" && !searchOnlyDemo && leadsQuery.isLoading);

  const totalRows = searchOnlyDemo ? previewRows.length : persistedLeads.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / tablePageSize));
  const currentPage = Math.min(tablePage, totalPages);
  const offset = (currentPage - 1) * tablePageSize;
  const paginatedPreviewRows = previewRows.slice(offset, offset + tablePageSize);
  const paginatedLeads = persistedLeads.slice(offset, offset + tablePageSize);

  useEffect(() => {
    setTablePage(1);
    setProcessingTipIndex(0);
  }, [jobId, searchOnlyDemo]);

  useEffect(() => {
    if (!showTableSkeleton) return undefined;
    const timer = window.setInterval(() => {
      setProcessingTipIndex((i) => (i + 1) % WORKSPACE_PROCESSING_TIPS.length);
    }, 2800);
    return () => window.clearInterval(timer);
  }, [showTableSkeleton]);

  const profileTexts = useMemo(() => {
    if (searchOnlyDemo) {
      return paginatedPreviewRows.map((row) => row.title?.trim()).filter(Boolean) as string[];
    }
    return paginatedLeads
      .map((lead) => `${lead.full_name || ""} | ${lead.specialty || ""}`.trim())
      .filter(Boolean);
  }, [searchOnlyDemo, paginatedPreviewRows, paginatedLeads]);

  const parsedProfilesQuery = useQuery({
    queryKey: ["profile-interpret", jobId, ...profileTexts],
    queryFn: () => interpretProfileTexts(profileTexts),
    enabled: profileTexts.length > 0,
    staleTime: 5 * 60 * 1000,
  });

  const parsedProfilesMap = useMemo(() => {
    const map = new Map<string, ParsedProfile>();
    for (const item of parsedProfilesQuery.data?.items ?? []) {
      map.set(item.source_text, item);
    }
    return map;
  }, [parsedProfilesQuery.data?.items]);

  /** Solo `isPending`: si usamos `isFetching`, un refetch en segundo plano vaciaría celdas ya resueltas. */
  const pageInterpretLoading =
    !showTableSkeleton && profileTexts.length > 0 && parsedProfilesQuery.isPending;

  const searchLabel =
    jobStatusQuery.data?.query_text?.trim() || passedState?.searchLabel?.trim() || "búsqueda";
  const workspaceTitle = `Búsqueda de ${searchLabel}`;
  const createdAtLabel = new Date(jobStatusQuery.data?.updated_at ?? Date.now()).toLocaleDateString("es-HN", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });

  const getParsedValues = (
    sourceText: string,
    fallbackName: string,
    fallbackSpecialty: string,
  ): { name: string; company: string; specialty: string } => {
    const parsed = parsedProfilesMap.get(sourceText);
    return {
      name: parsed?.normalized_name?.trim() || fallbackName || "—",
      company: parsed?.normalized_company?.trim() || "—",
      specialty: parsed?.normalized_specialty?.trim() || fallbackSpecialty || "—",
    };
  };

  return (
    <div className="search-workspace search-workspace--v2 search-workspace--single-column">
      <Card className="search-workspace-job-card panel">
        <div className="search-workspace-job-main">
          <div className="search-workspace-job-title-row">
            <h2 className="search-workspace-job-title">{workspaceTitle}</h2>
            {isProcessing ? (
              <span className="search-workspace-status-badge" aria-busy="true">
                <Loader2 className="spin search-workspace-spinner" aria-hidden />
                Procesando...
              </span>
            ) : null}
          </div>
          <p className="search-workspace-job-meta muted-text">Fecha de búsqueda: {createdAtLabel}</p>
        </div>
        <div className="search-workspace-job-actions">
          {jobStatus === "completed" && jobId && !searchOnlyDemo ? (
            <Button
              type="button"
              className="cta-button search-workspace-export-btn"
              disabled={downloadCsvMutation.isPending}
              onClick={() => downloadCsvMutation.mutate()}
            >
              {downloadCsvMutation.isPending ? "Generando..." : "Exportar"}
            </Button>
          ) : null}
        </div>
      </Card>

      <section className="search-workspace-metrics-grid search-workspace-metrics-grid--single">
        <article className="panel workspace-metric-card">
          <p className="workspace-metric-label">Resultados encontrados</p>
          <strong className="workspace-metric-value">{totalRows}</strong>
        </article>
      </section>

      <Card
        className={`search-workspace-main panel${isProcessing && jobStatusQuery.isFetching ? " search-workspace-main--live-fetch" : ""}`}
      >
        {exaMoreMessage ? (
          <div className="workspace-flash-message" role="status">
            {exaMoreMessage}
          </div>
        ) : null}

        {showTableSkeleton ? (
          <div className="search-workspace-live-block" aria-live="polite" aria-busy="true">
            <div className="search-workspace-live-track" aria-hidden>
              <span className="search-workspace-live-dot" />
              <span className="search-workspace-live-dot search-workspace-live-dot--delay1" />
              <span className="search-workspace-live-dot search-workspace-live-dot--delay2" />
            </div>
            <p className="search-workspace-live-text">{WORKSPACE_PROCESSING_TIPS[processingTipIndex]}</p>
            {jobStatusQuery.isFetching ? (
              <p className="search-workspace-live-sub muted-text">Actualizando estado del trabajo…</p>
            ) : null}
          </div>
        ) : null}

        <div className="search-workspace-toolbar search-workspace-toolbar--bulk">
          <div className="search-workspace-toolbar-left search-workspace-toolbar-left--bulk">
            {searchOnlyDemo && jobStatus === "completed" && previewRows.length > 0 ? (
              <Button
                type="button"
                variant="outline"
                className="workspace-tool-btn workspace-tool-btn--primary"
                disabled={exaMoreMutation.isPending}
                onClick={() => {
                  setExaMoreMessage(null);
                  exaMoreMutation.mutate();
                }}
              >
                {exaMoreMutation.isPending ? "Cargando..." : "Cargar más resultados"}
              </Button>
            ) : null}
          </div>
        </div>

        <div className="search-workspace-table-wrap">
          <table className="search-workspace-table search-workspace-table--card-rows">
            <thead>
              <tr>
                <th scope="col" className="workspace-col-avatar"> </th>
                <th scope="col">Perfil</th>
                <th scope="col" className="workspace-card-th-hide-sm">Empresa / rol</th>
                <th scope="col" className="workspace-card-th-hide-sm">Especialidad</th>
                <th scope="col" className="workspace-card-th-hide-sm">Ubicación</th>
                <th scope="col">Acción</th>
              </tr>
            </thead>
            <tbody>
              {showTableSkeleton
                ? Array.from({ length: tablePageSize }).map((_, index) => (
                    <tr key={`sk-loading-${index}`} className="workspace-lead-card-row workspace-row-skeleton">
                      <td><span className="workspace-skeleton-avatar" /></td>
                      <td>
                        <div className="workspace-skeleton-stack">
                          <span className="workspace-skeleton-line workspace-skeleton-line--fluid" />
                          <span className="workspace-skeleton-line workspace-skeleton-line--fluid workspace-skeleton-line--narrow" />
                        </div>
                      </td>
                      <td>
                        <div className="workspace-skeleton-stack">
                          <span className="workspace-skeleton-line workspace-skeleton-line--fluid" />
                        </div>
                      </td>
                      <td>
                        <div className="workspace-skeleton-stack">
                          <span className="workspace-skeleton-line workspace-skeleton-line--fluid workspace-skeleton-line--mid" />
                          <span className="workspace-skeleton-line workspace-skeleton-line--fluid workspace-skeleton-line--narrow" />
                        </div>
                      </td>
                      <td>
                        <div className="workspace-skeleton-stack">
                          <span className="workspace-skeleton-line workspace-skeleton-line--fluid workspace-skeleton-line--tiny-width" />
                        </div>
                      </td>
                      <td>
                        <span className="workspace-skeleton-pill" />
                      </td>
                    </tr>
                  ))
                : null}
              {!showTableSkeleton && jobStatus === "error" ? (
                <tr className="workspace-table-row-message">
                  <td colSpan={6} className="workspace-error-cell">
                    El job falló. <Link to="/search" className="link-button">Volver a buscar</Link>
                  </td>
                </tr>
              ) : null}

              {!showTableSkeleton && jobStatus !== "error" && searchOnlyDemo
                ? paginatedPreviewRows.map((row) => {
                    const sourceText = row.title?.trim() || "";
                    const parsed = getParsedValues(sourceText, row.title || "Sin título", row.specialty || "");
                    const initial = (pageInterpretLoading ? row.title || "?" : parsed.name).charAt(0).toUpperCase() || "?";
                    return (
                      <tr key={`exa-${row.index}`} className="workspace-lead-card-row">
                        <td className="workspace-card-td-avatar">
                          <span className="workspace-avatar-placeholder" aria-hidden>
                            {initial}
                          </span>
                        </td>
                        <td className="workspace-card-td-name">
                          <div className="workspace-card-name-block">
                            {pageInterpretLoading ? (
                              <WorkspaceInterpretCellSkeleton variant="profile" />
                            ) : (
                              <strong className="workspace-card-name-title">{parsed.name}</strong>
                            )}
                          </div>
                        </td>
                        <td className="workspace-card-td-hide-sm">
                          {pageInterpretLoading ? <WorkspaceInterpretCellSkeleton variant="line" /> : parsed.company}
                        </td>
                        <td className="workspace-card-td-hide-sm">
                          {pageInterpretLoading ? <WorkspaceInterpretCellSkeleton variant="block" /> : parsed.specialty}
                        </td>
                        <td className="workspace-card-td-hide-sm">{(row.city ?? "").trim() || "—"}</td>
                        <td className="workspace-card-td-action">
                          <Link to={`/jobs/${jobId}/result/${row.index}`} className="cta-button workspace-row-cta">
                            Ver Lead
                          </Link>
                        </td>
                      </tr>
                    );
                  })
                : null}

              {!showTableSkeleton && jobStatus !== "error" && !searchOnlyDemo
                ? paginatedLeads.map((lead) => {
                    const sourceText = `${lead.full_name || ""} | ${lead.specialty || ""}`.trim();
                    const parsed = getParsedValues(sourceText, lead.full_name, lead.specialty || "");
                    const initial = (pageInterpretLoading ? lead.full_name || "?" : parsed.name).charAt(0).toUpperCase() || "?";
                    return (
                      <tr key={lead.lead_id} className="workspace-lead-card-row">
                        <td className="workspace-card-td-avatar">
                          <span className="workspace-avatar-placeholder" aria-hidden>
                            {initial}
                          </span>
                        </td>
                        <td className="workspace-card-td-name">
                          <div className="workspace-card-name-block">
                            {pageInterpretLoading ? (
                              <WorkspaceInterpretCellSkeleton variant="profile" />
                            ) : (
                              <strong className="workspace-card-name-title">{parsed.name}</strong>
                            )}
                          </div>
                        </td>
                        <td className="workspace-card-td-hide-sm">
                          {pageInterpretLoading ? <WorkspaceInterpretCellSkeleton variant="line" /> : parsed.company}
                        </td>
                        <td className="workspace-card-td-hide-sm">
                          {pageInterpretLoading ? <WorkspaceInterpretCellSkeleton variant="block" /> : parsed.specialty}
                        </td>
                        <td className="workspace-card-td-hide-sm">{lead.city || "—"}</td>
                        <td className="workspace-card-td-action">
                          <Link className="cta-button workspace-row-cta" to={`/leads/${lead.lead_id}`}>
                            Ver Lead
                          </Link>
                        </td>
                      </tr>
                    );
                  })
                : null}

              {!showTableSkeleton && jobStatus === "completed" && searchOnlyDemo && previewRows.length === 0 ? (
                <tr className="workspace-table-row-message">
                  <td colSpan={6} className="workspace-empty-cell">La búsqueda terminó sin resultados en la vista previa.</td>
                </tr>
              ) : null}
              {!showTableSkeleton && jobStatus === "completed" && !searchOnlyDemo && persistedLeads.length === 0 ? (
                <tr className="workspace-table-row-message">
                  <td colSpan={6} className="workspace-empty-cell">No hay filas guardadas para este job.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        {!showTableSkeleton && totalRows > 0 ? (
          <div className="workspace-table-pagination">
            <Button
              type="button"
              variant="outline"
              className="workspace-pagination-btn"
              disabled={currentPage <= 1}
              onClick={() => setTablePage((value) => Math.max(1, value - 1))}
            >
              Anterior
            </Button>
            <span className="workspace-table-pagination-label muted-text">Página {currentPage} de {totalPages}</span>
            <Button
              type="button"
              variant="outline"
              className="workspace-pagination-btn"
              disabled={currentPage >= totalPages}
              onClick={() => setTablePage((value) => Math.min(totalPages, value + 1))}
            >
              Siguiente
            </Button>
          </div>
        ) : null}

        {parsedProfilesQuery.isError ? (
          <p className="muted-text workspace-expand-error">No se pudo interpretar todos los perfiles; se muestran valores base.</p>
        ) : null}
        {leadsQuery.isError ? <p className="error-text workspace-table-error">No se pudieron cargar las oportunidades.</p> : null}
      </Card>
    </div>
  );
}
