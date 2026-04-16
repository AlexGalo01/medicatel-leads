import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { Activity, BarChart3, CheckCircle2, Loader2, Search, Sparkles } from "lucide-react";

import { getSearchJobStatus } from "../api";

const PIPELINE_STEPS: { id: string; label: string }[] = [
  { id: "planner", label: "Plan de búsqueda" },
  { id: "exa_webset", label: "Búsqueda web (Exa)" },
  { id: "scoring_cleaning", label: "Scoring con IA" },
  { id: "lead_purification", label: "Purificación de leads" },
  { id: "contact_retry", label: "Reintento de contacto" },
  { id: "storage_export", label: "Guardado y exportación" },
  { id: "done", label: "Listo" },
];

const STAGE_ALIASES: Record<string, string> = {
  exa_search: "exa_webset",
  pending: "planner",
  running: "planner",
};

const LOADING_MESSAGES: string[] = [
  "Analizando fuentes y señales de contacto…",
  "Extrayendo fragmentos útiles de cada resultado…",
  "Clasificando calidad del lead con criterios médicos…",
  "Dedupe y validación de correos y teléfonos…",
  "Preparando tu lista de oportunidades…",
];

function normalizeStageKey(raw: string): string {
  const trimmed = raw.trim().toLowerCase();
  return STAGE_ALIASES[trimmed] ?? trimmed;
}

function stageIndex(stageKey: string): number {
  const key = normalizeStageKey(stageKey);
  const idx = PIPELINE_STEPS.findIndex((s) => s.id === key);
  return idx >= 0 ? idx : 0;
}

function formatStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: "En cola",
    running: "En ejecución",
    completed: "Completado",
    error: "Error",
  };
  return map[status] ?? status;
}

