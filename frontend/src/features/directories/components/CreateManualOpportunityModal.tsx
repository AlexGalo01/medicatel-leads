import { useState, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { createManualOpportunity, listDirectories } from "../../../api";
import type { DirectoryStep } from "../../../types";

interface Props {
  /** Pre-selected directory. If omitted the modal shows a directory picker. */
  directoryId?: string;
  /** Steps for the pre-selected directory. Ignored when directoryId is omitted. */
  steps?: DirectoryStep[];
  onClose: () => void;
}

export function CreateManualOpportunityModal({ directoryId: fixedDirectoryId, steps: fixedSteps, onClose }: Props) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [city, setCity] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [stepId, setStepId] = useState("");
  const [selectedDirectoryId, setSelectedDirectoryId] = useState(fixedDirectoryId ?? "");

  // Only fetch directories when no fixed directory was provided
  const directoriesQuery = useQuery({
    queryKey: ["directories"],
    queryFn: () => listDirectories(),
    enabled: !fixedDirectoryId,
  });

  const effectiveDirectoryId = fixedDirectoryId ?? selectedDirectoryId;

  const effectiveSteps: DirectoryStep[] = useMemo(() => {
    if (fixedSteps) return fixedSteps;
    if (!effectiveDirectoryId || !directoriesQuery.data) return [];
    const dir = directoriesQuery.data.items.find((d) => d.id === effectiveDirectoryId);
    return dir?.steps ?? [];
  }, [fixedSteps, effectiveDirectoryId, directoriesQuery.data]);

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
        title: title.trim(),
        source_url: sourceUrl.trim() || undefined,
        specialty: specialty.trim() || undefined,
        city: city.trim() || undefined,
        directory_id: effectiveDirectoryId || undefined,
        step_id: targetStepId || undefined,
        contacts: contacts.length > 0 ? contacts : undefined,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["opportunities"] });
      if (effectiveDirectoryId) {
        void queryClient.invalidateQueries({ queryKey: ["directory-items", effectiveDirectoryId] });
      }
      onClose();
    },
  });

  return (
    <div className="manual-opp-modal-overlay" onClick={onClose}>
      <div className="manual-opp-modal" onClick={(e) => e.stopPropagation()}>
        <header className="manual-opp-modal-header">
          <h3>Nueva oportunidad manual</h3>
          <button type="button" className="manual-opp-modal-close" onClick={onClose} aria-label="Cerrar">
            <X size={18} />
          </button>
        </header>

        <div className="manual-opp-modal-content">
          <div className="manual-opp-form-group">
            <label>Título / Nombre *</label>
            <input
              className="ui-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ej. Dr. Juan Pérez"
              autoFocus
            />
          </div>

          <div className="manual-opp-form-group">
            <label>Enlace / URL (opcional)</label>
            <input
              className="ui-input"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://..."
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <div className="manual-opp-form-group">
              <label>Especialidad / Rol</label>
              <input
                className="ui-input"
                value={specialty}
                onChange={(e) => setSpecialty(e.target.value)}
                placeholder="Ej. Cardiólogo"
              />
            </div>
            <div className="manual-opp-form-group">
              <label>Ciudad</label>
              <input
                className="ui-input"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Ej. Tegucigalpa"
              />
            </div>
          </div>

          <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "8px 0" }} />
          <h4 style={{ margin: 0, fontSize: "14px", fontWeight: 600 }}>Información de Contacto</h4>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <div className="manual-opp-form-group">
              <label>Correo Electrónico</label>
              <input
                type="email"
                className="ui-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="correo@ejemplo.com"
              />
            </div>
            <div className="manual-opp-form-group">
              <label>Teléfono</label>
              <input
                type="tel"
                className="ui-input"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+504 9999-9999"
              />
            </div>
            <div className="manual-opp-form-group">
              <label>WhatsApp</label>
              <input
                type="tel"
                className="ui-input"
                value={whatsapp}
                onChange={(e) => setWhatsapp(e.target.value)}
                placeholder="+504 9999-9999"
              />
            </div>
            <div className="manual-opp-form-group">
              <label>LinkedIn</label>
              <input
                className="ui-input"
                value={linkedin}
                onChange={(e) => setLinkedin(e.target.value)}
                placeholder="https://linkedin.com/in/..."
              />
            </div>
          </div>

          <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "8px 0" }} />

          {/* Directory picker (only shown when no fixed directory) */}
          {!fixedDirectoryId && (
            <div className="manual-opp-form-group">
              <label>Directorio</label>
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
            </div>
          )}

          {effectiveSteps.length > 0 && (
            <div className="manual-opp-form-group">
              <label>Fase Inicial</label>
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
            </div>
          )}

          {createMutation.isError ? (
            <p className="error-text">{(createMutation.error as Error).message}</p>
          ) : null}
        </div>

        <footer className="manual-opp-modal-footer">
          <Button variant="ghost" onClick={onClose} disabled={createMutation.isPending}>
            Cancelar
          </Button>
          <Button
            onClick={() => createMutation.mutate()}
            disabled={!title.trim() || createMutation.isPending}
          >
            {createMutation.isPending ? "Guardando..." : "Crear oportunidad"}
          </Button>
        </footer>
      </div>
    </div>
  );
}
