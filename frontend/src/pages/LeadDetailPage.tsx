import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { getLeadDetail } from "../api";

export function LeadDetailPage(): JSX.Element {
  const { leadId = "" } = useParams();
  const navigate = useNavigate();
  const leadDetailQuery = useQuery({
    queryKey: ["lead-detail", leadId],
    queryFn: () => getLeadDetail(leadId),
    enabled: Boolean(leadId),
  });

  if (leadDetailQuery.isLoading) {
    return <section className="panel">Cargando detalle del lead...</section>;
  }
  if (leadDetailQuery.isError || !leadDetailQuery.data) {
    return <section className="panel error-text">No se pudo cargar el detalle del lead.</section>;
  }

  const lead = leadDetailQuery.data;
  return (
    <section className="panel">
      <h2>{lead.full_name}</h2>
      <p className="muted-text">
        {lead.specialty} - {lead.city}, {lead.country}
      </p>
      <div className="status-grid">
        <p>Score: {lead.score ?? "-"}</p>
        <p>Estado validación: {lead.validation_status}</p>
      </div>
      <p>{lead.score_reasoning ?? "Sin justificación registrada."}</p>

      <h3>Contactos</h3>
      <ul>
        <li>Email: {lead.email ?? "-"}</li>
        <li>WhatsApp: {lead.whatsapp ?? "-"}</li>
        <li>LinkedIn: {lead.linkedin_url ? <a href={lead.linkedin_url}>Perfil</a> : "-"}</li>
      </ul>

      <h3>Fuentes</h3>
      {lead.source_citations.length === 0 ? <p className="muted-text">No hay citas detalladas.</p> : null}
      <ul>
        {lead.source_citations.map((sourceItem, index) => (
          <li key={index}>{JSON.stringify(sourceItem)}</li>
        ))}
      </ul>

      <div className="actions-row">
        <button className="link-button" onClick={() => navigate(-1)} type="button">
          Volver
        </button>
      </div>
    </section>
  );
}

