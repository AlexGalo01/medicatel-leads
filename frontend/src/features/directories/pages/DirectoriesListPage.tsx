import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Folder, FolderOpen, Plus, Search, LayoutGrid, List, Trash2, Pencil, Loader2 } from "lucide-react";

import { listDirectories, deleteDirectory, createDirectory } from "../../../api";
import { Card } from "../../../components/ui/card";

const PAGE_SIZE = 12;

export function DirectoriesListPage(): JSX.Element {
  const [viewMode, setViewMode] = useState<"card" | "table">(() => {
    return (localStorage.getItem("directories-view") ?? "card") as "card" | "table";
  });
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  // "delete" = eliminar opps también | "reassign" = reasignar
  const [deleteMode, setDeleteMode] = useState<"delete" | "reassign">("reassign");
  const [reassignTargetId, setReassignTargetId] = useState<string>("");
  // crear directorio nuevo inline
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
      // Usar el nuevo directorio como destino de reasignación
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
      (d) =>
        d.name.toLowerCase().includes(q) || (d.description ?? "").toLowerCase().includes(q)
    );
  }, [query.data, search]);

  useEffect(() => {
    setPage(1);
  }, [search]);

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
  const canConfirm = isEmpty
    || deleteMode === "delete"
    || (deleteMode === "reassign" && creatingNew && newDirName.trim().length > 0)
    || (deleteMode === "reassign" && !creatingNew && reassignTargetId !== "");

  return (
    <section className="directories-page">
      <header className="directories-page-head">
        <div>
          <h1 className="directories-page-title">Directorios</h1>
          <p className="muted-text directories-page-sub">
            Cada directorio tiene su propio flow de steps. Las búsquedas se asignan a un directorio
            y sus oportunidades progresan dentro de él.
          </p>
        </div>
        <Link to="/directories/new" className="cta-button">
          <Plus size={16} aria-hidden /> Crear directorio
        </Link>
      </header>

      {query.isLoading ? (
        <p className="muted-text">Cargando directorios…</p>
      ) : query.isError ? (
        <p className="error-text">No se pudieron cargar los directorios.</p>
      ) : query.data && query.data.items.length > 0 ? (
        <>
          <div className="directories-toolbar">
            <div className="directories-search-wrap">
              <Search size={16} aria-hidden />
              <input
                type="text"
                placeholder="Buscar por nombre o descripción…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="directories-search-input"
              />
            </div>
            <div className="directories-view-toggle">
              <button
                onClick={() => toggleViewMode("card")}
                className={`directories-view-btn ${viewMode === "card" ? "is-active" : ""}`}
                title="Vista en tarjetas"
                type="button"
              >
                <LayoutGrid size={18} />
              </button>
              <button
                onClick={() => toggleViewMode("table")}
                className={`directories-view-btn ${viewMode === "table" ? "is-active" : ""}`}
                title="Vista en tabla"
                type="button"
              >
                <List size={18} />
              </button>
            </div>
          </div>

          {viewMode === "card" ? (
            <div className="directories-grid">
              {paged.map((dir) => (
                <Card
                  key={dir.id}
                  className="ui-card ui-card--interactive directory-card"
                >
                  <Link
                    to={`/directories/${dir.id}/edit`}
                    className="directory-card-delete"
                    title="Editar directorio"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Pencil size={16} />
                  </Link>
                  <button
                    onClick={(e) => handleDeleteClick(e, dir.id)}
                    className="directory-card-delete"
                    type="button"
                    title="Eliminar directorio"
                  >
                    <Trash2 size={16} />
                  </button>
                  <Link to={`/directories/${dir.id}`} className="directory-card-body">
                    <div className="directory-card-head">
                      <Folder size={18} aria-hidden />
                      <h3 className="directory-card-title">{dir.name}</h3>
                    </div>
                    {dir.description ? (
                      <p className="muted-text directory-card-desc">{dir.description}</p>
                    ) : null}
                    <div className="directory-card-meta">
                      <span className="ui-badge ui-badge--muted">
                        {dir.item_count}{" "}
                        {dir.item_count === 1 ? "oportunidad" : "oportunidades"}
                      </span>
                      <span className="ui-badge ui-badge--muted">
                        {dir.steps.length} {dir.steps.length === 1 ? "step" : "steps"}
                      </span>
                    </div>
                  </Link>
                </Card>
              ))}
            </div>
          ) : (
            <div className="directories-table-wrap">
              <table className="directories-table">
                <thead>
                  <tr>
                    <th>Nombre</th>
                    <th>Descripción</th>
                    <th>Steps</th>
                    <th>Oportunidades</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {paged.map((dir) => (
                    <tr key={dir.id}>
                      <td className="directories-table-name">{dir.name}</td>
                      <td className="directories-table-desc">{dir.description ?? "—"}</td>
                      <td>{dir.steps.length}</td>
                      <td>{dir.item_count}</td>
                      <td>
                        <div className="directories-table-actions">
                          <Link
                            to={`/directories/${dir.id}`}
                            className="directories-table-link"
                            title="Abrir directorio"
                          >
                            <FolderOpen size={15} />
                          </Link>
                          <Link
                            to={`/directories/${dir.id}/edit`}
                            className="directories-table-link"
                            title="Editar directorio"
                          >
                            <Pencil size={14} />
                          </Link>
                          <button
                            onClick={(e) => handleDeleteClick(e, dir.id)}
                            className="directories-table-delete"
                            type="button"
                            title="Eliminar directorio"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {totalPages > 1 && (
            <div className="directories-pagination">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={safePage === 1}
                className="directories-pagination-btn"
                type="button"
              >
                ← Anterior
              </button>
              <span className="directories-pagination-info">
                Página {safePage} de {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={safePage === totalPages}
                className="directories-pagination-btn"
                type="button"
              >
                Siguiente →
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="directories-empty">
          <Folder size={32} aria-hidden />
          <h3>Aún no hay directorios</h3>
          <p className="muted-text">
            Crea el primero para empezar a organizar tus búsquedas y oportunidades.
          </p>
          <Link to="/directories/new" className="cta-button">
            <Plus size={16} aria-hidden /> Crear directorio
          </Link>
        </div>
      )}

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
                  Este directorio tiene <strong>{confirmDir.item_count}</strong>{" "}
                  {confirmDir.item_count === 1 ? "oportunidad" : "oportunidades"}. ¿Qué deseas hacer con ellas?
                </p>

                <div className="dirs-confirm-options">
                  <label className="dirs-confirm-option">
                    <input
                      type="radio"
                      name="delete-mode"
                      value="reassign"
                      checked={deleteMode === "reassign"}
                      onChange={() => setDeleteMode("reassign")}
                    />
                    <span>Reasignar a otro directorio</span>
                  </label>
                  <label className="dirs-confirm-option">
                    <input
                      type="radio"
                      name="delete-mode"
                      value="delete"
                      checked={deleteMode === "delete"}
                      onChange={() => setDeleteMode("delete")}
                    />
                    <span>Eliminar las oportunidades también</span>
                  </label>
                </div>

                {deleteMode === "reassign" && (
                  <div className="dirs-confirm-reassign">
                    {!creatingNew ? (
                      <>
                        <select
                          value={reassignTargetId}
                          onChange={(e) => setReassignTargetId(e.target.value)}
                          className="dirs-confirm-select"
                        >
                          <option value="">Seleccionar directorio…</option>
                          {otherDirs.map((d) => (
                            <option key={d.id} value={d.id}>{d.name}</option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="link-button"
                          style={{ fontSize: "0.85rem", marginTop: "6px" }}
                          onClick={() => { setCreatingNew(true); setReassignTargetId(""); }}
                        >
                          + Crear nuevo directorio
                        </button>
                      </>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                        <input
                          type="text"
                          className="dirs-confirm-input"
                          placeholder="Nombre del nuevo directorio…"
                          value={newDirName}
                          onChange={(e) => setNewDirName(e.target.value)}
                          autoFocus
                          maxLength={160}
                        />
                        <button
                          type="button"
                          className="link-button"
                          style={{ fontSize: "0.85rem" }}
                          onClick={() => { setCreatingNew(false); setNewDirName(""); }}
                        >
                          ← Elegir existente
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </>
            ) : (
              <p className="dirs-confirm-description">
                El directorio está vacío. Esta acción no se puede deshacer.
              </p>
            )}

            {(deleteMut.isError || createDirMut.isError) && (
              <p className="error-text" style={{ fontSize: "0.85rem", marginTop: "8px" }}>
                Ocurrió un error. Intenta de nuevo.
              </p>
            )}

            <div className="dirs-confirm-actions">
              <button
                onClick={closeDeleteModal}
                className="dirs-confirm-btn dirs-confirm-btn--cancel"
                type="button"
                disabled={isPending}
              >
                Cancelar
              </button>
              <button
                onClick={handleDeleteConfirm}
                className="dirs-confirm-btn dirs-confirm-btn--delete"
                type="button"
                disabled={isPending || !canConfirm}
              >
                {isPending ? <><Loader2 size={14} className="spin" /> Procesando…</> : "Confirmar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
