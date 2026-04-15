import { FormEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { createSearchJob } from "../api";

export function SearchPage(): JSX.Element {
  const navigate = useNavigate();
  const [specialty, setSpecialty] = useState("Cardiología");
  const [country, setCountry] = useState("Honduras");
  const [city, setCity] = useState("Tegucigalpa");
  const [notes, setNotes] = useState("");

  const createJobMutation = useMutation({
    mutationFn: createSearchJob,
    onSuccess: (data) => navigate(`/jobs/${data.job_id}`),
  });

  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    createJobMutation.mutate({
      specialty,
      country,
      city,
      notes,
      contact_channels: ["email", "whatsapp", "linkedin"],
    });
  };

  return (
    <section className="panel">
      <h2>Crear nueva búsqueda</h2>
      <p className="muted-text">Define especialidad y ubicación para iniciar el pipeline real.</p>
      <form className="form-grid" onSubmit={onSubmit}>
        <label>
          Especialidad
          <input value={specialty} onChange={(event) => setSpecialty(event.target.value)} required />
        </label>
        <label>
          País
          <input value={country} onChange={(event) => setCountry(event.target.value)} required />
        </label>
        <label>
          Ciudad
          <input value={city} onChange={(event) => setCity(event.target.value)} required />
        </label>
        <label>
          Notas
          <textarea
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder="Contexto adicional de la prospección"
          />
        </label>
        <button className="cta-button" type="submit" disabled={createJobMutation.isPending}>
          {createJobMutation.isPending ? "Creando búsqueda..." : "Crear búsqueda"}
        </button>
      </form>
      {createJobMutation.isError ? (
        <p className="error-text">No se pudo crear el job. Revisa que el backend esté activo.</p>
      ) : null}
    </section>
  );
}

