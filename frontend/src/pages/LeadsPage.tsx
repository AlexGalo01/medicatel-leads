import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { downloadLeadsCsvFile, listLeads } from "../api";
import type { LeadsContactFilter } from "../types";

const CONTACT_FILTER_OPTIONS: { value: LeadsContactFilter; label: string }[] = [
  { value: "all", label: "Cualquier canal" },
  { value: "has_any", label: "Con al menos un contacto" },
  { value: "linkedin", label: "Con LinkedIn" },
  { value: "whatsapp", label: "Con WhatsApp" },
  { value: "email", label: "Con email" },
  { value: "linkedin_and_whatsapp", label: "LinkedIn y WhatsApp" },
];

export function LeadsPage(): JSX.Element {
  const { jobId = "" } = useParams();
  const [minScore, setMinScore] = useState<number | undefined>(undefined);
  const [nameQuery, setNameQuery] = useState("");
  const [contactFilter, setContactFilter] = useState<LeadsContactFilter>("all");

  const listParams = useMemo(
    () => ({
      minScore,
      nameQuery,
      contactFilter: contactFilter === "all" ? undefined : contactFilter,
    }),
    [minScore, nameQuery, contactFilter],
  );

  const leadsQuery = useQuery({
    queryKey: ["leads", jobId, listParams],
    queryFn: () => listLeads(jobId, listParams),
    enabled: Boolean(jobId),
  });

  const downloadMutation = useMutation({
    mutationFn: () =>
      downloadLeadsCsvFile(jobId, {
        min_score: minScore,
        q: nameQuery.trim() || undefined,
        contact_filter: contactFilter === "all" ? undefined : contactFilter,
      }),
  });

  const parsedMinScore = useMemo(() => (typeof minScore === "number" ? minScore : ""), [minScore]);

  return (
    <section className="leads-layout">
      <header className="panel leads-header">
        <div>
          <h2>Oportunidades</h2>
          <p className="muted-text leads-subtitle">
            {leadsQuery.data ? `${leadsQuery.data.total} oportunidades encontradas` : "Buscando oportunidades..."}
          </p>
        </div>
        <div className="actions-row">
          <button className="link-button" onClick={() => leadsQuery.refetch()} type="button">
            Actualizar
          </button>
          <button
            className="cta-button"
            onClick={() => downloadMutation.mutate()}
            type="button"
            disabled={!jobId || downloadMutation.isPending}
          >
            {downloadMutation.isPending ? "Generando CSV…" : "Descargar CSV"}
          </button>
        </div>
      </header>

      <div className="leads-content">
        <aside className="panel leads-filters">
          <h3>Filtros</h3>
          <label>
            Nombre (contiene)
            <input
              type="search"
              value={nameQuery}
              onChange={(event) => setNameQuery(event.target.value)}
              placeholder="Ej. García"
              maxLength={200}
            />
          </label>
          <label>
            Canal de contacto
            <select
              value={contactFilter}
              onChange={(event) => setContactFilter(event.target.value as LeadsContactFilter)}
            >
              {CONTACT_FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Score mínimo
            <input
              type="number"
              min={0}
              max={10}
              step={0.1}
              value={parsedMinScore}
              onChange={(event) => {
                const value = event.target.value;
                setMinScore(value ? Number(value) : undefined);
              }}
            />
          </label>
          <button className="link-button" onClick={() => leadsQuery.refetch()} type="button">
            Aplicar filtros
          </button>
        </aside>

        <main className="leads-list">
          {downloadMutation.isError ? (
            <p className="error-text">No se pudo descargar el CSV. Revisa la conexión o inténtalo de nuevo.</p>
          ) : null}

          {leadsQuery.isLoading ? <p>Cargando oportunidades...</p> : null}
          {leadsQuery.isError ? <p className="error-text">No se pudieron cargar las oportunidades.</p> : null}
          {leadsQuery.data && leadsQuery.data.items.length === 0 ? (
            <p className="muted-text">No hay resultados con los filtros actuales.</p>
          ) : null}

          {leadsQuery.data?.items.map((lead) => (
            <article key={lead.lead_id} className="panel lead-item-card">
              <div className="lead-item-row">
                <div>
                  <h3>{lead.full_name}</h3>
                  <p className="muted-text">
                    {lead.specialty} | {lead.city}
                  </p>
                </div>
                <div className="lead-item-score">Score: {lead.score ?? "-"}</div>
              </div>

              <div className="lead-item-meta lead-item-meta--sparse">
                {lead.email ? <span>Email: {lead.email}</span> : null}
                {lead.whatsapp ? <span>WhatsApp: {lead.whatsapp}</span> : null}
                {lead.linkedin_url ? (
                  <span>
                    LinkedIn:{" "}
                    <a href={lead.linkedin_url} target="_blank" rel="noreferrer">
                      Perfil
                    </a>
                  </span>
                ) : null}
                {!lead.email && !lead.whatsapp && !lead.linkedin_url ? (
                  <span className="muted-text">Sin datos de contacto en esta ejecución</span>
                ) : null}
              </div>

              <div className="actions-row">
                <Link className="cta-button" to={`/leads/${lead.lead_id}`}>
                  Ver oportunidad
                </Link>
              </div>
            </article>
          ))}
        </main>
      </div>
    </section>
  );
}
