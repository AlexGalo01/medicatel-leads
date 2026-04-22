import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { Check, ExternalLink, Sparkles } from "lucide-react";

import { deepEnrichLead, getLeadDetail } from "../api";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import type { LeadSourceCitation } from "../types";

function formatDateTime(dateValue: string): string {
  const parsedDate = new Date(dateValue);
  if (Number.isNaN(parsedDate.getTime())) {
    return "Sin fecha";
  }
  return parsedDate.toLocaleString("es-HN");
}

function normalizeCitations(raw: LeadSourceCitation[]): LeadSourceCitation[] {
  return raw
    .map((item) => ({
      url: typeof item.url === "string" ? item.url.trim() : "",
      title: typeof item.title === "string" ? item.title : "Fuente",
      confidence: typeof item.confidence === "string" ? item.confidence : undefined,
    }))
    .filter((citation) => citation.url.length > 0);
}

function collectSourceLinks(primaryUrl: string | null, citations: LeadSourceCitation[]): { url: string; label: string }[] {
  const seen = new Set<string>();
  const out: { url: string; label: string }[] = [];
  if (primaryUrl) {
    seen.add(primaryUrl);
    out.push({ url: primaryUrl, label: "Fuente principal del pipeline" });
  }
  for (const citation of citations) {
    if (seen.has(citation.url)) {
      continue;
    }
    seen.add(citation.url);
    out.push({ url: citation.url, label: citation.title || citation.url });
  }
  return out;
}

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

