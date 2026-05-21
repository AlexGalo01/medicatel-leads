import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Building2,
  CheckCircle2,
  CloudDownload,
  Facebook,
  Globe,
  Instagram,
  Link as LinkIcon,
  Linkedin,
  Loader2,
  Map,
  Plus,
  Search,
  Sparkles,
  Twitter,
  UserRound,
  Youtube,
  Zap,
} from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import type { JobSearchLocationState } from "./JobSearchWorkspacePage";

import { clarifySearchJob, createSearchJob, createUrlScrapeJob, listDirectories, listScrapingSites } from "../api";
import { Button } from "../components/ui/button";
import { SearchableSelect } from "../components/ui/SearchableSelect";
import { defaultChannelsForFocus } from "../data/searchSuggestions";
import type { ExaCategoryChoice, SearchFocus } from "../types";

const PRIMARY = "var(--color-primary)";
const BORDER = "var(--color-border)";
const TEXT_MAIN = "var(--color-text)";
const TEXT_MUTED = "var(--color-text-secondary)";
const BG_LIGHT = "var(--color-surface-alt)";

const cardStyle: React.CSSProperties = {
  background: "var(--c-card-bg)",
  borderRadius: 16,
  boxShadow: "var(--c-card-shadow)",
  border: `1px solid ${BORDER}`,
  padding: "8px 32px 32px",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 14,
  fontWeight: 600,
  color: TEXT_MAIN,
  marginBottom: 12,
};

const inputBaseStyle: React.CSSProperties = {
  width: "100%",
  background: "var(--c-input-bg)",
  border: `1px solid ${BORDER}`,
  borderRadius: 12,
  fontSize: 14,
  color: TEXT_MAIN,
  outline: "none",
  transition: "border-color 0.2s, box-shadow 0.2s",
  boxSizing: "border-box",
  fontFamily: "inherit",
};

function TypeCard({
  selected,
  onClick,
  icon,
  label,
}: {
  selected: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        flex: 1,
        padding: 16,
        borderRadius: 12,
        border: selected ? `2px solid ${PRIMARY}` : `1px solid ${BORDER}`,
        background: selected ? "var(--color-primary-tint)" : "var(--c-card-bg)",
        cursor: "pointer",
        position: "relative",
        textAlign: "center",
        transition: "border-color 0.15s, background 0.15s",
      }}
    >
      {selected && (
        <CheckCircle2
          size={16}
          style={{ position: "absolute", top: 12, right: 12, color: PRIMARY }}
        />
      )}
      <div
        style={{
          width: 40,
          height: 40,
          borderRadius: "50%",
          background: selected ? "var(--color-primary-tint)" : "var(--color-surface-alt)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          margin: "0 auto 8px",
          color: selected ? PRIMARY : TEXT_MUTED,
          transition: "background 0.15s, color 0.15s",
        }}
      >
        {icon}
      </div>
      <span style={{ fontWeight: 500, color: TEXT_MAIN, fontSize: 14 }}>{label}</span>
    </button>
  );
}

