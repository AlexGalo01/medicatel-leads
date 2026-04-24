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
import { ChevronLeft, CheckCircle2, XCircle, Pencil, RotateCcw, Flag, Clock3, ChevronDown } from "lucide-react";

import {
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
} from "../../../types";

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
    queryFn: () => listSearchJobs({ directory_id: directoryId, limit: 20 }),
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
      if (item.terminated_at) continue; // las terminadas se muestran aparte
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
    // Restricción ±1
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
            <Pencil size={14} aria-hidden /> Editar directorio
          </Link>
          <button
            type="button"
            className="cta-button"
            onClick={() => navigate(`/search?directory_id=${directory.id}`)}
          >
            Buscar en este directorio
          </button>
        </div>
      </header>

      <details className="directory-board-searches">
        <summary>
          <span>Búsquedas en este directorio</span>
          <span className="muted-text">{searchesQuery.data?.items.length ?? 0}</span>
          <ChevronDown size={14} aria-hidden className="directory-board-searches-chev" />
        </summary>
        <div className="directory-board-searches-body">
          {searchesQuery.isLoading ? (
            <p className="muted-text">Cargando búsquedas…</p>
          ) : (searchesQuery.data?.items ?? []).length === 0 ? (
            <p className="muted-text">Sin búsquedas en este directorio.</p>
          ) : (
            <ul className="directory-board-searches-list">
              {searchesQuery.data!.items.map((s) => (
                <li key={s.job_id}>
                  <Link to={`/jobs/${s.job_id}`} className="directory-board-search-row">
                    <span className="directory-board-search-query">{s.query || "(sin query)"}</span>
                    <span className="muted-text directory-board-search-meta">
                      <Clock3 size={11} aria-hidden /> {formatRecent(s.created_at)}
                    </span>
                    {s.status && s.status !== "completed" ? (
                      <span
                        className={`ui-badge ui-badge--${s.status === "error" ? "error" : "default"}`}
                        title={s.status === "error" ? s.error_message ?? "Búsqueda fallida" : undefined}
                      >
                        {s.status === "error" ? "Error" : "En vivo"}
                      </span>
                    ) : null}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>

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
          Elige una oportunidad activa y marca su resultado final. El item se mueve a la sección "Terminadas".
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
    </section>
  );
}