export function JobStatusPage(): JSX.Element {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const [tipIndex, setTipIndex] = useState(0);

  const jobStatusQuery = useQuery({
    queryKey: ["job-status", jobId],
    queryFn: () => getSearchJobStatus(jobId),
    refetchInterval: 1500,
    enabled: Boolean(jobId),
  });

  const statusData = jobStatusQuery.data;

  useEffect(() => {
    if (!statusData || statusData.status !== "completed") {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      navigate(`/jobs/${jobId}/leads`, { replace: true });
    }, 900);
    return () => window.clearTimeout(timeoutId);
  }, [statusData, navigate, jobId]);

  useEffect(() => {
    if (!statusData || statusData.status === "completed" || statusData.status === "error") {
      return;
    }
    const id = window.setInterval(() => {
      setTipIndex((i) => (i + 1) % LOADING_MESSAGES.length);
    }, 3200);
    return () => window.clearInterval(id);
  }, [statusData]);

  const statusSubtitle = useMemo(() => {
    if (!statusData) {
      return LOADING_MESSAGES[tipIndex] ?? LOADING_MESSAGES[0];
    }
    if (statusData.status === "completed") {
      return "Redirigiendo a tus oportunidades…";
    }
    if (statusData.status === "error") {
      return "Algo falló en el pipeline. Puedes iniciar otra búsqueda.";
    }
    return LOADING_MESSAGES[tipIndex] ?? LOADING_MESSAGES[0];
  }, [statusData, tipIndex]);

  if (jobStatusQuery.isLoading) {
    return (
      <section className="job-status-page">
        <div className="job-status-loading-shell">
          <div className="job-status-skeleton-row" />
          <div className="job-status-skeleton-row short" />
          <div className="job-status-spinner-block">
            <Loader2 className="job-status-page-spinner spin" aria-hidden />
            <p className="muted-text">Cargando estado…</p>
          </div>
        </div>
      </section>
    );
  }

  if (jobStatusQuery.isError || !statusData) {
    return (
      <section className="job-status-page panel error-text">
        No se pudo cargar el estado del job.
      </section>
    );
  }

  const isProcessing = statusData.status !== "completed" && statusData.status !== "error";
  const activeStep = stageIndex(statusData.current_stage);
  const qm = statusData.quality_metrics;

  return (
    <section className="job-status-page">
      <div className="job-status-card">
        {isProcessing ? (
          <div className="job-status-hero-processing">
            <div className="job-status-icon-cluster" aria-hidden>
              <span className="job-status-icon-badge">
                <Search size={22} />
              </span>
              <span className="job-status-icon-badge secondary">
                <Sparkles size={20} />
              </span>
              <span className="job-status-icon-badge tertiary">
                <Activity size={20} />
              </span>
            </div>
            <h1 className="job-status-title">Preparando tus oportunidades</h1>
            <p className="job-status-rotating-tip">{statusSubtitle}</p>
            <div className="job-status-shimmer" />
          </div>
        ) : (
          <div className="job-status-hero-processing">
            {statusData.status === "completed" ? (
              <CheckCircle2 className="job-status-done-icon" aria-hidden />
            ) : (
              <Loader2 className="job-status-page-spinner spin" aria-hidden />
            )}
            <h1 className="job-status-title">
              {statusData.status === "completed" ? "Listo" : "Estado del proceso"}
            </h1>
            <p className="muted-text">{statusSubtitle}</p>
          </div>
        )}

        <div className="job-status-stepper" aria-label="Etapas del pipeline">
          {PIPELINE_STEPS.map((step, index) => {
            const done = index < activeStep || (index === activeStep && statusData.status === "completed");
            const active = index === activeStep && isProcessing;
            return (
              <div
                key={step.id}
                className={`job-status-step${done ? " is-done" : ""}${active ? " is-active" : ""}`}
              >
                <span className="job-status-step-dot">{done ? "✓" : index + 1}</span>
                <span className="job-status-step-label">{step.label}</span>
              </div>
            );
          })}
        </div>

        <div className="job-status-summary-grid">
          <div className="job-status-pill">
            <span className="muted-text">Estado</span>
            <strong>{formatStatusLabel(statusData.status)}</strong>
          </div>
          <div className="job-status-pill">
            <span className="muted-text">Etapa actual</span>
            <strong className="job-status-stage-name">
              {PIPELINE_STEPS.find((s) => s.id === normalizeStageKey(statusData.current_stage))?.label ??
                statusData.current_stage}
            </strong>
          </div>
          <div className="job-status-pill">
            <span className="muted-text">Progreso</span>
            <strong>{statusData.progress}%</strong>
          </div>
        </div>

        <div className="progress-bar job-status-progress">
          <div className="progress-value" style={{ width: `${Math.min(100, Math.max(0, statusData.progress))}%` }} />
        </div>

        <div className="job-status-metrics">
          <h2 className="job-status-metrics-title">
            <BarChart3 size={18} aria-hidden /> Métricas
          </h2>
          <div className="job-status-metrics-grid">
            <div className="job-status-metric-card">
              <span className="muted-text">Fuentes / resultados</span>
              <span className="job-status-metric-value" key={statusData.metrics.sources_visited}>
                {statusData.metrics.sources_visited}
              </span>
            </div>
            <div className="job-status-metric-card">
              <span className="muted-text">Extraídos</span>
              <span className="job-status-metric-value" key={statusData.metrics.leads_extracted}>
                {statusData.metrics.leads_extracted}
              </span>
            </div>
            <div className="job-status-metric-card">
              <span className="muted-text">Procesados / score</span>
              <span className="job-status-metric-value" key={statusData.metrics.leads_scored}>
                {statusData.metrics.leads_scored}
              </span>
            </div>
          </div>

          {qm ? (
            <div className="job-status-quality-block">
              <h3 className="job-status-quality-title">Calidad</h3>
              <ul className="job-status-quality-list">
                <li key={`cov-${qm.contact_coverage}`}>
                  Cobertura de contacto: <strong>{(qm.contact_coverage * 100).toFixed(1)}%</strong>
                </li>
                <li key={`miss-${qm.missing_contact_count}`}>
                  Sin email ni WhatsApp: <strong>{qm.missing_contact_count}</strong>
                </li>
                <li key={`retry-${qm.retry_used}`}>
                  Reintento Exa: <strong>{qm.retry_used ? "Sí" : "No"}</strong>
                </li>
                <li key={`disc-${qm.discarded_leads_count}`}>
                  Descartados: <strong>{qm.discarded_leads_count}</strong>
                </li>
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
