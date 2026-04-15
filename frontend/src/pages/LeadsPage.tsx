import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { exportLeads, listLeads } from "../api";

export function LeadsPage(): JSX.Element {
  const { jobId = "" } = useParams();
  const [minScore, setMinScore] = useState<number | undefined>(undefined);

  const leadsQuery = useQuery({
    queryKey: ["leads", jobId, minScore],
    queryFn: () => listLeads(jobId, minScore),
    enabled: Boolean(jobId),
  });

  const exportMutation = useMutation({
    mutationFn: () => exportLeads(jobId, minScore),
  });

  const parsedMinScore = useMemo(() => (typeof minScore === "number" ? minScore : ""), [minScore]);

  return (
    <section className="panel">
      <h2>Resultados de leads</h2>
      <div className="actions-row">
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
          Aplicar filtro
        </button>
        <button className="cta-button" onClick={() => exportMutation.mutate()} type="button">
          Exportar CSV
        </button>
      </div>

      {exportMutation.data ? (
        <p className="muted-text">Archivo generado en: {exportMutation.data.download_path}</p>
      ) : null}

      {leadsQuery.isLoading ? <p>Cargando leads...</p> : null}
      {leadsQuery.isError ? <p className="error-text">No se pudieron cargar los leads.</p> : null}
      {leadsQuery.data && leadsQuery.data.items.length === 0 ? (
        <p className="muted-text">No hay leads para este job con los filtros actuales.</p>
      ) : null}

      {leadsQuery.data && leadsQuery.data.items.length > 0 ? (
        <table className="leads-table">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Especialidad</th>
              <th>Ciudad</th>
              <th>Score</th>
              <th>Email</th>
              <th>WhatsApp</th>
              <th>LinkedIn</th>
              <th>Detalle</th>
            </tr>
          </thead>
          <tbody>
            {leadsQuery.data.items.map((lead) => (
              <tr key={lead.lead_id}>
                <td>{lead.full_name}</td>
                <td>{lead.specialty}</td>
                <td>{lead.city}</td>
                <td>{lead.score ?? "-"}</td>
                <td>{lead.email ?? "-"}</td>
                <td>{lead.whatsapp ?? "-"}</td>
                <td>{lead.linkedin_url ? <a href={lead.linkedin_url}>Perfil</a> : "-"}</td>
                <td>
                  <Link to={`/leads/${lead.lead_id}`}>Ver detalle</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </section>
  );
}

