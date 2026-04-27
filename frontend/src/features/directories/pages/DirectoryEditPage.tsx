import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";

import {
  addDirectoryStep,
  deleteDirectoryStep,
  getDirectory,
  reorderDirectorySteps,
  updateDirectory,
  updateDirectoryStep,
} from "../../../api";
import { Button } from "../../../components/ui/button";
import { StepsEditor, type EditableStep } from "../components/StepsEditor";

export function DirectoryEditPage(): JSX.Element {
  const { directoryId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["directory", directoryId],
    queryFn: () => getDirectory(directoryId),
    enabled: Boolean(directoryId),
  });

  const data = query.data;

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [steps, setSteps] = useState<EditableStep[]>([]);
  const [originalSteps, setOriginalSteps] = useState<EditableStep[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    setName(data.name);
    setDescription(data.description ?? "");
    const editable: EditableStep[] = data.steps.map((s) => ({
      key: s.id,
      id: s.id,
      name: s.name,
      is_terminal: s.is_terminal,
      is_won: s.is_won,
    }));
    setSteps(editable);
    setOriginalSteps(editable);
  }, [data]);

  const handleSave = async () => {
    if (!data || !name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await updateDirectory(directoryId, {
        name: name.trim(),
        description: description.trim() || null,
      });

      // Eliminar steps que el usuario quitó
      const removedIds = originalSteps
        .filter((os) => os.id && !steps.find((s) => s.id === os.id))
        .map((os) => os.id!);
      for (const id of removedIds) {
        await deleteDirectoryStep(directoryId, id);
      }

      // Agregar steps nuevos y actualizar existentes; construir lista final de IDs en orden
      const finalIds: string[] = [];
      for (const step of steps) {
        if (!step.id) {
          const created = await addDirectoryStep(directoryId, {
            name: step.name.trim(),
            is_terminal: step.is_terminal,
            is_won: step.is_won,
          });
          finalIds.push(created.id);
        } else {
          const orig = originalSteps.find((os) => os.id === step.id);
          if (
            !orig ||
            orig.name !== step.name ||
            orig.is_terminal !== step.is_terminal ||
            orig.is_won !== step.is_won
          ) {
            await updateDirectoryStep(directoryId, step.id, {
              name: step.name.trim(),
              is_terminal: step.is_terminal,
              is_won: step.is_won,
            });
          }
          finalIds.push(step.id);
        }
      }

      // Aplicar orden final
      if (finalIds.length > 0) {
        await reorderDirectorySteps(directoryId, finalIds);
      }

      await queryClient.invalidateQueries({ queryKey: ["directory", directoryId] });
      await queryClient.invalidateQueries({ queryKey: ["directories"] });
      navigate(`/directories/${directoryId}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error al guardar");
      setSaving(false);
    }
  };

  if (query.isLoading) {
    return <section className="panel muted-text">Cargando directorio…</section>;
  }

  if (query.isError || !data) {
    return (
      <section className="panel error-text">
        No se encontró el directorio.{" "}
        <Link to="/directories" className="link-button">
          Volver
        </Link>
      </section>
    );
  }

  const canSave = name.trim().length > 0 && steps.some((s) => s.name.trim().length > 0) && !saving;

  return (
    <section className="directory-create-page">
      <nav className="directory-create-nav" aria-label="Navegación">
        <Link to={`/directories/${directoryId}`} className="link-button">
          <ChevronLeft size={14} aria-hidden /> {data.name}
        </Link>
      </nav>

      <header className="directory-create-head">
        <h1>Editar directorio</h1>
        <p className="muted-text">Modifica nombre, descripción y el flow de pasos.</p>
      </header>

      <form
        className="directory-create-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (!canSave) return;
          void handleSave();
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
            />
          </label>
        </div>

        <hr className="directory-create-divider" />

        <StepsEditor steps={steps} onChange={setSteps} />

        {error ? <p className="error-text">{error}</p> : null}

        <footer className="directory-create-actions">
          <Link to={`/directories/${directoryId}`} className="link-button">
            Cancelar
          </Link>
          <Button type="submit" disabled={!canSave}>
            {saving ? "Guardando…" : "Guardar cambios"}
          </Button>
        </footer>
      </form>
    </section>
  );
}
