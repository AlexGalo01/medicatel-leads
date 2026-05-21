import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Activity,
  FolderOpen,
  LayoutGrid,
  List,
  Loader2,
  Pencil,
  Plus,
  Search,
  Target,
  Trash2,
  TrendingUp,
} from "lucide-react";

import { listDirectories, deleteDirectory, createDirectory } from "../../../api";

const PAGE_SIZE = 12;

const CARD_PALETTE = [
  { iconBg: "#DBEAFE", iconColor: "#1D4ED8" },
  { iconBg: "#EDE9FE", iconColor: "#7C3AED" },
  { iconBg: "#D1FAE5", iconColor: "#059669" },
  { iconBg: "#FEF3C7", iconColor: "#D97706" },
  { iconBg: "#FCE7F3", iconColor: "#DB2777" },
  { iconBg: "#CFFAFE", iconColor: "#0891B2" },
];

export function DirectoriesListPage(): JSX.Element {
  const [viewMode, setViewMode] = useState<"card" | "table">(() => {
    return (localStorage.getItem("directories-view") ?? "card") as "card" | "table";
  });
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deleteMode, setDeleteMode] = useState<"delete" | "reassign">("reassign");
  const [reassignTargetId, setReassignTargetId] = useState<string>("");
  const [creatingNew, setCreatingNew] = useState(false);
  const [newDirName, setNewDirName] = useState("");

  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["directories"],
    queryFn: () => listDirectories(),
  });

  const deleteMut = useMutation({
    mutationFn: ({ id, reassignToDirectoryId }: { id: string; reassignToDirectoryId?: string }) =>
      deleteDirectory(id, reassignToDirectoryId ? { reassignToDirectoryId } : undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["directories"] });
      closeDeleteModal();
    },
  });

  const createDirMut = useMutation({
    mutationFn: (name: string) =>
      createDirectory({
        name,
        description: null,
        steps: [{ name: "Sin clasificar", is_terminal: false, is_won: false }],
      }),
    onSuccess: (newDir) => {
      qc.invalidateQueries({ queryKey: ["directories"] });
      if (confirmDeleteId) {
        deleteMut.mutate({ id: confirmDeleteId, reassignToDirectoryId: newDir.id });
      }
    },
  });

  function closeDeleteModal() {
    setConfirmDeleteId(null);
    setDeleteMode("reassign");
    setReassignTargetId("");
    setCreatingNew(false);
    setNewDirName("");
  }

  function handleDeleteConfirm() {
    if (!confirmDeleteId) return;
    if (isEmpty) {
      deleteMut.mutate({ id: confirmDeleteId });
      return;
    }
    if (deleteMode === "reassign") {
      if (creatingNew) {
        if (!newDirName.trim()) return;
        createDirMut.mutate(newDirName.trim());
      } else {
        if (!reassignTargetId) return;
        deleteMut.mutate({ id: confirmDeleteId, reassignToDirectoryId: reassignTargetId });
      }
    } else {
      deleteMut.mutate({ id: confirmDeleteId });
    }
  }

  const filtered = useMemo(() => {
    if (!query.data) return [];
    const q = search.trim().toLowerCase();
    if (!q) return query.data.items;
    return query.data.items.filter(
      (d) => d.name.toLowerCase().includes(q) || (d.description ?? "").toLowerCase().includes(q),
    );
  }, [query.data, search]);

  useEffect(() => { setPage(1); }, [search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const paged = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  function toggleViewMode(mode: "card" | "table") {
    setViewMode(mode);
    localStorage.setItem("directories-view", mode);
  }

  function handleDeleteClick(e: React.MouseEvent, id: string) {
    e.preventDefault();
    e.stopPropagation();
    setConfirmDeleteId(id);
    setDeleteMode("reassign");
    setReassignTargetId("");
    setCreatingNew(false);
    setNewDirName("");
  }

  const confirmDir = query.data?.items.find((d) => d.id === confirmDeleteId);
  const otherDirs = (query.data?.items ?? []).filter((d) => d.id !== confirmDeleteId);
  const isPending = deleteMut.isPending || createDirMut.isPending;
  const isEmpty = (confirmDir?.item_count ?? 0) === 0;
  const canConfirm =
    isEmpty ||
    deleteMode === "delete" ||
    (deleteMode === "reassign" && creatingNew && newDirName.trim().length > 0) ||
    (deleteMode === "reassign" && !creatingNew && reassignTargetId !== "");

  const totalDirs = query.data?.items.length ?? 0;
  const totalOpps = (query.data?.items ?? []).reduce((acc, d) => acc + (d.item_count ?? 0), 0);

  const viewBtnStyle = (active: boolean): React.CSSProperties => ({
    width: 32, height: 32, borderRadius: 6,
    display: "flex", alignItems: "center", justifyContent: "center",
    background: active ? "white" : "transparent",
    border: "none", cursor: "pointer",
    color: active ? "#0000FF" : "#808080",
    boxShadow: active ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
    transition: "all 0.15s",
  });

  return (
    <section className="directories-v2">

      {/* ── HEADER ── */}
      <header style={{
        height: 72, background: "var(--c-card-bg)", borderBottom: "1px solid #D3D3D3",
        padding: "0 32px", display: "flex", alignItems: "center",
        justifyContent: "space-between", flexShrink: 0,
      }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--color-text)", margin: 0 }}>
          Listas
        </h1>

        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          {/* Search */}
          <div style={{ position: "relative", width: 280 }}>
            <Search size={15} aria-hidden style={{
              position: "absolute", left: 14, top: "50%",
              transform: "translateY(-50%)", color: "var(--color-text-secondary)", pointerEvents: "none",
            }} />
            <input
              type="text"
              placeholder="Buscar directorios..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: "100%", height: 38, paddingLeft: 40, paddingRight: 14,
                borderRadius: 999, border: "1px solid #D3D3D3",
                background: "var(--color-surface-alt)", fontSize: 13, outline: "none",
                fontFamily: "inherit", color: "var(--color-text)", boxSizing: "border-box",
                transition: "border-color 0.2s",
              }}
            />
          </div>

          {/* View toggle */}
          <div style={{
            display: "flex", alignItems: "center",
            background: "var(--color-surface-alt)", borderRadius: 8,
            border: "1px solid #D3D3D3", padding: 4, gap: 2,
          }}>
            <button
              type="button"
              style={viewBtnStyle(viewMode === "card")}
              onClick={() => toggleViewMode("card")}
              title="Vista cuadrícula"
            >
              <LayoutGrid size={16} />
            </button>
            <button
              type="button"
              style={viewBtnStyle(viewMode === "table")}
              onClick={() => toggleViewMode("table")}
              title="Vista lista"
            >
              <List size={16} />
            </button>
          </div>

          {/* CTA */}
          <Link
            to="/lists/new"
            style={{
              display: "flex", alignItems: "center", gap: 8,
              background: "#0000FF", color: "white", textDecoration: "none",
              height: 38, paddingLeft: 20, paddingRight: 20,
              borderRadius: 999, fontSize: 13, fontWeight: 500,
              boxShadow: "0 2px 8px rgba(0,0,255,0.2)",
              transition: "background 0.15s",
            }}
          >
            <Plus size={15} aria-hidden /> Crear lista
          </Link>
        </div>
      </header>

      {/* ── SCROLLABLE CONTENT ── */}
      <div style={{ flex: 1, overflowY: "auto", padding: 32 }}>

        {/* STATS ROW — skeleton while loading, real values after */}
        {query.isLoading ? (
          <div className="dir-skeleton-stats">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="dir-skeleton-stat-card">
                <span className={`skel skel--d${i + 1}`} style={{ width: 48, height: 48, borderRadius: "50%", flexShrink: 0 }} />
                <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
                  <span className={`skel skel--d${i + 1}`} style={{ height: 11, width: "65%" }} />
                  <span className={`skel skel--d${i + 1}`} style={{ height: 22, width: "40%" }} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
            gap: 20,
            marginBottom: 32,
          }}>
            {[
              { icon: <FolderOpen size={22} />, iconBg: "#DBEAFE", iconColor: "#1D4ED8", label: "Total Listas", value: totalDirs },
              { icon: <Target size={22} />, iconBg: "#D1FAE5", iconColor: "#059669", label: "Oportunidades Activas", value: totalOpps },
              { icon: <Activity size={22} />, iconBg: "#EDE9FE", iconColor: "#7C3AED", label: "Pasos Ejecutados", value: 0 },
              { icon: <TrendingUp size={22} />, iconBg: "#FED7AA", iconColor: "#D97706", label: "Tasa de Conversión", value: "0%" },
            ].map((stat, i) => (
              <div key={i} style={{
                background: "var(--c-card-bg)", borderRadius: 14, border: "1px solid var(--color-border)",
                padding: "18px 20px", display: "flex", alignItems: "center", gap: 16,
                boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
              }}>
                <div style={{
                  width: 48, height: 48, borderRadius: "50%",
                  background: stat.iconBg, color: stat.iconColor,
                  display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                }}>
                  {stat.icon}
                </div>
                <div>
                  <p style={{ fontSize: 12, color: "var(--color-text-secondary)", fontWeight: 500, margin: "0 0 4px" }}>{stat.label}</p>
                  <p style={{ fontSize: 22, fontWeight: 700, color: "var(--color-text)", margin: 0 }}>{stat.value}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* LOADING / ERROR */}
        {query.isLoading ? (
          <div className="dir-skeleton-grid">
            {Array.from({ length: 6 }).map((_, i) => {
              const delay = `skel--d${(i % 4) + 1}`;
              return (
                <div key={i} className="dir-skeleton-card">
                  <div className="dir-skeleton-card__body">
                    <span className={`skel ${delay}`} style={{ width: 40, height: 40, borderRadius: 10 }} />
                    <span className={`skel ${delay}`} style={{ height: 15, width: "72%", marginTop: 4 }} />
                    <span className={`skel ${delay}`} style={{ height: 11, width: "92%" }} />
                    <span className={`skel ${delay}`} style={{ height: 11, width: "65%" }} />
                  </div>
                  <div className="dir-skeleton-card__footer">
                    <span className={`skel ${delay}`} style={{ flex: 1, height: 32, borderRadius: 8 }} />
                    <span className={`skel ${delay}`} style={{ flex: 1, height: 32, borderRadius: 8 }} />
                  </div>
                </div>
              );
            })}
          </div>
        ) : query.isError ? (
          <p className="error-text">No se pudieron cargar las listas.</p>
        ) : (
          <>
            {/* ── GRID VIEW ── */}
            {viewMode === "card" && (
              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
                gap: 20,
              }}>
                {paged.map((dir, i) => {
                  const pal = CARD_PALETTE[i % CARD_PALETTE.length];
                  return (
                    <div key={dir.id} className="dir-card">
                      {/* Hover actions */}
                      <div className="dir-card-actions">
                        <Link
                          to={`/lists/${dir.id}/edit`}
                          className="dir-card-action-btn"
                          title="Editar"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <Pencil size={12} />
                        </Link>
                        <button
                          type="button"
                          className="dir-card-action-btn dir-card-action-btn--delete"
                          title="Eliminar"
                          onClick={(e) => handleDeleteClick(e, dir.id)}
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>

                      <Link to={`/lists/${dir.id}`} style={{ textDecoration: "none", display: "block" }}>
                        {/* Icon */}
                        <div style={{
                          width: 40, height: 40, borderRadius: 10,
                          background: pal.iconBg, color: pal.iconColor,
                          display: "flex", alignItems: "center", justifyContent: "center",
                          marginBottom: 14,
                        }}>
                          <FolderOpen size={20} />
                        </div>

                        {/* Title */}
                        <h3 style={{
                          fontSize: 15, fontWeight: 700, color: "var(--color-text)",
                          margin: "0 0 8px", paddingRight: 48,
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        }}>
                          {dir.name}
                        </h3>

                        {/* Description */}
                        <p style={{
                          fontSize: 13, color: "var(--color-text-secondary)", margin: "0 0 16px",
                          lineHeight: 1.5, height: "2.9em",
                          overflow: "hidden",
                          display: "-webkit-box",
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: "vertical",
                        }}>
                          {dir.description || "Sin descripción"}
                        </p>

                        {/* Progress bar */}
                        <div style={{ paddingTop: 14, borderTop: "1px solid #F1F5F9" }}>
                          <div style={{
                            display: "flex", justifyContent: "space-between",
                            alignItems: "center", marginBottom: 8,
                          }}>
                            <span style={{ fontSize: 11, color: "var(--color-text-secondary)", fontWeight: 500 }}>
                              Progreso de campaña
                            </span>
                            <span style={{ fontSize: 11, fontWeight: 700, color: pal.iconColor }}>0%</span>
                          </div>
                          <div style={{
                            width: "100%", height: 5, background: "#F1F5F9",
                            borderRadius: 999, overflow: "hidden",
                          }}>
                            <div style={{ height: "100%", background: pal.iconColor, width: "0%", borderRadius: 999 }} />
                          </div>

                          {/* Mini stats */}
                          <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
                            <div style={{
                              flex: 1, background: "var(--color-surface-alt)", border: "1px solid var(--color-border)",
                              borderRadius: 8, padding: "7px 10px",
                              display: "flex", alignItems: "center", gap: 6,
                            }}>
                              <Target size={11} style={{ color: "#059669" }} />
                              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--color-text)" }}>
                                {dir.item_count}{" "}
                                <span style={{ fontWeight: 400, color: "var(--color-text-secondary)" }}>oport.</span>
                              </span>
                            </div>
                            <div style={{
                              flex: 1, background: "var(--color-surface-alt)", border: "1px solid var(--color-border)",
                              borderRadius: 8, padding: "7px 10px",
                              display: "flex", alignItems: "center", gap: 6,
                            }}>
                              <Activity size={11} style={{ color: "#0000FF" }} />
                              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--color-text)" }}>
                                {dir.steps.length}{" "}
                                <span style={{ fontWeight: 400, color: "var(--color-text-secondary)" }}>pasos</span>
                              </span>
                            </div>
                          </div>
                        </div>
                      </Link>
                    </div>
                  );
                })}

                {/* Create new card */}
                <Link
                  to="/lists/new"
                  className="dir-card dir-card--create"
                  style={{ textDecoration: "none", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", minHeight: 220 }}
                >
                  <div style={{
                    width: 48, height: 48, borderRadius: "50%",
                    border: "2px dashed #0000FF", color: "#0000FF",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    background: "var(--c-card-bg)", marginBottom: 12,
                  }}>
                    <Plus size={22} />
                  </div>
                  <h3 style={{ fontSize: 15, fontWeight: 700, color: "var(--color-text)", margin: "0 0 6px" }}>
                    Nuevo Lista
                  </h3>
                  <p style={{ fontSize: 12, color: "var(--color-text-secondary)", margin: 0 }}>
                    Comienza a prospectar un nuevo segmento
                  </p>
                </Link>
              </div>
            )}

            {/* ── LIST VIEW ── */}
            {viewMode === "table" && filtered.length > 0 && (
              <div className="dir-table-wrap">
                <table className="dir-table">
                  <thead>
                    <tr>
                      <th>Nombre del Lista</th>
                      <th style={{ width: "38%" }}>Descripción</th>
                      <th>Oportunidades</th>
                      <th>Pasos</th>
                      <th style={{ textAlign: "right" }}>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paged.map((dir, i) => {
                      const pal = CARD_PALETTE[i % CARD_PALETTE.length];
                      return (
                        <tr key={dir.id} className="dir-table-row">
                          <td>
                            <Link to={`/lists/${dir.id}`} style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none" }}>
                              <div style={{
                                width: 32, height: 32, borderRadius: 8,
                                background: pal.iconBg, color: pal.iconColor,
                                display: "flex", alignItems: "center", justifyContent: "center",
                                flexShrink: 0,
                              }}>
                                <FolderOpen size={15} />
                              </div>
                              <span style={{ fontWeight: 700, color: "var(--color-text)", fontSize: 14 }}>
                                {dir.name}
                              </span>
                            </Link>
                          </td>
                          <td style={{ fontSize: 13, color: "var(--color-text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 300 }}>
                            {dir.description ?? "—"}
                          </td>
                          <td>
                            <span style={{
                              display: "inline-flex", alignItems: "center", gap: 5,
                              background: "#D1FAE5", color: "#059669",
                              padding: "3px 10px", borderRadius: 6,
                              fontSize: 12, fontWeight: 600,
                              border: "1px solid #A7F3D0",
                            }}>
                              <Target size={11} /> {dir.item_count}
                            </span>
                          </td>
                          <td>
                            <span style={{
                              display: "inline-flex", alignItems: "center", gap: 5,
                              background: "#DBEAFE", color: "#1D4ED8",
                              padding: "3px 10px", borderRadius: 6,
                              fontSize: 12, fontWeight: 600,
                              border: "1px solid #BFDBFE",
                            }}>
                              <Activity size={11} /> {dir.steps.length}
                            </span>
                          </td>
                          <td>
                            <div className="dir-table-row-actions">
                              <Link
                                to={`/lists/${dir.id}/edit`}
                                className="dir-card-action-btn"
                                title="Editar"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <Pencil size={12} />
                              </Link>
                              <button
                                type="button"
                                className="dir-card-action-btn dir-card-action-btn--delete"
                                title="Eliminar"
                                onClick={(e) => handleDeleteClick(e, dir.id)}
                              >
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                {/* Table pagination */}
                {totalPages > 1 && (
                  <div style={{
                    padding: "14px 24px", borderTop: "1px solid #E5E7EB",
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    background: "#F8FAFC50",
                  }}>
                    <span style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>
                      Mostrando {(safePage - 1) * PAGE_SIZE + 1}–{Math.min(safePage * PAGE_SIZE, filtered.length)} de {filtered.length}
                    </span>
                    <div style={{ display: "flex", gap: 4 }}>
                      {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                        <button
                          key={p}
                          type="button"
                          onClick={() => setPage(p)}
                          style={{
                            width: 32, height: 32, borderRadius: 6,
                            border: p === safePage ? "none" : "1px solid #D3D3D3",
                            background: p === safePage ? "#0000FF" : "white",
                            color: p === safePage ? "white" : "#374151",
                            fontSize: 13, fontWeight: p === safePage ? 600 : 400,
                            cursor: "pointer", fontFamily: "inherit",
                          }}
                        >
                          {p}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ── EMPTY STATE ── */}
            {filtered.length === 0 && !query.isLoading && (
              <div style={{
                background: "var(--c-card-bg)", borderRadius: 16,
                border: "1px solid var(--color-border)",
                padding: "64px 32px",
                display: "flex", flexDirection: "column",
                alignItems: "center", textAlign: "center",
              }}>
                <div style={{
                  width: 64, height: 64, borderRadius: "50%",
                  background: "#F1F5F9", display: "flex",
                  alignItems: "center", justifyContent: "center",
                  marginBottom: 20, color: "#94A3B8",
                }}>
                  <FolderOpen size={30} />
                </div>
                <h2 style={{ fontSize: 20, fontWeight: 700, color: "var(--color-text)", margin: "0 0 10px" }}>
                  {search ? "Sin coincidencias" : "No tienes directorios aún"}
                </h2>
                <p style={{ color: "var(--color-text-secondary)", maxWidth: 400, margin: "0 0 24px", lineHeight: 1.6 }}>
                  {search
                    ? `No hay directorios que coincidan con "${search}".`
                    : "Comienza a organizar tus prospectos creando tu primer lista."}
                </p>
                {!search && (
                  <Link
                    to="/lists/new"
                    style={{
                      display: "inline-flex", alignItems: "center", gap: 8,
                      background: "#0000FF", color: "white", textDecoration: "none",
                      padding: "10px 24px", borderRadius: 999,
                      fontSize: 14, fontWeight: 600,
                    }}
                  >
                    <Plus size={16} /> Crear tu primer lista
                  </Link>
                )}
              </div>
            )}

            {/* Card-view pagination (only if more than one page and no create card visible) */}
            {viewMode === "card" && totalPages > 1 && (
              <div style={{ marginTop: 28, display: "flex", justifyContent: "center", alignItems: "center", gap: 8 }}>
                <button
                  type="button"
                  disabled={safePage === 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  style={{
                    padding: "6px 14px", borderRadius: 8, border: "1px solid #D3D3D3",
                    background: "var(--c-card-bg)", fontSize: 13, cursor: safePage === 1 ? "not-allowed" : "pointer",
                    color: safePage === 1 ? "#9CA3AF" : "#374151", fontFamily: "inherit",
                  }}
                >
                  ← Anterior
                </button>
                <span style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>
                  {safePage} / {totalPages}
                </span>
                <button
                  type="button"
                  disabled={safePage === totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  style={{
                    padding: "6px 14px", borderRadius: 8, border: "1px solid #D3D3D3",
                    background: "var(--c-card-bg)", fontSize: 13,
                    cursor: safePage === totalPages ? "not-allowed" : "pointer",
                    color: safePage === totalPages ? "#9CA3AF" : "#374151", fontFamily: "inherit",
                  }}
                >
                  Siguiente →
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* ── DELETE MODAL ── */}
      {confirmDir && (
        <div
          className="dirs-confirm-overlay"
          onClick={(e) => { if (e.target === e.currentTarget && !isPending) closeDeleteModal(); }}
        >
          <div className="dirs-confirm-panel" onClick={(e) => e.stopPropagation()}>
            <h2 className="dirs-confirm-title">Eliminar «{confirmDir.name}»</h2>

            {confirmDir.item_count > 0 ? (
              <>
                <p className="dirs-confirm-description">
                  Este lista tiene <strong>{confirmDir.item_count}</strong>{" "}
                  {confirmDir.item_count === 1 ? "oportunidad" : "oportunidades"}. ¿Qué deseas hacer con ellas?
                </p>
                <div className="dirs-confirm-options">
                  <label className="dirs-confirm-option">
                    <input type="radio" name="delete-mode" value="reassign"
                      checked={deleteMode === "reassign"} onChange={() => setDeleteMode("reassign")} />
                    <span>Reasignar a otro lista</span>
                  </label>
                  <label className="dirs-confirm-option">
                    <input type="radio" name="delete-mode" value="delete"
                      checked={deleteMode === "delete"} onChange={() => setDeleteMode("delete")} />
                    <span>Eliminar las oportunidades también</span>
                  </label>
                </div>
                {deleteMode === "reassign" && (
                  <div className="dirs-confirm-reassign">
                    {!creatingNew ? (
                      <>
                        <select value={reassignTargetId} onChange={(e) => setReassignTargetId(e.target.value)}
                          className="dirs-confirm-select">
                          <option value="">Seleccionar lista…</option>
                          {otherDirs.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                        </select>
                        <button type="button" className="link-button"
                          style={{ fontSize: "0.85rem", marginTop: "6px" }}
                          onClick={() => { setCreatingNew(true); setReassignTargetId(""); }}>
                          + Crear nuevo lista
                        </button>
                      </>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                        <input type="text" className="dirs-confirm-input"
                          placeholder="Nombre del nuevo lista…"
                          value={newDirName} onChange={(e) => setNewDirName(e.target.value)}
                          autoFocus maxLength={160} />
                        <button type="button" className="link-button"
                          style={{ fontSize: "0.85rem" }}
                          onClick={() => { setCreatingNew(false); setNewDirName(""); }}>
                          ← Elegir existente
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </>
            ) : (
              <p className="dirs-confirm-description">
                El lista está vacío. Esta acción no se puede deshacer.
              </p>
            )}

            {(deleteMut.isError || createDirMut.isError) && (
              <p className="error-text" style={{ fontSize: "0.85rem", marginTop: "8px" }}>
                Ocurrió un error. Intenta de nuevo.
              </p>
            )}

            <div className="dirs-confirm-actions">
              <button onClick={closeDeleteModal} className="dirs-confirm-btn dirs-confirm-btn--cancel"
                type="button" disabled={isPending}>
                Cancelar
              </button>
              <button onClick={handleDeleteConfirm} className="dirs-confirm-btn dirs-confirm-btn--delete"
                type="button" disabled={isPending || !canConfirm}>
                {isPending ? <><Loader2 size={14} className="spin" /> Procesando…</> : "Confirmar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
