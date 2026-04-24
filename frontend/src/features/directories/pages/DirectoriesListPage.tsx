import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Folder, Plus } from "lucide-react";

import { listDirectories } from "../../../api";
import { Card } from "../../../components/ui/card";

export function DirectoriesListPage(): JSX.Element {
  const query = useQuery({
    queryKey: ["directories"],
    queryFn: () => listDirectories(),
  });

  return (
    <section className="directories-page">
      <header className="directories-page-head">
        <div>
          <h1 className="directories-page-title">Directorios</h1>
          <p className="muted-text directories-page-sub">
            Cada directorio tiene su propio flow de steps. Las búsquedas se asignan a un directorio y sus
            oportunidades progresan dentro de él.
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
        <div className="directories-grid">
          {query.data.items.map((dir) => (
            <Card key={dir.id} className="ui-card ui-card--interactive directory-card">
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
                    {dir.item_count} {dir.item_count === 1 ? "oportunidad" : "oportunidades"}
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
        <div className="directories-empty">
          <Folder size={32} aria-hidden />
          <h3>Aún no hay directorios</h3>
          <p className="muted-text">Crea el primero para empezar a organizar tus búsquedas y oportunidades.</p>
          <Link to="/directories/new" className="cta-button">
            <Plus size={16} aria-hidden /> Crear directorio
          </Link>
        </div>
      )}
    </section>
  );
}
