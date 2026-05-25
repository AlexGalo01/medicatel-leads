import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, AreaChart, Area,
} from "recharts";
import { BarChart3, Download } from "lucide-react";

import { getDashboardPipeline, getDashboardActivity } from "../api";
import type {
  DashboardPipelineResponse,
  DashboardActivityResponse,
  ConversionStep,
} from "../types";

import "./DashboardPage.css";

// ── Colors ──────────────────────────────────────────────────────

const COLORS = ["#6366F1", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#06B6D4", "#F97316"];
const PIE_COLORS_RESPONSE = ["#10B981", "#EF4444", "#F59E0B", "#9CA3AF"];
const PIE_COLORS_WINLOSS = ["#10B981", "#EF4444"];
const PIE_COLORS_SCRAPE = ["#10B981", "#3B82F6", "#EF4444", "#9CA3AF"];

type Tab = "pipeline" | "actividad" | "fuentes";

// ── Helpers ─────────────────────────────────────────────────────

function mapToChartData(record: Record<string, number>): { name: string; value: number }[] {
  return Object.entries(record).map(([name, value]) => ({ name, value }));
}

function pct(n: number): string { return `${(n * 100).toFixed(1)}%`; }

function formatHours(h: number): string {
  if (h < 1) return `${Math.round(h * 60)}min`;
  if (h < 24) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

// ── KPI Card ────────────────────────────────────────────────────

function KpiCard({ label, value, sub, borderColor, icon }: {
  label: string; value: string | number; sub?: string; borderColor?: string; icon?: string;
}) {
  return (
    <div className={`dashboard-kpi ${borderColor ?? ""}`}>
      <div className="dashboard-kpi-top">
        <span className="dashboard-kpi-label">{label}</span>
        {icon && <span className="dashboard-kpi-icon">{icon}</span>}
      </div>
      <span className="dashboard-kpi-value">{value}</span>
      {sub && <span className={`dashboard-kpi-sub ${sub.includes("↑") ? "up" : ""}`}>{sub}</span>}
    </div>
  );
}

// ── Reusable Cards ──────────────────────────────────────────────

function ChartCard({ title, full, children }: { title: string; full?: boolean; children: React.ReactNode }) {
  return (
    <div className={`dashboard-card ${full ? "dashboard-card-full" : ""}`}>
      <div className="dashboard-card-header">
        <h3 className="dashboard-card-title">{title}</h3>
      </div>
      {children}
    </div>
  );
}

function HBarChart({ data, color }: { data: { name: string; value: number }[]; color?: string }) {
  if (!data.length) return <p className="dashboard-empty">Sin datos</p>;
  return (
    <ResponsiveContainer width="100%" height={Math.max(200, data.length * 36)}>
      <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E8E8EC" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 12 }} />
        <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12 }} />
        <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #E8E8EC" }} />
        <Bar dataKey="value" fill={color ?? "#6366F1"} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function DonutChart({ data, colors }: { data: { name: string; value: number }[]; colors: string[] }) {
  if (!data.length) return <p className="dashboard-empty">Sin datos</p>;
  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie data={data} cx="50%" cy="50%" innerRadius={55} outerRadius={100} dataKey="value" nameKey="name"
          label={({ name, percent }: { name?: string; percent?: number }) => `${name ?? ""} ${((percent ?? 0) * 100).toFixed(0)}%`}
          labelLine={false}
        >
          {data.map((_, idx) => <Cell key={idx} fill={colors[idx % colors.length]} />)}
        </Pie>
        <Tooltip contentStyle={{ borderRadius: 8 }} />
        <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}

// ── Pipeline Tab ────────────────────────────────────────────────

function PipelineTab({ data }: { data: DashboardPipelineResponse }) {
  const stepData = data.opportunities_by_step.map((s) => ({ name: s.step_name, value: s.count }));
  const convData = data.conversion_rates.map((r) => ({
    name: `${r.from_step}→${r.to_step}`,
    value: Math.round(r.rate * 100),
  }));

  return (
    <>
      {/* KPI strip */}
      <div className="dashboard-kpi-row" style={{ marginBottom: 24 }}>
        <KpiCard label="Total Oportunidades" value={data.total_opportunities.toLocaleString()} icon="📋" />
        <KpiCard label="Activas" value={data.active_opportunities} sub="En proceso" />
        <KpiCard label="Ganadas" value={data.won_count} borderColor="success" icon="✓" />
        <KpiCard label="Perdidas" value={data.lost_count} borderColor="error" icon="✕" />
        <KpiCard label="Win Rate" value={pct(data.overall_win_rate)} />
      </div>

      <div className="dashboard-grid">
        <ChartCard title="Oportunidades por Paso">
          <HBarChart data={stepData} />
        </ChartCard>

        <ChartCard title="Tasa de Conversión">
          {convData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={convData} margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E8E8EC" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 12 }} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                <Tooltip formatter={(v) => `${v}%`} contentStyle={{ borderRadius: 8 }} />
                <Bar dataKey="value" fill="#10B981" radius={[4, 4, 0, 0]} label={{ position: "top", fontSize: 11, formatter: (v) => `${v}%` }} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="dashboard-empty">Sin datos</p>}
        </ChartCard>

        <ChartCard title="Resultado de Respuestas">
          <DonutChart data={mapToChartData(data.response_outcomes)} colors={PIE_COLORS_RESPONSE} />
        </ChartCard>

        <ChartCard title="Ganados vs Perdidos">
          <DonutChart data={mapToChartData(data.won_lost)} colors={PIE_COLORS_WINLOSS} />
        </ChartCard>

        <ChartCard title="Por Responsable">
          <HBarChart data={data.by_owner.map((o) => ({ name: o.display_name, value: o.count }))} />
        </ChartCard>

        {data.avg_time_per_step.length > 0 && (
          <ChartCard title="Tiempo Promedio por Paso">
            <HBarChart
              data={data.avg_time_per_step.map((t) => ({ name: t.step_name, value: Math.round(t.avg_hours * 10) / 10 }))}
              color="#F59E0B"
            />
          </ChartCard>
        )}
      </div>
    </>
  );
}

// ── Actividad Tab ───────────────────────────────────────────────

function ActividadTab({ data }: { data: DashboardActivityResponse }) {
  const coveragePct = Object.values(data.contact_coverage);
  const avgCoverage = coveragePct.length ? Math.round(coveragePct.reduce((a, b) => a + b, 0) / coveragePct.length * 100) : 0;

  return (
    <>
      <div className="dashboard-kpi-row cols-4" style={{ marginBottom: 24 }}>
        <KpiCard label="Total Búsquedas" value={data.total_searches.toLocaleString()} />
        <KpiCard label="Promedio Leads/Búsqueda" value={data.avg_leads_per_search.toFixed(1)} />
        <KpiCard label="Score Promedio" value={`${data.avg_lead_score.toFixed(1)} /10`} borderColor="success" />
        <KpiCard label="Cobertura Contacto" value={`${avgCoverage}%`} />
      </div>

      <div className="dashboard-grid">
        <ChartCard title="Oportunidades por Día (Últimos 30 días)" full>
          {data.opportunities_per_day.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={data.opportunities_per_day} margin={{ left: 0, right: 20, top: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E8E8EC" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(d: string) => d.slice(5)} />
                <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
                <Tooltip contentStyle={{ borderRadius: 8 }} />
                <Area type="monotone" dataKey="count" stroke="#6366F1" fill="rgba(99,102,241,0.1)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          ) : <p className="dashboard-empty">Sin datos en los últimos 30 días</p>}
        </ChartCard>

        <ChartCard title="Fuente de Importación">
          <DonutChart data={mapToChartData(data.by_import_source)} colors={COLORS} />
        </ChartCard>

        <ChartCard title="Distribución de Score">
          {data.lead_score_distribution.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={data.lead_score_distribution.map((s) => ({ name: s.range, value: s.count }))} margin={{ left: 0, right: 20, top: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E8E8EC" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
                <Tooltip contentStyle={{ borderRadius: 8 }} />
                <Bar dataKey="value" fill="#8B5CF6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="dashboard-empty">Sin datos</p>}
        </ChartCard>
      </div>
    </>
  );
}

// ── Fuentes Tab ─────────────────────────────────────────────────

function FuentesTab({ activity }: { activity: DashboardActivityResponse }) {
  return (
    <div className="dashboard-grid">
      <ChartCard title="Jobs de Scraping por Estado">
        <DonutChart data={mapToChartData(activity.scrape_jobs_by_status)} colors={PIE_COLORS_SCRAPE} />
      </ChartCard>

      <ChartCard title="Top Sitios de Scraping">
        <HBarChart data={activity.top_scraping_sites.map((s) => ({ name: s.name, value: s.count }))} />
      </ChartCard>

      <ChartCard title="Directorios Activos">
        <HBarChart data={activity.active_directories.map((d) => ({ name: d.name, value: d.count }))} />
      </ChartCard>

      <ChartCard title="Oportunidades por Origen">
        <DonutChart data={mapToChartData(activity.by_import_source)} colors={COLORS} />
      </ChartCard>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────

export function DashboardPage(): JSX.Element {
  const [tab, setTab] = useState<Tab>("pipeline");

  const pipelineQ = useQuery({ queryKey: ["dashboard-pipeline"], queryFn: getDashboardPipeline, staleTime: 60_000 });
  const activityQ = useQuery({ queryKey: ["dashboard-activity"], queryFn: getDashboardActivity, staleTime: 60_000 });

  const isLoading = pipelineQ.isPending || activityQ.isPending;
  const error = pipelineQ.error || activityQ.error;

  if (isLoading) return <div className="dashboard-loading">Cargando métricas...</div>;
  if (error || !pipelineQ.data || !activityQ.data) {
    return (
      <div className="dashboard-loading" style={{ color: "#EF4444" }}>
        Error al cargar el dashboard: {error instanceof Error ? error.message : "Error desconocido"}
      </div>
    );
  }

  const pipeline = pipelineQ.data;
  const activity = activityQ.data;

  return (
    <div className="dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="dashboard-header-top">
          <div>
            <h1><BarChart3 size={22} /> Analytics Dashboard</h1>
            <p>Rendimiento detallado de generación de leads médicos en Honduras.</p>
          </div>
          <div className="dashboard-header-actions">
            <button><Download size={14} style={{ marginRight: 4 }} /> Exportar</button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="dashboard-tabs">
        {(["pipeline", "actividad", "fuentes"] as Tab[]).map((t) => (
          <button key={t} className={`dashboard-tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
            {t === "pipeline" ? "Pipeline" : t === "actividad" ? "Actividad" : "Fuentes"}
          </button>
        ))}
      </div>

      {/* Content */}
      {tab === "pipeline" && <PipelineTab data={pipeline} />}
      {tab === "actividad" && <ActividadTab data={activity} />}
      {tab === "fuentes" && <FuentesTab activity={activity} />}
    </div>
  );
}
