import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { listSearchJobs } from "../api";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Select } from "../components/ui/select";

function formatRecentTime(createdAt: string): string {
  const timestamp = new Date(createdAt).getTime();
  if (Number.isNaN(timestamp)) {
    return "Sin fecha";
  }
  const diffMs = Date.now() - timestamp;
  const diffMinutes = Math.max(1, Math.floor(diffMs / 60000));
  if (diffMinutes < 60) return `Hace ${diffMinutes} min`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `Hace ${diffHours} h`;
  const diffDays = Math.floor(diffHours / 24);
  return `Hace ${diffDays} día${diffDays > 1 ? "s" : ""}`;
}

export function ExaResultsPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedJobId = (searchParams.get("jobId") || "").trim();
  const term = (searchParams.get("q") || "").trim();
  const page = Math.max(1, Number(searchParams.get("page") || "1") || 1);
  const limitParam = (searchParams.get("limit") || "15").toLowerCase();
  const pageSize = limitParam === "10" ? 10 : limitParam === "20" ? 20 : limitParam === "all" ? 5000 : 15;
  const offset = (page - 1) * pageSize;

  const updateParams = (changes: Record<string, string>): void => {
    const next = new URLSearchParams(searchParams);
    Object.entries(changes).forEach(([key, value]) => {
      if (!value) {
        next.delete(key);
      } else {
        next.set(key, value);
      }
    });
    setSearchParams(next, { replace: true });
  };

  useEffect(() => {
    const hasPage = Boolean(searchParams.get("page"));
    const hasLimit = Boolean(searchParams.get("limit"));
    if (!hasPage || !hasLimit) {
      updateParams({
        page: hasPage ? searchParams.get("page") || "1" : "1",
        limit: hasLimit ? searchParams.get("limit") || "15" : "15",
      });
    }
  }, [searchParams]);

  const jobsQuery = useQuery({
    queryKey: ["search-jobs", "busquedas", term, page, pageSize],
    queryFn: () => listSearchJobs({ limit: pageSize, offset, q: term.trim() || undefined }),
  });
  const jobs = jobsQuery.data?.items ?? [];

  const filteredJobs = useMemo(() => {
    return jobs;
  }, [jobs]);

  return (
    <section className="exa-results-page">
      <Card className="panel exa-results-header">
        <div>
          <h1 className="exa-results-title">Búsquedas</h1>
          <p className="muted-text">
            Aquí están todas tus búsquedas recientes. Total de páginas: {jobsQuery.data?.total_pages ?? 1}
          </p>
        </div>
        <label className="exa-results-search">
          <Search size={16} aria-hidden />
          <Input
            type="search"
            value={term}
            onChange={(event) => {
              updateParams({
                q: event.target.value,
                page: "1",
              });
            }}
            placeholder="Buscar por consulta"
            aria-label="Buscar jobs"
          />
        </label>
        <label className="exa-results-limit">
          <span className="muted-text">Resultados por página</span>
          <Select
            value={limitParam}
            onChange={(event) => {
              updateParams({
                limit: event.target.value,
                page: "1",
              });
            }}
            aria-label="Resultados por página"
          >
            <option value="10">10</option>
            <option value="15">15</option>
            <option value="20">20</option>
            <option value="all">Todos</option>
          </Select>
        </label>
      </Card>

      <Card className="panel exa-results-list-wrap">
        {jobsQuery.isLoading ? <p className="muted-text">Cargando jobs…</p> : null}
        {jobsQuery.isError ? <p className="error-text">No se pudieron cargar los jobs.</p> : null}
        {!jobsQuery.isLoading && !jobsQuery.isError && filteredJobs.length === 0 ? (
          <p className="muted-text">No hay jobs para mostrar con ese filtro.</p>
        ) : (
          <ul className="exa-results-list">
            {filteredJobs.map((item) => (
              <li key={item.job_id} className={`exa-results-item${item.job_id === selectedJobId ? " is-selected" : ""}`}>
                <Link to={`/jobs/${item.job_id}`} className="exa-results-item-link">
                  <div className="exa-results-item-main">
                    <strong>{item.query}</strong>
                    <p className="muted-text">
                      {item.exa_category === "people"
                        ? "Personas"
                        : item.exa_category === "company"
                          ? "Empresas"
                          : "General"}
                    </p>
                  </div>
                  <div className="exa-results-item-actions">
                    <span className="muted-text">{formatRecentTime(item.created_at)}</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
        {!jobsQuery.isLoading && !jobsQuery.isError ? (
          <div className="exa-results-pagination">
            <button
              type="button"
              className="link-button"
              disabled={page <= 1}
              onClick={() => updateParams({ page: String(Math.max(1, page - 1)) })}
            >
              Anterior
            </button>
            <span className="muted-text">
              Página {jobsQuery.data?.page ?? page} de {jobsQuery.data?.total_pages ?? 1}
            </span>
            <button
              type="button"
              className="link-button"
              disabled={page >= (jobsQuery.data?.total_pages ?? 1)}
              onClick={() =>
                updateParams({
                  page: String(Math.min(jobsQuery.data?.total_pages ?? 1, page + 1)),
                })
              }
            >
              Siguiente
            </button>
          </div>
        ) : null}
      </Card>
    </section>
  );
}
