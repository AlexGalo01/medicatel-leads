import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
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
  ChevronRight,
  CheckCircle2,
  XCircle,
  Pencil,
  RotateCcw,
  Clock3,
  Plus,
  ExternalLink,
  Users,
  Building2,
  GripVertical,
  Link2,
  Search,
  MapPin,
  List,
  Globe,
  LayoutGrid,
} from "lucide-react";

import {
  getDirectory,
  listOpportunities,
  listSearchJobs,
  moveOpportunityStep,
  reopenOpportunity,
  terminateOpportunity,
} from "../../../api";
import { Button } from "../../../components/ui/button";
import type {
  DirectoryStep,
  OpportunityListItem,
  OpportunityTerminatedOutcome,
  SearchJobListItem,
} from "../../../types";
import { UrlScraperModal } from "../components/UrlScraperModal";
import { SourceReferenceList } from "../components/SourceReferenceList";

type ActiveTab = "board" | "searches" | "scrapes";

// ─── Helpers ─────────────────────────────────────────────────────────────────

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

function getStatusBadge(status: string): { bg: string; color: string; border: string } {
  if (status === "completed") return { bg: "#F0FDF4", color: "#059669", border: "#BBF7D0" };
  if (status === "error") return { bg: "#FEF2F2", color: "#EF4444", border: "#FECACA" };
  if (status === "running") return { bg: "#FFFBEB", color: "#D97706", border: "#FDE68A" };
  return { bg: "#F4F4F6", color: "#6B6B6B", border: "#E8E8EC" };
}

function stepDotColor(step: DirectoryStep, index: number): string {
  if (step.is_terminal && step.is_won) return "#10B981";
  if (step.is_terminal && !step.is_won) return "#EF4444";
  const palette = ["#9CA3AF", "#6366F1", "#F59E0B", "#8B5CF6", "#3B82F6", "#EC4899"];
  return palette[index % palette.length];
}

const AVATAR_PALETTE = [
  { bg: "#DBEAFE", color: "#1D4ED8" },
  { bg: "#EDE9FE", color: "#7C3AED" },
  { bg: "#D1FAE5", color: "#059669" },
  { bg: "#FEF3C7", color: "#D97706" },
  { bg: "#FCE7F3", color: "#DB2777" },
  { bg: "#CFFAFE", color: "#0891B2" },
];

function getAvatarStyle(text: string) {
  let n = 0;
  for (let i = 0; i < text.length; i++) n = (n * 31 + text.charCodeAt(i)) & 0xffff;
  return AVATAR_PALETTE[n % AVATAR_PALETTE.length];
}

function hostLabel(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url.slice(0, 30); }
}

function getSourceBadge(
  opp: OpportunityListItem,
  jobInfo?: { query: string; exa_category: string | null | undefined }
): { label: string; bg: string; color: string; border: string } | null {
  if (jobInfo) {
    if (jobInfo.exa_category === "linkedin_profile") {
      return { label: "LI", bg: "#EDE9FE", color: "#7C3AED", border: "#C4B5FD" };
    }
    return { label: "Búsqueda", bg: "#EEF2FF", color: "#4F46E5", border: "#C7D2FE" };
  }
  if (opp.scrape_target_url) {
    if (opp.scrape_target_url.includes("linkedin")) {
      return { label: "LI", bg: "#EDE9FE", color: "#7C3AED", border: "#C4B5FD" };
    }
    const host = hostLabel(opp.scrape_target_url).slice(0, 5).toUpperCase();
    return { label: host, bg: "#F0FDF4", color: "#059669", border: "#BBF7D0" };
  }
  return null;
}

// ─── SearchRow ────────────────────────────────────────────────────────────────

