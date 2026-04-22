import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Building2, Clock3, Globe, Loader2, Search, Users } from "lucide-react";
import { useNavigate } from "react-router-dom";

import type { JobSearchLocationState } from "./JobSearchWorkspacePage";

import { createSearchJob, listSearchJobs } from "../api";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { defaultChannelsForFocus } from "../data/searchSuggestions";
import type { ExaCategoryChoice, SearchFocus } from "../types";

type ExaCategoryUi = "general" | ExaCategoryChoice;

const EXA_CATEGORY_OPTIONS: { value: ExaCategoryUi; label: string }[] = [
  { value: "people", label: "Personas" },
  { value: "company", label: "Empresas" },
  { value: "general", label: "General" },
];

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

export function SearchPage(): JSX.Element {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [exaCategoryUi, setExaCategoryUi] = useState<ExaCategoryUi>("general");
  const searchFocus: SearchFocus = "general";
  const contactChannels = defaultChannelsForFocus(searchFocus);
  const recentJobsQuery = useQuery({
    queryKey: ["search-jobs", "recent", 5],
    queryFn: () => listSearchJobs({ limit: 5 }),
  });
  const recentSearches = recentJobsQuery.data?.items ?? [];

  const queryPlaceholder = useMemo(() => {
    if (exaCategoryUi === "people") {
      return "ginecólogos en San Pedro Sula";
    }
    if (exaCategoryUi === "company") {
      return "Aseguradoras de Tegucigalpa";
    }
    return "clínicas privadas en Honduras";
  }, [exaCategoryUi]);

  const createJobMutation = useMutation({
    mutationFn: createSearchJob,
    onSuccess: (data) => {
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem("last_search_job_id", data.job_id);
      }
      const state: JobSearchLocationState = {
        searchLabel: query.trim(),
        contactChannels: [...contactChannels],
        searchFocus,
        exaCategory: exaCategoryUi !== "general" ? exaCategoryUi : undefined,
      };
      navigate(`/jobs/${data.job_id}`, { state });
    },
  });

  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    createJobMutation.mutate({
      query: query.trim(),
      contact_channels: contactChannels,
      search_focus: searchFocus,
      ...(exaCategoryUi !== "general" ? { exa_category: exaCategoryUi } : {}),
    });
  };

  return (
    <section className="search-page-v2">
      <div className="search-page-v2-content">
        <section className="search-command-center">
          <div className="search-command-title">
            <h2>¿Qué estás buscando?</h2>
          </div>

          <Card className="search-command-card panel">
            <CardContent>
          <form className="search-command-form" onSubmit={onSubmit}>
            <div className="search-command-tabs" role="group" aria-label="Categoría Exa">
              {EXA_CATEGORY_OPTIONS.map((opt) => {
                const selected = exaCategoryUi === opt.value;
                const icon =
                  opt.value === "people" ? (
                    <Users size={15} aria-hidden />
                  ) : opt.value === "company" ? (
                    <Building2 size={15} aria-hidden />
                  ) : (
                    <Globe size={15} aria-hidden />
                  );
                return (
                  <button
                    key={opt.value}
                    type="button"
                    className={`search-command-tab${selected ? " is-active" : ""}`}
                    onClick={() => setExaCategoryUi(opt.value)}
                  >
                    {icon}
                    <span>{opt.label}</span>
                  </button>
                );
              })}
            </div>

            <div className="search-command-input-row">
              <Search className="search-command-search-icon" aria-hidden />
              <Input
                className="search-command-input"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={queryPlaceholder}
                required
                minLength={3}
                maxLength={500}
                aria-label="Consulta de búsqueda"
              />
              <Button className="search-command-submit" type="submit" disabled={createJobMutation.isPending}>
                {createJobMutation.isPending ? (
                  <>
                    <Loader2 className="search-submit-icon spin" aria-hidden />
                    <span>Buscando…</span>
                  </>
                ) : (
                  <span>Ejecutar búsqueda</span>
                )}
              </Button>
            </div>

            {createJobMutation.isError ? (
              <p className="error-text">No se pudo crear el job. Revisa que el backend esté activo.</p>
            ) : null}
          </form>
            </CardContent>
          </Card>
        </section>

        <section className="search-recent-v2">
          <h3>Búsquedas recientes</h3>
          <div className="search-recent-v2-list">
            {recentJobsQuery.isLoading ? (
              <p className="muted-text search-recent-v2-empty">Cargando búsquedas recientes…</p>
            ) : null}
            {recentJobsQuery.isError ? (
              <p className="error-text search-recent-v2-empty">No se pudieron cargar las búsquedas recientes.</p>
            ) : null}
            {!recentJobsQuery.isLoading && !recentJobsQuery.isError && recentSearches.length === 0 ? (
              <p className="muted-text search-recent-v2-empty">Aún no hay búsquedas recientes.</p>
            ) : (
              recentSearches.slice(0, 5).map((item) => (
                <Button
                  key={item.job_id}
                  type="button"
                  className="search-recent-v2-item panel search-recent-v2-button"
                  onClick={() => {
                    navigate(`/busquedas?jobId=${encodeURIComponent(item.job_id)}`);
                  }}
                >
                  <div className="search-recent-v2-head">
                    <strong>{item.query}</strong>
                    <span className="muted-text">
                      <Clock3 size={12} aria-hidden /> {formatRecentTime(item.created_at)}
                    </span>
                  </div>
                  <p className="muted-text">
                    {item.exa_category === "people"
                      ? "Personas"
                      : item.exa_category === "company"
                        ? "Empresas"
                        : "General"}
                  </p>
                </Button>
              ))
            )}
          </div>
        </section>
      </div>
    </section>
  );
}
