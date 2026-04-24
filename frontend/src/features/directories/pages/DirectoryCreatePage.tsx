import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ChevronLeft } from "lucide-react";

import { createDirectory } from "../../../api";
import { Button } from "../../../components/ui/button";
import { StepsEditor, type EditableStep } from "../components/StepsEditor";

const DEFAULT_STEPS: EditableStep[] = [
  { key: "s1", name: "Primer contacto", is_terminal: false, is_won: false },
  { key: "s2", name: "Presentación", is_terminal: false, is_won: false },
  { key: "s3", name: "Seguimiento", is_terminal: false, is_won: false },
  { key: "s4", name: "Cerrada (ganada)", is_terminal: true, is_won: true },
  { key: "s5", name: "Cerrada (perdida)", is_terminal: true, is_won: false },
];

export function DirectoryCreatePage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get("returnTo");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [steps, setSteps] = useState<EditableStep[]>(DEFAULT_STEPS);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      createDirectory({
        name: name.trim(),
        description: description.trim() || null,
        steps: steps
          .filter((s) => s.name.trim().length > 0)
          .map((s) => ({
            name: s.name.trim(),
            is_terminal: s.is_terminal,
            is_won: s.is_won,
          })),
      }),
    onSuccess: (dir) => {
      void queryClient.invalidateQueries({ queryKey: ["directories"] });
      if (returnTo) {
        navigate(`${returnTo}?directory_id=${dir.id}`);
      } else {
        navigate(`/directories/${dir.id}`);
      }
    },
    onError: (e: Error) => setError(e.message),
  });

  const canSubmit = name.trim().length > 0 && steps.some((s) => s.name.trim().length > 0);

  return (
    <section className="directory-create-page">
      <nav className="directory-create-nav" aria-label="Navegación">
        <Link to="/directories" className="link-button">
          <ChevronLeft size={14} aria-hidden /> Directorios
        </Link>
      </nav>

      <header className="directory-create-head">
        <h1>Crear directorio</h1>
        <p className="muted-text">
          Define nombre y el flow de pasos por los que progresarán las oportunidades.
        </p>
      </header>

      <form
        className="directory-create-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (!canSubmit) return;
          setError(null);
          mutation.mutate();
        }}
      >
        <div className="directory-create-fields">
          <label className="directory-create-field">
            <span className="directory-create-field-label">Nombre</span>
            <input
              type="text"
              className="directory-create-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ej. Cardiólogos Tegucigalpa"
              maxLength={160}
              required
            />
          </label>
          <label className="directory-create-field">
            <span className="directory-create-field-label">
              Descripción <span className="directory-create-optional">(opcional)</span>
            </span>
            <textarea
              className="directory-create-input directory-create-textarea"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              maxLength={1000}
              placeholder="Para qué se usa este directorio"
            />
          </label>
        </div>

        <hr className="directory-create-divider" />

        <StepsEditor steps={steps} onChange={setSteps} />

        {error ? <p className="error-text">{error}</p> : null}

        <footer className="directory-create-actions">
          <Link to="/directories" className="link-button">
            Cancelar
          </Link>
          <Button type="submit" disabled={!canSubmit || mutation.isPending}>
            {mutation.isPending ? "Creando…" : "Crear directorio"}
          </Button>
        </footer>
      </form>
    </section>
  );
}
