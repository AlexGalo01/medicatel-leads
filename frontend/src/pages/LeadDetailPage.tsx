import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { deepEnrichLead, getLeadDetail } from "../api";
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
    return <section className="panel">Cargando detalle...</section>;
  }
  if (leadDetailQuery.isError || !leadDetailQuery.data) {
    return <section className="panel error-text">No se pudo cargar esta oportunidad.</section>;
  }

  const lead = leadDetailQuery.data;
  const description =
    lead.score_reasoning?.trim() ||
    "Aún no hay una descripción generada para esta oportunidad. Puedes ejecutar una búsqueda extensiva para intentar enriquecerla con evidencia verificable.";

  return (
    <section className="lead-detail-page">
      <div className="panel lead-detail-header">
        <div className="lead-detail-header-left">
          <button className="link-button lead-back-button" onClick={() => navigate(-1)} type="button">
            Volver a la lista
          </button>
          <h2>{lead.full_name}</h2>
          <p className="muted-text">
            {lead.specialty} — {lead.city}, {lead.country}
          </p>
        </div>
        <div className="lead-detail-header-actions">
          <div className="lead-score-badge">Score IA: {lead.score ?? "-"}</div>
          <button
            className="cta-button lead-deep-enrich-button"
            type="button"
            disabled={deepEnrichMutation.isPending || !leadId}
            onClick={() => {
              setDeepError(null);
              deepEnrichMutation.mutate();
            }}
          >
            {deepEnrichMutation.isPending ? "Búsqueda en curso…" : "Búsqueda extensiva (IA + evidencia)"}
          </button>
        </div>
      </div>

      {lead.enrichment_message ? (
        <div className="panel lead-enrichment-banner muted-text">
          <strong>Última búsqueda extensiva:</strong> {lead.enrichment_message}
          {lead.enrichment_status ? <span> ({lead.enrichment_status})</span> : null}
        </div>
      ) : null}

      {deepError ? <div className="panel error-text">{deepError}</div> : null}

      <div className="lead-detail-grid">
        <aside className="lead-detail-sidebar">
          <section className="panel lead-detail-card">
            <h3>Contacto</h3>
            <p className="muted-text">Solo se muestran datos presentes en esta ejecución.</p>
            <ul className="lead-detail-list">
              {lead.email ? (
                <li>
                  <strong>Email:</strong> {lead.email}
                </li>
              ) : null}
              {lead.whatsapp ? (
                <li>
                  <strong>WhatsApp:</strong> {lead.whatsapp}
                </li>
              ) : null}
              {lead.linkedin_url ? (
                <li>
                  <strong>LinkedIn:</strong>{" "}
                  <a href={lead.linkedin_url} target="_blank" rel="noreferrer">
                    Abrir perfil
                  </a>
                </li>
              ) : null}
              {!lead.email && !lead.whatsapp && !lead.linkedin_url ? (
                <li className="muted-text">Sin canales de contacto en el registro actual.</li>
              ) : null}
            </ul>
          </section>

          <section className="panel lead-detail-card">
            <h3>Metadatos</h3>
            <ul className="lead-detail-list">
              <li>
                <strong>Validación:</strong> {lead.validation_status}
              </li>
              <li>
                <strong>Creado:</strong> {formatDateTime(lead.created_at)}
              </li>
              <li>
                <strong>Actualizado:</strong> {formatDateTime(lead.updated_at)}
              </li>
            </ul>
          </section>
        </aside>

        <main className="lead-detail-main">
          <section className="panel lead-detail-card">
            <h3>Descripción</h3>
            <p className="lead-detail-description">{description}</p>
          </section>

          <section className="panel lead-detail-card">
            <h3>Fuentes enlazadas</h3>
            {sourceLinks.length > 0 ? (
              <ul className="lead-detail-list">
                {sourceLinks.map((item) => (
                  <li key={item.url}>
                    <a href={item.url} target="_blank" rel="noreferrer">
                      {item.label}
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted-text">No hay URLs de fuente registradas.</p>
            )}
          </section>

          <section className="panel lead-detail-card">
            <h3>Citas y evidencia</h3>
            {citations.length > 0 ? (
              <ul className="lead-citation-blocks">
                {citations.map((citation) => (
                  <li key={citation.url} className="lead-citation-block">
                    <div className="lead-citation-title">
                      <a href={citation.url} target="_blank" rel="noreferrer">
                        {citation.title}
                      </a>
                    </div>
                    <div className="muted-text lead-citation-meta">
                      Confianza: {citation.confidence ?? "media"}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted-text">No hay citas estructuradas. Tras la búsqueda extensiva pueden aparecer aquí.</p>
            )}
          </section>
        </main>
      </div>

      <div className="actions-row">
        <button className="link-button" onClick={() => navigate(-1)} type="button">
          Volver a la lista
        </button>
      </div>
    </section>
  );
}
