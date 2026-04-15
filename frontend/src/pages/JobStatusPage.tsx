import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { getSearchJobStatus } from "../api";

export function JobStatusPage(): JSX.Element {
  const { jobId = "" } = useParams();
  const jobStatusQuery = useQuery({
    queryKey: ["job-status", jobId],
    queryFn: () => getSearchJobStatus(jobId),
    refetchInterval: 3000,
    enabled: Boolean(jobId),
  });

  if (jobStatusQuery.isLoading) {
    return <section className="panel">Cargando estado del job...</section>;
  }
  if (jobStatusQuery.isError || !jobStatusQuery.data) {
    return <section className="panel error-text">No se pudo cargar el estado del job.</section>;
  }

  const statusData = jobStatusQuery.data;
  return (
    <section className="panel">
      <h2>Estado del job</h2>
      <p className="muted-text">Job ID: {statusData.job_id}</p>
      <div className="status-grid">
        <p>
          Estado: <strong>{statusData.status}</strong>
        </p>
        <p>
          Etapa actual: <strong>{statusData.current_stage}</strong>
        </p>
        <p>
          Progreso: <strong>{statusData.progress}%</strong>
        </p>
      </div>
      <div className="progress-bar">
        <div className="progress-value" style={{ width: `${statusData.progress}%` }} />
      </div>

      <h3>Métricas</h3>
      <ul>
        <li>Fuentes visitadas: {statusData.metrics.sources_visited}</li>
        <li>Leads extraídos: {statusData.metrics.leads_extracted}</li>
        <li>Leads scoreados: {statusData.metrics.leads_scored}</li>
      </ul>

      <div className="actions-row">
        <Link className="link-button" to={`/jobs/${jobId}/leads`}>
          Ver resultados
        </Link>
      </div>
    </section>
  );
}