export function LeadDetailPage(): JSX.Element {
  const { leadId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [deepError, setDeepError] = useState<string | null>(null);

  const leadDetailQuery = useQuery({
    queryKey: ["lead-detail", leadId],
    queryFn: () => getLeadDetail(leadId),
    enabled: Boolean(leadId),
  });

  const deepEnrichMutation = useMutation({
    mutationFn: () => deepEnrichLead(leadId),
    onSuccess: (updated) => {
      setDeepError(null);
      queryClient.setQueryData(["lead-detail", leadId], updated);
    },
    onError: (error: Error) => {
      setDeepError(error.message);
    },
  });

  const citations = useMemo(() => {
    const raw = leadDetailQuery.data?.source_citations;
    if (!raw?.length) {
      return [];
    }
    return normalizeCitations(raw);
  }, [leadDetailQuery.data?.source_citations]);

  const sourceLinks = useMemo(
    () => collectSourceLinks(leadDetailQuery.data?.primary_source_url ?? null, citations),
    [leadDetailQuery.data?.primary_source_url, citations],
  );

  if (leadDetailQuery.isLoading) {
    return <section className="panel">Cargando detalle…</section>;
  }
  if (leadDetailQuery.isError || !leadDetailQuery.data) {
    return <section className="panel error-text">No se pudo cargar esta oportunidad.</section>;
  }

  const lead = leadDetailQuery.data;
  const description =
    lead.score_reasoning?.trim() ||
    "Aún no hay un resumen de relevancia. Puedes ejecutar el enriquecimiento para buscar evidencia verificable en la web (perfiles públicos, directorios, etc.).";

  const hasContact = Boolean(lead.email || lead.whatsapp || lead.linkedin_url);

  return (
    <section className="lead-detail-page lead-detail-page--two-col">
      <nav className="lead-detail-topbar" aria-label="Navegación del detalle">
        <button className="link-button lead-back-button" onClick={() => navigate(-1)} type="button">
          Volver a la lista
        </button>
      </nav>

      {deepError ? (
        <div className="panel error-text lead-detail-inline-alert" role="alert">
          {deepError}
        </div>
      ) : null}

      <div className="lead-detail-grid lead-detail-grid--proposal-b">
        <div className="lead-detail-main">
          <Card className="panel lead-detail-hero">
            <div className="lead-detail-hero-visual">
              <span className="lead-detail-avatar" aria-hidden>
                {profileInitial(lead.full_name)}
              </span>
            </div>
            <div className="lead-detail-hero-text">
              <h1 className="lead-detail-title">{lead.full_name}</h1>
              <p className="lead-detail-subtitle muted-text">
                {lead.specialty}
                {lead.city || lead.country
                  ? ` · ${[lead.city, lead.country].filter(Boolean).join(", ")}`
                  : null}
              </p>
              <div className="lead-detail-hero-meta">
                <span className="lead-score-badge">Score IA: {lead.score ?? "—"}</span>
                <span className="muted-text lead-detail-validation">Validación: {lead.validation_status}</span>
              </div>
            </div>
          </Card>

          <details className="panel lead-detail-accordion" open>
            <summary className="lead-detail-accordion-summary">Resumen de relevancia</summary>
            <div className="lead-detail-accordion-body">
              <p className="lead-detail-description">{description}</p>
            </div>
          </details>

          <details className="panel lead-detail-accordion" open={citations.length > 0}>
            <summary className="lead-detail-accordion-summary">Evidencia y referencias</summary>
            <div className="lead-detail-accordion-body">
              {citations.length > 0 ? (
                <ul className="lead-evidence-list">
                  {citations.map((citation) => (
                    <li key={citation.url} className="lead-evidence-row">
                      <span className="lead-evidence-check" aria-hidden>
                        <Check size={20} strokeWidth={2.5} />
                      </span>
                      <div>
                        <div className="lead-evidence-title">{citation.title}</div>
                        <p className="muted-text lead-evidence-note">
                          Referencia indexada en el pipeline
                          {citation.confidence ? ` · confianza: ${citation.confidence}` : ""}.
                        </p>
                        <a
                          className="lead-evidence-link"
                          href={citation.url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {hostLabel(citation.url)}
                          <ExternalLink size={14} aria-hidden />
                        </a>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted-text">
                  Sin citas estructuradas todavía. Tras enriquecer la oportunidad pueden aparecer enlaces verificables aquí.
                </p>
              )}
            </div>
          </details>

          <Card className="panel lead-detail-card">
            <h2 className="lead-detail-section-title">Fuentes y enlaces</h2>
            {sourceLinks.length > 0 ? (
              <ul className="lead-source-link-list">
                {sourceLinks.map((item) => (
                  <li key={item.url} className="lead-source-link-row">
                    <span className="lead-source-host">{hostLabel(item.url)}</span>
                    <a href={item.url} target="_blank" rel="noreferrer" className="lead-source-anchor">
                      {item.label}
                      <ExternalLink size={14} aria-hidden />
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted-text">No hay URLs de fuente registradas.</p>
            )}
          </Card>
        </div>

        <aside className="lead-detail-sidebar" aria-label="Contacto y acciones">
          <Card className="panel lead-detail-enrich-card">
            <div className="lead-detail-enrich-icon" aria-hidden>
              <Sparkles size={22} />
            </div>
            <h2 className="lead-detail-enrich-title">Enriquecer esta oportunidad</h2>
            <p className="muted-text lead-detail-enrich-copy">
              Ejecuta una búsqueda ampliada con IA sobre la web para localizar correo, WhatsApp, LinkedIn y otras pistas
              públicas. Más adelante podrás orientar el agente hacia Instagram u otras redes.
            </p>
            <Button
              className="cta-button lead-detail-enrich-cta"
              type="button"
              disabled={deepEnrichMutation.isPending || !leadId}
              onClick={() => {
                setDeepError(null);
                deepEnrichMutation.mutate();
              }}
            >
              {deepEnrichMutation.isPending ? "Búsqueda en curso…" : "Ejecutar búsqueda extensiva"}
            </Button>
            {lead.enrichment_message ? (
              <p className="lead-detail-enrich-status muted-text">
                <strong>Última ejecución:</strong> {lead.enrichment_message}
                {lead.enrichment_status ? ` (${lead.enrichment_status})` : null}
              </p>
            ) : null}
          </Card>

          <Card className="panel lead-detail-card lead-detail-contact-card">
            <h2 className="lead-detail-section-title">Contacto</h2>
            <p className="muted-text lead-detail-card-hint">Solo datos presentes en el registro o añadidos tras enriquecer.</p>
            <dl className="lead-contact-dl">
              <div className="lead-contact-row">
                <dt>Correo</dt>
                <dd>{lead.email ? <a href={`mailto:${lead.email}`}>{lead.email}</a> : <span className="muted-text">Sin dato — enriquecer</span>}</dd>
              </div>
              <div className="lead-contact-row">
                <dt>WhatsApp</dt>
                <dd>
                  {lead.whatsapp ? (
                    <a href={`https://wa.me/${lead.whatsapp.replace(/\D/g, "")}`} target="_blank" rel="noreferrer">
                      {lead.whatsapp}
                    </a>
                  ) : (
                    <span className="muted-text">Sin dato — enriquecer</span>
                  )}
                </dd>
              </div>
              <div className="lead-contact-row">
                <dt>LinkedIn</dt>
                <dd>
                  {lead.linkedin_url ? (
                    <a href={lead.linkedin_url} target="_blank" rel="noreferrer">
                      Abrir perfil
                      <ExternalLink size={14} aria-hidden />
                    </a>
                  ) : (
                    <span className="muted-text">Sin dato — enriquecer</span>
                  )}
                </dd>
              </div>
              <div className="lead-contact-row">
                <dt>Fuente principal</dt>
                <dd>
                  {lead.primary_source_url ? (
                    <a href={lead.primary_source_url} target="_blank" rel="noreferrer">
                      {hostLabel(lead.primary_source_url)}
                      <ExternalLink size={14} aria-hidden />
                    </a>
                  ) : (
                    <span className="muted-text">—</span>
                  )}
                </dd>
              </div>
            </dl>
            {!hasContact ? (
              <p className="lead-inline-note">Aún no hay canales de contacto verificables. Usa el enriquecimiento para intentar localizarlos.</p>
            ) : null}
          </Card>

          <Card className="panel lead-detail-card lead-detail-crm-card">
            <h2 className="lead-detail-section-title">CRM</h2>
            <dl className="lead-contact-dl">
              <div className="lead-contact-row">
                <dt>Etapa</dt>
                <dd>{lead.crm_stage}</dd>
              </div>
              {lead.crm_notes ? (
                <div className="lead-contact-row lead-contact-row--block">
                  <dt>Notas</dt>
                  <dd className="lead-crm-notes">{lead.crm_notes}</dd>
                </div>
              ) : null}
              <div className="lead-contact-row">
                <dt>Creado</dt>
                <dd className="muted-text">{formatDateTime(lead.created_at)}</dd>
              </div>
              <div className="lead-contact-row">
                <dt>Actualizado</dt>
                <dd className="muted-text">{formatDateTime(lead.updated_at)}</dd>
              </div>
            </dl>
            {lead.activity_timeline?.length ? (
              <div className="lead-activity-preview">
                <h3 className="lead-activity-heading">Actividad reciente</h3>
                <ul className="lead-activity-list">
                  {lead.activity_timeline.slice(-4).map((entry, idx) => (
                    <li key={idx} className="muted-text">
                      {Object.entries(entry)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(" · ")}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Card>
        </aside>
      </div>
    </section>
  );
}