function SearchRow({ job, directoryName }: { job: SearchJobListItem; directoryName: string }): JSX.Element {
  const badge = getStatusBadge(job.status);
  return (
    <tr className="dboard-searches-table-row">
      <td>
        <Link to={`/jobs/${job.job_id}`} style={{ textDecoration: "none" }}>
          <div style={{ fontWeight: 500, color: "#0A0A0A", fontSize: 13 }}>{job.query || "(sin query)"}</div>
        </Link>
      </td>
      <td>
        {job.exa_category === "company" ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, fontWeight: 500, padding: "3px 8px", borderRadius: 5, background: "#EDE9FE", color: "#7C3AED", border: "1px solid #C4B5FD" }}>
            <Building2 size={10} /> Empresas
          </span>
        ) : (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, fontWeight: 500, padding: "3px 8px", borderRadius: 5, background: "#EEF2FF", color: "#4F46E5", border: "1px solid #C7D2FE" }}>
            <Users size={10} /> Personas
          </span>
        )}
      </td>
      <td style={{ fontSize: 13, color: "#0A0A0A", fontWeight: 500 }}>{directoryName}</td>
      <td>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 500, padding: "3px 10px", borderRadius: 20, background: badge.bg, color: badge.color, border: `1px solid ${badge.border}` }}>
          {statusLabel(job.status)}
        </span>
      </td>
      <td style={{ fontSize: 12, color: "#6B6B6B", whiteSpace: "nowrap" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <Clock3 size={11} /> {formatRecent(job.created_at)}
        </span>
      </td>
      <td style={{ textAlign: "right" }}>
        <Link to={`/jobs/${job.job_id}`} style={{ color: "#9B9BA8", display: "inline-flex" }}>
          <ExternalLink size={14} />
        </Link>
      </td>
    </tr>
  );
}

// ─── OpportunityCard ──────────────────────────────────────────────────────────

function OpportunityCard({
  opp,
  jobInfo,
}: {
  opp: OpportunityListItem;
  jobInfo?: { query: string; exa_category: string | null | undefined };
}): JSX.Element {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `opp-${opp.opportunity_id}`,
    data: { opportunityId: opp.opportunity_id, currentStepId: opp.current_step_id },
    disabled: Boolean(opp.terminated_at),
  });
  const dragStyle: React.CSSProperties = {
    transform: transform ? `translate(${transform.x}px, ${transform.y}px)` : undefined,
    opacity: isDragging ? 0.4 : 1,
  };

  const sourceBadge = getSourceBadge(opp, jobInfo);
  const av = getAvatarStyle(opp.title || opp.opportunity_id);
  const firstChar = (opp.title || "?")[0].toUpperCase();

  return (
    <div ref={setNodeRef} style={dragStyle} className="dboard-card">
      <div className="dboard-card-top">
        {sourceBadge ? (
          <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 7px", borderRadius: 4, background: sourceBadge.bg, color: sourceBadge.color, border: `1px solid ${sourceBadge.border}` }}>
            {sourceBadge.label}
          </span>
        ) : <span />}
        {!opp.terminated_at && (
          <div className="dboard-card-handle" {...attributes} {...listeners} aria-label="Arrastrar">
            <GripVertical size={13} />
          </div>
        )}
      </div>

      <Link to={`/opportunities/${opp.opportunity_id}`} className="dboard-card-link">
        <strong className="dboard-card-title">{opp.title || "Sin título"}</strong>
      </Link>

      <div className="dboard-card-footer">
        {opp.city ? (
          <span className="dboard-card-city">
            <MapPin size={10} /> {opp.city}
          </span>
        ) : <span />}
        <div style={{ width: 22, height: 22, borderRadius: "50%", background: av.bg, color: av.color, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, flexShrink: 0 }}>
          {firstChar}
        </div>
      </div>
    </div>
  );
}

// ─── StepColumn ───────────────────────────────────────────────────────────────

