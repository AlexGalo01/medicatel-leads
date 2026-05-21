import { useState, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  Trash2,
  Plus,
  ExternalLink,
  Loader2,
  Edit2,
  Check,
  X,
} from "lucide-react";

import {
  listScrapingSites,
  createScrapingSite,
  updateScrapingSite,
  deleteScrapingSite,
  scrapeScrapingSite,
} from "../api";
import { Button } from "../components/ui/button";
import type {
  ScrapingSite,
  ScrapingSiteCreateRequest,
} from "../types";

// ─── Helpers ──────────────────────────────────────────────────────────────

function hostLabel(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url.slice(0, 30); }
}

function formatRecent(iso: string): string {
  const d = new Date(iso);
  const ts = d.getTime();
  if (Number.isNaN(ts)) return iso;
  const diffMin = Math.max(1, Math.floor((Date.now() - ts) / 60000));
  if (diffMin < 60) return `hace ${diffMin} min`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `hace ${diffH} h`;
  const diffD = Math.floor(diffH / 24);
  return `hace ${diffD} día${diffD > 1 ? "s" : ""}`;
}

// ─── Delete Confirmation Modal ────────────────────────────────────────────

function DeleteConfirmModal({
  isOpen,
  siteTitle,
  onConfirm,
  onCancel,
  isLoading,
}: {
  isOpen: boolean;
  siteTitle: string;
  onConfirm: () => void;
  onCancel: () => void;
  isLoading: boolean;
}): JSX.Element {
  if (!isOpen) return <></>;

  return (
    <div style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
      background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 1000, padding: 20,
    }}>
      <div style={{
        background: "var(--c-card-bg)", borderRadius: 12, padding: "24px", maxWidth: 400, width: "100%",
        boxShadow: "0 20px 25px -5px rgba(0,0,0,0.1)",
      }}>
        <h2 style={{ margin: "0 0 12px", fontSize: 18, fontWeight: 700, color: "#0F172A" }}>
          ¿Eliminar fuente?
        </h2>
        <p style={{ margin: "0 0 20px", fontSize: 14, color: "var(--color-text-secondary)" }}>
          ¿Estás seguro de que deseas eliminar <strong>{siteTitle}</strong>? Esta acción no se puede deshacer.
        </p>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button
            onClick={onCancel}
            disabled={isLoading}
            style={{
              padding: "8px 16px", background: "transparent", color: "#64748B", border: "1px solid #E2E8F0",
              borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: isLoading ? "not-allowed" : "pointer",
            }}
          >
            Cancelar
          </button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            style={{
              padding: "8px 16px", background: isLoading ? "#E5E7EB" : "#EF4444",
              color: "white", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600,
              cursor: isLoading ? "not-allowed" : "pointer",
              display: "flex", alignItems: "center", gap: 6,
            }}
          >
            {isLoading && <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />}
            Eliminar
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Add Source Modal ─────────────────────────────────────────────────────

