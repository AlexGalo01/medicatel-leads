import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Building2,
  Check,
  ChevronRight,
  ClipboardList,
  ExternalLink,
  FileText,
  Loader2,
  MessageSquare,
  PenLine,
  Phone,
  Plus,
  Presentation,
  Search,
  Trash2,
} from "lucide-react";

import {
  enrichOpportunity,
  getDirectory,
  getSearchJobStatus,
  getOpportunity,
  moveOpportunityStep,
  patchOpportunity,
  postOpportunityBitacora,
  putOpportunityContacts,
  summarizeProfile,
  terminateOpportunity,
  type OpportunityEnrichResult,
} from "../../../api";
import { usePermissions } from "../../../auth/usePermissions";
import { mergeProfileAboutText } from "../../../lib/utils";
import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Select } from "../../../components/ui/select";
import {
  OPPORTUNITY_STAGES_ORDER,
  contactKindLabel,
  opportunityJourneyLabelShort,
  opportunityStageLabel,
  responseOutcomeLabel,
} from "../model/stages";
import { EnrichContactModal, ENRICH_STAGES } from "../../../components/EnrichContactModal";
import type {
  OpportunityContact,
  OpportunityContactKind,
  OpportunityProfileOverrides,
  OpportunityResponseOutcome,
  OpportunityStageKey,
} from "../../../types";

const LOCATION_PLACEHOLDER = "No identificada";

function objectHasOwn(o: object, k: string): boolean {
  return Object.prototype.hasOwnProperty.call(o, k);
}

