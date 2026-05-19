import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, Download, FolderOpen, Loader2, Plus, Search } from "lucide-react";

import { listDirectories, listOpportunities } from "../../../api";
import type { OpportunityListItem } from "../../../types";

const PAGE_SIZE = 25;

const AVATAR_PALETTE = [
  { bg: "#DBEAFE", color: "#1D4ED8" },
  { bg: "#EDE9FE", color: "#7C3AED" },
  { bg: "#D1FAE5", color: "#059669" },
  { bg: "#FEF3C7", color: "#D97706" },
  { bg: "#FCE7F3", color: "#DB2777" },
  { bg: "#CFFAFE", color: "#0891B2" },
];

function getAvatarStyle(text: string) {
  let n = 0;
  for (let i = 0; i < text.length; i++) n = (n * 31 + text.charCodeAt(i)) & 0xffff;
  return AVATAR_PALETTE[n % AVATAR_PALETTE.length];
}

function initials(text: string): string {
  const parts = text.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return text.slice(0, 2).toUpperCase();
}

function formatRelative(iso: string): string {
  const d = new Date(iso);
  const ts = d.getTime();
  if (Number.isNaN(ts)) return iso;
  const diffMin = Math.max(0, Math.floor((Date.now() - ts) / 60000));
  if (diffMin < 60) return diffMin <= 1 ? "Hace 1 min" : `Hace ${diffMin} min`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `Hace ${diffH} h`;
  const diffD = Math.floor(diffH / 24);
  if (diffD === 1) return "Ayer";
  if (diffD < 7) return `Hace ${diffD} días`;
  return d.toLocaleDateString("es-HN", { dateStyle: "short" });
}

const STEP_COLORS = [
  { bg: "#EFF6FF", color: "#2563EB", border: "#BFDBFE", dot: "#3B82F6" },
  { bg: "#FFFBEB", color: "#B45309", border: "#FDE68A", dot: "#F59E0B" },
  { bg: "#F3E8FF", color: "#7C3AED", border: "#E9D5FF", dot: "#8B5CF6" },
  { bg: "#F0F9FF", color: "#0369A1", border: "#BAE6FD", dot: "#0EA5E9" },
  { bg: "#FFF1F2", color: "#BE123C", border: "#FECDD3", dot: "#F43F5E" },
];

function getStepBadge(row: OpportunityListItem, stepName?: string) {
  if (row.terminated_at) {
    if (row.terminated_outcome === "won")
      return { bg: "#F0FDF4", color: "#059669", border: "#BBF7D0", dot: "#10B981", label: "Cerrado Ganado" };
    if (row.terminated_outcome === "lost")
      return { bg: "#FEF2F2", color: "#DC2626", border: "#FECACA", dot: "#EF4444", label: "Cerrado Perdido" };
    return { bg: "#F8FAFC", color: "#64748B", border: "#E2E8F0", dot: "#94A3B8", label: "Sin respuesta" };
  }
  if (!stepName) return { bg: "#F8FAFC", color: "#64748B", border: "#E2E8F0", dot: "#94A3B8", label: "—" };
  let n = 0;
  for (let i = 0; i < stepName.length; i++) n = (n * 31 + stepName.charCodeAt(i)) & 0xffff;
  return { ...STEP_COLORS[n % STEP_COLORS.length], label: stepName };
}

