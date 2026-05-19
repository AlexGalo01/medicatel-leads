import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "./ui/button";

function hostLabel(url: string): string {
  try {
    const u = new URL(url.startsWith("http") ? url : `https://${url}`);
    return u.hostname.replace(/^www\./, "");
  } catch {
    return url.slice(0, 32);
  }
}

function absoluteUrl(url: string): string {
  if (!url) return url;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return `https://${url}`;
}

function SourceBadge({ src }: { src: string }) {
  if (!src) return null;
  if (src === "brave_local") {
    return <span className="enrich-modal-contact-source">Google Maps</span>;
  }
  return (
    <a href={absoluteUrl(src)} target="_blank" rel="noreferrer" className="enrich-modal-contact-source enrich-modal-contact-source--link">
      {hostLabel(src)}
    </a>
  );
}

export const ENRICH_STAGES = [
  "Buscando información del perfil en la web...",
  "Visitando páginas personales y redes sociales...",
  "Consultando datos locales y redes sociales...",
  "Verificando datos con inteligencia artificial...",
];

export interface EnrichContactModalProps {
  isOpen: boolean;
  onClose: () => void;
  isPending: boolean;
  isError: boolean;
  stageIdx: number;
  data: any | null; // the OpportunityEnrichResult
  onSave: (selectedData: { email?: string; phone?: string; whatsapp?: string; source_urls?: string[] }) => void;
  isSaving: boolean;
  saveError: boolean;
}

