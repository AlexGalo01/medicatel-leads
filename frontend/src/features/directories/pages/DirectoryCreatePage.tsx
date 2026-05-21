import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, FolderPlus } from "lucide-react";

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

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 6,
};

const labelTextStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 500,
  color: "#0A0A0A",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 14px",
  border: "1px solid var(--color-border)",
  borderRadius: 8,
  fontSize: 14,
  color: "#0A0A0A",
  background: "var(--c-card-bg)",
  outline: "none",
  transition: "border-color 0.15s",
  boxSizing: "border-box",
};

export function DirectoryCreatePage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get("returnTo");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [steps, setSteps] = useState<EditableStep[]>(DEFAULT_STEPS);
  const [error, setError] = useState<string | null>(null);
  const [nameFocused, setNameFocused] = useState(false);
  const [descFocused, setDescFocused] = useState(false);

  const mutation = useMutation({
    mutationFn: () =>
      createDirectory({
        name: name.trim(),
        description: description.trim() || null,
        steps: steps.map((s) => ({
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
        navigate(`/lists/${dir.id}`);
      }
    },
    onError: (e: Error) => setError(e.message),
  });

  const hasEmptyStepName = steps.some((s) => s.name.trim().length === 0);
  const canSubmit =
    name.trim().length > 0 &&
    steps.length > 0 &&
    !hasEmptyStepName;

  return (
    <section className="dir-create-v2">
      {/* Header */}
      <div className="dir-create-v2-header">
        <Link
          to="/lists"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            color: "#6B6B6B",
            textDecoration: "none",
            fontSize: 14,
            fontWeight: 500,
            padding: "6px 10px",
            borderRadius: 8,
            border: "1px solid var(--color-border)",
            background: "var(--c-card-bg)",
            transition: "color 0.15s, border-color 0.15s",
          }}
        >
          <ArrowLeft size={15} />
          Listas
        </Link>
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: "#EEF2FF",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <FolderPlus size={16} color="#6366F1" />
          </div>
          <span style={{ fontSize: 15, fontWeight: 600, color: "#0A0A0A" }}>
            Nuevo lista
          </span>
        </div>
      </div>

      {/* Body */}
      <div className="dir-create-v2-body">
        <form
          className="dir-create-v2-card"
          onSubmit={(e) => {
            e.preventDefault();
            if (!canSubmit) return;
            setError(null);
            mutation.mutate();
          }}
        >
          {/* Title section */}
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#0A0A0A" }}>
              Configurar lista
            </h2>
            <p style={{ margin: 0, fontSize: 14, color: "#6B6B6B" }}>
              Define nombre y el flujo de pasos por los que progresarán las oportunidades.
            </p>
          </div>

          <hr style={{ border: "none", borderTop: "1px solid #F0F0F4", margin: 0 }} />

          {/* Fields */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <label style={labelStyle}>
              <span style={labelTextStyle}>Nombre del lista</span>
              <input
                type="text"
                style={{
                  ...inputStyle,
                  borderColor: nameFocused ? "#6366F1" : "#E8E8EC",
                  boxShadow: nameFocused ? "0 0 0 3px rgba(99,102,241,0.1)" : "none",
                }}
                value={name}
                onChange={(e) => setName(e.target.value)}
                onFocus={() => setNameFocused(true)}
                onBlur={() => setNameFocused(false)}
                placeholder="Ej. Cardiólogos Tegucigalpa"
                maxLength={160}
                required
              />
            </label>
            <label style={labelStyle}>
              <span style={labelTextStyle}>
                Descripción{" "}
                <span style={{ fontWeight: 400, color: "#9B9BA8", fontSize: 12 }}>(opcional)</span>
              </span>
              <textarea
                style={{
                  ...inputStyle,
                  resize: "vertical",
                  minHeight: 72,
                  borderColor: descFocused ? "#6366F1" : "#E8E8EC",
                  boxShadow: descFocused ? "0 0 0 3px rgba(99,102,241,0.1)" : "none",
                }}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                onFocus={() => setDescFocused(true)}
                onBlur={() => setDescFocused(false)}
                rows={2}
                maxLength={1000}
                placeholder="Para qué se usa este lista"
              />
            </label>
          </div>

          <hr style={{ border: "none", borderTop: "1px solid #F0F0F4", margin: 0 }} />

          {/* Steps editor */}
          <StepsEditor steps={steps} onChange={setSteps} />

          {/* Validation messages */}
          {steps.length === 0 && (
            <p style={{ margin: 0, fontSize: 13, color: "#EF4444" }}>
              Agrega al menos un paso al flujo.
            </p>
          )}
          {hasEmptyStepName && (
            <p style={{ margin: 0, fontSize: 13, color: "#EF4444" }}>
              Todos los pasos deben tener un nombre.
            </p>
          )}
          {error && (
            <p style={{ margin: 0, fontSize: 13, color: "#EF4444" }}>{error}</p>
          )}

          {/* Footer actions */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, paddingTop: 8 }}>
            <Link
              to="/lists"
              style={{
                fontSize: 14,
                fontWeight: 500,
                color: "#6B6B6B",
                textDecoration: "none",
                padding: "8px 16px",
                borderRadius: 8,
                border: "1px solid var(--color-border)",
                background: "var(--c-card-bg)",
              }}
            >
              Cancelar
            </Link>
            <Button
              type="submit"
              className="cta-button"
              disabled={!canSubmit || mutation.isPending}
              style={{ padding: "8px 20px", fontSize: 14 }}
            >
              {mutation.isPending ? "Creando…" : "Crear lista"}
            </Button>
          </div>
        </form>
      </div>
    </section>
  );
}
