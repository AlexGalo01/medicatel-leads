import { useState, useMemo } from "react";
import { ExternalLink, Loader2, Trash2, ChevronDown, ChevronRight, Search } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  listAllSources,
  scrapeDirectorySource,
  updateDirectorySource,
  deleteDirectorySource,
} from "../api";
import type { AllSourcesItem } from "../types";

const STATUS_LABEL: Record<string, { label: string; variant: "default" | "muted" | "success" }> = {
  pending: { label: "Pendiente", variant: "muted" },
  scraping: { label: "Scrapeando", variant: "default" },
  scraped: { label: "Scrapeado", variant: "success" },
  discarded: { label: "Descartado", variant: "muted" },
};

const STATUS_OPTIONS = [
  { value: "", label: "Todos" },
  { value: "pending", label: "Pendiente" },
  { value: "scraping", label: "Scrapeando" },
  { value: "scraped", label: "Scrapeado" },
  { value: "discarded", label: "Descartado" },
];

function hostLabel(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url.slice(0, 40);
  }
}

type GroupedSources = { directoryId: string; directoryName: string; sources: AllSourcesItem[] }[];

function groupByDirectory(items: AllSourcesItem[]): GroupedSources {
  const map = new Map<string, { directoryName: string; sources: AllSourcesItem[] }>();
  for (const item of items) {
    let group = map.get(item.directory_id);
    if (!group) {
      group = { directoryName: item.directory_name, sources: [] };
      map.set(item.directory_id, group);
    }
    group.sources.push(item);
  }
  return Array.from(map.entries()).map(([directoryId, g]) => ({
    directoryId,
    directoryName: g.directoryName,
    sources: g.sources,
  }));
}

