import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ChevronLeft, Loader2 } from "lucide-react";

import { createManualOpportunity } from "../../../api";
import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";

export function OpportunityCreatePage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [city, setCity] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const createMut = useMutation({
    mutationFn: createManualOpportunity,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["opportunities"] });
      navigate("/opportunities", { replace: true });
    },
    onError: (e: Error) => setErr(e.message),
  });

  return (
    <div className="opportunity-create-page">
      <nav className="admin-page-nav">
        <Link to="/opportunities" className="link-button">
          <ChevronLeft size={14} aria-hidden />
          Volver a oportunidades
        </Link>
      </nav>

      <Card className="panel admin-section-card">
        <h1 className="admin-page-title">Nueva oportunidad</h1>
        <p className="muted-text" style={{ margin: "0.25rem 0 1.5rem" }}>
          Crea una oportunidad manualmente sin necesidad de una búsqueda.
        </p>

        <form
          className="opportunity-create-form"
          onSubmit={(e) => {
            e.preventDefault();
            setErr(null);
            createMut.mutate({
              title,
              specialty,
              city,
              source_url: sourceUrl,
            });
          }}
        >
          <label className="admin-field">
            <span className="admin-field-label">Título / Nombre *</span>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ej. Clínica San José, Dr. Pérez, Hospital del Valle…"
              required
            />
          </label>

          <div className="admin-form-row">
            <label className="admin-field">
              <span className="admin-field-label">Especialidad / Tipo</span>
              <Input
                value={specialty}
                onChange={(e) => setSpecialty(e.target.value)}
                placeholder="Ej. Cardiología, Clínica privada…"
              />
            </label>
            <label className="admin-field">
              <span className="admin-field-label">Ciudad</span>
              <Input
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Ej. Tegucigalpa, San Pedro Sula…"
              />
            </label>
          </div>

          <label className="admin-field">
            <span className="admin-field-label">URL fuente (opcional)</span>
            <Input
              type="url"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://…"
            />
          </label>

          {err && <p className="error-text">{err}</p>}

          <div style={{ display: "flex", gap: "0.75rem", marginTop: "0.5rem" }}>
            <Button type="submit" className="cta-button" disabled={createMut.isPending}>
              {createMut.isPending ? <Loader2 className="spin" size={14} aria-hidden /> : null}
              Crear oportunidad
            </Button>
            <Link to="/opportunities" className="link-button" style={{ alignSelf: "center" }}>
              Cancelar
            </Link>
          </div>
        </form>
      </Card>
    </div>
  );
}