export function OpportunitiesListPage(): JSX.Element {
  const [directoryFilter, setDirectoryFilter] = useState<string>("");
  const [searchText, setSearchText] = useState("");
  const [currentPage, setCurrentPage] = useState(1);

  const directoriesQuery = useQuery({
    queryKey: ["directories"],
    queryFn: () => listDirectories(),
  });

  const listQuery = useQuery({
    queryKey: ["opportunities", "list", directoryFilter],
    queryFn: () =>
      listOpportunities({ directory_id: directoryFilter || undefined, limit: 500 }),
  });

  const directoryById = useMemo(() => {
    const map = new Map<string, { name: string; stepName: Map<string, string> }>();
    for (const d of directoriesQuery.data?.items ?? []) {
      const stepMap = new Map<string, string>();
      for (const s of d.steps) stepMap.set(s.id, s.name);
      map.set(d.id, { name: d.name, stepName: stepMap });
    }
    return map;
  }, [directoriesQuery.data]);

  const filtered = useMemo(() => {
    const all = listQuery.data?.items ?? [];
    const q = searchText.trim().toLowerCase();
    if (!q) return all;
    return all.filter(
      (row) =>
        (row.title ?? "").toLowerCase().includes(q) ||
        (row.city ?? "").toLowerCase().includes(q) ||
        (row.owner?.display_name ?? "").toLowerCase().includes(q),
    );
  }, [listQuery.data?.items, searchText]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(currentPage, totalPages);
  const pagedItems = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const handleSearch = (q: string) => {
    setSearchText(q);
    setCurrentPage(1);
  };

  const handleDirectoryFilter = (val: string) => {
    setDirectoryFilter(val);
    setCurrentPage(1);
  };

  const startItem = filtered.length === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const endItem = Math.min(safePage * PAGE_SIZE, filtered.length);

  // Pagination pages to show
  const pageNums: (number | "…")[] = useMemo(() => {
    if (totalPages <= 5) return Array.from({ length: totalPages }, (_, i) => i + 1);
    const pages: (number | "…")[] = [1];
    if (safePage > 3) pages.push("…");
    for (let p = Math.max(2, safePage - 1); p <= Math.min(totalPages - 1, safePage + 1); p++) pages.push(p);
    if (safePage < totalPages - 2) pages.push("…");
    pages.push(totalPages);
    return pages;
  }, [totalPages, safePage]);

  return (
    <div style={{ padding: "32px", maxWidth: 1200, margin: "0 auto", display: "flex", flexDirection: "column", gap: 24 }}>

      {/* ── Action bar ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#0F172A" }}>Oportunidades</h1>
          {listQuery.data && (
            <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 10px", borderRadius: 20, background: "#EEF2FF", color: "#4F46E5", border: "1px solid #C7D2FE" }}>
              {filtered.length}
            </span>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {/* Search */}
          <div style={{ position: "relative" }}>
            <Search size={14} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "#94A3B8", pointerEvents: "none" }} />
            <input
              type="text"
              placeholder="Buscar oportunidades..."
              value={searchText}
              onChange={(e) => handleSearch(e.target.value)}
              style={{ paddingLeft: 32, paddingRight: 12, paddingTop: 8, paddingBottom: 8, width: 240, background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: 8, fontSize: 13, color: "#0F172A", outline: "none" }}
            />
          </div>

          {/* Directory filter */}
          <div style={{ position: "relative" }}>
            <FolderOpen size={13} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "#94A3B8", pointerEvents: "none" }} />
            <select
              value={directoryFilter}
              onChange={(e) => handleDirectoryFilter(e.target.value)}
              style={{ paddingLeft: 28, paddingRight: 28, paddingTop: 8, paddingBottom: 8, background: "white", border: "1px solid #E2E8F0", borderRadius: 8, fontSize: 13, color: "#374151", outline: "none", appearance: "none", cursor: "pointer" }}
            >
              <option value="">Todos los directorios</option>
              {(directoriesQuery.data?.items ?? []).map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
            <ChevronRight size={12} style={{ position: "absolute", right: 9, top: "50%", transform: "translateY(-50%) rotate(90deg)", color: "#94A3B8", pointerEvents: "none" }} />
          </div>

          {/* CTA */}
          <Link
            to="/opportunities/new"
            style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 16px", background: "#2563EB", color: "white", borderRadius: 8, fontSize: 13, fontWeight: 600, textDecoration: "none", boxShadow: "0 1px 3px rgba(37,99,235,0.3)", transition: "background 0.15s" }}
          >
            <Plus size={14} /> Nueva oportunidad
          </Link>
        </div>
      </div>

      {/* ── Table card ── */}
      <div style={{ background: "white", border: "1px solid #E2E8F0", borderRadius: 12, overflow: "hidden", boxShadow: "0 1px 4px rgba(0,0,0,0.05)" }}>

        {/* Toolbar */}
        <div style={{ padding: "12px 20px", borderBottom: "1px solid #F1F5F9", background: "#FAFAFA", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 12, color: "#64748B", fontWeight: 500 }}>
              {listQuery.isLoading ? "Cargando…" : filtered.length === 0 ? "Sin resultados" : `Mostrando ${startItem}–${endItem} de ${filtered.length}`}
            </span>
          </div>
          <button
            type="button"
            style={{ width: 30, height: 30, display: "flex", alignItems: "center", justifyContent: "center", border: "none", background: "transparent", color: "#94A3B8", borderRadius: 6, cursor: "pointer" }}
            title="Exportar"
          >
            <Download size={14} />
          </button>
        </div>

        {/* Loading */}
        {listQuery.isLoading && (
          <div style={{ padding: 48, display: "flex", flexDirection: "column", alignItems: "center", gap: 12, color: "#94A3B8" }}>
            <Loader2 size={24} style={{ animation: "spin 1s linear infinite" }} />
            <span style={{ fontSize: 13 }}>Cargando oportunidades…</span>
          </div>
        )}

        {/* Error */}
        {listQuery.isError && (
          <p style={{ padding: "24px", color: "#DC2626", fontSize: 13 }}>No se pudo cargar la lista. Intenta de nuevo.</p>
        )}

        {/* Empty */}
        {!listQuery.isLoading && !listQuery.isError && filtered.length === 0 && (
          <div style={{ padding: 64, display: "flex", flexDirection: "column", alignItems: "center", gap: 12, textAlign: "center" }}>
            <div style={{ width: 64, height: 64, borderRadius: "50%", background: "#F1F5F9", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <FolderOpen size={28} color="#CBD5E1" />
            </div>
            <div>
              <p style={{ margin: "0 0 4px", fontSize: 15, fontWeight: 600, color: "#0F172A" }}>No hay oportunidades encontradas</p>
              <p style={{ margin: 0, fontSize: 13, color: "#64748B" }}>
                {searchText.trim() ? "Intenta ajustar tu búsqueda." : "No hay oportunidades en este directorio todavía."}
              </p>
            </div>
          </div>
        )}

        {/* Table */}
        {!listQuery.isLoading && pagedItems.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table className="opp-table-v2" style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#F8FAFC", borderBottom: "1px solid #E2E8F0" }}>
                  {["Nombre", "Directorio", "Paso actual", "Ciudad", "Propietario", "Actualizado", ""].map((h) => (
                    <th key={h} style={{ padding: "10px 20px", textAlign: h === "" ? "right" : "left", fontSize: 11, fontWeight: 600, color: "#64748B", textTransform: "uppercase", letterSpacing: "0.04em", whiteSpace: "nowrap" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pagedItems.map((row) => {
                  const dir = row.directory_id ? directoryById.get(row.directory_id) : undefined;
                  const stepName = dir && row.current_step_id ? dir.stepName.get(row.current_step_id) : undefined;
                  const badge = getStepBadge(row, stepName);
                  const av = getAvatarStyle(row.title || row.opportunity_id);
                  const ownerAv = getAvatarStyle(row.owner?.display_name || row.opportunity_id);

                  return (
                    <tr key={row.opportunity_id} className="opp-table-row-v2">
                      {/* Nombre */}
                      <td style={{ padding: "14px 20px", whiteSpace: "nowrap" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <div style={{ width: 32, height: 32, borderRadius: 6, background: av.bg, color: av.color, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, flexShrink: 0 }}>
                            {initials(row.title || "?")}
                          </div>
                          <div>
                            <Link
                              to={`/opportunities/${row.opportunity_id}`}
                              className="opp-row-name-link"
                              style={{ fontWeight: 600, color: "#0F172A", textDecoration: "none", fontSize: 13 }}
                            >
                              {row.title || "Sin título"}
                            </Link>
                          </div>
                        </div>
                      </td>

                      {/* Directorio */}
                      <td style={{ padding: "14px 20px", whiteSpace: "nowrap" }}>
                        {dir ? (
                          <Link
                            to={`/directories/${row.directory_id}`}
                            style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 13, color: "#475569", textDecoration: "none" }}
                          >
                            <FolderOpen size={12} color="#94A3B8" /> {dir.name}
                          </Link>
                        ) : (
                          <span style={{ color: "#CBD5E1" }}>—</span>
                        )}
                      </td>

                      {/* Paso actual */}
                      <td style={{ padding: "14px 20px", whiteSpace: "nowrap" }}>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 9px", borderRadius: 6, fontSize: 12, fontWeight: 500, background: badge.bg, color: badge.color, border: `1px solid ${badge.border}` }}>
                          <span style={{ width: 6, height: 6, borderRadius: "50%", background: badge.dot, flexShrink: 0 }} />
                          {badge.label}
                        </span>
                      </td>

                      {/* Ciudad */}
                      <td style={{ padding: "14px 20px", whiteSpace: "nowrap", color: "#475569", fontSize: 13 }}>
                        {row.city || <span style={{ color: "#CBD5E1" }}>—</span>}
                      </td>

                      {/* Propietario */}
                      <td style={{ padding: "14px 20px", whiteSpace: "nowrap" }}>
                        {row.owner ? (
                          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                            <div style={{ width: 24, height: 24, borderRadius: "50%", background: ownerAv.bg, color: ownerAv.color, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, fontWeight: 700, flexShrink: 0 }}>
                              {initials(row.owner.display_name)}
                            </div>
                            <span style={{ fontSize: 12, fontWeight: 500, color: "#374151" }}>
                              {row.owner.display_name.split(" ").slice(0, 2).join(" ")}
                            </span>
                          </div>
                        ) : (
                          <span style={{ color: "#CBD5E1", fontSize: 13 }}>—</span>
                        )}
                      </td>

                      {/* Actualizado */}
                      <td style={{ padding: "14px 20px", whiteSpace: "nowrap", color: "#94A3B8", fontSize: 12 }}>
                        {formatRelative(row.updated_at)}
                      </td>

                      {/* Actions */}
                      <td style={{ padding: "14px 20px", textAlign: "right" }}>
                        <Link
                          to={`/opportunities/${row.opportunity_id}`}
                          className="opp-row-action-btn"
                          style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 28, height: 28, borderRadius: 6, border: "1px solid #E2E8F0", background: "white", color: "#94A3B8", textDecoration: "none", opacity: 0, transition: "opacity 0.15s, color 0.15s" }}
                          aria-label="Abrir oportunidad"
                        >
                          <ChevronRight size={14} />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div style={{ padding: "14px 20px", borderTop: "1px solid #F1F5F9", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 13, color: "#64748B" }}>
              Página <strong style={{ color: "#0F172A" }}>{safePage}</strong> de <strong style={{ color: "#0F172A" }}>{totalPages}</strong>
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={safePage === 1}
                className="opp-page-btn"
                style={{ padding: "5px 10px", border: "1px solid #E2E8F0", borderRadius: 6, fontSize: 13, color: safePage === 1 ? "#CBD5E1" : "#475569", background: safePage === 1 ? "#F8FAFC" : "white", cursor: safePage === 1 ? "not-allowed" : "pointer" }}
              >
                <ChevronLeft size={14} />
              </button>

              {pageNums.map((p, i) =>
                p === "…" ? (
                  <span key={`ellipsis-${i}`} style={{ padding: "0 4px", color: "#94A3B8", fontSize: 13 }}>…</span>
                ) : (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setCurrentPage(p as number)}
                    style={{ minWidth: 32, padding: "5px 8px", border: "1px solid #E2E8F0", borderRadius: 6, fontSize: 13, fontWeight: p === safePage ? 600 : 400, color: p === safePage ? "white" : "#475569", background: p === safePage ? "#2563EB" : "white", cursor: "pointer" }}
                  >
                    {p}
                  </button>
                )
              )}

              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={safePage === totalPages}
                style={{ padding: "5px 10px", border: "1px solid #E2E8F0", borderRadius: 6, fontSize: 13, color: safePage === totalPages ? "#CBD5E1" : "#475569", background: safePage === totalPages ? "#F8FAFC" : "white", cursor: safePage === totalPages ? "not-allowed" : "pointer" }}
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