export function SourcesByDirectoryPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const sourcesQuery = useQuery({
    queryKey: ["all-sources", statusFilter],
    queryFn: () => listAllSources(statusFilter || undefined),
    refetchInterval: 8000,
  });

  const grouped = useMemo(
    () => groupByDirectory(sourcesQuery.data?.items ?? []),
    [sourcesQuery.data],
  );

  const totalSources = sourcesQuery.data?.items.length ?? 0;

  // --- Mutations ---
  const scrapeMutation = useMutation({
    mutationFn: ({ directoryId, sourceId }: { directoryId: string; sourceId: string }) =>
      scrapeDirectorySource(directoryId, sourceId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["all-sources"] }),
  });

  const discardMutation = useMutation({
    mutationFn: ({ directoryId, sourceId }: { directoryId: string; sourceId: string }) =>
      updateDirectorySource(directoryId, sourceId, { status: "discarded" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["all-sources"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: ({ directoryId, sourceId }: { directoryId: string; sourceId: string }) =>
      deleteDirectorySource(directoryId, sourceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["all-sources"] });
    },
  });

  // --- Bulk actions ---
  const bulkScrapeMutation = useMutation({
    mutationFn: async (items: { directoryId: string; sourceId: string }[]) => {
      await Promise.allSettled(items.map((i) => scrapeDirectorySource(i.directoryId, i.sourceId)));
    },
    onSuccess: () => {
      setSelected(new Set());
      queryClient.invalidateQueries({ queryKey: ["all-sources"] });
    },
  });

  const bulkDiscardMutation = useMutation({
    mutationFn: async (items: { directoryId: string; sourceId: string }[]) => {
      await Promise.allSettled(
        items.map((i) => updateDirectorySource(i.directoryId, i.sourceId, { status: "discarded" })),
      );
    },
    onSuccess: () => {
      setSelected(new Set());
      queryClient.invalidateQueries({ queryKey: ["all-sources"] });
    },
  });

  function toggleSelect(sourceId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(sourceId)) next.delete(sourceId);
      else next.add(sourceId);
      return next;
    });
  }

  function toggleSelectAll(directoryId: string, sources: AllSourcesItem[]) {
    const ids = sources.map((s) => s.source_id);
    const allSelected = ids.every((id) => selected.has(id));
    setSelected((prev) => {
      const next = new Set(prev);
      if (allSelected) {
        ids.forEach((id) => next.delete(id));
      } else {
        ids.forEach((id) => next.add(id));
      }
      return next;
    });
  }

  function toggleCollapse(directoryId: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(directoryId)) next.delete(directoryId);
      else next.add(directoryId);
      return next;
    });
  }

  function getSelectedItems(): { directoryId: string; sourceId: string }[] {
    const all = sourcesQuery.data?.items ?? [];
    return all
      .filter((s) => selected.has(s.source_id) && s.status === "pending")
      .map((s) => ({ directoryId: s.directory_id, sourceId: s.source_id }));
  }

  const bulkPending = bulkScrapeMutation.isPending || bulkDiscardMutation.isPending;

  return (
    <div className="sbd-page">
      {/* Header */}
      <div className="sbd-header">
        <div>
          <h1 className="sbd-title">Fuentes</h1>
          <span className="muted-text">{totalSources} fuentes en total</span>
        </div>
        <div className="sbd-header-actions">
          <select
            className="sbd-status-filter"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setSelected(new Set());
            }}
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Bulk actions bar */}
      {selected.size > 0 && (
        <div className="sbd-bulk-bar">
          <span>{selected.size} seleccionadas</span>
          <Button
            size="sm"
            onClick={() => bulkScrapeMutation.mutate(getSelectedItems())}
            disabled={bulkPending || getSelectedItems().length === 0}
          >
            {bulkScrapeMutation.isPending ? <Loader2 className="spin" size={12} /> : <Search size={12} />}
            <span style={{ marginLeft: 4 }}>Scrapear seleccionadas</span>
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              const items = (sourcesQuery.data?.items ?? [])
                .filter((s) => selected.has(s.source_id) && s.status === "pending")
                .map((s) => ({ directoryId: s.directory_id, sourceId: s.source_id }));
              bulkDiscardMutation.mutate(items);
            }}
            disabled={bulkPending}
          >
            Descartar seleccionadas
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
            Deseleccionar
          </Button>
        </div>
      )}

      {/* Loading */}
      {sourcesQuery.isLoading && (
        <div className="sbd-loading">
          <Loader2 className="spin" size={24} />
          <span>Cargando fuentes...</span>
        </div>
      )}

      {/* Empty */}
      {!sourcesQuery.isLoading && grouped.length === 0 && (
        <div className="sbd-empty">No hay fuentes guardadas.</div>
      )}

      {/* Groups */}
      {grouped.map((group) => {
        const isCollapsed = collapsed.has(group.directoryId);
        const allIds = group.sources.map((s) => s.source_id);
        const allSelected = allIds.length > 0 && allIds.every((id) => selected.has(id));
        const someSelected = allIds.some((id) => selected.has(id));

        return (
          <div key={group.directoryId} className="sbd-group">
            <div className="sbd-group-header" onClick={() => toggleCollapse(group.directoryId)}>
              <div className="sbd-group-header-left">
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = someSelected && !allSelected;
                  }}
                  onChange={(e) => {
                    e.stopPropagation();
                    toggleSelectAll(group.directoryId, group.sources);
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className="sbd-checkbox"
                />
                {isCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
                <span className="sbd-group-name">{group.directoryName}</span>
                <Badge variant="muted">{group.sources.length}</Badge>
              </div>
            </div>

            {!isCollapsed && (
              <div className="sbd-source-list">
                {group.sources.map((source) => {
                  const st = STATUS_LABEL[source.status] ?? STATUS_LABEL.pending;
                  return (
                    <div key={source.source_id} className="sbd-source-row">
                      <input
                        type="checkbox"
                        checked={selected.has(source.source_id)}
                        onChange={() => toggleSelect(source.source_id)}
                        className="sbd-checkbox"
                      />
                      <div className="sbd-source-info">
                        <span className="sbd-source-host">{hostLabel(source.url)}</span>
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noreferrer"
                          className="sbd-source-title"
                        >
                          {source.title || source.url.slice(0, 80)}
                          <ExternalLink size={11} style={{ marginLeft: 4, flexShrink: 0 }} />
                        </a>
                      </div>
                      <Badge variant={st.variant}>{st.label}</Badge>
                      <div className="sbd-source-actions">
                        {source.status === "pending" && (
                          <>
                            <Button
                              size="sm"
                              onClick={() =>
                                scrapeMutation.mutate({
                                  directoryId: source.directory_id,
                                  sourceId: source.source_id,
                                })
                              }
                              disabled={scrapeMutation.isPending}
                            >
                              Scrapear
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() =>
                                discardMutation.mutate({
                                  directoryId: source.directory_id,
                                  sourceId: source.source_id,
                                })
                              }
                            >
                              Descartar
                            </Button>
                          </>
                        )}
                        {source.status === "scraping" && (
                          <Badge variant="default">
                            <Loader2 className="spin" size={10} style={{ marginRight: 4 }} />
                            En progreso
                          </Badge>
                        )}
                        {source.status === "scraped" && (
                          <span className="muted-text" style={{ fontSize: 12 }}>
                            Completado
                          </span>
                        )}
                        <button
                          type="button"
                          onClick={() =>
                            deleteMutation.mutate({
                              directoryId: source.directory_id,
                              sourceId: source.source_id,
                            })
                          }
                          className="sbd-delete-btn"
                          aria-label="Eliminar"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
