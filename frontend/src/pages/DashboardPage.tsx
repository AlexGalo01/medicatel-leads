import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, AreaChart, Area,
} from "recharts";

import { getDashboardPipeline, getDashboardActivity } from "../api";
import type {
  DashboardPipelineResponse,
  DashboardActivityResponse,
  ConversionStep,
} from "../types";

import "./DashboardPage.css";

// ── Color palette ────────────────────────────────────────────────

const COLORS = ["#6366F1", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#06B6D4", "#F97316"];
const PIE_COLORS = ["#6366F1", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899"];

type Tab = "pipeline" | "actividad" | "fuentes";

// ── Helpers ──────────────────────────────────────────────────────

function mapToChartData(record: Record<string, number>): { name: string; value: number }[] {
  return Object.entries(record).map(([name, value]) => ({ name, value }));
}

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function formatHours(h: number): string {
  if (h < 1) return `${Math.round(h * 60)}min`;
  if (h < 24) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

// ── KPI Card ─────────────────────────────────────────────────────

function KpiCard({ label, value, className }: { label: string; value: string | number; className?: string }) {
  return (
    <div className="dashboard-kpi">
      <span className="dashboard-kpi-label">{label}</span>
      <span className={`dashboard-kpi-value ${className ?? ""}`}>{value}</span>
    </div>
  );
}

// ── Chart Cards ──────────────────────────────────────────────────

function ChartCard({ title, full, children }: { title: string; full?: boolean; children: React.ReactNode }) {
  return (
    <div className={`dashboard-card ${full ? "dashboard-card-full" : ""}`}>
      <h3 className="dashboard-card-title">{title}</h3>
      {children}
    </div>
  );
}

function HorizontalBarCard({ title, data, full }: { title: string; data: { name: string; value: number }[]; full?: boolean }) {
  if (!data.length) return <ChartCard title={title}><p className="dashboard-empty">Sin datos</p></ChartCard>;
  return (
    <ChartCard title={title} full={full}>
      <ResponsiveContainer width="100%" height={Math.max(200, data.length * 36)}>
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E8E8EC" />
          <XAxis type="number" tick={{ fontSize: 12 }} />
          <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12 }} />
          <Tooltip />
          <Bar dataKey="value" fill="#6366F1" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

function PieChartCard({ title, data }: { title: string; data: { name: string; value: number }[] }) {
  if (!data.length) return <ChartCard title={title}><p className="dashboard-empty">Sin datos</p></ChartCard>;
  return (
    <ChartCard title={title}>
      <ResponsiveContainer width="100%" height={280}>
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" innerRadius={50} outerRadius={100} dataKey="value" nameKey="name" label={(props: any) => `${props.name ?? ""} ${((props.percent ?? 0) * 100).toFixed(0)}%`}>
            {data.map((_entry, idx) => (
              <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Conversion Table ─────────────────────────────────────────────

function ConversionTable({ rates }: { rates: ConversionStep[] }) {
  if (!rates.length) return <ChartCard title="Tasa de Conversion"><p className="dashboard-empty">Sin datos</p></ChartCard>;
  return (
    <ChartCard title="Tasa de Conversion">
      <table className="dashboard-conversion-table">
        <thead>
          <tr>
            <th>De</th>
            <th>A</th>
            <th>Entrada</th>
            <th>Salida</th>
            <th>Tasa</th>
            <th style={{ minWidth: 100 }}></th>
          </tr>
        </thead>
        <tbody>
          {rates.map((r, i) => (
            <tr key={i}>
              <td>{r.from_step}</td>
              <td>{r.to_step}</td>
              <td>{r.from_count}</td>
              <td>{r.to_count}</td>
              <td>{pct(r.rate)}</td>
              <td>
                <div className="conversion-bar">
                  <div className="conversion-bar-fill" style={{ width: `${Math.min(r.rate * 100, 100)}%` }} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </ChartCard>
  );
}

// ── Pipeline Tab ─────────────────────────────────────────────────

function PipelineTab({ data }: { data: DashboardPipelineResponse }) {
  const stepData = data.opportunities_by_step.map((s) => ({ name: s.step_name, value: s.count }));
  const ownerData = data.by_owner.map((o) => ({ name: o.display_name, value: o.count }));
  const timeData = data.avg_time_per_step.map((t) => ({ name: t.step_name, value: t.avg_hours }));

  return (
    <div className="dashboard-grid">
      <HorizontalBarCard title="Oportunidades por Etapa" data={stepData} full />
      <ConversionTable rates={data.conversion_rates} />
      <PieChartCard title="Ganadas vs Perdidas" data={mapToChartData(data.won_lost)} />
      <PieChartCard title="Resultado de Respuesta" data={mapToChartData(data.response_outcomes)} />
      <HorizontalBarCard title="Oportunidades por Responsable" data={ownerData} />
      {timeData.length > 0 && (
        <ChartCard title="Tiempo Promedio por Etapa">
          <ResponsiveContainer width="100%" height={Math.max(200, timeData.length * 36)}>
            <BarChart data={timeData} layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E8E8EC" />
              <XAxis type="number" tick={{ fontSize: 12 }} tickFormatter={formatHours} />
              <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(val) => formatHours(Number(val))} />
              <Bar dataKey="value" fill="#F59E0B" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}
    </div>
  );
}

// ── Actividad Tab ────────────────────────────────────────────────

function ActividadTab({ data }: { data: DashboardActivityResponse }) {
  const scoreData = data.lead_score_distribution.map((s) => ({ name: s.range, value: s.count }));
  const coverageData = Object.entries(data.contact_coverage).map(([name, value]) => ({
    name,
    value: Math.round(value * 100),
  }));

  return (
    <div className="dashboard-grid">
      {/* Trend */}
      <ChartCard title="Oportunidades Creadas (30 dias)" full>
        {data.opportunities_per_day.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={data.opportunities_per_day} margin={{ left: 0, right: 20, top: 5, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E8E8EC" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(d: string) => d.slice(5)} />
              <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
              <Tooltip />
              <Area type="monotone" dataKey="count" stroke="#6366F1" fill="rgba(99,102,241,0.15)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="dashboard-empty">Sin datos en los ultimos 30 dias</p>
        )}
      </ChartCard>

      <PieChartCard title="Busquedas por Estado" data={mapToChartData(data.search_jobs_by_status)} />

      {/* Lead score histogram */}
      <ChartCard title="Distribucion de Score de Leads">
        {scoreData.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={scoreData} margin={{ left: 0, right: 20, top: 5, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E8E8EC" />
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" fill="#8B5CF6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="dashboard-empty">Sin datos</p>
        )}
      </ChartCard>

      <PieChartCard title="Tasa de Validacion" data={mapToChartData(data.validation_rates)} />

      {/* Contact coverage */}
      <HorizontalBarCard
        title="Cobertura de Contacto (%)"
        data={coverageData}
      />

      {/* Top categories */}
      <HorizontalBarCard title="Top Especialidades" data={data.top_specialties.map((s) => ({ name: s.name, value: s.count }))} />
      <HorizontalBarCard title="Top Ciudades" data={data.top_cities.map((c) => ({ name: c.name, value: c.count }))} />
      <HorizontalBarCard title="Top Paises" data={data.top_countries.map((c) => ({ name: c.name, value: c.count }))} />
    </div>
  );
}

// ── Fuentes Tab ──────────────────────────────────────────────────

function FuentesTab({ pipeline, activity }: { pipeline: DashboardPipelineResponse; activity: DashboardActivityResponse }) {
  return (
    <div className="dashboard-grid">
      <PieChartCard title="Oportunidades por Origen" data={mapToChartData(activity.by_import_source)} />
      <PieChartCard title="Scrape Jobs por Estado" data={mapToChartData(activity.scrape_jobs_by_status)} />
      <HorizontalBarCard
        title="Sitios de Scraping mas Productivos"
        data={activity.top_scraping_sites.map((s) => ({ name: s.name, value: s.count }))}
      />
      <HorizontalBarCard
        title="Directorios Activos"
        data={activity.active_directories.map((d) => ({ name: d.name, value: d.count }))}
      />
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────

export function DashboardPage(): JSX.Element {
  const [tab, setTab] = useState<Tab>("pipeline");

  const pipelineQ = useQuery({
    queryKey: ["dashboard-pipeline"],
    queryFn: getDashboardPipeline,
    staleTime: 60_000,
  });

  const activityQ = useQuery({
    queryKey: ["dashboard-activity"],
    queryFn: getDashboardActivity,
    staleTime: 60_000,
  });

  const isLoading = pipelineQ.isPending || activityQ.isPending;
  const error = pipelineQ.error || activityQ.error;

  if (isLoading) {
    return <div className="dashboard-loading">Cargando metricas...</div>;
  }

  if (error || !pipelineQ.data || !activityQ.data) {
    return (
      <div className="dashboard-loading" style={{ color: "var(--color-error)" }}>
        Error al cargar el dashboard: {error instanceof Error ? error.message : "Error desconocido"}
      </div>
    );
  }

  const pipeline = pipelineQ.data;
  const activity = activityQ.data;

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1>Dashboard</h1>
      </div>

      {/* KPI row */}
      <div className="dashboard-kpi-row">
        <KpiCard label="Total Oportunidades" value={pipeline.total_opportunities} />
        <KpiCard label="Activas" value={pipeline.active_opportunities} className="primary" />
        <KpiCard label="Ganadas" value={pipeline.won_count} className="success" />
        <KpiCard label="Perdidas" value={pipeline.lost_count} className="error" />
        <KpiCard label="Win Rate" value={pct(pipeline.overall_win_rate)} className="success" />
        <KpiCard label="Busquedas" value={activity.total_searches} />
        <KpiCard label="Leads/Busqueda" value={activity.avg_leads_per_search} />
        <KpiCard label="Score Promedio" value={activity.avg_lead_score} className="primary" />
      </div>

      {/* Tabs */}
      <div className="dashboard-tabs">
        {(["pipeline", "actividad", "fuentes"] as Tab[]).map((t) => (
          <button
            key={t}
            className={`dashboard-tab ${tab === t ? "active" : ""}`}
            onClick={() => setTab(t)}
          >
            {t === "pipeline" ? "Pipeline" : t === "actividad" ? "Actividad" : "Fuentes"}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "pipeline" && <PipelineTab data={pipeline} />}
      {tab === "actividad" && <ActividadTab data={activity} />}
      {tab === "fuentes" && <FuentesTab pipeline={pipeline} activity={activity} />}
    </div>
  );
}
