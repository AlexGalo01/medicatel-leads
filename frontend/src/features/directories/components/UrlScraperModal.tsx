import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Select } from "../../../components/ui/select";
import { createUrlScrapeJob } from "../../../api";
import type { DirectoryStep } from "../../../types";

export interface UrlScraperModalProps {
  isOpen: boolean;
  onClose: () => void;
  directoryId: string;
  steps: DirectoryStep[];
  prefillUrl?: string;
  prefillTitle?: string;
  sourceId?: string;
  onComplete?: (created: number) => void;
}

export function UrlScraperModal({
  isOpen,
  onClose,
  directoryId,
  steps,
  prefillUrl,
  prefillTitle,
}: UrlScraperModalProps) {
  const navigate = useNavigate();
  const [url, setUrl] = useState(prefillUrl ?? "");
  const [prompt, setPrompt] = useState("");
  const [stepId, setStepId] = useState(steps[0]?.id ?? "");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (prefillUrl) setUrl(prefillUrl);
    if (prefillTitle) {
      setPrompt(`Extraer profesionales y entidades del directorio: ${prefillTitle}`);
    }
  }, [prefillUrl, prefillTitle]);

  useEffect(() => {
    if (steps.length > 0 && !stepId) {
      setStepId(steps[0].id);
    }
  }, [steps, stepId]);

  const handleStart = useCallback(async () => {
    if (!url.trim()) return;
    setError(null);
    setStarting(true);
    try {
      const job = await createUrlScrapeJob({
        target_url: url.trim(),
        user_prompt: prompt.trim() || `Extraer profesionales y entidades del directorio`,
        directory_id: directoryId,
      });
      onClose();
      const params = new URLSearchParams();
      if (stepId) params.set("stepId", stepId);
      navigate(`/url-scrape-jobs/${job.job_id}?${params.toString()}`);
    } catch (e) {
      setError(String(e));
      setStarting(false);
    }
  }, [url, prompt, directoryId, stepId, navigate, onClose]);

  if (!isOpen) return null;

  return (
    <div className="enrich-modal-overlay" onClick={() => { if (!starting) onClose(); }}>
      <div className="enrich-modal-panel" style={{ maxWidth: 560 }} onClick={(e) => e.stopPropagation()}>
        <div className="enrich-modal-header">
          <h3 className="enrich-modal-title">Scrapear URL</h3>
          {!starting && (
            <button type="button" className="enrich-modal-close" aria-label="Cerrar" onClick={onClose}>✕</button>
          )}
        </div>

        {error && <p style={{ padding: "0 1rem", color: "#E41E3F", fontSize: 14 }}>{error}</p>}

        <div style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <label style={{ fontSize: 13, fontWeight: 600, display: "block", marginBottom: 4 }}>URL</label>
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://ejemplo.com/directorio" />
          </div>
          <div>
            <label style={{ fontSize: 13, fontWeight: 600, display: "block", marginBottom: 4 }}>Prompt para extracción</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe qué extraer de esta página..."
              className="ui-input"
              style={{ width: "100%", minHeight: 60, resize: "vertical", padding: "8px 12px", fontSize: 14, borderRadius: 8, border: "1px solid var(--border-color, #CED0D4)" }}
            />
          </div>
          {steps.length > 0 && (
            <div>
              <label style={{ fontSize: 13, fontWeight: 600, display: "block", marginBottom: 4 }}>Step destino</label>
              <Select value={stepId} onChange={(e) => setStepId(e.target.value)}>
                {steps.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </Select>
            </div>
          )}
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <Button variant="outline" type="button" onClick={onClose} disabled={starting}>Cancelar</Button>
            <Button onClick={handleStart} disabled={!url.trim() || starting}>
              {starting ? <><Loader2 className="spin" size={14} /> Iniciando…</> : "Iniciar scrapeo"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
