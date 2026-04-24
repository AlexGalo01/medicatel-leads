import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Folder, Plus, Search, LayoutGrid, List, Trash2, ExternalLink } from "lucide-react";

import { listDirectories, deleteDirectory } from "../../../api";
import { Card } from "../../../components/ui/card";

const PAGE_SIZE = 12;

export function DirectoriesListPage(): JSX.Element {
  const [viewMode, setViewMode] = useState<"card" | "table">(() => {
    return (localStorage.getItem("directories-view") ?? "card") as "card" | "table";
  });
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["directories"],
    queryFn: () => listDirectories(),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteDirectory(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["directories"] });
      setConfirmDeleteId(null);
    },
  });

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
  }

  function handleDeleteConfirm() {
    if (confirmDeleteId) {
      deleteMut.mutate(confirmDeleteId);
    }
  }

  const confirmDir = query.data?.items.find((d) => d.id === confirmDeleteId);

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
                            <ExternalLink size={14} />
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
        <div className="dirs-confirm-overlay">
          <div className="dirs-confirm-panel">
            <h2 className="dirs-confirm-title">Eliminar directorio</h2>
            <p className="dirs-confirm-description">
              ¿Estás seguro de que deseas eliminar el directorio "{confirmDir.name}"? Esta acción
              no se puede deshacer.
            </p>
            <div className="dirs-confirm-actions">
              <button
                onClick={() => setConfirmDeleteId(null)}
                className="dirs-confirm-btn dirs-confirm-btn--cancel"
                type="button"
                disabled={deleteMut.isPending}
              >
                Cancelar
              </button>
              <button
                onClick={handleDeleteConfirm}
                className="dirs-confirm-btn dirs-confirm-btn--delete"
                type="button"
                disabled={deleteMut.isPending}
              >
                {deleteMut.isPending ? "Eliminando…" : "Eliminar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