function DirectoryRow({
  directoryId,
  setDirectoryId,
  directoriesData,
}: {
  directoryId: string;
  setDirectoryId: (id: string) => void;
  directoriesData: Array<{ id: string; name: string }>;
}) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <label style={{ ...labelStyle, marginBottom: 0 }}>Lista de destino</label>
        <Link
          to="/lists/new?returnTo=/search"
          style={{
            fontSize: 13,
            color: PRIMARY,
            fontWeight: 500,
            display: "flex",
            alignItems: "center",
            gap: 4,
            textDecoration: "none",
          }}
        >
          <Plus size={12} /> Crear nuevo
        </Link>
      </div>
      <SearchableSelect
        value={directoryId}
        onChange={setDirectoryId}
        options={directoriesData}
        placeholder="Buscar lista..."
        required
        ariaLabel="Lista destino"
      />
    </div>
  );
}

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
  const [activeMode, setActiveMode] = useState<"search" | "import">("search");
  const [targetUrl, setTargetUrl] = useState("");
  const [userPrompt, setUserPrompt] = useState("");
  const [selectedScrapingSiteIds, setSelectedScrapingSiteIds] = useState<Set<string>>(new Set());
  const searchFocus: SearchFocus = "general";
  const contactChannels = defaultChannelsForFocus(searchFocus);
  const directoriesQuery = useQuery({
    queryKey: ["directories"],
    queryFn: () => listDirectories(),
  });
  const scrapingSitesQuery = useQuery({
    queryKey: ["scraping-sites"],
    queryFn: () => listScrapingSites(),
  });

  useEffect(() => {
    if (preselectedDirectoryId) {
      setDirectoryId(preselectedDirectoryId);
    }
  }, [preselectedDirectoryId]);

  const queryPlaceholder = useMemo(() => {
    if (exaCategoryUi === "people") {
      return "ginecólogos en San Pedro Sula";
    }
    return "Aseguradoras de Tegucigalpa o Car Wash en Tegucigalpa";
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

  const urlScrapeMutation = useMutation({
    mutationFn: () =>
      createUrlScrapeJob({
        target_url: targetUrl.trim(),
        user_prompt: userPrompt.trim(),
        directory_id: directoryId || null,
      }),
    onSuccess: (job) => navigate(`/url-scrape-jobs/${job.job_id}`),
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
      scraping_site_ids: selectedScrapingSiteIds.size > 0 ? Array.from(selectedScrapingSiteIds) : undefined,
    });
  };

  const dirOptions = (directoriesQuery.data?.items ?? []).map((d) => ({ id: d.id, name: d.name }));

  const submitBtnStyle: React.CSSProperties = {
    width: "100%",
    background: PRIMARY,
    color: "white",
    border: "none",
    borderRadius: 12,
    padding: "16px 24px",
    fontWeight: 500,
    fontSize: 15,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    boxShadow: "0 4px 14px rgba(0,0,255,0.25)",
    fontFamily: "inherit",
    transition: "background 0.15s",
  };

  const modeTabStyle = (active: boolean): React.CSSProperties => ({
    flex: 1,
    padding: "12px 16px",
    borderRadius: 8,
    fontWeight: 500,
    fontSize: 14,
    border: "none",
    background: active ? "var(--c-card-bg)" : "transparent",
    color: active ? PRIMARY : TEXT_MUTED,
    boxShadow: active ? "0 1px 3px rgba(0,0,0,0.1), 0 0 0 1px rgba(0,0,0,0.05)" : "none",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    transition: "all 0.2s",
    fontFamily: "inherit",
  });

  return (
    <section
      className="search-page-v2"
      style={{ position: "relative", width: "100%", minHeight: "100%" }}
    >
      {/* Modals */}
      {showDirectoryModal ? (
        <div className="search-clarify-overlay" role="presentation">
          <div
            className="search-clarify-dialog panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="directory-modal-title"
          >
            <h3 id="directory-modal-title" className="search-clarify-title">
              Crear lista destino
            </h3>
            <p className="search-clarify-question muted-text">
              Debes crear o elegir una lista destino antes de lanzar la búsqueda. Una lista organiza tus prospectos en etapas personalizadas.
            </p>
            <div className="search-clarify-actions">
              <Button type="button" variant="ghost" onClick={() => setShowDirectoryModal(false)}>
                Cancelar
              </Button>
              <Link to="/lists/new?returnTo=/search" className="link-button">
                + Crear lista
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
                  clarifyMutation.mutate({ jobId: clarifyContext.jobId, reply: clarifyReply.trim() });
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

      {/* Gradient overlay */}
      <div
        aria-hidden
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: "40%",
          background: "linear-gradient(to bottom, var(--c-card-bg), transparent)",
          pointerEvents: "none",
          zIndex: 0,
        }}
      />

      {/* Main content */}
      <div
        style={{
          position: "relative",
          zIndex: 10,
          maxWidth: 700,
          margin: "0 auto",
          padding: "72px 24px 80px",
        }}
      >
        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: 48 }}>
          <h1
            style={{
              fontSize: "2.25rem",
              fontWeight: 700,
              color: TEXT_MAIN,
              margin: "0 0 16px",
              letterSpacing: "-0.02em",
              lineHeight: 1.15,
            }}
          >
            Nueva Búsqueda de Leads
          </h1>
          <p style={{ color: TEXT_MUTED, fontSize: "1.05rem", margin: 0 }}>
            Define tu objetivo ideal o importa datos externos para comenzar a prospectar.
          </p>
        </div>

        {/* Card */}
        <div style={cardStyle}>
          {/* Mode tabs */}
          <div
            style={{
              display: "flex",
              padding: 4,
              background: BG_LIGHT,
              borderRadius: 12,
              margin: "24px 0 32px",
            }}
          >
            <button type="button" style={modeTabStyle(activeMode === "search")} onClick={() => setActiveMode("search")}>
              <Zap size={15} aria-hidden /> Búsqueda EXA
            </button>
            <button type="button" style={modeTabStyle(activeMode === "import")} onClick={() => setActiveMode("import")}>
              <LinkIcon size={15} aria-hidden /> Importar URL
            </button>
          </div>

          {/* EXA search tab */}
          {activeMode === "search" ? (
            <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: 28 }}>
              {/* Type selector */}
              <div>
                <label style={labelStyle}>¿Qué estás buscando?</label>
                <div style={{ display: "flex", gap: 16 }}>
                  <TypeCard
                    selected={exaCategoryUi === "people"}
                    onClick={() => setExaCategoryUi("people")}
                    icon={<UserRound size={18} />}
                    label="Personas"
                  />
                  <TypeCard
                    selected={exaCategoryUi === "company"}
                    onClick={() => setExaCategoryUi("company")}
                    icon={<Building2 size={18} />}
                    label="Empresas"
                  />
                </div>
              </div>

              {/* Social network quick search — not yet functional */}
              <div>
                <label style={{ ...labelStyle, marginBottom: 8 }}>Buscar en red específica</label>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {[
                    { icon: <Instagram size={14} />, label: "Instagram", color: "#E1306C", bg: "#FDF2F8" },
                    { icon: <Facebook size={14} />, label: "Facebook", color: "#1877F2", bg: "#EFF6FF" },
                    { icon: <Linkedin size={14} />, label: "LinkedIn", color: "#0A66C2", bg: "#EFF6FF" },
                    { icon: <Twitter size={14} />, label: "Twitter / X", color: "var(--color-text)", bg: "var(--color-surface-alt)" },
                    { icon: <Youtube size={14} />, label: "YouTube", color: "#FF0000", bg: "#FEF2F2" },
                    { icon: <Map size={14} />, label: "Google Maps", color: "#059669", bg: "#F0FDF4" },
                  ].map(({ icon, label, color, bg }) => (
                    <button
                      key={label}
                      type="button"
                      disabled
                      title="Próximamente"
                      style={{
                        display: "inline-flex", alignItems: "center", gap: 6,
                        padding: "6px 12px", borderRadius: 8,
                        border: `1px solid ${color}30`,
                        background: bg, color,
                        fontSize: 12, fontWeight: 500,
                        fontFamily: "inherit",
                        cursor: "not-allowed", opacity: 0.65,
                      }}
                    >
                      {icon} {label}
                    </button>
                  ))}
                </div>
                <p style={{ fontSize: 11, color: TEXT_MUTED, marginTop: 6 }}>
                  Próximamente disponibles — por ahora usa la búsqueda general.
                </p>
              </div>

              {/* Scraping Sources */}
              {(scrapingSitesQuery.data?.items ?? []).length > 0 && (
                <div>
                  <label style={{ ...labelStyle, marginBottom: 8 }}>Incluir fuentes de scraping</label>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {scrapingSitesQuery.data?.items.map((site) => (
                      <label
                        key={site.site_id}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          padding: 8,
                          borderRadius: 8,
                          border: `1px solid ${BORDER}`,
                          cursor: "pointer",
                          transition: "background 0.15s",
                          background: selectedScrapingSiteIds.has(site.site_id)
                            ? "rgba(239, 246, 255, 0.5)"
                            : "transparent",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={selectedScrapingSiteIds.has(site.site_id)}
                          onChange={(e) => {
                            const next = new Set(selectedScrapingSiteIds);
                            if (e.target.checked) {
                              next.add(site.site_id);
                            } else {
                              next.delete(site.site_id);
                            }
                            setSelectedScrapingSiteIds(next);
                          }}
                          style={{ cursor: "pointer" }}
                        />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 500, color: TEXT_MAIN }}>
                            {site.title || new URL(site.url).hostname}
                          </div>
                          <div style={{ fontSize: 12, color: TEXT_MUTED }}>
                            {site.url}
                          </div>
                        </div>
                      </label>
                    ))}
                  </div>
                  <p style={{ fontSize: 11, color: TEXT_MUTED, marginTop: 6 }}>
                    Las fuentes se scraped en paralelo y sus resultados se agregan al directorio.
                  </p>
                </div>
              )}

              {/* Directory */}
              <DirectoryRow
                directoryId={directoryId}
                setDirectoryId={setDirectoryId}
                directoriesData={dirOptions}
              />

              {/* Query */}
              <div>
                <label style={labelStyle}>Consulta de búsqueda (IA)</label>
                <div style={{ position: "relative" }}>
                  <Search
                    size={18}
                    aria-hidden
                    style={{
                      position: "absolute",
                      left: 16,
                      top: 14,
                      color: PRIMARY,
                      pointerEvents: "none",
                    }}
                  />
                  <textarea
                    rows={3}
                    style={{
                      ...inputBaseStyle,
                      padding: "13px 16px 13px 48px",
                      resize: "none",
                    }}
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={`Ej: ${queryPlaceholder}...`}
                    required
                    minLength={3}
                    maxLength={500}
                    aria-label="Consulta de búsqueda"
                    onFocus={(e) => {
                      e.currentTarget.style.borderColor = PRIMARY;
                      e.currentTarget.style.boxShadow = `0 0 0 3px rgba(0,0,255,0.08)`;
                    }}
                    onBlur={(e) => {
                      e.currentTarget.style.borderColor = BORDER;
                      e.currentTarget.style.boxShadow = "none";
                    }}
                  />
                </div>
                <p
                  style={{
                    fontSize: 12,
                    color: TEXT_MUTED,
                    marginTop: 8,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <Sparkles size={12} style={{ color: PRIMARY }} aria-hidden />
                  Describe en lenguaje natural el perfil exacto que buscas.
                </p>
              </div>

              {/* Error */}
              {createJobMutation.isError ? (
                <p className="error-text" role="alert">
                  {createJobMutation.error instanceof Error
                    ? createJobMutation.error.message
                    : "No se pudo crear el trabajo de búsqueda."}
                </p>
              ) : null}

              {/* Submit */}
              <div style={{ paddingTop: 16, borderTop: "1px solid #F3F4F6" }}>
                <button
                  type="submit"
                  disabled={createJobMutation.isPending}
                  style={{
                    ...submitBtnStyle,
                    opacity: createJobMutation.isPending ? 0.7 : 1,
                    cursor: createJobMutation.isPending ? "not-allowed" : "pointer",
                  }}
                >
                  {createJobMutation.isPending ? (
                    <>
                      <Loader2 size={16} className="spin" aria-hidden />
                      <span>Buscando…</span>
                    </>
                  ) : (
                    <>
                      <span>Ejecutar búsqueda</span>
                      <ArrowRight size={16} aria-hidden />
                    </>
                  )}
                </button>
              </div>
            </form>
          ) : (
            /* URL import tab */
            <form
              style={{ display: "flex", flexDirection: "column", gap: 28 }}
              onSubmit={(e) => {
                e.preventDefault();
                if (!directoryId) {
                  setShowDirectoryModal(true);
                  return;
                }
                urlScrapeMutation.mutate();
              }}
            >
              {/* Directory */}
              <DirectoryRow
                directoryId={directoryId}
                setDirectoryId={setDirectoryId}
                directoriesData={dirOptions}
              />

              {/* URL */}
              <div>
                <label style={labelStyle}>URL Fuente</label>
                <div style={{ position: "relative" }}>
                  <Globe
                    size={16}
                    aria-hidden
                    style={{
                      position: "absolute",
                      left: 16,
                      top: "50%",
                      transform: "translateY(-50%)",
                      color: TEXT_MUTED,
                      pointerEvents: "none",
                    }}
                  />
                  <input
                    type="url"
                    style={{ ...inputBaseStyle, padding: "13px 16px 13px 44px" }}
                    value={targetUrl}
                    onChange={(e) => setTargetUrl(e.target.value)}
                    placeholder="https://ejemplo.com/lista..."
                    required
                    onFocus={(e) => {
                      e.currentTarget.style.borderColor = PRIMARY;
                      e.currentTarget.style.boxShadow = `0 0 0 3px rgba(0,0,255,0.08)`;
                    }}
                    onBlur={(e) => {
                      e.currentTarget.style.borderColor = BORDER;
                      e.currentTarget.style.boxShadow = "none";
                    }}
                  />
                </div>
              </div>

              {/* Instructions */}
              <div>
                <label style={labelStyle}>Instrucciones de extracción (IA)</label>
                <textarea
                  rows={5}
                  style={{ ...inputBaseStyle, padding: "13px 16px", resize: "none" }}
                  value={userPrompt}
                  onChange={(e) => setUserPrompt(e.target.value)}
                  placeholder="Ej: Extrae el nombre de la empresa, el correo de contacto y el teléfono de cada tarjeta en la página. Ignora los anuncios..."
                  required
                  onFocus={(e) => {
                    e.currentTarget.style.borderColor = PRIMARY;
                    e.currentTarget.style.boxShadow = `0 0 0 3px rgba(0,0,255,0.08)`;
                  }}
                  onBlur={(e) => {
                    e.currentTarget.style.borderColor = BORDER;
                    e.currentTarget.style.boxShadow = "none";
                  }}
                />
                <p style={{ fontSize: 12, color: TEXT_MUTED, marginTop: 8 }}>
                  Indícale a la IA qué datos específicos debe buscar y estructurar desde esta URL.
                </p>
              </div>

              {/* Error */}
              {urlScrapeMutation.isError ? (
                <p className="error-text" role="alert">
                  {urlScrapeMutation.error instanceof Error
                    ? urlScrapeMutation.error.message
                    : "No se pudo crear el trabajo de importación."}
                </p>
              ) : null}

              {/* Submit */}
              <div style={{ paddingTop: 16, borderTop: "1px solid #F3F4F6" }}>
                <button
                  type="submit"
                  disabled={urlScrapeMutation.isPending}
                  style={{
                    ...submitBtnStyle,
                    opacity: urlScrapeMutation.isPending ? 0.7 : 1,
                    cursor: urlScrapeMutation.isPending ? "not-allowed" : "pointer",
                  }}
                >
                  {urlScrapeMutation.isPending ? (
                    <>
                      <Loader2 size={16} className="spin" aria-hidden />
                      <span>Iniciando extracción…</span>
                    </>
                  ) : (
                    <>
                      <span>Extraer entradas</span>
                      <CloudDownload size={16} aria-hidden />
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>

      </div>
    </section>
  );
}