function AddSourceModal({
  isOpen,
  onClose,
  onSubmit,
  isLoading,
}: {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: ScrapingSiteCreateRequest) => void;
  isLoading: boolean;
}): JSX.Element {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [prompt, setPrompt] = useState("");

  const handleSubmit = () => {
    if (!url.trim()) return;
    onSubmit({
      url: url.trim(),
      title: title.trim(),
      notes: notes.trim() || undefined,
      scrape_prompt: prompt.trim() || undefined,
    });
    setUrl("");
    setTitle("");
    setNotes("");
    setPrompt("");
  };

  if (!isOpen) return <></>;

  return (
    <div style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
      background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 1000, padding: 20,
    }}>
      <div style={{
        background: "#FFFFFF", borderRadius: 12, padding: "24px", maxWidth: 500, width: "100%",
        boxShadow: "0 20px 25px -5px rgba(0,0,0,0.1)",
      }}>
        <h2 style={{ margin: "0 0 20px", fontSize: 18, fontWeight: 700, color: "#0F172A" }}>
          Agregar fuente de scraping
        </h2>

        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: "#0F172A", display: "block", marginBottom: 6 }}>
            URL *
          </label>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://..."
            style={{
              width: "100%", padding: "8px 12px", border: "1px solid var(--color-border)", background: "var(--c-input-bg)", color: "var(--color-text)", borderRadius: 8,
              fontSize: 13, outline: "none", fontFamily: "inherit",
              boxSizing: "border-box",
            }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: "var(--color-text)", display: "block", marginBottom: 6 }}>
            Título
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="ej. Doctores de Honduras"
            style={{
              width: "100%", padding: "8px 12px", border: "1px solid var(--color-border)", background: "var(--c-input-bg)", color: "var(--color-text)", borderRadius: 8,
              fontSize: 13, outline: "none", fontFamily: "inherit",
              boxSizing: "border-box",
            }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: "var(--color-text)", display: "block", marginBottom: 6 }}>
            Observaciones (estructura de la página)
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="ej. Tiene input de búsqueda + paginación..."
            style={{
              width: "100%", padding: "8px 12px", border: "1px solid var(--color-border)", background: "var(--c-input-bg)", color: "var(--color-text)", borderRadius: 8,
              fontSize: 13, outline: "none", fontFamily: "inherit",
              boxSizing: "border-box", minHeight: 80, resize: "vertical",
            }}
          />
        </div>

        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: "var(--color-text)", display: "block", marginBottom: 6 }}>
            Prompt de scraping inicial
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="ej. Extraer médicos con especialidad..."
            style={{
              width: "100%", padding: "8px 12px", border: "1px solid var(--color-border)", background: "var(--c-input-bg)", color: "var(--color-text)", borderRadius: 8,
              fontSize: 13, outline: "none", fontFamily: "inherit",
              boxSizing: "border-box", minHeight: 80, resize: "vertical",
            }}
          />
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button
            onClick={onClose}
            style={{
              padding: "8px 16px", background: "transparent", color: "var(--color-text-secondary)", border: "1px solid var(--color-border)",
              borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer",
            }}
          >
            Cancelar
          </button>
          <button
            onClick={handleSubmit}
            disabled={!url.trim() || isLoading}
            style={{
              padding: "8px 16px", background: url.trim() && !isLoading ? "#4F46E5" : "var(--color-border)",
              color: "white", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600,
              cursor: url.trim() && !isLoading ? "pointer" : "not-allowed",
              display: "flex", alignItems: "center", gap: 6,
            }}
          >
            {isLoading && <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />}
            Agregar
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Site Card with Inline Editing ────────────────────────────────────────

