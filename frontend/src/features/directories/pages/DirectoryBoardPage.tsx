import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { useDraggable } from "@dnd-kit/core";
import {
  ChevronLeft,
  CheckCircle2,
  XCircle,
  Pencil,
  RotateCcw,
  Flag,
  Clock3,
  Plus,
  ExternalLink,
  Users,
  Building2,
} from "lucide-react";

import {
  createUrlScrapeJob,
  getDirectory,
  listOpportunities,
  listSearchJobs,
  moveOpportunityStep,
  reopenOpportunity,
  terminateOpportunity,
} from "../../../api";
import { Card } from "../../../components/ui/card";
import { Button } from "../../../components/ui/button";
import { Select } from "../../../components/ui/select";
import type {
  DirectoryStep,
  OpportunityListItem,
  OpportunityTerminatedOutcome,
  SearchJobListItem,
} from "../../../types";

type ActiveTab = "board" | "searches" | "url-scraper";

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

function statusLabel(status: string): string {
  switch (status) {
    case "completed": return "Completada";
    case "running": return "En progreso";
    case "pending": return "Pendiente";
    case "error": return "Error";
    default: return status;
  }
}

function statusBadgeClass(status: string): string {
  if (status === "completed") return "ui-badge ui-badge--success";
  if (status === "error") return "ui-badge ui-badge--error";
  return "ui-badge ui-badge--default";
}

function SearchRow({ job }: { job: SearchJobListItem }): JSX.Element {
  return (
    <Link to={`/jobs/${job.job_id}`} className="directory-searches-row">
      <div className="directory-searches-row-main">
        <span className="directory-searches-row-query">{job.query || "(sin query)"}</span>
        <div className="directory-searches-row-badges">
          {job.exa_category === "company" ? (
            <span className="ui-badge ui-badge--muted" title="Empresas">
              <Building2 size={11} aria-hidden /> Empresas
            </span>
          ) : (
            <span className="ui-badge ui-badge--muted" title="Personas">
              <Users size={11} aria-hidden /> Personas
            </span>
          )}
          <span className={statusBadgeClass(job.status)} title={job.error_message ?? undefined}>
            {statusLabel(job.status)}
          </span>
        </div>
      </div>
      <div className="directory-searches-row-meta">
        <Clock3 size={11} aria-hidden />
        {formatRecent(job.created_at)}
      </div>
      <ExternalLink size={13} className="directory-searches-row-icon" aria-hidden />
    </Link>
  );
}

function OpportunityCard({ opp }: { opp: OpportunityListItem }): JSX.Element {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `opp-${opp.opportunity_id}`,
    data: { opportunityId: opp.opportunity_id, currentStepId: opp.current_step_id },
    disabled: Boolean(opp.terminated_at),
  });
  const style: React.CSSProperties = {
    transform: transform ? `translate(${transform.x}px, ${transform.y}px)` : undefined,
    opacity: isDragging ? 0.4 : 1,
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      className="ui-card directory-board-card"
      {...attributes}
      {...listeners}
    >
      <Link
        to={`/opportunities/${opp.opportunity_id}`}
        className="directory-board-card-link"
        onClick={(e) => e.stopPropagation()}
      >
        <strong className="directory-board-card-title">{opp.title || "Sin título"}</strong>
        {opp.city ? <span className="muted-text directory-board-card-meta">{opp.city}</span> : null}
      </Link>
      {opp.terminated_at ? (
        <span className={`directory-board-card-outcome directory-board-card-outcome--${opp.terminated_outcome}`}>
          {opp.terminated_outcome === "won"
            ? "Ganada"
            : opp.terminated_outcome === "lost"
            ? "Perdida"
            : "Sin respuesta"}
        </span>
      ) : null}
    </div>
  );
}

