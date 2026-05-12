import { ExternalLink, Loader2, Trash2, Search } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "../../../components/ui/button";
import { Badge } from "../../../components/ui/badge";
import {
  deleteDirectorySource,
  listDirectorySources,
  scrapeDirectorySource,
  updateDirectorySource,
} from "../../../api";
import type { DirectorySourceItem } from "../../../types";

export interface SourceReferenceListProps {
  directoryId: string;
  onScrapeJobCreated?: (scrapeJobId: string) => void;
  onOpenUrlScraper?: (url: string, title: string) => void;
}

const STATUS_LABEL: Record<string, { label: string; variant: "default" | "muted" | "success" }> = {
  pending: { label: "Pendiente", variant: "muted" },
  scraping: { label: "Scrapeando", variant: "default" },
  scraped: { label: "Scrapeado", variant: "success" },
  discarded: { label: "Descartado", variant: "muted" },
};

function hostLabel(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url.slice(0, 40);
  }
}

export function SourceReferenceList({ directoryId, onScrapeJobCreated, onOpenUrlScraper }: SourceReferenceListProps) {
  const queryClient = useQueryClient();

  const sourcesQuery = useQuery({
    queryKey: ["directory-sources", directoryId],
    queryFn: () => listDirectorySources(directoryId),
    refetchInterval: 5000,
  });

  const scrapeMutation = useMutation({
    mutationFn: (sourceId: string) => scrapeDirectorySource(directoryId, sourceId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["directory-sources", directoryId] });
      onScrapeJobCreated?.(data.scrape_job_id);
    },
  });

  const discardMutation = useMutation({
    mutationFn: (sourceId: string) =>
      updateDirectorySource(directoryId, sourceId, { status: "discarded" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["directory-sources", directoryId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (sourceId: string) => deleteDirectorySource(directoryId, sourceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["directory-sources", directoryId] });
    },
  });

  const sources = sourcesQuery.data?.items ?? [];
  const activeSources = sources.filter((s) => s.status !== "discarded");

  if (sourcesQuery.isLoading) {
    return <div style={{ padding: 16, textAlign: "center" }}><Loader2 className="spin" size={20} /></div>;
  }

  if (activeSources.length === 0) {
    return (
      <div className="muted-text" style={{ padding: 16, textAlign: "center" }}>
        No hay fuentes guardadas. Usa "Scrapear URL" o guarda referencias desde los resultados de búsqueda.
      </div>
    );
  }

  return (
    <div className="source-reference-grid">
      {activeSources.map((source: DirectorySourceItem) => {
        const st = STATUS_LABEL[source.status] ?? STATUS_LABEL.pending;
        return (
          <div key={source.source_id} className="source-reference-card">
            <div className="source-reference-card-top">
              <div className="source-reference-card-info">
                <span className="source-reference-card-host">{hostLabel(source.url)}</span>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                  className="source-reference-card-title"
                >
                  {source.title || source.url.slice(0, 60)}
                  <ExternalLink size={11} style={{ marginLeft: 4, flexShrink: 0 }} />
                </a>
              </div>
              <button
                type="button"
                onClick={() => deleteMutation.mutate(source.source_id)}
                className="source-reference-card-delete"
                aria-label="Eliminar"
              >
                <Trash2 size={13} />
              </button>
            </div>

            <div className="source-reference-card-footer">
              <Badge variant={st.variant}>{st.label}</Badge>
              <div className="source-reference-card-actions">
                {source.status === "pending" && (
                  <>
                    {onOpenUrlScraper ? (
                      <Button
                        size="sm"
                        onClick={() => onOpenUrlScraper(source.url, source.title || "")}
                      >
                        <Search size={12} style={{ marginRight: 4 }} />
                        Buscar por URL
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        onClick={() => scrapeMutation.mutate(source.source_id)}
                        disabled={scrapeMutation.isPending}
                      >
                        {scrapeMutation.isPending ? <Loader2 className="spin" size={12} /> : null}
                        Scrapear
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => discardMutation.mutate(source.source_id)}
                    >
                      Descartar
                    </Button>
                  </>
                )}
                {source.status === "scraping" && (
                  <Badge variant="default"><Loader2 className="spin" size={10} style={{ marginRight: 4 }} />En progreso</Badge>
                )}
                {source.status === "scraped" && (
                  <span className="muted-text" style={{ fontSize: 12 }}>Completado</span>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