function ScrapingSiteCard({
  site,
  onUpdate,
  onDelete,
  onScrape,
  isScrapingLoading,
  updateLoading,
  isDeleting,
}: {
  site: ScrapingSite;
  onUpdate: (siteId: string, field: "notes" | "scrape_prompt", value: string) => void;
  onDelete: (siteId: string) => void;
  onScrape: (siteId: string) => void;
  isScrapingLoading: boolean;
  updateLoading: boolean;
  isDeleting: boolean;
}): JSX.Element {
  const [editingField, setEditingField] = useState<"notes" | "scrape_prompt" | null>(null);
  const [editValue, setEditValue] = useState("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const navigate = useNavigate();

  const startEdit = (field: "notes" | "scrape_prompt") => {
    setEditingField(field);
    setEditValue(field === "notes" ? (site.notes || "") : (site.scrape_prompt || ""));
  };

  const saveEdit = () => {
    if (editingField) {
      onUpdate(site.site_id, editingField, editValue);
    }
    setEditingField(null);
  };

  const cancelEdit = () => {
    setEditingField(null);
  };

  return (
    <div style={{
      background: "var(--c-card-bg)", border: "1px solid var(--color-border)", borderRadius: 12,
      padding: "16px", marginBottom: 12,
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-text)" }}>
            🔗 {hostLabel(site.url)}
          </div>
          <div style={{ fontSize: 12, color: "#6B6B6B", marginTop: 2 }}>
            {site.url}
          </div>
        </div>
        <button
          onClick={() => setShowDeleteConfirm(true)}
          style={{
            background: "none", border: "none", cursor: "pointer", color: "var(--color-neutral)",
            padding: "4px 8px",
          }}
        >
          <Trash2 size={14} />
        </button>
      </div>

      {/* Observaciones */}
      <div style={{ marginBottom: 12, padding: "8px 12px", background: "var(--color-surface-alt)", borderRadius: 8 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--color-text-secondary)", textTransform: "uppercase" }}>
            Observaciones
          </span>
          <button
            onClick={() => startEdit("notes")}
            style={{
              background: "none", border: "none", cursor: "pointer", color: "#6366F1", fontSize: 12,
            }}
          >
            ✏ Editar
          </button>
        </div>
        {editingField === "notes" ? (
          <div>
            <textarea
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              style={{
                width: "100%", padding: "8px", border: "1px solid #E2E8F0", borderRadius: 6,
                fontSize: 12, fontFamily: "inherit", boxSizing: "border-box", minHeight: 60,
              }}
            />
            <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
              <button
                onClick={saveEdit}
                disabled={updateLoading}
                style={{
                  padding: "4px 10px", background: "#4F46E5", color: "white", border: "none",
                  borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: "pointer",
                }}
              >
                Guardar
              </button>
              <button
                onClick={cancelEdit}
                style={{
                  padding: "4px 10px", background: "#E2E8F0", color: "var(--color-text-secondary)", border: "none",
                  borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: "pointer",
                }}
              >
                Cancelar
              </button>
            </div>
          </div>
        ) : (
          <div style={{ fontSize: 12, color: site.notes ? "var(--color-text)" : "var(--color-neutral)" }}>
            {site.notes || "(sin observaciones)"}
          </div>
        )}
      </div>

      {/* Prompt de scraping */}
      <div style={{ marginBottom: 12, padding: "8px 12px", background: "var(--color-success-bg)", borderRadius: 8 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--color-text-secondary)", textTransform: "uppercase" }}>
            Prompt de scraping
          </span>
          <button
            onClick={() => startEdit("scrape_prompt")}
            style={{
              background: "none", border: "none", cursor: "pointer", color: "#6366F1", fontSize: 12,
            }}
          >
            ✏ Editar
          </button>
        </div>
        {editingField === "scrape_prompt" ? (
          <div>
            <textarea
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              style={{
                width: "100%", padding: "8px", border: "1px solid #E2E8F0", borderRadius: 6,
                fontSize: 12, fontFamily: "inherit", boxSizing: "border-box", minHeight: 60,
              }}
            />
            <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
              <button
                onClick={saveEdit}
                disabled={updateLoading}
                style={{
                  padding: "4px 10px", background: "#4F46E5", color: "white", border: "none",
                  borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: "pointer",
                }}
              >
                Guardar
              </button>
              <button
                onClick={cancelEdit}
                style={{
                  padding: "4px 10px", background: "#E2E8F0", color: "var(--color-text-secondary)", border: "none",
                  borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: "pointer",
                }}
              >
                Cancelar
              </button>
            </div>
          </div>
        ) : (
          <div style={{ fontSize: 12, color: site.scrape_prompt ? "var(--color-text)" : "var(--color-neutral)" }}>
            {site.scrape_prompt || "(usa prompt por defecto)"}
          </div>
        )}
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button
          onClick={() => onScrape(site.site_id)}
          disabled={isScrapingLoading}
          style={{
            padding: "6px 12px", background: "#4F46E5", color: "white", border: "none", borderRadius: 6,
            fontSize: 12, fontWeight: 600, cursor: isScrapingLoading ? "not-allowed" : "pointer",
            display: "inline-flex", alignItems: "center", gap: 4,
          }}
        >
          {isScrapingLoading ? (
            <>
              <Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} />
              Scrapeando...
            </>
          ) : (
            <>▶ Scrapear</>
          )}
        </button>

        {site.last_scrape_job_id && (
          <button
            onClick={() => navigate(`/url-scrape-jobs/${site.last_scrape_job_id}`)}
            style={{
              padding: "6px 12px", background: "transparent", color: "#6366F1", border: "1px solid #C7D2FE",
              borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer",
              display: "inline-flex", alignItems: "center", gap: 4,
            }}
          >
            Ver resultados
            <ExternalLink size={12} />
          </button>
        )}

        {site.last_scrape_job_id && (
          <span style={{ fontSize: 11, color: "var(--color-neutral)" }}>
            {formatRecent(site.updated_at)}
          </span>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      <DeleteConfirmModal
        isOpen={showDeleteConfirm}
        siteTitle={site.title || hostLabel(site.url)}
        onConfirm={() => {
          onDelete(site.site_id);
          setShowDeleteConfirm(false);
        }}
        onCancel={() => setShowDeleteConfirm(false)}
        isLoading={isDeleting}
      />
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────

export function ScrapingSourcesPage(): JSX.Element {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [showAddModal, setShowAddModal] = useState(false);

  const sourcesQuery = useQuery({
    queryKey: ["scraping-sites"],
    queryFn: () => listScrapingSites(),
  });

  const createMutation = useMutation({
    mutationFn: (payload: ScrapingSiteCreateRequest) => createScrapingSite(payload),
    onSuccess: () => {
      setShowAddModal(false);
      void queryClient.invalidateQueries({ queryKey: ["scraping-sites"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      siteId,
      field,
      value,
    }: {
      siteId: string;
      field: "notes" | "scrape_prompt";
      value: string;
    }) =>
      updateScrapingSite(siteId, {
        [field]: value || undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["scraping-sites"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (siteId: string) => deleteScrapingSite(siteId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["scraping-sites"] });
    },
  });

  const scrapeMutation = useMutation({
    mutationFn: (siteId: string) => scrapeScrapingSite(siteId),
    onSuccess: (data) => {
      navigate(`/url-scrape-jobs/${data.scrape_job_id}`);
    },
  });

  if (sourcesQuery.isLoading) {
    return (
      <div style={{ padding: 32, textAlign: "center", color: "var(--color-neutral)" }}>
        Cargando fuentes...
      </div>
    );
  }

  const sites = sourcesQuery.data?.items ?? [];

  return (
    <div style={{ padding: "24px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: "var(--color-text)" }}>
          Fuentes de Scraping
        </h1>
        <button
          onClick={() => setShowAddModal(true)}
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "8px 16px", background: "#4F46E5", color: "white", border: "none", borderRadius: 8,
            fontSize: 13, fontWeight: 600, cursor: "pointer",
          }}
        >
          <Plus size={14} /> Agregar
        </button>
      </div>

      {/* Sites list */}
      <div style={{ maxWidth: 900 }}>
        {sites.length === 0 ? (
          <div style={{
            padding: "48px 24px", textAlign: "center", color: "var(--color-neutral)", fontSize: 14,
            background: "var(--color-surface-alt)", borderRadius: 12,
          }}>
            No hay fuentes de scraping. Haz click en "+ Agregar" para crear una.
          </div>
        ) : (
          sites.map((site) => (
            <ScrapingSiteCard
              key={site.site_id}
              site={site}
              onUpdate={(siteId, field, value) =>
                updateMutation.mutate({ siteId, field, value })
              }
              onDelete={(siteId) => deleteMutation.mutate(siteId)}
              onScrape={(siteId) => scrapeMutation.mutate(siteId)}
              isScrapingLoading={scrapeMutation.isPending}
              updateLoading={updateMutation.isPending}
              isDeleting={deleteMutation.isPending}
            />
          ))
        )}
      </div>

      {/* Add Modal */}
      <AddSourceModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onSubmit={(payload) => createMutation.mutate(payload)}
        isLoading={createMutation.isPending}
      />
    </div>
  );
}
