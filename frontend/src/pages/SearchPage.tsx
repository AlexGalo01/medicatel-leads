import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Building2, Folder, Loader2, Search, Users } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import type { JobSearchLocationState } from "./JobSearchWorkspacePage";

import { clarifySearchJob, createSearchJob, listDirectories } from "../api";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Select } from "../components/ui/select";
import { defaultChannelsForFocus } from "../data/searchSuggestions";
import type { ExaCategoryChoice, SearchFocus } from "../types";

const EXA_CATEGORY_OPTIONS: { value: ExaCategoryChoice; label: string }[] = [
  { value: "people", label: "Personas" },
  { value: "company", label: "Empresas" },
];

export function SearchPage(): JSX.Element {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedDirectoryId = searchParams.get("directory_id") ?? "";
  const [query, setQuery] = useState("");
  const [directoryId, setDirectoryId] = useState<string>(preselectedDirectoryId);
  const [exaCategoryUi, setExaCategoryUi] = useState<ExaCategoryChoice>("people");
  const [clarifyContext, setClarifyContext] = useState<{ jobId: string; question: string } | null>(null);
  const [clarifyReply, setClarifyReply] = useState("");
  const [showDirectoryModal, setShowDirectoryModal] = useState(false);
  const searchFocus: SearchFocus = "general";
  const contactChannels = defaultChannelsForFocus(searchFocus);
  const directoriesQuery = useQuery({
    queryKey: ["directories"],
    queryFn: () => listDirectories(),
  });

  // Si cambia el query param (ej. volver de crear directorio), respetarlo.
  useEffect(() => {
    if (preselectedDirectoryId) {
      setDirectoryId(preselectedDirectoryId);
    }
  }, [preselectedDirectoryId]);

  const queryPlaceholder = useMemo(() => {
    if (exaCategoryUi === "people") {
      return "ginecólogos en San Pedro Sula";
    }
    return "Aseguradoras de Tegucigalpa";
  }, [exaCategoryUi]);

  const navigateToJob = (jobId: string): void => {
    const state: JobSearchLocationState = {
      searchLabel: query.trim(),
      contactChannels: [...contactChannels],
      searchFocus,
      exaCategory: exaCategoryUi,
    };
    navigate(`/jobs/${jobId}`, { state });
  };

  const createJobMutation = useMutation({
    mutationFn: createSearchJob,
    onSuccess: (data) => {
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem("last_search_job_id", data.job_id);
      }
      const cq = data.clarifying_question?.trim() ?? "";
      const explicitNo = data.requires_clarification === false;
      if (cq && !explicitNo) {
        setClarifyReply("");
        setClarifyContext({ jobId: data.job_id, question: cq });
        return;
      }
      navigateToJob(data.job_id);
    },
  });

  const clarifyMutation = useMutation({
    mutationFn: ({ jobId, reply }: { jobId: string; reply: string }) =>
      clarifySearchJob(jobId, { reply }),
    onSuccess: (_data, { jobId }) => {
      setClarifyContext(null);
      setClarifyReply("");
      navigateToJob(jobId);
    },
  });

  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!directoryId) {
      setShowDirectoryModal(true);
      return;
    }
    createJobMutation.mutate({
      query: query.trim(),
      directory_id: directoryId,
      contact_channels: contactChannels,
      search_focus: searchFocus,
      exa_category: exaCategoryUi,
    });
  };

  return (
    <section className="search-page-v2">
      {showDirectoryModal ? (
        <div className="search-clarify-overlay" role="presentation">
          <div
            className="search-clarify-dialog panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="directory-modal-title"
          >
            <h3 id="directory-modal-title" className="search-clarify-title">
              Crear directorio destino
            </h3>
            <p className="search-clarify-question muted-text">
              Debes crear o elegir un directorio destino antes de lanzar la búsqueda. Un directorio organiza tus prospectos en etapas personalizadas.
            </p>
            <div className="search-clarify-actions">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setShowDirectoryModal(false)}
              >
                Cancelar
              </Button>
              <Link to="/directories/new?returnTo=/search" className="link-button">
                + Crear directorio
              </Link>
            </div>
          </div>
        </div>
      ) : null}
      {clarifyContext ? (
        <div className="search-clarify-overlay" role="presentation">
          <div
            className="search-clarify-dialog panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="search-clarify-title"
          >
            <h3 id="search-clarify-title" className="search-clarify-title">
              Antes de buscar, una aclaración
            </h3>
            <p className="search-clarify-question muted-text">{clarifyContext.question}</p>
            <label className="search-clarify-label" htmlFor="search-clarify-reply">
              Tu respuesta
            </label>
            <textarea
              id="search-clarify-reply"
              className="search-clarify-textarea"
              value={clarifyReply}
              onChange={(e) => setClarifyReply(e.target.value)}
              rows={4}
              maxLength={500}
              placeholder="Ej.: Solo El Salvador, zona de San Salvador."
              aria-required="true"
            />
            {clarifyMutation.isError ? (
              <p className="error-text" role="alert">
                {clarifyMutation.error instanceof Error
                  ? clarifyMutation.error.message
                  : "No se pudo enviar la aclaración."}
              </p>
            ) : null}
            <div className="search-clarify-actions">
              <Button
                type="button"
                variant="ghost"
                disabled={clarifyMutation.isPending}
                onClick={() => {
                  setClarifyContext(null);
                  setClarifyReply("");
                }}
              >
                Cancelar
              </Button>
              <Button
                type="button"
                className="search-command-submit"
                disabled={clarifyMutation.isPending || clarifyReply.trim().length < 1}
                onClick={() => {
                  clarifyMutation.mutate({
                    jobId: clarifyContext.jobId,
                    reply: clarifyReply.trim(),
                  });
                }}
              >
                {clarifyMutation.isPending ? (
                  <>
                    <Loader2 className="search-submit-icon spin" aria-hidden />
                    <span>Enviando…</span>
                  </>
                ) : (
                  <span>Continuar búsqueda</span>
                )}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
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
                  ) : (
                    <Building2 size={15} aria-hidden />
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

            <div className="search-command-directory-row">
              <label className="search-command-directory-label">
                <Folder size={14} aria-hidden />
                <span>Directorio destino</span>
              </label>
              <Select
                value={directoryId}
                onChange={(e) => setDirectoryId(e.target.value)}
                required
                aria-label="Directorio destino"
              >
                <option value="">— Elige un directorio —</option>
                {(directoriesQuery.data?.items ?? []).map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </Select>
              <Link to="/directories/new?returnTo=/search" className="link-button">
                + Crear directorio
              </Link>
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
              <Button
                className="search-command-submit"
                type="submit"
                disabled={createJobMutation.isPending}
              >
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
              <p className="error-text" role="alert">
                {createJobMutation.error instanceof Error
                  ? createJobMutation.error.message
                  : "No se pudo crear el trabajo de búsqueda."}
              </p>
            ) : null}
          </form>
            </CardContent>
          </Card>
        </section>
      </div>
    </section>
  );
}
