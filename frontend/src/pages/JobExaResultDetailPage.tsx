import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Bookmark, Briefcase, ChevronLeft, ChevronRight, Download, ExternalLink, Loader2, Search } from "lucide-react";

import {
  createDirectorySource,
  createOpportunityFromPreview,
  downloadPreviewResultXlsx,
  getOpportunityByPreview,
  getSearchJobStatus,
  listDirectories,
  summarizeProfile,
  enrichOpportunity,
  savePreviewContact,
  type OpportunityEnrichResult,
} from "../api";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { EnrichContactModal, ENRICH_STAGES } from "../components/EnrichContactModal";
import { mergeAbortSignals, mergeProfileAboutText } from "../lib/utils";
import type { ExaResultPreviewItem } from "../types";

function hostLabel(url: string): string {
  try {
    const u = new URL(url.startsWith("http") ? url : `https://${url}`);
    return u.hostname.replace(/^www\./, "");
  } catch {
    return url.slice(0, 32);
  }
}

function profileInitial(name: string): string {
  const t = name.trim();
  return t ? t.charAt(0).toUpperCase() : "?";
}

function parseResultIndex(raw: string | undefined): number | null {
  if (!raw?.length) {
    return null;
  }
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function findPreviewRow(preview: ExaResultPreviewItem[] | undefined, index: number): ExaResultPreviewItem | undefined {
  return preview?.find((row) => row.index === index);
}

function cleanAiText(value: string | null | undefined): string {
  return value?.replace(/\s+/g, " ").trim() || "";
}

function cleanAiField(value: string | null | undefined): string {
  const v = value?.trim() ?? "";
  if (v === "null" || v === "undefined" || v === "N/A" || v === "n/a") return "";
  return v;
}

function inferCompanyFromText(title: string, snippet: string): string {
  const text = `${title} ${snippet}`.trim();
  const byIn = text.match(/\ben\s+([^|,/.-]{2,80})/i);
  if (byIn?.[1]) return byIn[1].trim();
  const byAt = text.match(/\b(?:at|@)\s+([^|,/.-]{2,80})/i);
  if (byAt?.[1]) return byAt[1].trim();
  return "";
}

function inferLocationFromText(city: string, title: string, snippet: string): string {
  if (city.trim()) return city.trim();
  const text = `${title} ${snippet}`.trim();
  const from = text.match(/\b(?:en|de)\s+([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ\s]{2,50})/);
  return from?.[1]?.trim() || "";
}

/** Evita espera infinita si el backend no responde (p. ej. Gemini colgado). */
const PROFILE_SUMMARY_TIMEOUT_MS = 90_000;



function profileSummaryErrorMessage(err: unknown): string {
  if (err instanceof DOMException && err.name === "AbortError") {
    return "El resumen con IA tardó demasiado o se canceló. Puedes recargar la página o revisar el backend.";
  }
  if (err instanceof Error) {
    const m = err.message;
    if (/abort/i.test(m) || m.includes("The user aborted")) {
      return "El resumen con IA tardó demasiado o se canceló. Puedes recargar la página o revisar el backend.";
    }
    return m;
  }
  return "No se pudo generar el resumen con IA. Se muestran los datos del resultado.";
}

export function JobExaResultDetailPage(): JSX.Element {
  const { jobId = "", resultIndex: resultIndexParam = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const resultIndex = parseResultIndex(resultIndexParam);
  const [enrichModalOpen, setEnrichModalOpen] = useState(false);
  const [enrichStageIdx, setEnrichStageIdx] = useState(0);
  const [isExporting, setIsExporting] = useState(false);
  const [savedAsSource, setSavedAsSource] = useState(false);
  const [savingAsSource, setSavingAsSource] = useState(false);
  const [sourceDirPickerOpen, setSourceDirPickerOpen] = useState(false);
  const [sourceDirId, setSourceDirId] = useState("");

  const jobQuery = useQuery({
    queryKey: ["job-status", jobId],
    queryFn: () => getSearchJobStatus(jobId),
    enabled: Boolean(jobId),
  });

  const jobDirectoryId = (jobQuery.data as unknown as { directory_id?: string })?.directory_id ?? null;

  const directoriesQuery = useQuery({
    queryKey: ["directories"],
    queryFn: listDirectories,
    staleTime: 60_000,
    enabled: sourceDirPickerOpen,
  });

  const saveAsSource = async (dirId: string) => {
    if (!url) return;
    setSavingAsSource(true);
    try {
      await createDirectorySource(dirId, {
        url,
        title,
        source_search_job_id: jobId,
      });
      setSavedAsSource(true);
      setSourceDirPickerOpen(false);
      setSourceDirId("");
    } catch { /* silent */ } finally {
      setSavingAsSource(false);
    }
  };

  const row = useMemo(
    () => (resultIndex != null ? findPreviewRow(jobQuery.data?.exa_results_preview, resultIndex) : undefined),
    [jobQuery.data?.exa_results_preview, resultIndex],
  );

  const hasPreviewRow = useMemo(
    () =>
      Boolean(
        jobQuery.isSuccess &&
          resultIndex != null &&
          (jobQuery.data?.exa_results_preview ?? []).some((r) => r.index === resultIndex),
      ),
    [jobQuery.isSuccess, jobQuery.data?.exa_results_preview, resultIndex],
  );

  const oppLookup = useQuery({
    queryKey: ["opportunity-by-preview", jobId, resultIndex],
    queryFn: () => getOpportunityByPreview(jobId, resultIndex!),
    enabled: Boolean(jobId && resultIndex && hasPreviewRow),
  });

  const createOppMut = useMutation({
    mutationFn: () => {
      // Pasar los datos enriquecidos del preview a la oportunidad
      const contactData: Record<string, string> = {};
      if (row?.email) contactData.email = row.email;
      if (row?.phone) contactData.phone = row.phone;
      if (row?.whatsapp) contactData.whatsapp = row.whatsapp;

      return createOpportunityFromPreview({
        job_id: jobId,
        exa_preview_index: resultIndex!,
        contact_overrides: Object.keys(contactData).length > 0 ? contactData : undefined,
      });
    },
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["opportunities"] });
      void queryClient.invalidateQueries({ queryKey: ["opportunity-by-preview", jobId, resultIndex] });
      navigate(`/opportunities/${data.opportunity_id}`);
    },
  });

  const enrichMut = useMutation<OpportunityEnrichResult>({
    mutationFn: async () => {
      const opp = oppLookup.data;
      if (opp) {
        return enrichOpportunity(opp.opportunity_id, (msg) => {
          const idx = ENRICH_STAGES.indexOf(msg);
          if (idx >= 0) {
            setEnrichStageIdx(idx);
          }
        });
      }
      const newOpp = await createOpportunityFromPreview({ job_id: jobId, exa_preview_index: resultIndex! });
      void queryClient.invalidateQueries({ queryKey: ["opportunity-by-preview", jobId, resultIndex] });
      return enrichOpportunity(newOpp.opportunity_id, (msg) => {
        const idx = ENRICH_STAGES.indexOf(msg);
        if (idx >= 0) {
          setEnrichStageIdx(idx);
        }
      });
    },
  });

  const saveMut = useMutation({
    mutationFn: (data: { email?: string; phone?: string; whatsapp?: string; source_urls?: string[] }) =>
      savePreviewContact(jobId, resultIndex!, data),
    onSuccess: (_, savedData) => {
      // Actualizar el row local inmediatamente sin recargar
      if (row) {
        const updatedRow = {
          ...row,
          email: savedData.email !== undefined ? savedData.email : row.email,
          phone: savedData.phone !== undefined ? savedData.phone : row.phone,
          whatsapp: savedData.whatsapp !== undefined ? savedData.whatsapp : row.whatsapp,
          saved_source_urls: savedData.source_urls !== undefined ? savedData.source_urls : row.saved_source_urls,
        };
        // Actualizar el cache de React Query directamente
        queryClient.setQueryData(["job-status", jobId], (oldData: any) => {
          if (!oldData) return oldData;
          return {
            ...oldData,
            exa_results_preview: (oldData.exa_results_preview || []).map((item: any) =>
              item.index === resultIndex ? updatedRow : item
            ),
          };
        });
      }
      setEnrichModalOpen(false);
    },
  });

  const profileSectionsQuery = useQuery({
    queryKey: ["profile-sections", jobId, resultIndex],
    queryFn: async ({ signal }) => {
      const r = resultIndex != null ? findPreviewRow(jobQuery.data?.exa_results_preview, resultIndex) : undefined;
      const titleQ = r?.title?.trim() || "Sin título";
      const descriptionQ = r?.snippet?.trim() || "Abre la fuente para ver el contexto completo en la web.";
      const specialtyQ = (r?.specialty ?? "").trim();
      const cityQ = (r?.city ?? "").trim();
      const timeoutCtrl = new AbortController();
      const tid = window.setTimeout(() => timeoutCtrl.abort(), PROFILE_SUMMARY_TIMEOUT_MS);
      try {
        return await summarizeProfile(
          {
            title: titleQ,
            specialty: specialtyQ || null,
            city: cityQ || null,
            snippet: descriptionQ || null,
          },
          { signal: mergeAbortSignals(signal, timeoutCtrl.signal) },
        );
      } finally {
        window.clearTimeout(tid);
      }
    },
    enabled: Boolean(jobId && resultIndex != null && jobQuery.isSuccess && jobQuery.data && row),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  if (!jobId || resultIndex == null) {
    return <section className="panel error-text">Enlace de resultado no válido.</section>;
  }

  if (jobQuery.isLoading) {
    return <section className="panel">Cargando resultado…</section>;
  }

  if (jobQuery.isError || !jobQuery.data) {
    return <section className="panel error-text">No se pudo cargar el trabajo de búsqueda.</section>;
  }

  if (jobQuery.data.status === "error") {
    return (
      <section className="panel" style={{ padding: "1.5rem", maxWidth: 560 }}>
        <p className="error-text" style={{ marginBottom: "0.75rem" }}>
          <strong>Esta búsqueda terminó con error.</strong>
        </p>
        {jobQuery.data.error_message ? (
          <p className="muted-text" style={{ whiteSpace: "pre-wrap", marginBottom: "1rem", fontSize: "0.95rem" }}>
            {jobQuery.data.error_message}
          </p>
        ) : null}
        <Link to={`/jobs/${jobId}`} className="link-button">
          <ChevronLeft size={14} aria-hidden /> Volver a la búsqueda
        </Link>
      </section>
    );
  }

  const title = row?.title?.trim() || "Sin título";
  const url = row?.url?.trim() || "";
  const specialty = (row?.specialty ?? "").trim();
  const city = (row?.city ?? "").trim();
  const description = row?.snippet?.trim() || "Abre la fuente para ver el contexto completo en la web.";

  if (!row) {
    return (
      <section className="panel error-text">
        No se encontró el resultado en esta búsqueda.{" "}
        <Link to={`/jobs/${jobId}`} className="link-button">
          <ChevronLeft size={14} aria-hidden />
        </Link>
      </section>
    );
  }

  const aiSummary = cleanAiText(profileSectionsQuery.data?.professional_summary);
  const aiAbout = cleanAiText(profileSectionsQuery.data?.about);
  const aiCompany = cleanAiField(profileSectionsQuery.data?.company);
  const aiLocation = cleanAiField(profileSectionsQuery.data?.location);
  const aboutText = mergeProfileAboutText(aiAbout, aiSummary, specialty || description);
  /** Cuando no hay experiencia estructurada, se muestra el resumen o el snippet. */
  const experienceFallback = aiSummary || specialty || description;
  const normalizedLocation = aiLocation || inferLocationFromText(city, title, description) || "";
  const normalizedCompany = aiCompany || inferCompanyFromText(title, description) || "";
  const experiences = profileSectionsQuery.data?.experiences ?? [];

  const existingOpp = oppLookup.data;
  const oppLoading = oppLookup.isLoading;

  return (
    <section className="lead-detail-page lead-detail-page--two-col lead-detail-page--preview">
      <nav className="lead-detail-topbar" aria-label="Navegación del detalle">
        <button type="button" className="link-button lead-back-button" onClick={() => navigate(-1)}>
          <ChevronLeft size={14} aria-hidden />
        </button>
      </nav>

      <div className="lead-detail-grid lead-detail-grid--proposal-b">
        <div className="lead-detail-main">
          <Card className="panel lead-detail-hero">
            <div className="lead-detail-hero-visual">
              <span className="lead-detail-avatar" aria-hidden>
                {profileInitial(title)}
              </span>
            </div>
            <div className="lead-detail-hero-text">
              <h1 className="lead-detail-title">{title}</h1>
              {specialty || city ? (
                <p className="lead-detail-context-line muted-text">
                  {[specialty || null, city || null].filter(Boolean).join(" · ")}
                </p>
              ) : null}
            </div>
          </Card>

          <div className="lead-detail-summary-section">
            {profileSectionsQuery.isError ? (
              <p className="error-text lead-detail-ai-error" role="alert">
                {profileSummaryErrorMessage(profileSectionsQuery.error)}
              </p>
            ) : null}
            <div className="lead-detail-summary-actions">
              <button
                type="button"
                className="workspace-tool-btn"
                onClick={() => {
                  setEnrichModalOpen(true);
                  setEnrichStageIdx(0);
                  enrichMut.reset();
                  enrichMut.mutate();
                }}
                disabled={enrichMut.isPending}
              >
                <Search size={16} aria-hidden /> Enriquecer
              </button>
              <button
                type="button"
                className="workspace-tool-btn"
                onClick={async () => {
                  if (!jobId || resultIndex == null) return;
                  setIsExporting(true);
                  try {
                    const downloadName = existingOpp?.title || title;
                    await downloadPreviewResultXlsx(jobId, resultIndex, downloadName);
                  } catch (err) {
                    console.error("Export failed:", err);
                  } finally {
                    setIsExporting(false);
                  }
                }}
                disabled={isExporting}
              >
                <Download size={16} aria-hidden /> Exportar
              </button>
            </div>
            <div className={`lead-detail-summary-cards${profileSectionsQuery.isFetching ? " lead-detail-summary-cards--loading" : ""}`}>
              <article className="lead-detail-summary-card panel">
                <h3>Acerca de</h3>
                <p>{aboutText}</p>
              </article>
              <article className="lead-detail-summary-card lead-detail-summary-card--experience panel">
                <h3>Experiencia</h3>
                {experiences.length > 0 ? (
                  <ul className="opportunity-summary-experience-list">
                    {experiences.map((experience, index) => (
                      <li key={`${experience.role}-${index}`} className="opportunity-summary-experience-item">
                        <strong>{experience.role}</strong>
                        {(() => {
                          const org = cleanAiField(experience.organization);
                          const period = cleanAiField(experience.period);
                          const parts = [org, period].filter(Boolean);
                          return parts.length ? (
                            <span className="muted-text">{parts.join(" · ")}</span>
                          ) : null;
                        })()}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="lead-detail-experience-fallback-text muted-text">{experienceFallback}</p>
                )}
              </article>
              {normalizedLocation && (
                <article className="lead-detail-summary-card panel">
                  <h3>Ubicación</h3>
                  <p>{normalizedLocation}</p>
                </article>
              )}
              {normalizedCompany && (
                <article className="lead-detail-summary-card panel">
                  <h3>Empresa</h3>
                  <p>{normalizedCompany}</p>
                </article>
              )}
            </div>
          </div>

          <Card className="panel lead-detail-card">
            <h2 className="lead-detail-section-title">Fuentes y enlaces</h2>
            {url ? (
              <ul className="lead-source-link-list">
                {url && (
                  <li className="lead-source-link-row">
                    <span className="lead-source-host">{hostLabel(url)}</span>
                    <a href={url} target="_blank" rel="noreferrer" className="lead-source-anchor">
                      {title}
                      <ExternalLink size={14} aria-hidden />
                    </a>
                  </li>
                )}
                {row.saved_source_urls?.map((surl, idx) => (
                  <li key={`saved-src-${idx}`} className="lead-source-link-row">
                    <span className="lead-source-host">{hostLabel(surl)}</span>
                    <a href={surl} target="_blank" rel="noreferrer" className="lead-source-anchor">
                      {surl}
                      <ExternalLink size={14} aria-hidden />
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted-text">No hay URL registrada para este resultado.</p>
            )}
          </Card>
        </div>

        <aside className="lead-detail-sidebar" aria-label="Acciones">
          <section className="panel lead-detail-card lead-detail-contact-card">
            <h2 className="lead-detail-section-title">Contacto</h2>
            {row?.email || row?.phone || row?.whatsapp || row?.linkedin_url ? (
              <p className="muted-text lead-detail-card-hint">
                Información encontrada en la búsqueda. Podrás confirmar o agregar más en la ficha de oportunidad.
              </p>
            ) : (
              <p className="muted-text lead-detail-card-hint">
                Tras crear la oportunidad podrás registrar correos, teléfonos, WhatsApp y más en la ficha.
              </p>
            )}
            <dl className="lead-contact-dl">
              {row?.email && (
                <div className="lead-contact-row">
                  <dt>Correo</dt>
                  <dd>
                    <a href={`mailto:${row.email}`} className="link">
                      {row.email}
                    </a>
                  </dd>
                </div>
              )}
              {row?.phone && (
                <div className="lead-contact-row">
                  <dt>Teléfono</dt>
                  <dd>
                    <a href={`tel:${row.phone}`} className="link">
                      {row.phone}
                    </a>
                  </dd>
                </div>
              )}
              {row?.whatsapp && (
                <div className="lead-contact-row">
                  <dt>WhatsApp</dt>
                  <dd>
                    <a href={`https://wa.me/${row.whatsapp.replace(/\D/g, '')}`} target="_blank" rel="noreferrer" className="link">
                      {row.whatsapp}
                    </a>
                  </dd>
                </div>
              )}
              {row?.linkedin_url && (
                <div className="lead-contact-row">
                  <dt>LinkedIn</dt>
                  <dd>
                    <a href={row.linkedin_url} target="_blank" rel="noreferrer" className="link">
                      Perfil
                      <ExternalLink size={14} aria-hidden />
                    </a>
                  </dd>
                </div>
              )}
              {url && (
                <div className="lead-contact-row">
                  <dt>Fuente</dt>
                  <dd>
                    <a href={url} target="_blank" rel="noreferrer" className="link">
                      {hostLabel(url)}
                      <ExternalLink size={14} aria-hidden />
                    </a>
                  </dd>
                </div>
              )}
            </dl>
          </section>

          <Card className="panel lead-detail-opportunity-card">
            <div className="lead-detail-opportunity-icon" aria-hidden>
              <Briefcase size={22} />
            </div>
            <h2 className="lead-detail-section-title">Oportunidad</h2>
            <p className="muted-text lead-detail-opportunity-copy">
              Guarda este resultado como oportunidad para dar seguimiento comercial: fases, bitácora y varios contactos.
            </p>
            {oppLoading ? (
              <p className="muted-text lead-detail-opportunity-status">
                <Loader2 className="spin" size={16} aria-hidden /> Comprobando…
              </p>
            ) : null}
            {!oppLoading && existingOpp ? (
              <Link
                className="cta-button lead-detail-opportunity-cta"
                to={`/opportunities/${existingOpp.opportunity_id}`}
              >
                Ir a la oportunidad
                <ChevronRight size={16} aria-hidden />
              </Link>
            ) : null}
            {!oppLoading && !existingOpp ? (
              <Button
                type="button"
                className="cta-button lead-detail-opportunity-cta"
                disabled={createOppMut.isPending}
                onClick={() => createOppMut.mutate()}
              >
                {createOppMut.isPending ? <Loader2 className="spin" size={16} aria-hidden /> : null}
                Crear oportunidad
              </Button>
            ) : null}
            {createOppMut.isError ? (
              <p className="error-text lead-detail-opportunity-error" role="alert">
                No se pudo crear la oportunidad. Revisa que el resultado siga disponible en el job.
              </p>
            ) : null}
          </Card>

          {url ? (
            <Card className="panel lead-detail-opportunity-card">
              <div className="lead-detail-opportunity-icon" aria-hidden>
                <Bookmark size={22} />
              </div>
              <h2 className="lead-detail-section-title">Fuente</h2>
              <p className="muted-text lead-detail-opportunity-copy">
                Guarda esta URL como fuente de un directorio para explorarla más adelante.
              </p>
              {savedAsSource ? (
                <p className="muted-text" style={{ fontSize: 13 }}>✓ Guardado como fuente</p>
              ) : jobDirectoryId ? (
                <Button
                  type="button"
                  className="cta-button lead-detail-opportunity-cta"
                  disabled={savingAsSource}
                  onClick={() => saveAsSource(jobDirectoryId)}
                >
                  {savingAsSource ? <Loader2 className="spin" size={16} aria-hidden /> : null}
                  Guardar como fuente
                </Button>
              ) : sourceDirPickerOpen ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                  <select
                    className="workspace-v3-sources-dir-select"
                    style={{ width: "100%" }}
                    value={sourceDirId}
                    onChange={(e) => setSourceDirId(e.target.value)}
                  >
                    <option value="">Elegir directorio…</option>
                    {(directoriesQuery.data?.items ?? []).map((d) => (
                      <option key={d.id} value={d.id}>{d.name}</option>
                    ))}
                  </select>
                  <div style={{ display: "flex", gap: 6 }}>
                    <Button
                      type="button"
                      variant="default"
                      size="sm"
                      disabled={!sourceDirId || savingAsSource}
                      onClick={() => saveAsSource(sourceDirId)}
                    >
                      {savingAsSource ? <Loader2 className="spin" size={13} aria-hidden /> : null}
                      Guardar
                    </Button>
                    <Button type="button" variant="ghost" size="sm" onClick={() => setSourceDirPickerOpen(false)}>
                      Cancelar
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  type="button"
                  className="cta-button lead-detail-opportunity-cta"
                  onClick={() => setSourceDirPickerOpen(true)}
                >
                  Guardar como fuente
                </Button>
              )}
            </Card>
          ) : null}
        </aside>
      </div>

      <EnrichContactModal
        isOpen={enrichModalOpen}
        onClose={() => {
          setEnrichModalOpen(false);
        }}
        isPending={enrichMut.isPending}
        isError={enrichMut.isError}
        stageIdx={enrichStageIdx}
        data={enrichMut.data ?? null}
        onSave={(data) => saveMut.mutate(data)}
        isSaving={saveMut.isPending}
        saveError={saveMut.isError}
      />
    </section>
  );
}