export function EnrichContactModal({
  isOpen,
  onClose,
  isPending,
  isError,
  stageIdx,
  data,
  onSave,
  isSaving,
  saveError,
}: EnrichContactModalProps) {
  const [checkedFields, setCheckedFields] = useState<Record<string, boolean>>({});
  const [checkedSources, setCheckedSources] = useState<Record<string, boolean>>({});

  if (!isOpen) return null;

  return (
    <div
      className="enrich-modal-overlay"
      onClick={() => {
        if (!isPending) onClose();
      }}
    >
      <div className="enrich-modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="enrich-modal-header">
          <h3 className="enrich-modal-title">Búsqueda de contactos</h3>
          {!isPending && (
            <button
              type="button"
              className="enrich-modal-close"
              aria-label="Cerrar"
              onClick={onClose}
            >
              ✕
            </button>
          )}
        </div>

        {isPending && (
          <div className="enrich-modal-loading">
            <ul className="enrich-modal-steps">
              {ENRICH_STAGES.map((stage, i) => (
                <li
                  key={i}
                  className={`enrich-modal-step-item${i < stageIdx ? " is-done" : i === stageIdx ? " is-active" : " is-pending"}`}
                >
                  <span className="enrich-modal-step-icon" aria-hidden>
                    {i < stageIdx ? "✓" : i === stageIdx ? <Loader2 className="spin" size={13} /> : "○"}
                  </span>
                  <span className="enrich-modal-step-text">{stage}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {isError && (
          <p className="error-text" style={{ padding: "1rem" }}>
            Error al buscar. Intenta de nuevo.
          </p>
        )}

        {!isPending && !isError && data && (() => {
          const r = data;
          const contactSources: Record<string, string> = r.contact_sources ?? {};

          const contactFields = [
            { key: "email", label: "Email", value: r.email },
            { key: "phone", label: "Teléfono", value: r.phone },
            { key: "whatsapp", label: "WhatsApp", value: r.whatsapp },
          ].filter((x) => x.value?.trim());

          // Campos informativos de Google Maps (ya persistidos, solo se muestran)
          const infoFields = [
            { key: "website", label: "Página web", value: r.website },
            { key: "address", label: "Dirección", value: r.address },
          ].filter((x) => x.value?.trim() && contactSources[x.key] === "brave_local");

          const sourceItems = r.citations
            .filter((c: { url?: string; source?: string }) => c.url?.trim())
            .map((c: { url?: string; source?: string }) => ({ ...c, url: c.url! }));

          if (contactFields.length > 0 && Object.keys(checkedFields).length === 0) {
            const initial: Record<string, boolean> = {};
            for (const f of contactFields) initial[f.key] = true;
            setCheckedFields(initial);
          }

          if (sourceItems.length > 0 && Object.keys(checkedSources).length === 0) {
            const initSrc: Record<string, boolean> = {};
            for (const c of sourceItems) initSrc[c.url] = false;
            setCheckedSources(initSrc);
          }

          const selectedContactData = Object.fromEntries(
            contactFields
              .filter((f) => checkedFields[f.key])
              .map((f) => [f.key, f.value]),
          ) as Record<string, string>;

          const selectedSourceUrls = sourceItems
            .filter((c: { url: string }) => checkedSources[c.url])
            .map((c: { url: string }) => c.url)
            .filter((url: string): url is string => Boolean(url));

          const selectedData: { email?: string; phone?: string; whatsapp?: string; source_urls?: string[] } = {
            email: selectedContactData.email,
            phone: selectedContactData.phone,
            whatsapp: selectedContactData.whatsapp,
            source_urls: selectedSourceUrls.length ? selectedSourceUrls : undefined,
          };

          const hasAnything = contactFields.length > 0 || infoFields.length > 0;

          return (
            <div className="enrich-modal-results">
              {!hasAnything ? (
                <p className="muted-text" style={{ padding: "0.5rem 0" }}>
                  No se encontró información de contacto verificada.
                </p>
              ) : (
                <>
                  {contactFields.length > 0 && (
                    <>
                      <p className="enrich-modal-summary">
                        {contactFields.length} dato{contactFields.length !== 1 ? "s" : ""} encontrado{contactFields.length !== 1 ? "s" : ""}
                      </p>
                      <ul className="enrich-modal-contact-list">
                        {contactFields.map((item) => (
                          <li key={item.key} className="enrich-modal-contact-row">
                            <label className="enrich-modal-contact-check">
                              <input
                                type="checkbox"
                                checked={checkedFields[item.key] ?? true}
                                onChange={(e) =>
                                  setCheckedFields((prev) => ({ ...prev, [item.key]: e.target.checked }))
                                }
                              />
                              <span className="enrich-modal-contact-label">{item.label}</span>
                            </label>
                            <div className="enrich-modal-contact-value-col">
                              <span className="enrich-modal-contact-value">{item.value}</span>
                              {contactSources[item.key] && (
                                <SourceBadge src={contactSources[item.key]} />
                              )}
                            </div>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}

                  {infoFields.length > 0 && (
                    <div className="enrich-modal-info-section">
                      <p className="enrich-modal-sources-title">Desde Google Maps</p>
                      <ul className="enrich-modal-info-list">
                        {infoFields.map((item) => (
                          <li key={item.key} className="enrich-modal-info-row">
                            <span className="enrich-modal-info-label">{item.label}</span>
                            {item.key === "website" ? (
                              <a href={absoluteUrl(item.value)} target="_blank" rel="noreferrer" className="enrich-modal-info-value link">
                                {hostLabel(item.value)}
                              </a>
                            ) : (
                              <span className="enrich-modal-info-value">{item.value}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {sourceItems.length > 0 && (
                    <div className="enrich-modal-sources-section">
                      <p className="enrich-modal-sources-title">Fuentes consultadas</p>
                      <ul className="enrich-modal-sources-list">
                        {sourceItems.slice(0, 5).map((c: { url: string; source?: string }) => (
                          <li key={c.url} className="enrich-modal-source-row">
                            <label className="enrich-modal-source-check">
                              <input
                                type="checkbox"
                                checked={checkedSources[c.url] ?? false}
                                onChange={(e) =>
                                  setCheckedSources((prev) => ({ ...prev, [c.url]: e.target.checked }))
                                }
                              />
                            </label>
                            <a href={absoluteUrl(c.url)} target="_blank" rel="noreferrer" className="enrich-modal-source-link">
                              {hostLabel(c.url)}
                            </a>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {contactFields.length > 0 && (
                    <div style={{ display: "flex", gap: "0.75rem", marginTop: "1rem" }}>
                      <Button
                        type="button"
                        className="cta-button"
                        style={{ flex: 1 }}
                        disabled={Object.keys(selectedData).length === 0 || isSaving}
                        onClick={() => onSave(selectedData)}
                      >
                        {isSaving ? "Guardando..." : "Guardar Datos"}
                      </Button>
                      <Button
                        type="button"
                        className="link-button"
                        onClick={onClose}
                      >
                        Cancelar
                      </Button>
                    </div>
                  )}
                  {contactFields.length === 0 && infoFields.length > 0 && (
                    <div style={{ marginTop: "1rem" }}>
                      <Button type="button" className="link-button" onClick={onClose}>
                        Cerrar
                      </Button>
                    </div>
                  )}
                  {saveError && (
                    <p className="error-text" style={{ marginTop: "0.5rem" }}>
                      Error al guardar. Intenta de nuevo.
                    </p>
                  )}
                </>
              )}
            </div>
          );
        })()}
      </div>
    </div>
  );
}
