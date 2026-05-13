import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, Search, Building2, Users, Loader2, CheckCircle2, XCircle, Clock, AlertCircle } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { listAdminUserJobs } from "../api";
import { Card } from "../components/ui/card";
import { useAuth } from "../auth/AuthContext";

function StatusBadge({ status }: { status: string }): JSX.Element {
  const map: Record<string, { label: string; icon: JSX.Element; cls: string }> = {
    completed: { label: "Completado", icon: <CheckCircle2 size={13} />, cls: "badge-status--completed" },
    running: { label: "En progreso", icon: <Loader2 size={13} className="spin" />, cls: "badge-status--running" },
    pending: { label: "Pendiente", icon: <Clock size={13} />, cls: "badge-status--pending" },
    error: { label: "Error", icon: <XCircle size={13} />, cls: "badge-status--error" },
    cancelled: { label: "Cancelado", icon: <AlertCircle size={13} />, cls: "badge-status--cancelled" },
  };
  const s = map[status] ?? { label: status, icon: null, cls: "" };
  return (
    <span className={`admin-badge ${s.cls}`} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      {s.icon}
      {s.label}
    </span>
  );
}

export function AdminUserJobsPage(): JSX.Element {
  const { user } = useAuth();
  const { userId } = useParams<{ userId: string }>();

  const jobsQuery = useQuery({
    queryKey: ["admin", "user-jobs", userId],
    queryFn: () => listAdminUserJobs(userId!, { limit: 200 }),
    enabled: !!userId && user?.role === "admin",
  });

  if (user?.role !== "admin") {
    return (
      <section className="panel error-text" style={{ padding: "2rem" }}>
        No autorizado. <Link to="/directories">Volver</Link>
      </section>
    );
  }

  const targetUser = jobsQuery.data?.user;
  const jobs = jobsQuery.data?.items ?? [];
  const total = jobsQuery.data?.total ?? 0;

  return (
    <div className="admin-page">
      <nav className="admin-page-nav">
        <Link to="/admin/users" className="link-button">
          <ChevronLeft size={14} aria-hidden />
          Usuarios
        </Link>
      </nav>

      <div className="admin-page-head">
        <div>
          <h1 className="admin-page-title">
            Búsquedas de{" "}
            {targetUser ? (
              <span>{targetUser.display_name}</span>
            ) : (
              "usuario"
            )}
          </h1>
          {targetUser && (
            <p className="muted-text" style={{ marginBottom: 0 }}>
              {targetUser.email} · {total} búsqueda{total !== 1 ? "s" : ""} en total
            </p>
          )}
        </div>
      </div>

      <Card className="panel admin-section-card" style={{ marginTop: "1.5rem" }}>
        {jobsQuery.isLoading && <p className="muted-text">Cargando…</p>}
        {jobsQuery.isError && <p className="error-text">No se pudo cargar el historial.</p>}
        {!jobsQuery.isLoading && jobs.length === 0 && !jobsQuery.isError && (
          <p className="muted-text">Este usuario no ha realizado búsquedas.</p>
        )}
        {jobs.length > 0 && (
          <ul className="admin-users-list">
            {jobs.map((job) => (
              <li key={job.job_id} className="admin-user-row">
                <div className="admin-user-info" style={{ flex: 1, minWidth: 0 }}>
                  <Link
                    to={`/jobs/${job.job_id}`}
                    className="link-button"
                    style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  >
                    <Search size={13} aria-hidden style={{ flexShrink: 0 }} />
                    {job.query}
                  </Link>
                  {job.directory_name && (
                    <span className="muted-text" style={{ fontSize: "0.8rem" }}>
                      Directorio: {job.directory_name}
                    </span>
                  )}
                </div>
                <div className="admin-user-badges">
                  {job.exa_category === "people" && (
                    <span className="admin-badge">
                      <Users size={11} aria-hidden /> Personas
                    </span>
                  )}
                  {job.exa_category === "company" && (
                    <span className="admin-badge">
                      <Building2 size={11} aria-hidden /> Empresas
                    </span>
                  )}
                  <StatusBadge status={job.status} />
                  <span className="muted-text" style={{ fontSize: "0.75rem" }}>
                    {new Date(job.created_at).toLocaleDateString("es", {
                      day: "2-digit",
                      month: "short",
                      year: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
