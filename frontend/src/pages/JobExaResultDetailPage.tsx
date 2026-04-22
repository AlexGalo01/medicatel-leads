import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Briefcase, ChevronLeft, ChevronRight, ExternalLink, Loader2 } from "lucide-react";

import {
  createOpportunityFromPreview,
  getOpportunityByPreview,
  getSearchJobStatus,
  summarizeProfile,
} from "../api";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { mergeProfileAboutText } from "../lib/utils";
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

export function JobExaResultDetailPage(): JSX.Element {
  const { jobId = "", resultIndex: resultIndexParam = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const resultIndex = parseResultIndex(resultIndexParam);

  const jobQuery = useQuery({
    queryKey: ["job-status", jobId],
    queryFn: () => getSearchJobStatus(jobId),
    enabled: Boolean(jobId),
  });

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
    mutationFn: () =>
      createOpportunityFromPreview({ job_id: jobId, exa_preview_index: resultIndex! }),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["opportunities"] });
      void queryClient.invalidateQueries({ queryKey: ["opportunity-by-preview", jobId, resultIndex] });
      navigate(`/opportunities/${data.opportunity_id}`);
    },
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

  const title = row?.title?.trim() || "Sin título";
  const url = row?.url?.trim() || "";
  const specialty = (row?.specialty ?? "").trim();
  const city = (row?.city ?? "").trim();
  const description = row?.snippet?.trim() || "Abre la fuente para ver el contexto completo en la web.";
  const profileSectionsQuery = useQuery({
    queryKey: ["profile-sections", jobId, resultIndex, title, specialty, city, description],
    queryFn: () =>
      summarizeProfile({
        title,
        specialty: specialty || null,
        city: city || null,
        snippet: description || null,
      }),
    enabled: Boolean(row),
    staleTime: 5 * 60 * 1000,
  });

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
  const aiCompany = cleanAiText(profileSectionsQuery.data?.company);
  const aiLocation = cleanAiText(profileSectionsQuery.data?.location);
  const aboutText = mergeProfileAboutText(aiAbout, aiSummary, specialty || description);
  /** Cuando no hay experiencia estructurada, se muestra el resumen o el snippet. */
  const experienceFallback = aiSummary || specialty || description;
  const normalizedLocation = aiLocation || inferLocationFromText(city, title, description) || "No especificada";
  const normalizedCompany = aiCompany || inferCompanyFromText(title, description) || "No especificada";
  const experiences = profileSectionsQuery.data?.experiences ?? [];

  const existingOpp = oppLookup.data;
  const oppLoading = oppLookup.isLoading;

  return (
    <section className="lead-detail-page lead-detail-page--two-col lead-detail-page--preview">
      <nav className="lead-detail-topbar" aria-label="Navegación del detalle">
        <Link className="link-button lead-back-button" to={`/jobs/${jobId}`}>
          <ChevronLeft size={14} aria-hidden />
        </Link>
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

          <details className="panel lead-detail-accordion" open>
            <summary className="lead-detail-accordion-summary">Resumen</summary>
            <div className="lead-detail-accordion-body">
              <div className="lead-detail-summary-actions">
                <button type="button" className="workspace-tool-btn" disabled>
                  Enrichment (próximamente)
                </button>
              </div>
              <div className="lead-detail-summary-cards">
                <article className="lead-detail-summary-card">
                  <h3>About</h3>
                  <p>{aboutText}</p>
                </article>
                <article className="lead-detail-summary-card">
                  <h3>Experiencia</h3>
                  {experiences.length > 0 ? (
                    <ul className="opportunity-summary-experience-list">
                      {experiences.map((experience, index) => (
                        <li key={`${experience.role}-${index}`} className="opportunity-summary-experience-item">
                          <strong>{experience.role}</strong>
                          <span className="muted-text">
                            {[experience.organization || null, experience.period || null].filter(Boolean).join(" · ") || "Sin detalle"}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>{experienceFallback}</p>
                  )}
                </article>
                <article className="lead-detail-summary-card">
                  <h3>Ubicación</h3>
                  <p>{normalizedLocation}</p>
                </article>
                <article className="lead-detail-summary-card">
                  <h3>Empresa</h3>
                  <p>{normalizedCompany}</p>
                </article>
              </div>
              {profileSectionsQuery.isError ? (
                <p className="muted-text lead-detail-description">No se pudo estructurar completamente con IA; se muestran datos base.</p>
              ) : null}
            </div>
          </details>

          <Card className="panel lead-detail-card">
            <h2 className="lead-detail-section-title">Fuentes y enlaces</h2>
            {url ? (
              <ul className="lead-source-link-list">
                <li className="lead-source-link-row">
                  <span className="lead-source-host">{hostLabel(url)}</span>
                  <a href={url} target="_blank" rel="noreferrer" className="lead-source-anchor">
                    {title}
                    <ExternalLink size={14} aria-hidden />
                  </a>
                </li>
              </ul>
            ) : (
              <p className="muted-text">No hay URL registrada para este resultado.</p>
            )}
          </Card>
        </div>

        <aside className="lead-detail-sidebar" aria-label="Acciones">
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

          <section className="panel lead-detail-card lead-detail-contact-card">
            <h2 className="lead-detail-section-title">Contacto</h2>
            <p className="muted-text lead-detail-card-hint">
              Tras crear la oportunidad podrás registrar correos, teléfonos, WhatsApp y más en la ficha.
            </p>
            <dl className="lead-contact-dl">
              <div className="lead-contact-row">
                <dt>Correo</dt>
                <dd>
                  <span className="muted-text">En la ficha de oportunidad</span>
                </dd>
              </div>
              <div className="lead-contact-row">
                <dt>WhatsApp</dt>
                <dd>
                  <span className="muted-text">En la ficha de oportunidad</span>
                </dd>
              </div>
              <div className="lead-contact-row">
                <dt>LinkedIn</dt>
                <dd>
                  <span className="muted-text">En la ficha de oportunidad</span>
                </dd>
              </div>
              <div className="lead-contact-row">
                <dt>Fuente principal</dt>
                <dd>
                  {url ? (
                    <a href={url} target="_blank" rel="noreferrer">
                      {hostLabel(url)}
                      <ExternalLink size={14} aria-hidden />
                    </a>
                  ) : (
                    <span className="muted-text">—</span>
                  )}
                </dd>
              </div>
            </dl>
          </section>
        </aside>
      </div>
    </section>
  );
}