function StepColumn({
  step,
  stepIndex,
  items,
  jobMap,
}: {
  step: DirectoryStep;
  stepIndex: number;
  items: OpportunityListItem[];
  jobMap: Map<string, { query: string; exa_category: string | null | undefined }>;
}): JSX.Element {
  const { setNodeRef, isOver } = useDroppable({ id: `step-${step.id}` });
  const dotColor = stepDotColor(step, stepIndex);

  let colClass = "dboard-column";
  if (isOver) colClass += " dboard-column--over";
  if (step.is_terminal && step.is_won) colClass += " dboard-column--won";
  if (step.is_terminal && !step.is_won) colClass += " dboard-column--lost";

  return (
    <div ref={setNodeRef} className={colClass}>
      <div className="dboard-column-head">
        <h3>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: dotColor, display: "inline-block", flexShrink: 0 }} />
          {step.name}
        </h3>
        <span className="dboard-count">{items.length}</span>
      </div>
      <ul className="dboard-column-list">
        {items.map((opp) => (
          <li key={opp.opportunity_id}>
            <OpportunityCard
              opp={opp}
              jobInfo={opp.job_id ? jobMap.get(opp.job_id) : undefined}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function DirectoryBoardPage(): JSX.Element {
  const { directoryId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<ActiveTab>("board");
  const [boardSearch, setBoardSearch] = useState("");
  const [terminateTarget, setTerminateTarget] = useState<OpportunityListItem | null>(null);
  const [terminateOutcome, setTerminateOutcome] = useState<OpportunityTerminatedOutcome>("won");
  const [terminateNote, setTerminateNote] = useState("");
  const [moveError, setMoveError] = useState<string | null>(null);
  const [editingStep, setEditingStep] = useState<DirectoryStep | null>(null);
  const [scraperOpen, setScraperOpen] = useState(false);
  const [scraperUrl, setScraperUrl] = useState<string | undefined>(undefined);
  const [scraperTitle, setScraperTitle] = useState<string | undefined>(undefined);

  useEffect(() => {
    const state = location.state as
      | { openUrlScraper?: boolean; prefillUrl?: string; prefillTitle?: string }
      | undefined;
    if (state?.openUrlScraper) {
      setScraperUrl(state.prefillUrl);
      setScraperTitle(state.prefillTitle);
      setScraperOpen(true);
      window.history.replaceState({}, document.title);
    }
  }, [location.state]);

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
    mutationFn: (args: { opportunityId: string; targetStepId: string }) =>
      moveOpportunityStep(args.opportunityId, args.targetStepId),
    onMutate: async ({ opportunityId, targetStepId }) => {
      await queryClient.cancelQueries({ queryKey: ["directory-items", directoryId] });
      const prev = queryClient.getQueryData(["directory-items", directoryId]);
      queryClient.setQueryData(["directory-items", directoryId], (old: any) => {
        if (!old?.items) return old;
        return {
          ...old,
          items: old.items.map((item: OpportunityListItem) =>
            item.opportunity_id === opportunityId ? { ...item, current_step_id: targetStepId } : item
          ),
        };
      });
      return { prev };
    },
    onError: (e: Error, _args, context: any) => {
      if (context?.prev) {
        queryClient.setQueryData(["directory-items", directoryId], context.prev);
      }
      setMoveError(e.message);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["directory-items", directoryId] });
    },
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

  const filteredItemsByStep = useMemo(() => {
    if (!boardSearch.trim()) return itemsByStep;
    const q = boardSearch.toLowerCase();
    const filtered = new Map<string, OpportunityListItem[]>();
    for (const [stepId, items] of itemsByStep) {
      const matching = items.filter(
        (o) => (o.title ?? "").toLowerCase().includes(q) || (o.city ?? "").toLowerCase().includes(q),
      );
      filtered.set(stepId, matching);
    }
    return filtered;
  }, [itemsByStep, boardSearch]);

  const jobMap = useMemo(() => {
    const map = new Map<string, { query: string; exa_category: string | null | undefined }>();
    for (const job of searchesQuery.data?.items ?? []) {
      map.set(job.job_id, { query: job.query, exa_category: job.exa_category });
    }
    return map;
  }, [searchesQuery.data]);

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
    setMoveError(null);
    moveMutation.mutate({ opportunityId, targetStepId: overStepId });
  };

  if (directoryQuery.isLoading) {
    return (
      <section className="directory-board-v2">
        {/* Header skeleton */}
        <div className="dboard-header" style={{ pointerEvents: "none" }}>
          <div className="dboard-header-top">
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <span className="skel" style={{ width: 120, height: 12 }} />
              <span className="skel skel--d1" style={{ width: 220, height: 22 }} />
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <span className="skel skel--d2" style={{ width: 70, height: 32, borderRadius: 8 }} />
              <span className="skel skel--d2" style={{ width: 100, height: 32, borderRadius: 8 }} />
              <span className="skel skel--d3" style={{ width: 110, height: 32, borderRadius: 8 }} />
            </div>
          </div>
          {/* Tab bar skeleton */}
          <div style={{ display: "flex", gap: 4, marginTop: 16, borderBottom: "1px solid #E5E7EB", paddingBottom: 0 }}>
            {[80, 70, 60].map((w, i) => (
              <span key={i} className={`skel skel--d${i + 1}`} style={{ width: w, height: 28, borderRadius: "6px 6px 0 0" }} />
            ))}
          </div>
        </div>

        {/* Kanban columns skeleton */}
        <div style={{ display: "flex", gap: 14, padding: "20px 24px", overflowX: "auto" }}>
          {[3, 2, 4, 2].map((cardCount, colIdx) => (
            <div
              key={colIdx}
              style={{
                minWidth: 230, width: 230, background: "#F8FAFC",
                borderRadius: 12, padding: "12px 10px",
                border: "1px solid #E5E7EB", flexShrink: 0,
              }}
            >
              {/* Column header */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, padding: "0 4px" }}>
                <span className={`skel skel--d${colIdx + 1}`} style={{ flex: 1, height: 14 }} />
                <span className={`skel skel--d${colIdx + 1}`} style={{ width: 22, height: 18, borderRadius: 4 }} />
              </div>
              {/* Cards */}
              {Array.from({ length: cardCount }).map((_, cardIdx) => (
                <div
                  key={cardIdx}
                  style={{
                    background: "white", borderRadius: 8, padding: "10px 12px",
                    marginBottom: 8, border: "1px solid #E5E7EB",
                    boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
                  }}
                >
                  <span className={`skel skel--d${(cardIdx % 4) + 1}`} style={{ display: "block", width: "80%", height: 13, marginBottom: 6 }} />
                  <span className={`skel skel--d${((cardIdx + 1) % 4) + 1}`} style={{ display: "block", width: "55%", height: 11 }} />
                </div>
              ))}
            </div>
          ))}
        </div>
      </section>
    );
  }
  if (directoryQuery.isError || !directoryQuery.data) {
    return <section className="panel error-text">No se pudo cargar el lista.</section>;
  }
  const directory = directoryQuery.data;
  const searches = searchesQuery.data?.items ?? [];

  // suppress unused-var warnings for state that exists for future use
  void terminateTarget; void terminateOutcome; void terminateNote; void terminateMutation; void editingStep; void setEditingStep;

  return (
    <section className="directory-board-v2">
      {/* ── Header ── */}
      <div className="dboard-header">
        {/* Top row: breadcrumb + title + actions */}
        <div className="dboard-header-top">
          <div>
            <nav style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 5 }}>
              <Link to="/lists" style={{ fontSize: 13, color: "#6B6B6B", textDecoration: "none" }}>
                Listas
              </Link>
              <ChevronRight size={12} color="#B0B0BA" />
              <span style={{ fontSize: 13, color: "#0A0A0A", fontWeight: 500 }}>{directory.name}</span>
            </nav>
            <h1 style={{ margin: 0, fontSize: 21, fontWeight: 700, color: "#0A0A0A", letterSpacing: "-0.3px" }}>
              {directory.name}
            </h1>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Link to={`/lists/${directory.id}/edit`} className="dboard-btn">
              <Pencil size={13} /> Editar
            </Link>
            <button
              type="button"
              className="dboard-btn"
              onClick={() => { setScraperUrl(undefined); setScraperTitle(undefined); setScraperOpen(true); }}
            >
              <Link2 size={13} /> Importar URL
            </button>
            <button
              type="button"
              className="dboard-btn dboard-btn--primary"
              onClick={() => navigate(`/search?directory_id=${directory.id}`)}
            >
              <Search size={13} /> Nueva búsqueda
            </button>
            <Link
              to={`/opportunities/new?directory_id=${directory.id}`}
              className="dboard-btn dboard-btn--dark"
            >
              <Plus size={13} /> Oportunidad
            </Link>
          </div>
        </div>

        {/* Bottom row: tabs */}
        <div className="dboard-header-bottom">
          <div className="dboard-tabs-pill">
            <button
              type="button"
              className={`dboard-tab-pill-btn${activeTab === "board" ? " active" : ""}`}
              onClick={() => setActiveTab("board")}
            >
              <LayoutGrid size={13} /> Tablero
            </button>
            <button
              type="button"
              className={`dboard-tab-pill-btn${activeTab === "searches" ? " active" : ""}`}
              onClick={() => setActiveTab("searches")}
            >
              <List size={13} /> Búsquedas
            </button>
            <button
              type="button"
              className={`dboard-tab-pill-btn${activeTab === "scrapes" ? " active" : ""}`}
              onClick={() => setActiveTab("scrapes")}
            >
              <Globe size={13} /> Scrapes
            </button>
          </div>
        </div>
      </div>

      {/* ── Content ── */}
      <div className="dboard-content">

        {/* BOARD */}
        {activeTab === "board" && (
          <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
            {/* Board search bar */}
            <div style={{
              padding: "10px 20px", background: "white",
              borderBottom: "1px solid #E8E8EC", flexShrink: 0,
              display: "flex", alignItems: "center", gap: 10,
            }}>
              <div style={{ position: "relative", width: 280 }}>
                <Search size={14} aria-hidden style={{
                  position: "absolute", left: 12, top: "50%",
                  transform: "translateY(-50%)", color: "#9B9BA8", pointerEvents: "none",
                }} />
                <input
                  type="text"
                  placeholder="Buscar oportunidades…"
                  value={boardSearch}
                  onChange={(e) => setBoardSearch(e.target.value)}
                  style={{
                    width: "100%", height: 34, paddingLeft: 34, paddingRight: 12,
                    borderRadius: 8, border: "1px solid #D3D3D3",
                    background: "#F8FAFC", fontSize: 13, outline: "none",
                    fontFamily: "inherit", color: "#0A0A0A", boxSizing: "border-box",
                  }}
                />
              </div>
              {boardSearch && (
                <button
                  type="button"
                  onClick={() => setBoardSearch("")}
                  style={{ fontSize: 12, color: "#9B9BA8", background: "none", border: "none", cursor: "pointer", padding: "4px 8px", borderRadius: 6, fontFamily: "inherit" }}
                >
                  Limpiar
                </button>
              )}
            </div>

            {moveError && (
              <div style={{ padding: "8px 28px", fontSize: 13, color: "#EF4444", background: "#FEF2F2", borderBottom: "1px solid #FECACA", flexShrink: 0 }}>
                {moveError}
              </div>
            )}
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
              <div className="dboard-kanban">
                <div className="dboard-kanban-inner">
                  {stepsOrdered.map((step, idx) => (
                    <StepColumn
                      key={step.id}
                      step={step}
                      stepIndex={idx}
                      items={filteredItemsByStep.get(step.id) ?? []}
                      jobMap={jobMap}
                    />
                  ))}

                  {terminatedItems.length > 0 && (
                    <div className="dboard-column">
                      <div className="dboard-column-head">
                        <h3>
                          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#9CA3AF", display: "inline-block", flexShrink: 0 }} />
                          Terminadas
                        </h3>
                        <span className="dboard-count">{terminatedItems.length}</span>
                      </div>
                      <ul className="dboard-column-list">
                        {terminatedItems.map((opp) => (
                          <li key={opp.opportunity_id}>
                            <div className={`dboard-card dboard-card--${opp.terminated_outcome}`}>
                              <Link to={`/opportunities/${opp.opportunity_id}`} className="dboard-card-link">
                                <strong className="dboard-card-title">{opp.title || "Sin título"}</strong>
                              </Link>
                              <div className="dboard-card-footer" style={{ marginTop: 8 }}>
                                <span style={{
                                  fontSize: 11, fontWeight: 500, padding: "2px 8px", borderRadius: 20,
                                  background: opp.terminated_outcome === "won" ? "#F0FDF4" : "#FEF2F2",
                                  color: opp.terminated_outcome === "won" ? "#059669" : "#EF4444",
                                  border: `1px solid ${opp.terminated_outcome === "won" ? "#BBF7D0" : "#FECACA"}`,
                                }}>
                                  {opp.terminated_outcome === "won" ? "Ganada" : opp.terminated_outcome === "lost" ? "Perdida" : "Sin respuesta"}
                                </span>
                                <button
                                  type="button"
                                  style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "#6B6B6B", background: "none", border: "none", cursor: "pointer", padding: "2px 4px" }}
                                  onClick={() => reopenMutation.mutate(opp.opportunity_id)}
                                  disabled={reopenMutation.isPending}
                                >
                                  <RotateCcw size={11} /> Reabrir
                                </button>
                              </div>
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            </DndContext>
          </div>
        )}

        {/* SEARCHES */}
        {activeTab === "searches" && (
          <div className="dboard-searches-wrap">
            <div className="dboard-searches-header">
              <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#0A0A0A" }}>
                Historial de Búsquedas
              </h2>
              <button
                type="button"
                className="dboard-btn dboard-btn--primary"
                onClick={() => navigate(`/search?directory_id=${directory.id}`)}
              >
                <Plus size={13} /> Nueva búsqueda
              </button>
            </div>
            {searchesQuery.isLoading ? (
              <div style={{ padding: 24, color: "#9B9BA8", fontSize: 14 }}>Cargando búsquedas…</div>
            ) : searches.length === 0 ? (
              <div style={{ padding: 48, textAlign: "center", color: "#9B9BA8", fontSize: 14 }}>
                No hay búsquedas en este lista aún.
              </div>
            ) : (
              <div className="dboard-searches-table-wrap">
                <table className="dboard-searches-table">
                  <thead>
                    <tr>
                      <th>Query / Término</th>
                      <th>Categoría</th>
                      <th>Lista</th>
                      <th>Estado</th>
                      <th>Fecha</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {searches.map((job) => (
                      <SearchRow key={job.job_id} job={job} directoryName={directory.name} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* SCRAPES */}
        {activeTab === "scrapes" && (
          <div className="dboard-scrapes-wrap">
            <div className="dboard-scrapes-header">
              <div>
                <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#0A0A0A" }}>
                  Búsqueda por URL
                </h2>
                <p style={{ margin: "4px 0 0", fontSize: 13, color: "#9B9BA8" }}>
                  Fuentes guardadas y scrapeos realizados en este lista
                </p>
              </div>
              <button
                type="button"
                className="dboard-btn dboard-btn--primary"
                onClick={() => { setScraperUrl(undefined); setScraperTitle(undefined); setScraperOpen(true); }}
              >
                <Plus size={13} /> Scrapear URL
              </button>
            </div>
            <div className="dboard-scrapes-body">
              <SourceReferenceList
                directoryId={directoryId}
                onScrapeJobCreated={(_scrapeJobId) => { setActiveTab("scrapes"); }}
                onOpenUrlScraper={(url, title) => { setScraperUrl(url); setScraperTitle(title); setScraperOpen(true); }}
              />
            </div>
          </div>
        )}
      </div>

      {/* URL Scraper Modal */}
      <UrlScraperModal
        isOpen={scraperOpen}
        onClose={() => { setScraperOpen(false); setScraperUrl(undefined); setScraperTitle(undefined); }}
        directoryId={directoryId}
        steps={stepsOrdered}
        prefillUrl={scraperUrl}
        prefillTitle={scraperTitle}
        onComplete={(_created) => {
          void queryClient.invalidateQueries({ queryKey: ["directory-items", directoryId] });
          void queryClient.invalidateQueries({ queryKey: ["directory-sources", directoryId] });
        }}
      />
    </section>
  );
}