function stripMarkdownHeadingNoise(text: string): string {
  if (!text.trim()) return text;
  return text
    .split("\n")
    .map((line) => line.replace(/^#{1,6}\s+/u, "").trim())
    .join("\n")
    .replace(/\[\.\.\.\]/g, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function mergeAbout(overrides: OpportunityProfileOverrides | undefined, fallback: string): string {
  if (overrides && objectHasOwn(overrides, "about")) return stripMarkdownHeadingNoise(overrides.about ?? "");
  return stripMarkdownHeadingNoise(fallback);
}

function mergeLocation(overrides: OpportunityProfileOverrides | undefined, fallback: string): string {
  if (overrides && objectHasOwn(overrides, "location")) return overrides.location ?? "";
  return fallback;
}

function formatWhen(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("es-HN", { dateStyle: "short", timeStyle: "short" });
}

function isUrl(s: string | null | undefined): boolean {
  if (!s) return false;
  try {
    new URL(s);
    return true;
  } catch {
    return false;
  }
}

function BitacoraStageIcon({ stage }: { stage: string }): JSX.Element {
  const key = stage as OpportunityStageKey;
  const iconProps = { size: 18, strokeWidth: 2, "aria-hidden": true as const };
  switch (key) {
    case "first_contact":
      return <Phone {...iconProps} />;
    case "presentation":
      return <Presentation {...iconProps} />;
    case "response":
      return <MessageSquare {...iconProps} />;
    case "documents_wait":
      return <FileText {...iconProps} />;
    case "agreement_sign":
      return <PenLine {...iconProps} />;
    case "medicatel_profile":
      return <Building2 {...iconProps} />;
    default:
      return <ClipboardList {...iconProps} />;
  }
}

const CONTACT_KINDS: OpportunityContactKind[] = ["email", "phone", "whatsapp", "linkedin", "other"];
const OUTCOMES: OpportunityResponseOutcome[] = ["pending", "positive", "negative"];



export function OpportunityDetailPage(): JSX.Element {
  const { opportunityId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  usePermissions();
  const [stageDraft, setStageDraft] = useState<OpportunityStageKey | "">("");
  const [stepDraft, setStepDraft] = useState<string>("");
  const [outcomeDraft, setOutcomeDraft] = useState<OpportunityResponseOutcome>("pending");
  const [stageNote, setStageNote] = useState("");
  const [bitacoraText, setBitacoraText] = useState("");
  const [contactsDraft, setContactsDraft] = useState<OpportunityContact[]>([]);
  const [contactsDirty, setContactsDirty] = useState(false);
  const [aboutDraft, setAboutDraft] = useState("");
  const [locationDraft, setLocationDraft] = useState("");
  const [cvDirty, setCvDirty] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [companyDraft, setCompanyDraft] = useState("");
  const [experiencesDraft, setExperiencesDraft] = useState<Array<{role: string; organization: string; period: string}>>([]);
  const [enrichModalOpen, setEnrichModalOpen] = useState(false);
  const [enrichStageIdx, setEnrichStageIdx] = useState(0);
  const [confirmInvalid, setConfirmInvalid] = useState(false);
  const [invalidNote, setInvalidNote] = useState("");
  const [confirmConcluded, setConfirmConcluded] = useState(false);
  const [concludeNote, setConcludeNote] = useState("");
  const [editingSection, setEditingSection] = useState<string | null>(null);
  const bitacoraScrollRef = useRef<HTMLDivElement>(null);
  const bitacoraTextareaRef = useRef<HTMLTextAreaElement>(null);
  const aboutTextareaRef = useRef<HTMLTextAreaElement>(null);

  const detailQuery = useQuery({
    queryKey: ["opportunity", opportunityId],
    queryFn: () => getOpportunity(opportunityId),
    enabled: Boolean(opportunityId),
  });

  const data = detailQuery.data;

  const directoryQuery = useQuery({
    queryKey: ["directory", data?.directory_id],
    queryFn: () => getDirectory(data!.directory_id!),
    enabled: Boolean(data?.directory_id),
    staleTime: 5 * 60 * 1000,
  });
  const dirSteps = (directoryQuery.data?.steps ?? [])
    .filter((s) => !s.is_terminal)
    .sort((a, b) => a.display_order - b.display_order);
  const dirTerminalSteps = (directoryQuery.data?.steps ?? [])
    .filter((s) => s.is_terminal)
    .sort((a, b) => a.display_order - b.display_order);
  const allDirSteps = [...dirSteps, ...dirTerminalSteps];
  const useDirectorySteps = Boolean(data?.directory_id && allDirSteps.length > 0);

  const moveStepMut = useMutation({
    mutationFn: (targetStepId: string) => moveOpportunityStep(opportunityId, targetStepId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["opportunity", opportunityId] });
      void queryClient.invalidateQueries({ queryKey: ["directory-items", data?.directory_id] });
      setStepDraft("");
    },
  });

  const sourceJobQuery = useQuery({
    queryKey: ["job-status", data?.job_id],
    queryFn: () => {
      const jid = data?.job_id;
      if (!jid) {
        return Promise.reject(new Error("job_id requerido"));
      }
      return getSearchJobStatus(jid);
    },
    enabled: Boolean(data?.job_id),
    staleTime: 5 * 60 * 1000,
  });
  const profileSummaryQuery = useQuery({
    queryKey: ["profile-summary", opportunityId, data?.title, data?.specialty, data?.city, data?.snippet],
    queryFn: ({ signal }) =>
      summarizeProfile(
        {
          title: data?.title || "",
          specialty: data?.specialty || null,
          city: data?.city || null,
          snippet: data?.snippet || null,
        },
        { signal },
      ),
    enabled: Boolean(data),
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (!data) return;
    setTitleDraft(data.title || "");
    setStageDraft(data.stage);
    setOutcomeDraft((data.response_outcome as OpportunityResponseOutcome) || "pending");
    if (!contactsDirty) setContactsDraft(data.contacts?.length ? data.contacts : []);
  }, [data, contactsDirty]);

  /** Overrides guardados: aplicar al cargar oportunidad sin esperar a la IA. */
  useEffect(() => {
    if (!data) return;
    if (cvDirty) return;
    const overrides = data.profile_overrides ?? {};
    if (objectHasOwn(overrides, "about")) {
      setAboutDraft(mergeAbout(overrides, ""));
    }
    if (objectHasOwn(overrides, "location")) {
      setLocationDraft(mergeLocation(overrides, ""));
    }
    if (objectHasOwn(overrides, "company")) {
      setCompanyDraft(overrides.company ?? "");
    }
    if (objectHasOwn(overrides, "experiences") && Array.isArray(overrides.experiences)) {
      setExperiencesDraft((overrides.experiences ?? []).map((e) => ({
        role: e.role ?? "",
        organization: e.organization ?? "",
        period: e.period ?? "",
      })));
    }
  }, [data, cvDirty]);

  /** Resumen IA: una sola actualización al terminar (evita parpadeo de texto al llegar el stream de datos). */
  useEffect(() => {
    if (!data || cvDirty) return;
    if (profileSummaryQuery.isPending) return;
    const overrides = data.profile_overrides ?? {};
    if (profileSummaryQuery.isError) {
      if (!objectHasOwn(overrides, "about")) {
        setAboutDraft(
          mergeAbout(overrides, mergeProfileAboutText("", "", data.specialty || "Sin resumen disponible.")),
        );
      }
      if (!objectHasOwn(overrides, "location")) {
        setLocationDraft(mergeLocation(overrides, data.city?.trim() || ""));
      }
      return;
    }
    if (!profileSummaryQuery.isSuccess) return;
    const rawAbout = mergeProfileAboutText(
      profileSummaryQuery.data?.about?.trim() ?? "",
      profileSummaryQuery.data?.professional_summary?.trim() ?? "",
      data.specialty || "Sin resumen disponible.",
    );
    const aiLocationRaw = profileSummaryQuery.data?.location?.trim() || data.city?.trim() || "";
    setAboutDraft(mergeAbout(overrides, rawAbout));
    setLocationDraft(mergeLocation(overrides, aiLocationRaw));
    if (!objectHasOwn(overrides, "company")) {
      setCompanyDraft(profileSummaryQuery.data?.company?.trim() || "");
    }
    if (!objectHasOwn(overrides, "experiences") && profileSummaryQuery.data?.experiences?.length) {
      setExperiencesDraft((profileSummaryQuery.data.experiences).map((e) => ({
        role: e.role ?? "",
        organization: e.organization ?? "",
        period: e.period ?? "",
      })));
    }
  }, [cvDirty, data, profileSummaryQuery.data, profileSummaryQuery.isPending, profileSummaryQuery.isError, profileSummaryQuery.isSuccess]);

  useLayoutEffect(() => {
    const el = aboutTextareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(el.scrollHeight, 88)}px`;
  }, [aboutDraft]);

  const patchMut = useMutation({
    mutationFn: (body: { title?: string; stage?: string; response_outcome?: string | null; note?: string | null }) =>
      patchOpportunity(opportunityId, body),
    onSuccess: (updated) => {
      queryClient.setQueryData(["opportunity", opportunityId], updated);
      setStageNote("");
    },
  });

  const contactTypeMut = useMutation({
    mutationFn: (ct: "employee" | "company") => patchOpportunity(opportunityId, { contact_type: ct }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["opportunity", opportunityId], updated);
    },
  });

  // Auto-set contact_type from exa_category when not yet defined
  useEffect(() => {
    if (!data || data.contact_type) return;
    const exaCat = sourceJobQuery.data?.exa_category;
    if (!exaCat) return;
    const inferred = exaCat === "company" ? "company" : "employee";
    contactTypeMut.mutate(inferred);
  }, [data?.contact_type, sourceJobQuery.data?.exa_category]);

  const profileCvMut = useMutation({
    mutationFn: (body: { profile_cv: OpportunityProfileOverrides }) => patchOpportunity(opportunityId, body),
    onSuccess: (updated) => {
      queryClient.setQueryData(["opportunity", opportunityId], updated);
      setCvDirty(false);
    },
  });

  const bitacoraMut = useMutation({
    mutationFn: (text: string) => postOpportunityBitacora(opportunityId, text),
    onSuccess: (updated) => {
      queryClient.setQueryData(["opportunity", opportunityId], updated);
      setBitacoraText("");
    },
  });

  const contactsMut = useMutation({
    mutationFn: (contacts: OpportunityContact[]) => putOpportunityContacts(opportunityId, contacts),
    onSuccess: (updated) => {
      queryClient.setQueryData(["opportunity", opportunityId], updated);
      setContactsDraft(updated.contacts ?? []);
      setContactsDirty(false);
    },
  });

  const enrichMut = useMutation<OpportunityEnrichResult>({
    mutationFn: () =>
      enrichOpportunity(opportunityId, (msg) => {
        const idx = ENRICH_STAGES.indexOf(msg);
        if (idx >= 0) {
          setEnrichStageIdx(idx);
        }
      }),
  });

  const stageIndex = useMemo(() => {
    if (!data) return 0;
    const i = OPPORTUNITY_STAGES_ORDER.indexOf(data.stage);
    return i >= 0 ? i : 0;
  }, [data]);

  const journeyFillPct = useMemo(() => {
    const n = OPPORTUNITY_STAGES_ORDER.length;
    if (n <= 1) return 0;
    return (stageIndex / (n - 1)) * 100;
  }, [stageIndex]);

  const terminateMut = useMutation({
    mutationFn: (note?: string) => terminateOpportunity(opportunityId, "no_valida", note || null),
    onSuccess: (updated) => {
      queryClient.setQueryData(["opportunity", opportunityId], updated);
      setConfirmInvalid(false);
      setInvalidNote("");
    },
  });

  const concludeMut = useMutation({
    mutationFn: (note?: string) => terminateOpportunity(opportunityId, "won", note || null),
    onSuccess: (updated) => {
      queryClient.setQueryData(["opportunity", opportunityId], updated);
      setConfirmConcluded(false);
      setConcludeNote("");
    },
  });

  if (!opportunityId) return <section className="panel error-text">Identificador no válido.</section>;
  if (detailQuery.isLoading) {
    return (
      <section className="panel opportunities-loading">
        <Loader2 className="spin" aria-hidden /> Cargando oportunidad…
      </section>
    );
  }
  if (detailQuery.isError || !data) {
    return (
      <section className="panel error-text">
        No se encontró la oportunidad.{" "}
        <Link to="/opportunities" className="link-button">
          Volver al listado
        </Link>
      </section>
    );
  }

  const addContactRow = () => {
    setContactsDirty(true);
    setContactsDraft((prev) => [
      ...prev,
      {
        id: `new-${Date.now()}`,
        kind: "email",
        value: "",
        note: null,
        role: null,
        is_primary: prev.length === 0,
      },
    ]);
  };

  const updateContact = (index: number, patch: Partial<OpportunityContact>) => {
    setContactsDirty(true);
    setContactsDraft((prev) => {
      const next = prev.map((c, i) => (i === index ? { ...c, ...patch } : c));
      if (patch.is_primary) return next.map((c, i) => ({ ...c, is_primary: i === index }));
      return next;
    });
  };

  const removeContact = (index: number) => {
    setContactsDirty(true);
    setContactsDraft((prev) => prev.filter((_, i) => i !== index));
  };

  const onSaveStage = () => {
    if (!stageDraft) return;
    const currentIdx = OPPORTUNITY_STAGES_ORDER.indexOf(data.stage);
    const draftIdx = OPPORTUNITY_STAGES_ORDER.indexOf(stageDraft as OpportunityStageKey);
    if (draftIdx >= 0 && currentIdx >= 0 && draftIdx < currentIdx) return;
    const body: { stage: string; response_outcome?: string | null; note?: string | null } = {
      stage: stageDraft,
      note: stageNote.trim() || null,
    };
    if (stageDraft === "response") body.response_outcome = outcomeDraft;
    else body.response_outcome = null;
    patchMut.mutate(body);
  };

  const timelineNewestFirst = [...(data.activity_timeline ?? [])].reverse();
  const sourceJobLabel = sourceJobQuery.data?.query_text?.trim() || "No disponible";
  const profileCompany = profileSummaryQuery.data?.company?.trim() || "No especificada";
  const storedProfileOverrides = data.profile_overrides ?? {};
  const profileIaPending = profileSummaryQuery.isPending && !cvDirty;
  const aboutFieldWaitingIa = profileIaPending && !objectHasOwn(storedProfileOverrides, "about");
  const locationFieldWaitingIa = profileIaPending && !objectHasOwn(storedProfileOverrides, "location");
  const experienceFromOverride =
    objectHasOwn(storedProfileOverrides, "experiences") &&
    Array.isArray(storedProfileOverrides.experiences) &&
    (storedProfileOverrides.experiences?.length ?? 0) > 0;

  const profileExperiences = (() => {
    const ov = data.profile_overrides;
    if (ov && objectHasOwn(ov, "experiences") && Array.isArray(ov.experiences) && (ov.experiences?.length ?? 0) > 0) {
      return ov.experiences ?? [];
    }
    return profileSummaryQuery.data?.experiences ?? [];
  })();

  const saveProfileCv = () => {
    const loc = locationDraft.trim();
    profileCvMut.mutate({
      profile_cv: { about: aboutDraft, location: loc.length > 0 ? loc : null },
    });
  };

  const saveExperiences = () => {
    profileCvMut.mutate({
      profile_cv: { experiences: experiencesDraft.filter((e) => e.role.trim()) },
    });
    setEditingSection(null);
  };

  const saveCompany = () => {
    profileCvMut.mutate({
      profile_cv: { company: companyDraft.trim() || null },
    });
    setEditingSection(null);
  };

  return (
    <div className="opportunity-ficha-page">
      <nav className="opportunity-detail-nav opportunity-ficha-area-nav" aria-label="Navegación">
        <Link to="/opportunities" className="link-button">
          Oportunidades
        </Link>
        <ChevronRight size={14} aria-hidden className="opportunity-detail-nav-chevron" />
        <span className="muted-text opportunity-detail-nav-current">Ficha</span>
      </nav>

      <Card
        className="panel opportunity-card opportunity-bento-card opportunity-journey-card opportunity-ficha-area-journey"
        aria-label="Progreso del embudo"
      >
        <h2 className="opportunity-journey-heading">Flujo de Oportunidad</h2>
        {useDirectorySteps ? (() => {
          const rawIdx = allDirSteps.findIndex((s) => s.id === data.current_step_id);
          // If no step assigned yet, treat first step as current
          const currentStepIdx = rawIdx >= 0 ? rawIdx : 0;
          const effectiveStepId = rawIdx >= 0 ? data.current_step_id : allDirSteps[0]?.id;
          const fillPct = allDirSteps.length <= 1 ? 0 : (currentStepIdx / (allDirSteps.length - 1)) * 100;
          return (
            <div
              className="opportunity-journey-track-wrap"
              style={{ "--opportunity-journey-fill-pct": `${fillPct}%` } as React.CSSProperties}
            >
              <div className="opportunity-journey-rail" aria-hidden />
              <ol className="opportunity-journey-track">
                {allDirSteps.map((step, idx) => {
                  const done = idx < currentStepIdx;
                  const current = step.id === effectiveStepId;
                  const upcoming = idx > currentStepIdx;
                  return (
                    <li
                      key={step.id}
                      className={`opportunity-journey-step${done ? " is-done" : ""}${current ? " is-current" : ""}${upcoming ? " is-upcoming" : ""}`}
                    >
                      <Button
                        type="button"
                        className="opportunity-journey-node"
                        onClick={() => setStepDraft(step.id)}
                        aria-current={current ? "step" : undefined}
                        aria-label={`Fase: ${step.name}${current ? " (actual)" : ""}`}
                      >
                        <span className="opportunity-journey-circle" aria-hidden>
                          {done ? <Check size={16} strokeWidth={2.5} /> : <span className="opportunity-journey-num">{idx + 1}</span>}
                        </span>
                        <span className="opportunity-journey-label">{step.name}</span>
                      </Button>
                    </li>
                  );
                })}
              </ol>
            </div>
          );
        })() : (
          <div
            className="opportunity-journey-track-wrap"
            style={{ "--opportunity-journey-fill-pct": `${journeyFillPct}%` } as React.CSSProperties}
          >
            <div className="opportunity-journey-rail" aria-hidden />
            <ol className="opportunity-journey-track">
              {OPPORTUNITY_STAGES_ORDER.map((key, idx) => {
                const done = idx < stageIndex;
                const current = idx === stageIndex;
                const upcoming = idx > stageIndex;
                const isPastPhase = idx < stageIndex;
                return (
                  <li
                    key={key}
                    className={`opportunity-journey-step${done ? " is-done" : ""}${current ? " is-current" : ""}${upcoming ? " is-upcoming" : ""}`}
                  >
                    <Button
                      type="button"
                      className="opportunity-journey-node"
                      disabled={isPastPhase}
                      onClick={() => { if (!isPastPhase) setStageDraft(key); }}
                      aria-current={current ? "step" : undefined}
                    >
                      <span className="opportunity-journey-circle" aria-hidden>
                        {done ? <Check size={16} strokeWidth={2.5} /> : <span className="opportunity-journey-num">{idx + 1}</span>}
                      </span>
                      <span className="opportunity-journey-label">{opportunityJourneyLabelShort[key]}</span>
                    </Button>
                    {key === "response" && current ? (
                      <span className="opportunity-journey-sub">
                        {responseOutcomeLabel[(data.response_outcome as OpportunityResponseOutcome) ?? "pending"]}
                      </span>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          </div>
        )}
        <p className="muted-text opportunity-journey-hint">
          Haz clic en una fase para seleccionarla y guarda abajo.
        </p>
      </Card>

      <Card className="panel opportunity-card opportunity-bento-card opportunity-summary-card opportunity-ficha-area-summary">
        <div className="opportunity-summary-title-wrapper" style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
          <Input
            value={titleDraft}
            onChange={(e) => setTitleDraft(e.target.value)}
            onBlur={() => {
              if (titleDraft.trim() !== data.title && titleDraft.trim()) {
                patchMut.mutate({ title: titleDraft.trim() });
              } else {
                setTitleDraft(data.title || "");
              }
            }}
            className="opportunity-summary-title-input"
            style={{ fontSize: "1.5rem", fontWeight: "700", border: "1px solid transparent", background: "transparent", padding: "0.25rem 0.5rem", boxShadow: "none", flex: 1, margin: "-0.25rem -0.5rem" }}
            title="Haz click para editar el nombre"
            placeholder="Nombre de la oportunidad"
          />
          {data.source_url ? (
            <a
              href={data.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="opportunity-summary-title-link"
              title="Ver fuente original"
            >
              <ExternalLink size={18} aria-hidden />
            </a>
          ) : null}
          {patchMut.isPending && patchMut.variables?.title === titleDraft.trim() ? <Loader2 size={16} className="spin muted-text" /> : null}
        </div>
        {data.owner ? (
          <p className="muted-text opportunity-owner-line" style={{ marginTop: "0.25rem" }}>
            A cargo: <strong>{data.owner.display_name}</strong>
          </p>
        ) : null}
        <div className="opportunity-summary-badges" aria-label="Resumen rápido">
          {data.city ? <span className="opportunity-summary-badge opportunity-summary-badge--muted">{data.city}</span> : null}
          {data.specialty ? (
            <span className="opportunity-summary-badge opportunity-summary-badge--muted">{data.specialty}</span>
          ) : null}
          {data.stage === "response" && data.response_outcome ? (
            <span className={`opportunity-summary-badge opportunity-summary-badge--outcome-${data.response_outcome}`}>
              {responseOutcomeLabel[data.response_outcome as OpportunityResponseOutcome]}
            </span>
          ) : null}
        </div>
        {data.contact_type === "company" ? (
          <div className="opportunity-summary-company-info">
            {data.snippet ? <p className="opportunity-summary-snippet muted-text">{data.snippet}</p> : null}
          </div>
        ) : (
          <>
            <div className="opportunity-summary-cv-toolbar">
              <Button
                type="button"
                className="cta-button opportunity-summary-cv-save"
                disabled={profileCvMut.isPending}
                onClick={() => saveProfileCv()}
              >
                {profileCvMut.isPending ? <Loader2 className="spin" size={16} aria-hidden /> : null}
                Guardar datos del perfil
              </Button>
            </div>
            {profileCvMut.isError ? <p className="error-text opportunity-summary-cv-error">No se pudo guardar el perfil.</p> : null}
            {profileIaPending ? (
              <p className="muted-text opportunity-summary-ia-hint" role="status" aria-live="polite">
                <Loader2 className="spin" size={16} strokeWidth={2} aria-hidden />
                {aboutFieldWaitingIa || locationFieldWaitingIa
                  ? "Generando resumen del perfil con la IA. Los campos se rellenan al terminar."
                  : "Completando datos del perfil…"}
              </p>
            ) : null}
            <div className="opportunity-summary-cv">
              <article className="opportunity-summary-cv-block">
                <div className="opportunity-card-header">
                  <h3 className="opportunity-card-subtitle">Resumen</h3>
                  <button
                    type="button"
                    className="opportunity-card-edit-btn"
                    onClick={() => setEditingSection(editingSection === "about" ? null : "about")}
                    aria-label={editingSection === "about" ? "Cerrar edición" : "Editar resumen"}
                  >
                    <PenLine size={15} aria-hidden />
                  </button>
                </div>
                <hr className="opportunity-card-divider" />
                {editingSection === "about" ? (
                  <textarea
                    ref={aboutTextareaRef}
                    className="opportunity-summary-cv-textarea"
                    value={aboutDraft}
                    onChange={(e) => {
                      setCvDirty(true);
                      setAboutDraft(e.target.value);
                    }}
                    rows={1}
                    maxLength={8000}
                    spellCheck
                    readOnly={aboutFieldWaitingIa}
                    aria-busy={aboutFieldWaitingIa}
                    placeholder={aboutFieldWaitingIa ? "Generando resumen con la IA…" : "Añade una descripción profesional..."}
                    style={{
                      border: "none",
                      background: "transparent",
                      padding: "0",
                      boxShadow: "none",
                      minHeight: "120px",
                      fontSize: "0.95rem",
                      lineHeight: "1.6",
                      color: "var(--color-text)",
                      width: "100%"
                    }}
                  />
                ) : aboutFieldWaitingIa ? (
                  <p className="muted-text">
                    <Loader2 className="spin" size={14} strokeWidth={2} aria-hidden /> Generando resumen…
                  </p>
                ) : (
                  <p style={{ fontSize: "0.95rem", lineHeight: "1.6", margin: 0 }}>
                    {aboutDraft || <span className="muted-text">Sin descripción.</span>}
                  </p>
                )}
              </article>
              <article className="opportunity-summary-cv-block opportunity-summary-cv-block--experience">
                <div className="opportunity-card-header">
                  <h3 className="opportunity-card-subtitle">Experiencia</h3>
                  <button
                    type="button"
                    className="opportunity-card-edit-btn"
                    onClick={() => setEditingSection(editingSection === "experiences" ? null : "experiences")}
                    aria-label={editingSection === "experiences" ? "Cerrar edición" : "Editar experiencia"}
                  >
                    <PenLine size={15} aria-hidden />
                  </button>
                </div>
                <hr className="opportunity-card-divider" />
                {editingSection === "experiences" ? (
                  <div>
                    {experiencesDraft.map((exp, i) => (
                      <div key={i} style={{ display: "flex", gap: "6px", marginBottom: "8px", alignItems: "flex-start" }}>
                        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "4px" }}>
                          <Input
                            value={exp.role}
                            onChange={(e) => setExperiencesDraft((prev) => prev.map((x, j) => j === i ? { ...x, role: e.target.value } : x))}
                            placeholder="Cargo / Rol"
                            className="ui-input--minimal-value"
                          />
                          <Input
                            value={exp.organization}
                            onChange={(e) => setExperiencesDraft((prev) => prev.map((x, j) => j === i ? { ...x, organization: e.target.value } : x))}
                            placeholder="Organización"
                            className="ui-input--minimal-meta"
                          />
                          <Input
                            value={exp.period}
                            onChange={(e) => setExperiencesDraft((prev) => prev.map((x, j) => j === i ? { ...x, period: e.target.value } : x))}
                            placeholder="Período"
                            className="ui-input--minimal-meta"
                          />
                        </div>
                        <button type="button" className="opportunity-card-edit-btn" onClick={() => setExperiencesDraft((prev) => prev.filter((_, j) => j !== i))}>
                          <Trash2 size={13} />
                        </button>
                      </div>
                    ))}
                    <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
                      <button
                        type="button"
                        className="link-button"
                        style={{ fontSize: "0.8rem" }}
                        onClick={() => setExperiencesDraft((prev) => [...prev, { role: "", organization: "", period: "" }])}
                      >
                        <Plus size={13} /> Añadir
                      </button>
                      <Button type="button" className="cta-button" style={{ fontSize: "0.8rem", padding: "4px 12px" }} disabled={profileCvMut.isPending} onClick={saveExperiences}>
                        {profileCvMut.isPending ? <Loader2 className="spin" size={13} /> : null} Guardar
                      </Button>
                    </div>
                  </div>
                ) : profileIaPending && !experienceFromOverride ? (
                  <p className="muted-text opportunity-summary-ia-experience-waiting">
                    <Loader2 className="spin" size={16} strokeWidth={2} aria-hidden />
                    Cargando experiencia estructurada…
                  </p>
                ) : experiencesDraft.length > 0 ? (
                  <ul className="opportunity-summary-experience-list" style={{ listStyle: "disc", paddingLeft: "1.1rem", margin: 0 }}>
                    {experiencesDraft.map((experience, index) => (
                      <li key={`${experience.role}-${index}`} className="opportunity-summary-experience-item">
                        <strong style={{ fontSize: "14px", fontWeight: 600 }}>{experience.role}</strong>
                        <span className="muted-text" style={{ fontSize: "13px", display: "block" }}>
                          {[experience.organization || null, experience.period || null].filter(Boolean).join(" · ") || "Sin detalle"}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted-text">Sin experiencia estructurada.</p>
                )}
              </article>
              <article className="opportunity-summary-cv-block">
                <div className="opportunity-card-header">
                  <h3 className="opportunity-card-subtitle">Ubicación</h3>
                  <button
                    type="button"
                    className="opportunity-card-edit-btn"
                    onClick={() => setEditingSection(editingSection === "location" ? null : "location")}
                    aria-label={editingSection === "location" ? "Cerrar edición" : "Editar ubicación"}
                  >
                    <PenLine size={15} aria-hidden />
                  </button>
                </div>
                <hr className="opportunity-card-divider" />
                {editingSection === "location" ? (
                  <Input
                    value={locationDraft}
                    placeholder={locationFieldWaitingIa ? "Generando o usando ciudad de la ficha…" : LOCATION_PLACEHOLDER}
                    readOnly={locationFieldWaitingIa}
                    aria-busy={locationFieldWaitingIa}
                    onChange={(e) => {
                      setCvDirty(true);
                      setLocationDraft(e.target.value);
                    }}
                    maxLength={500}
                    className="opportunity-summary-location-input"
                  />
                ) : (
                  <p className="muted-text">{locationDraft || LOCATION_PLACEHOLDER}</p>
                )}
              </article>
              <article className="opportunity-summary-cv-block">
                <div className="opportunity-card-header">
                  <h3 className="opportunity-card-subtitle">Empresa</h3>
                  <button
                    type="button"
                    className="opportunity-card-edit-btn"
                    onClick={() => setEditingSection(editingSection === "company" ? null : "company")}
                    aria-label={editingSection === "company" ? "Cerrar edición" : "Editar empresa"}
                  >
                    <PenLine size={15} aria-hidden />
                  </button>
                </div>
                <hr className="opportunity-card-divider" />
                {editingSection === "company" ? (
                  <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                    <Input
                      value={companyDraft}
                      onChange={(e) => setCompanyDraft(e.target.value)}
                      placeholder="Nombre de empresa u organización"
                      maxLength={120}
                      className="opportunity-summary-location-input"
                    />
                    <Button type="button" className="cta-button" style={{ fontSize: "0.8rem", padding: "4px 12px", whiteSpace: "nowrap" }} disabled={profileCvMut.isPending} onClick={saveCompany}>
                      {profileCvMut.isPending ? <Loader2 className="spin" size={13} /> : null} Guardar
                    </Button>
                  </div>
                ) : (
                  <p className="muted-text">{companyDraft || "No especificada"}</p>
                )}
              </article>
            </div>
          </>
        )}
      </Card>

      <div className="opportunity-ficha-area-bitacora opportunity-ficha-side-stack">

      <Card className="panel opportunity-card opportunity-bento-card opportunity-contacts-card">
        <div className="opportunity-panel-head">
          <h2 className="opportunity-card-title" style={{ marginBottom: 0 }}>Contactos</h2>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <Button
              type="button"
              className="workspace-tool-btn"
              onClick={() => {
                setEnrichModalOpen(true);
                setEnrichStageIdx(0);
                enrichMut.reset();
                enrichMut.mutate();
              }}
            >
              <Search size={16} aria-hidden /> Enriquecer
            </Button>
            <Button type="button" className="workspace-tool-btn" onClick={() => addContactRow()}>
              <Plus size={16} aria-hidden /> Añadir
            </Button>
          </div>
        </div>
        <hr className="opportunity-card-divider" />
        {contactsDraft.length === 0 ? (
          <p className="muted-text">Aún no hay contactos. Añade correos, teléfonos u otros canales.</p>
        ) : (
          <ul className="opportunity-contact-editor-list">
            {contactsDraft.map((c, idx) => (
              <li key={c.id || idx} className="opportunity-contact-editor-card">
                  <div className="opportunity-contact-editor-card-inner">
                    <div className="opportunity-contact-editor-header">
                      <Select
                        value={c.kind}
                        onChange={(e) => updateContact(idx, { kind: e.target.value as OpportunityContactKind })}
                        className="ui-select--minimal-bold"
                      >
                        {CONTACT_KINDS.map((k) => (
                          <option key={k} value={k}>
                            {contactKindLabel[k].toUpperCase()}
                          </option>
                        ))}
                      </Select>
                      <div className="opportunity-contact-actions">
                        <label className="opportunity-field--checkbox-mini">
                          <input
                            type="checkbox"
                            checked={c.is_primary}
                            onChange={(e) => updateContact(idx, { is_primary: e.target.checked })}
                          />
                          <span>Principal</span>
                        </label>
                        <Button
                          type="button"
                          className="icon-btn-danger"
                          onClick={() => removeContact(idx)}
                          aria-label="Eliminar"
                        >
                          <Trash2 size={14} />
                        </Button>
                      </div>
                    </div>
                    
                    <div className="opportunity-contact-editor-body">
                      {c.kind === "linkedin" && isUrl(c.value) ? (
                        <a
                          href={c.value}
                          target="_blank"
                          rel="noreferrer"
                          className="link-button"
                          style={{ fontSize: "0.9rem" }}
                        >
                          Ver perfil →
                        </a>
                      ) : (
                        <Input
                          type="text"
                          value={c.value}
                          onChange={(e) => updateContact(idx, { value: e.target.value })}
                          maxLength={500}
                          placeholder="Valor del contacto..."
                          className="ui-input--minimal-value"
                        />
                      )}
                      
                      <div className="opportunity-contact-editor-meta">
                        <div className="input-with-badge-mini">
                          {c.note && isUrl(c.note) && (
                            <a
                              href={c.note}
                              target="_blank"
                              rel="noreferrer"
                              className="contact-source-badge-micro"
                              title="Ver fuente"
                            >
                              <ExternalLink size={8} />
                            </a>
                          )}
                          <Input
                            type="text"
                            value={c.note ?? ""}
                            onChange={(e) => updateContact(idx, { note: e.target.value || null })}
                            maxLength={500}
                            placeholder="Nota o fuente"
                            className="ui-input--minimal-meta"
                          />
                        </div>
                      </div>
                    </div>
                  </div>
              </li>
            ))}
          </ul>
        )}
        <Button
          type="button"
          className="cta-button"
          disabled={contactsMut.isPending || !contactsDirty}
          onClick={() => contactsMut.mutate(contactsDraft)}
        >
          {contactsMut.isPending ? <Loader2 className="spin" size={16} aria-hidden /> : null} Guardar contactos
        </Button>
      </Card>
      </div>

      <Card className="panel opportunity-card opportunity-bento-card opportunity-origin-card opportunity-ficha-area-origin">
        <h2 className="opportunity-card-title opportunity-card-title--flush">Origen</h2>
        <hr className="opportunity-card-divider" />
        <p className="muted-text" style={{ fontSize: "0.9rem", margin: 0 }}>
          {data.job_id
            ? `Búsqueda: "${sourceJobLabel}"`
            : data.source_url
              ? "Importada desde URL"
              : "Creada manualmente"}
        </p>
        {data.source_url ? (
          <p className="muted-text" style={{ fontSize: "0.9rem", marginTop: "6px" }}>
            Fuente:{" "}
            <a href={data.source_url} target="_blank" rel="noreferrer" className="link-button">
              {(() => { try { return new URL(data.source_url).hostname; } catch { return data.source_url; } })()}
            </a>
          </p>
        ) : null}
      </Card>

      <div className="opportunity-ficha-twin-row opportunity-ficha-area-twin">
        <Card className="panel opportunity-card opportunity-bento-card opportunity-bitacora-card">
          <div className="opportunity-bitacora-head">
            <h2 className="opportunity-card-title opportunity-card-title--flush">Bitácora de actividad</h2>
          </div>
          <hr className="opportunity-card-divider" />
          <div ref={bitacoraScrollRef} className="opportunity-bitacora-scroll">
            <ul className="opportunity-bitacora-feed">
              {timelineNewestFirst.map((entry, idx) => (
                <li key={`${entry.at}-${idx}`} className="opportunity-bitacora-feed-item">
                  <span className="opportunity-bitacora-feed-marker">
                    <BitacoraStageIcon stage={entry.stage} />
                  </span>
                  <div className="opportunity-bitacora-feed-body">
                    <div className="opportunity-bitacora-feed-title">
                      {opportunityStageLabel[entry.stage as OpportunityStageKey] ?? entry.stage}
                    </div>
                    <div className="opportunity-bitacora-feed-meta">
                      <time dateTime={entry.at}>{formatWhen(entry.at)}</time>
                      <span className="opportunity-bitacora-feed-author">{entry.author}</span>
                    </div>
                    <p className="opportunity-bitacora-feed-text">{entry.text}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <div className="opportunity-bitacora-form opportunity-bitacora-form--in-card">
            <label className="opportunity-field">
              <span>Nueva entrada</span>
              <textarea
                ref={bitacoraTextareaRef}
                value={bitacoraText}
                onChange={(e) => setBitacoraText(e.target.value)}
                rows={3}
                maxLength={4000}
                placeholder="Registra una interacción o seguimiento…"
              />
            </label>
            <Button
              type="button"
              className="cta-button"
              disabled={bitacoraMut.isPending || !bitacoraText.trim()}
              onClick={() => bitacoraMut.mutate(bitacoraText.trim())}
            >
              {bitacoraMut.isPending ? <Loader2 className="spin" size={16} aria-hidden /> : null} Añadir a bitácora
            </Button>
          </div>
        </Card>

        <Card className="panel opportunity-card opportunity-bento-card" style={{ marginTop: "1rem" }}>
          <h2 className="opportunity-card-title opportunity-card-title--flush" style={{ fontSize: "1rem" }}>Actualizar fase</h2>
          <hr className="opportunity-card-divider" />

          {useDirectorySteps ? (
            <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "12px" }}>
              <Select
                value={stepDraft}
                onChange={(e) => setStepDraft(e.target.value)}
                style={{ flex: 1, fontSize: "0.85rem" }}
              >
                <option value="">Seleccionar fase…</option>
                {allDirSteps.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </Select>
              <Button
                type="button"
                className="cta-button"
                style={{ fontSize: "0.8rem", padding: "4px 10px", whiteSpace: "nowrap" }}
                disabled={!stepDraft || moveStepMut.isPending}
                onClick={() => { if (stepDraft) moveStepMut.mutate(stepDraft); }}
              >
                {moveStepMut.isPending ? <Loader2 className="spin" size={13} /> : null} Guardar
              </Button>
            </div>
          ) : (
            <div style={{ marginBottom: "12px" }}>
              <Select
                value={stageDraft}
                onChange={(e) => setStageDraft(e.target.value as OpportunityStageKey)}
                style={{ fontSize: "0.85rem", width: "100%" }}
              >
                {OPPORTUNITY_STAGES_ORDER.map((key) => (
                  <option key={key} value={key}>{opportunityStageLabel[key]}</option>
                ))}
              </Select>
              {stageDraft === "response" && (
                <Select
                  value={outcomeDraft}
                  onChange={(e) => setOutcomeDraft(e.target.value as OpportunityResponseOutcome)}
                  style={{ marginTop: "6px", fontSize: "0.85rem", width: "100%" }}
                >
                  {OUTCOMES.map((o) => <option key={o} value={o}>{responseOutcomeLabel[o]}</option>)}
                </Select>
              )}
              <Button
                type="button"
                className="cta-button"
                style={{ marginTop: "8px", fontSize: "0.8rem" }}
                disabled={patchMut.isPending}
                onClick={onSaveStage}
              >
                {patchMut.isPending ? <Loader2 className="spin" size={13} /> : null} Guardar fase
              </Button>
            </div>
          )}

          {data.terminated_at ? (
            <p className="muted-text" style={{ fontSize: "0.85rem" }}>
              Oportunidad {data.terminated_outcome === "won" ? "concluida" : "marcada como no válida"}.
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {confirmConcluded ? (
                <div>
                  <textarea
                    value={concludeNote}
                    onChange={(e) => setConcludeNote(e.target.value)}
                    placeholder="Nota de cierre (opcional)…"
                    rows={2}
                    maxLength={4000}
                    style={{ width: "100%", marginBottom: "6px", fontSize: "0.85rem" }}
                  />
                  <div style={{ display: "flex", gap: "6px" }}>
                    <Button
                      type="button"
                      className="cta-button"
                      style={{ fontSize: "0.8rem" }}
                      disabled={concludeMut.isPending}
                      onClick={() => concludeMut.mutate(concludeNote || undefined)}
                    >
                      {concludeMut.isPending ? <Loader2 className="spin" size={13} /> : null} Confirmar
                    </Button>
                    <Button type="button" onClick={() => setConfirmConcluded(false)} style={{ fontSize: "0.8rem" }}>Cancelar</Button>
                  </div>
                </div>
              ) : (
                <Button type="button" className="cta-button" style={{ fontSize: "0.85rem" }} onClick={() => setConfirmConcluded(true)}>
                  Marcar como Concluida
                </Button>
              )}

              {confirmInvalid ? (
                <div>
                  <textarea
                    value={invalidNote}
                    onChange={(e) => setInvalidNote(e.target.value)}
                    placeholder="Motivo (opcional)…"
                    rows={2}
                    maxLength={4000}
                    style={{ width: "100%", marginBottom: "6px", fontSize: "0.85rem" }}
                  />
                  <div style={{ display: "flex", gap: "6px" }}>
                    <Button
                      type="button"
                      className="cta-button danger-button"
                      style={{ fontSize: "0.8rem" }}
                      disabled={terminateMut.isPending}
                      onClick={() => terminateMut.mutate(invalidNote || undefined)}
                    >
                      {terminateMut.isPending ? <Loader2 className="spin" size={13} /> : null} Confirmar
                    </Button>
                    <Button type="button" onClick={() => setConfirmInvalid(false)} style={{ fontSize: "0.8rem" }}>Cancelar</Button>
                  </div>
                </div>
              ) : (
                <Button type="button" className="link-button danger-text" style={{ fontSize: "0.85rem" }} onClick={() => setConfirmInvalid(true)}>
                  Marcar como No Válida
                </Button>
              )}
            </div>
          )}
        </Card>

      </div>

      <EnrichContactModal
        isOpen={enrichModalOpen}
        onClose={() => setEnrichModalOpen(false)}
        isPending={enrichMut.isPending}
        isError={enrichMut.isError}
        stageIdx={enrichStageIdx}
        data={enrichMut.data ?? null}
        isSaving={contactsMut.isPending}
        saveError={contactsMut.isError}
        onSave={(selectedData) => {
          const newContacts = [...contactsDraft];
          let added = false;
          const getNote = () => selectedData.source_urls?.[0] ?? null;
          
          if (selectedData.email && !newContacts.some(c => c.value.toLowerCase().trim() === selectedData.email!.toLowerCase().trim())) {
            newContacts.push({ id: `enrich-${Date.now()}-e`, kind: "email", value: selectedData.email, note: getNote(), role: null, is_primary: newContacts.length === 0 });
            added = true;
          }
          if (selectedData.phone && !newContacts.some(c => c.value.toLowerCase().trim() === selectedData.phone!.toLowerCase().trim())) {
            newContacts.push({ id: `enrich-${Date.now()}-p`, kind: "phone", value: selectedData.phone, note: getNote(), role: null, is_primary: newContacts.length === 0 });
            added = true;
          }
          if (selectedData.whatsapp && !newContacts.some(c => c.value.toLowerCase().trim() === selectedData.whatsapp!.toLowerCase().trim())) {
            newContacts.push({ id: `enrich-${Date.now()}-w`, kind: "whatsapp", value: selectedData.whatsapp, note: getNote(), role: null, is_primary: newContacts.length === 0 });
            added = true;
          }
          
          if (added) {
            setContactsDraft(newContacts);
            setContactsDirty(true);
            contactsMut.mutate(newContacts);
          }
          setEnrichModalOpen(false);
        }}
      />
    </div>
  );
}