function StepColumn({
  step,
  items,
}: {
  step: DirectoryStep;
  items: OpportunityListItem[];
}): JSX.Element {
  const { setNodeRef, isOver } = useDroppable({ id: `step-${step.id}` });
  return (
    <div
      ref={setNodeRef}
      className={`directory-board-column${step.is_terminal ? " is-terminal" : ""}${
        step.is_terminal && step.is_won ? " is-won" : ""
      }${step.is_terminal && !step.is_won ? " is-lost" : ""}${isOver ? " is-drop-target" : ""}`}
    >
      <header className="directory-board-column-head">
        <h3>
          {step.is_terminal ? (
            step.is_won ? (
              <CheckCircle2 size={14} aria-hidden />
            ) : (
              <XCircle size={14} aria-hidden />
            )
          ) : null}
          {step.name}
        </h3>
        <span className="muted-text">{items.length}</span>
      </header>
      <ul className="directory-board-column-list">
        {items.map((opp) => (
          <li key={opp.opportunity_id}>
            <OpportunityCard opp={opp} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DirectoryBoardPage(): JSX.Element {
  const { directoryId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<ActiveTab>("board");
  const [terminateTarget, setTerminateTarget] = useState<OpportunityListItem | null>(null);
  const [terminateOutcome, setTerminateOutcome] = useState<OpportunityTerminatedOutcome>("won");
  const [terminateNote, setTerminateNote] = useState("");
  const [moveError, setMoveError] = useState<string | null>(null);

  const directoryQuery = useQuery({
    queryKey: ["directory", directoryId],
    queryFn: () => getDirectory(directoryId),
    enabled: Boolean(directoryId),
  });

  const itemsQuery = useQuery({
    queryKey: ["directory-items", directoryId],
    queryFn: () => listOpportunities({ directory_id: directoryId }),
    enabled: Boolean(directoryId),
    refetchInterval: 5000,
  });

  const searchesQuery = useQuery({
    queryKey: ["directory-searches", directoryId],
    queryFn: () => listSearchJobs({ directory_id: directoryId, limit: 100 }),
    enabled: Boolean(directoryId),
  });

  const moveMutation = useMutation({
    mutationFn: (args: { opportunityId: string; direction: "forward" | "backward" }) =>
      moveOpportunityStep(args.opportunityId, args.direction),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["directory-items", directoryId] });
    },
    onError: (e: Error) => setMoveError(e.message),
  });

  const terminateMutation = useMutation({
    mutationFn: (args: {
      opportunityId: string;
      outcome: OpportunityTerminatedOutcome;
      note: string | null;
    }) => terminateOpportunity(args.opportunityId, args.outcome, args.note),
    onSuccess: () => {
      setTerminateTarget(null);
      setTerminateNote("");
      void queryClient.invalidateQueries({ queryKey: ["directory-items", directoryId] });
    },
  });

  const reopenMutation = useMutation({
    mutationFn: (opportunityId: string) => reopenOpportunity(opportunityId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["directory-items", directoryId] });
    },
  });

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const stepsOrdered = useMemo(() => {
    const steps = directoryQuery.data?.steps ?? [];
    return [...steps].sort((a, b) => a.display_order - b.display_order);
  }, [directoryQuery.data]);

  const itemsByStep = useMemo(() => {
    const map = new Map<string, OpportunityListItem[]>();
    const items = itemsQuery.data?.items ?? [];
    for (const item of items) {
      if (item.terminated_at) continue;
      const key = item.current_step_id ?? "__unassigned__";
      const bucket = map.get(key) ?? [];
      bucket.push(item);
      map.set(key, bucket);
    }
    return map;
  }, [itemsQuery.data]);

  const terminatedItems = useMemo(() => {
    return (itemsQuery.data?.items ?? []).filter((i) => i.terminated_at);
  }, [itemsQuery.data]);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;
    const opportunityId = (active.data.current as { opportunityId?: string } | undefined)?.opportunityId;
    const currentStepId = (active.data.current as { currentStepId?: string } | undefined)?.currentStepId;
    if (!opportunityId || !currentStepId) return;
    const overStepId = String(over.id).startsWith("step-") ? String(over.id).slice(5) : null;
    if (!overStepId) return;
    const currentIdx = stepsOrdered.findIndex((s) => s.id === currentStepId);
    const targetIdx = stepsOrdered.findIndex((s) => s.id === overStepId);
    if (currentIdx < 0 || targetIdx < 0 || currentIdx === targetIdx) return;
    if (Math.abs(targetIdx - currentIdx) !== 1) {
      setMoveError("Solo se puede mover al step adyacente (±1).");
      return;
    }
    const direction: "forward" | "backward" = targetIdx > currentIdx ? "forward" : "backward";
    setMoveError(null);
    moveMutation.mutate({ opportunityId, direction });
  };

  if (directoryQuery.isLoading) {
    return <section className="panel">Cargando directorio…</section>;
  }
  if (directoryQuery.isError || !directoryQuery.data) {
    return <section className="panel error-text">No se pudo cargar el directorio.</section>;
  }
  const directory = directoryQuery.data;
  const searches = searchesQuery.data?.items ?? [];

  return (
    <section className="directory-board-page">
      <nav className="directory-board-nav" aria-label="Navegación">
        <Link to="/directories" className="link-button">
          <ChevronLeft size={14} aria-hidden /> Directorios
        </Link>
      </nav>

      <header className="directory-board-head">
        <div>
          <h1>{directory.name}</h1>
          {directory.description ? <p className="muted-text">{directory.description}</p> : null}
        </div>
        <div className="directory-board-head-actions">
          <Link to={`/directories/${directory.id}/edit`} className="link-button">
            <Pencil size={14} aria-hidden /> Editar
          </Link>
        </div>
      </header>

      {/* Tabs */}
      <div className="directory-board-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "board"}
          className={`directory-board-tab${activeTab === "board" ? " is-active" : ""}`}
          onClick={() => setActiveTab("board")}
        >
          Tablero
          <span className="directory-board-tab-count">
            {itemsQuery.data?.items.filter((i) => !i.terminated_at).length ?? 0}
          </span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "searches"}
          className={`directory-board-tab${activeTab === "searches" ? " is-active" : ""}`}
          onClick={() => setActiveTab("searches")}
        >
          Búsquedas
          <span className="directory-board-tab-count">{searches.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "url-scraper"}
          className={`directory-board-tab${activeTab === "url-scraper" ? " is-active" : ""}`}
          onClick={() => setActiveTab("url-scraper")}
        >
          Importar URL
        </button>
      </div>

      {/* Tablero */}
      {activeTab === "board" && (
        <>
          {moveError ? <p className="error-text">{moveError}</p> : null}

          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <div className="directory-board-columns">
              {stepsOrdered.map((step) => (
                <StepColumn
                  key={step.id}
                  step={step}
                  items={itemsByStep.get(step.id) ?? []}
                />
              ))}
            </div>
          </DndContext>

          {terminatedItems.length > 0 ? (
            <section className="directory-board-terminated">
              <h2>Terminadas</h2>
              <ul className="directory-board-terminated-list">
                {terminatedItems.map((opp) => (
                  <li
                    key={opp.opportunity_id}
                    className={`directory-board-terminated-row directory-board-terminated-row--${opp.terminated_outcome}`}
                  >
                    <div>
                      <Link to={`/opportunities/${opp.opportunity_id}`}>
                        <strong>{opp.title || "Sin título"}</strong>
                      </Link>
                      <span className="muted-text"> · {opp.terminated_outcome}</span>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => reopenMutation.mutate(opp.opportunity_id)}
                      disabled={reopenMutation.isPending}
                    >
                      <RotateCcw size={14} aria-hidden /> Reabrir
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="directory-board-actions-panel">
            <h3>Acción rápida: marcar como terminada</h3>
            <p className="muted-text">
              Elige una oportunidad activa y marca su resultado final.
            </p>
            <div className="directory-board-terminate-form">
              <Select
                value={terminateTarget?.opportunity_id ?? ""}
                onChange={(e) => {
                  const id = e.target.value;
                  const items = itemsQuery.data?.items ?? [];
                  setTerminateTarget(items.find((i) => i.opportunity_id === id && !i.terminated_at) ?? null);
                }}
              >
                <option value="">— Elige oportunidad —</option>
                {(itemsQuery.data?.items ?? [])
                  .filter((i) => !i.terminated_at)
                  .map((i) => (
                    <option key={i.opportunity_id} value={i.opportunity_id}>
                      {i.title || "(sin título)"}
                    </option>
                  ))}
              </Select>
              <Select
                value={terminateOutcome}
                onChange={(e) => setTerminateOutcome(e.target.value as OpportunityTerminatedOutcome)}
              >
                <option value="won">Ganado</option>
                <option value="lost">Perdido</option>
                <option value="no_response">Sin respuesta</option>
              </Select>
              <input
                className="ui-input"
                value={terminateNote}
                onChange={(e) => setTerminateNote(e.target.value)}
                placeholder="Nota (opcional)"
                maxLength={500}
              />
              <Button
                type="button"
                disabled={!terminateTarget || terminateMutation.isPending}
                onClick={() =>
                  terminateTarget
                    ? terminateMutation.mutate({
                        opportunityId: terminateTarget.opportunity_id,
                        outcome: terminateOutcome,
                        note: terminateNote.trim() || null,
                      })
                    : undefined
                }
              >
                <Flag size={14} aria-hidden /> Terminar
              </Button>
            </div>
          </section>
        </>
      )}

      {/* Búsquedas */}
      {activeTab === "searches" && (
        <div className="directory-searches-panel">
          <div className="directory-searches-header">
            <div>
              <h2 className="directory-searches-title">Búsquedas</h2>
              <p className="muted-text directory-searches-subtitle">
                Búsquedas realizadas en este directorio
              </p>
            </div>
            <Button
              type="button"
              className="cta-button"
              onClick={() => navigate(`/search?directory_id=${directory.id}`)}
            >
              <Plus size={15} aria-hidden /> Nueva búsqueda
            </Button>
          </div>

          {searchesQuery.isLoading ? (
            <p className="muted-text">Cargando búsquedas…</p>
          ) : searches.length === 0 ? (
            <div className="directory-searches-empty">
              <p className="muted-text">No hay búsquedas en este directorio aún.</p>
              <Button
                type="button"
                onClick={() => navigate(`/search?directory_id=${directory.id}`)}
              >
                <Plus size={15} aria-hidden /> Crear primera búsqueda
              </Button>
            </div>
          ) : (
            <ul className="directory-searches-list">
              {searches.map((job) => (
                <li key={job.job_id}>
                  <SearchRow job={job} />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Importar URL */}
      {activeTab === "url-scraper" && <UrlScraperPanel directoryId={directoryId} />}
    </section>
  );
}

function UrlScraperPanel({ directoryId }: { directoryId: string }): JSX.Element {
  const navigate = useNavigate();
  const [targetUrl, setTargetUrl] = useState("");
  const [userPrompt, setUserPrompt] = useState("");

  const createMutation = useMutation({
    mutationFn: () =>
      createUrlScrapeJob({
        target_url: targetUrl.trim(),
        user_prompt: userPrompt.trim(),
        directory_id: directoryId,
      }),
    onSuccess: (job) => navigate(`/url-scrape-jobs/${job.job_id}`),
  });

  return (
    <div className="url-scraper-panel">
      <h2>Importar desde URL</h2>
      <p className="muted-text">
        Ingresa la URL de un directorio o listado y describe qué información quieres extraer.
      </p>
      <form
        className="url-scraper-form"
        onSubmit={(e) => {
          e.preventDefault();
          createMutation.mutate();
        }}
      >
        <label className="url-scraper-label">URL de la página</label>
        <input
          className="ui-input"
          type="url"
          value={targetUrl}
          onChange={(e) => setTargetUrl(e.target.value)}
          placeholder="https://ejemplo.com/directorio-medicos"
          required
        />
        <label className="url-scraper-label">¿Qué quieres extraer?</label>
        <textarea
          className="ui-input"
          value={userPrompt}
          onChange={(e) => setUserPrompt(e.target.value)}
          placeholder="Extrae todos los médicos con su nombre, especialidad, teléfono y ciudad"
          rows={4}
          required
        />
        {createMutation.isError && (
          <p className="error-text">{(createMutation.error as Error).message}</p>
        )}
        <Button type="submit" disabled={createMutation.isPending} className="cta-button">
          {createMutation.isPending ? "Iniciando extracción…" : "Extraer entradas"}
        </Button>
      </form>
    </div>
  );
}
