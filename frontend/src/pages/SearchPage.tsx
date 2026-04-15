import { FormEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { createSearchJob } from "../api";

const quickPrompts: string[] = [
  "Doctores de Honduras con WhatsApp y email",
  "Clínicas privadas en Tegucigalpa con presencia digital",
  "Distribuidores de equipo médico en Centroamérica",
  "Hospitales con área de ginecología y obstetricia",
];

export function SearchPage(): JSX.Element {
  const navigate = useNavigate();
  const [query, setQuery] = useState("Doctores de Honduras con email, whatsapp y linkedin");
  const [notes, setNotes] = useState("");

  const createJobMutation = useMutation({
    mutationFn: createSearchJob,
    onSuccess: (data) => navigate(`/jobs/${data.job_id}`),
  });

  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    createJobMutation.mutate({
      query,
      notes,
      contact_channels: ["email", "whatsapp", "linkedin"],
    });
  };

  return (
    <section className="search-hero">
      <div className="search-hero-card">
        <p className="hero-kicker">Lead intelligence</p>
        <h2>Encuentra leads de alta calidad con WebSets</h2>
        <p className="muted-text">
          Escribe cualquier búsqueda en lenguaje natural. El motor ejecuta pipeline real: WebSets,
          scoring y exportación.
        </p>

        <form className="hero-search-form" onSubmit={onSubmit}>
          <input
            className="hero-search-input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ej: clínicas privadas en Honduras con contacto directo"
            required
          />
          <button className="cta-button" type="submit" disabled={createJobMutation.isPending}>
            {createJobMutation.isPending ? "Ejecutando..." : "Buscar"}
          </button>
        </form>

        <div className="quick-prompts">
          {quickPrompts.map((promptItem) => (
            <button
              key={promptItem}
              type="button"
              className="prompt-chip"
              onClick={() => setQuery(promptItem)}
            >
              {promptItem}
            </button>
          ))}
        </div>

        <label className="notes-label">
          Contexto opcional
          <textarea
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder="Notas para orientar mejor el pipeline"
          />
        </label>

        {createJobMutation.isError ? (
          <p className="error-text">No se pudo crear el job. Revisa que el backend esté activo.</p>
        ) : null}
      </div>
    </section>
  );
}

