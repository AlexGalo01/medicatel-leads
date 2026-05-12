import { useState, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import { createManualOpportunity, listDirectories } from "../../../api";
import type { DirectoryStep } from "../../../types";

export function OpportunityCreatePage(): JSX.Element {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const urlDirectoryId = searchParams.get("directory_id") || "";

  const [title, setTitle] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [city, setCity] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [stepId, setStepId] = useState("");
  const [selectedDirectoryId, setSelectedDirectoryId] = useState(urlDirectoryId);

  const directoriesQuery = useQuery({
    queryKey: ["directories"],
    queryFn: () => listDirectories(),
  });

  const effectiveSteps: DirectoryStep[] = useMemo(() => {
    if (!selectedDirectoryId || !directoriesQuery.data) return [];
    const dir = directoriesQuery.data.items.find((d) => d.id === selectedDirectoryId);
    return dir?.steps ?? [];
  }, [selectedDirectoryId, directoriesQuery.data]);

  const createMutation = useMutation({
    mutationFn: async () => {
      const contacts: { kind: string; value: string; is_primary: boolean }[] = [];
      if (email.trim()) contacts.push({ kind: "email", value: email.trim(), is_primary: contacts.length === 0 });
      if (phone.trim()) contacts.push({ kind: "phone", value: phone.trim(), is_primary: contacts.length === 0 });
      if (whatsapp.trim()) contacts.push({ kind: "whatsapp", value: whatsapp.trim(), is_primary: contacts.length === 0 });
      if (linkedin.trim()) contacts.push({ kind: "linkedin", value: linkedin.trim(), is_primary: contacts.length === 0 });

      const defaultStep = effectiveSteps.find(s => !s.is_terminal);
      const targetStepId = stepId || defaultStep?.id;

      return createManualOpportunity({
        title: title.trim() || "Oportunidad manual",
        source_url: sourceUrl.trim() || undefined,
        specialty: specialty.trim() || undefined,
        city: city.trim() || undefined,
        directory_id: selectedDirectoryId || undefined,
        step_id: targetStepId || undefined,
        contacts: contacts.length > 0 ? contacts : undefined,
      });
    },
    onSuccess: (newOpp) => {
      void queryClient.invalidateQueries({ queryKey: ["opportunities"] });
      if (selectedDirectoryId) {
        void queryClient.invalidateQueries({ queryKey: ["directory-items", selectedDirectoryId] });
      }
      navigate(`/opportunities/${newOpp.opportunity_id}`);
    },
  });

  return (
    <div className="opportunity-create-page">
      <nav className="admin-page-nav">
        <Button variant="ghost" onClick={() => navigate(-1)} aria-label="Volver" className="link-button">
          <ChevronLeft size={14} aria-hidden />
          Volver
        </Button>
      </nav>

      <Card className="panel admin-section-card">
        <h1 className="admin-page-title">Nueva oportunidad</h1>
        <p className="muted-text" style={{ margin: "0.25rem 0 1.5rem" }}>
          Crea una oportunidad manualmente sin necesidad de una búsqueda. Todos los campos son opcionales.
        </p>

        <form
          className="opportunity-create-form"
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate();
          }}
          style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}
        >
          <label className="admin-field">
            <span className="admin-field-label">Título / Nombre</span>
            <input
              className="ui-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ej. Clínica San José, Dr. Pérez…"
              autoFocus
            />
          </label>

          <label className="admin-field">
            <span className="admin-field-label">Enlace / URL</span>
            <input
              className="ui-input"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://..."
            />
          </label>

          <div className="admin-form-row">
            <label className="admin-field">
              <span className="admin-field-label">Especialidad / Tipo</span>
              <input
                className="ui-input"
                value={specialty}
                onChange={(e) => setSpecialty(e.target.value)}
                placeholder="Ej. Cardiología, Clínica privada…"
              />
            </label>
            <label className="admin-field">
              <span className="admin-field-label">Ciudad</span>
              <input
                className="ui-input"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Ej. Tegucigalpa, San Pedro Sula…"
              />
            </label>
          </div>

          <hr style={{ border: "none", borderTop: "1px solid var(--color-border)", margin: "0.5rem 0" }} />
          <h3 style={{ margin: 0, fontSize: "1.1rem" }}>Información de Contacto</h3>

          <div className="admin-form-row">
            <label className="admin-field">
              <span className="admin-field-label">Correo Electrónico</span>
              <input
                type="email"
                className="ui-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="correo@ejemplo.com"
              />
            </label>
            <label className="admin-field">
              <span className="admin-field-label">Teléfono</span>
              <input
                type="tel"
                className="ui-input"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+504 9999-9999"
              />
            </label>
          </div>
          <div className="admin-form-row">
            <label className="admin-field">
              <span className="admin-field-label">WhatsApp</span>
              <input
                type="tel"
                className="ui-input"
                value={whatsapp}
                onChange={(e) => setWhatsapp(e.target.value)}
                placeholder="+504 9999-9999"
              />
            </label>
            <label className="admin-field">
              <span className="admin-field-label">LinkedIn</span>
              <input
                className="ui-input"
                value={linkedin}
                onChange={(e) => setLinkedin(e.target.value)}
                placeholder="https://linkedin.com/in/..."
              />
            </label>
          </div>

          <hr style={{ border: "none", borderTop: "1px solid var(--color-border)", margin: "0.5rem 0" }} />
          <h3 style={{ margin: 0, fontSize: "1.1rem" }}>Directorio y Fase Inicial</h3>

          <div className="admin-form-row">
            <label className="admin-field">
              <span className="admin-field-label">Directorio</span>
              <select
                className="ui-input"
                value={selectedDirectoryId}
                onChange={(e) => {
                  setSelectedDirectoryId(e.target.value);
                  setStepId("");
                }}
              >
                <option value="">Sin directorio</option>
                {(directoriesQuery.data?.items ?? []).map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            </label>

            {effectiveSteps.length > 0 ? (
              <label className="admin-field">
                <span className="admin-field-label">Fase Inicial</span>
                <select
                  className="ui-input"
                  value={stepId}
                  onChange={(e) => setStepId(e.target.value)}
                >
                  <option value="">Fase por defecto (Primera fase)</option>
                  {effectiveSteps.filter(s => !s.is_terminal).map(step => (
                    <option key={step.id} value={step.id}>{step.name}</option>
                  ))}
                </select>
              </label>
            ) : <div />}
          </div>

          {createMutation.isError ? (
            <p className="error-text">{(createMutation.error as Error).message}</p>
          ) : null}

          <div style={{ display: "flex", gap: "0.75rem", marginTop: "1rem" }}>
            <Button
              type="submit"
              className="cta-button"
              disabled={createMutation.isPending}
            >
              {createMutation.isPending ? "Creando..." : "Crear oportunidad"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
              Cancelar
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
