import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ChevronRight, Loader2, Search } from "lucide-react";

import { listDirectories, listOpportunities } from "../../../api";
import { Card } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Select } from "../../../components/ui/select";

function formatUpdated(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("es-HN", { dateStyle: "short", timeStyle: "short" });
}

export function OpportunitiesListPage(): JSX.Element {
  const [directoryFilter, setDirectoryFilter] = useState<string>("");
  const [searchText, setSearchText] = useState("");

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
      for (const s of d.steps) {
        stepMap.set(s.id, s.name);
      }
      map.set(d.id, { name: d.name, stepName: stepMap });
    }
    return map;
  }, [directoriesQuery.data]);

  const items = useMemo(() => {
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

  return (
    <div className="opportunities-page">
      <Card className="panel opportunities-page-header">
        <div>
          <h1 className="opportunities-page-title">Oportunidades</h1>
          <p className="muted-text" style={{ margin: 0 }}>
            {listQuery.data ? `${listQuery.data.items.length} en total` : ""}
          </p>
        </div>
        <div className="opportunities-filters-row">
          <Select
            value={directoryFilter}
            onChange={(e) => setDirectoryFilter(e.target.value)}
            aria-label="Filtrar por directorio"
          >
            <option value="">Todos los directorios</option>
            {(directoriesQuery.data?.items ?? []).map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </Select>
          <div className="opportunities-search-wrap">
            <Search size={16} className="opportunities-search-icon" aria-hidden />
            <Input
              type="text"
              placeholder="Buscar por título, ciudad o responsable…"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              className="opportunities-search-input"
            />
          </div>
        </div>
      </Card>

      <Card className="panel opportunities-table-wrap">
        {listQuery.isLoading ? (
          <div className="opportunities-loading-state">
            <Loader2 className="spin" size={28} />
            <p className="muted-text">Cargando oportunidades…</p>
          </div>
        ) : null}
        {listQuery.isError ? (
          <p className="error-text" style={{ padding: "1.5rem" }}>
            No se pudo cargar la lista. Intenta de nuevo.
          </p>
        ) : null}
        {!listQuery.isLoading && !listQuery.isError && items.length === 0 ? (
          <p className="muted-text opportunities-empty">
            {searchText.trim()
              ? "Sin resultados para esta búsqueda."
              : "No hay oportunidades en este directorio todavía."}
          </p>
        ) : null}
        {!listQuery.isLoading && items.length > 0 ? (
          <table className="opportunities-table">
            <thead>
              <tr>
                <th scope="col">Título</th>
                <th scope="col">Directorio</th>
                <th scope="col">Step</th>
                <th scope="col">Estado</th>
                <th scope="col">Actualizado</th>
                <th scope="col">
                  <span className="visually-hidden">Acción</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => {
                const dir = row.directory_id ? directoryById.get(row.directory_id) : undefined;
                const stepName = dir && row.current_step_id ? dir.stepName.get(row.current_step_id) : undefined;
                return (
                  <tr key={row.opportunity_id}>
                    <td>
                      <strong>{row.title || "Sin título"}</strong>
                      {row.city ? (
                        <span className="muted-text" style={{ display: "block", fontSize: 12 }}>
                          {row.city}
                        </span>
                      ) : null}
                    </td>
                    <td>
                      {dir ? (
                        <Link
                          to={`/directories/${row.directory_id}`}
                          className="muted-text"
                          style={{ textDecoration: "none" }}
                        >
                          {dir.name}
                        </Link>
                      ) : (
                        <span className="muted-text">—</span>
                      )}
                    </td>
                    <td className="muted-text">{stepName ?? "—"}</td>
                    <td>
                      {row.terminated_at ? (
                        <span
                          className={`ui-badge ui-badge--${
                            row.terminated_outcome === "won"
                              ? "success"
                              : row.terminated_outcome === "lost"
                                ? "error"
                                : "muted"
                          }`}
                        >
                          {row.terminated_outcome === "won"
                            ? "Ganada"
                            : row.terminated_outcome === "lost"
                              ? "Perdida"
                              : "Sin respuesta"}
                        </span>
                      ) : (
                        <span className="ui-badge ui-badge--default">Activa</span>
                      )}
                    </td>
                    <td className="muted-text">{formatUpdated(row.updated_at)}</td>
                    <td>
                      <Link
                        className="cta-button opportunities-row-link"
                        to={`/opportunities/${row.opportunity_id}`}
                      >
                        Abrir
                        <ChevronRight size={14} aria-hidden />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : null}
      </Card>
    </div>
  );
}
