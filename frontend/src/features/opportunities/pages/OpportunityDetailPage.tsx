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
  ListFilter,
  Loader2,
  MessageSquare,
  PenLine,
  Phone,
  Plus,
  Presentation,
  Trash2,
} from "lucide-react";

import {
  deleteOpportunity,
  getSearchJobStatus,
  getOpportunity,
  patchOpportunity,
  postOpportunityBitacora,
  putOpportunityContacts,
  summarizeProfile,
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

/** Quita marcadores tipo ## / ### al inicio de línea (ruido típico del resumen automático). */
function stripMarkdownHeadingNoise(text: string): string {
  if (!text.trim()) return text;
  return text
    .split("\n")
    .map((line) => line.replace(/^#{1,6}\s+/u, "").trimEnd())
    .join("\n")
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
  const { canManageOpportunities } = usePermissions();
  const [stageDraft, setStageDraft] = useState<OpportunityStageKey | "">("");
  const [outcomeDraft, setOutcomeDraft] = useState<OpportunityResponseOutcome>("pending");
  const [stageNote, setStageNote] = useState("");
  const [bitacoraText, setBitacoraText] = useState("");
  const [contactsDraft, setContactsDraft] = useState<OpportunityContact[]>([]);
  const [contactsDirty, setContactsDirty] = useState(false);
  const [aboutDraft, setAboutDraft] = useState("");
  const [locationDraft, setLocationDraft] = useState("");
  const [cvDirty, setCvDirty] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const bitacoraScrollRef = useRef<HTMLDivElement>(null);
  const bitacoraTextareaRef = useRef<HTMLTextAreaElement>(null);
  const aboutTextareaRef = useRef<HTMLTextAreaElement>(null);

  const detailQuery = useQuery({
    queryKey: ["opportunity", opportunityId],
    queryFn: () => getOpportunity(opportunityId),
    enabled: Boolean(opportunityId),
  });

  const data = detailQuery.data;
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
  }, [cvDirty, data, profileSummaryQuery.data, profileSummaryQuery.isPending, profileSummaryQuery.isError, profileSummaryQuery.isSuccess]);

  useLayoutEffect(() => {
    const el = aboutTextareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(el.scrollHeight, 88)}px`;
  }, [aboutDraft]);

  const patchMut = useMutation({
    mutationFn: (body: { stage?: string; response_outcome?: string | null; note?: string | null }) =>
      patchOpportunity(opportunityId, body),
    onSuccess: (updated) => {
      queryClient.setQueryData(["opportunity", opportunityId], updated);
      setStageNote("");
    },
  });

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

  const deleteMut = useMutation({
    mutationFn: () => deleteOpportunity(opportunityId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["opportunities"] });
      navigate("/opportunities", { replace: true });
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
  const hasStoredProfileOverrides = Object.keys(storedProfileOverrides).length > 0;
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
      profile_cv: {
        about: aboutDraft,
        location: loc.length > 0 ? loc : null,
        experiences: null,
      },
    });
  };

  const restoreProfileCv = () => {
    profileCvMut.mutate({
      profile_cv: { about: null, location: null, experiences: null },
    });
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
                    onClick={() => {
                      if (!isPastPhase) setStageDraft(key);
                    }}
                    aria-current={current ? "step" : undefined}
                    aria-label={`Fase: ${opportunityStageLabel[key]}${current ? " (actual)" : ""}${isPastPhase ? " (completada, no se puede reactivar)" : ""}`}
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
        <p className="muted-text opportunity-journey-hint">
          Solo puedes avanzar: las fases ya superadas no se pueden volver a activar. Elige la siguiente fase y guarda abajo.
        </p>
      </Card>

      <Card className="panel opportunity-card opportunity-bento-card opportunity-summary-card opportunity-ficha-area-summary">
        <h1 className="opportunity-summary-title">{data.title || "Sin título"}</h1>
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
          <Button
            type="button"
            variant="outline"
            className="workspace-tool-btn"
            disabled={profileCvMut.isPending || !hasStoredProfileOverrides}
            onClick={() => restoreProfileCv()}
          >
            Restaurar resumen generado
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
            <h3 className="opportunity-card-subtitle">About</h3>
            <label className="opportunity-field opportunity-summary-cv-field">
              <span className="muted-text">Texto libre; se guarda en la oportunidad.</span>
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
                placeholder={aboutFieldWaitingIa ? "Generando resumen con la IA…" : undefined}
              />
            </label>
          </article>
          <article className="opportunity-summary-cv-block opportunity-summary-cv-block--experience">
            <h3 className="opportunity-card-subtitle">Experiencia</h3>
            {profileIaPending && !experienceFromOverride ? (
              <p className="muted-text opportunity-summary-ia-experience-waiting">
                <Loader2 className="spin" size={16} strokeWidth={2} aria-hidden />
                Cargando experiencia estructurada…
              </p>
            ) : profileExperiences.length > 0 ? (
              <ul className="opportunity-summary-experience-list">
                {profileExperiences.map((experience, index) => (
                  <li key={`${experience.role}-${index}`} className="opportunity-summary-experience-item">
                    <strong>{experience.role}</strong>
                    <span className="muted-text">
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
            <h3 className="opportunity-card-subtitle">Ubicación</h3>
            <label className="opportunity-field opportunity-summary-cv-field">
              <span className="muted-text">Ciudad, país o nota breve.</span>
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
            </label>
          </article>
          <article className="opportunity-summary-cv-block">
            <h3 className="opportunity-card-subtitle">Empresa</h3>
            <p className="muted-text">{profileCompany}</p>
          </article>
        </div>
      </Card>

      <div className="opportunity-ficha-area-bitacora opportunity-ficha-side-stack">
      <Card className="panel opportunity-card opportunity-bento-card opportunity-phase-card opportunity-phase-card--prominent">
        <h2 className="opportunity-card-title">Actualizar fase</h2>
        <div className="opportunity-stage-form opportunity-stage-form--bento">
          <label className="opportunity-field">
            <span>Fase</span>
            <Select
              value={stageDraft || data.stage}
              onChange={(e) => setStageDraft(e.target.value as OpportunityStageKey)}
            >
              {OPPORTUNITY_STAGES_ORDER.filter((_, i) => i >= stageIndex).map((k) => (
                <option key={k} value={k}>
                  {opportunityStageLabel[k]}
                </option>
              ))}
            </Select>
          </label>
          {(stageDraft || data.stage) === "response" ? (
            <label className="opportunity-field">
              <span>Resultado</span>
              <Select
                value={outcomeDraft}
                onChange={(e) => setOutcomeDraft(e.target.value as OpportunityResponseOutcome)}
              >
                {OUTCOMES.map((o) => (
                  <option key={o} value={o}>
                    {responseOutcomeLabel[o]}
                  </option>
                ))}
              </Select>
            </label>
          ) : null}
          <label className="opportunity-field">
            <span>Nota para la bitácora (opcional)</span>
            <textarea
              value={stageNote}
              onChange={(e) => setStageNote(e.target.value)}
              rows={2}
              maxLength={4000}
              placeholder="Qué ocurrió al cambiar de fase…"
            />
          </label>
          <Button
            type="button"
            className="cta-button opportunity-phase-save"
            disabled={patchMut.isPending || !stageDraft}
            onClick={() => onSaveStage()}
          >
            {patchMut.isPending ? <Loader2 className="spin" size={16} aria-hidden /> : null} Guardar fase
          </Button>
        </div>
        {patchMut.isError ? <p className="error-text">No se pudo guardar.</p> : null}
      </Card>

      <Card className="panel opportunity-card opportunity-bento-card opportunity-contacts-card">
        <div className="opportunity-panel-head">
          <h2 className="opportunity-card-title">Contactos</h2>
          <Button type="button" className="workspace-tool-btn" onClick={() => addContactRow()}>
            <Plus size={16} aria-hidden /> Añadir
          </Button>
        </div>
        {contactsDraft.length === 0 ? (
          <p className="muted-text">Aún no hay contactos. Añade correos, teléfonos u otros canales.</p>
        ) : (
          <ul className="opportunity-contact-editor-list">
            {contactsDraft.map((c, idx) => (
              <li key={c.id || idx} className="opportunity-contact-editor-card">
                <div className="opportunity-contact-editor-grid">
                  <label className="opportunity-field">
                    <span>Tipo</span>
                    <Select
                      value={c.kind}
                      onChange={(e) => updateContact(idx, { kind: e.target.value as OpportunityContactKind })}
                    >
                      {CONTACT_KINDS.map((k) => (
                        <option key={k} value={k}>
                          {contactKindLabel[k]}
                        </option>
                      ))}
                    </Select>
                  </label>
                  <label className="opportunity-field opportunity-field--grow">
                    <span>Valor</span>
                    <Input
                      type="text"
                      value={c.value}
                      onChange={(e) => updateContact(idx, { value: e.target.value })}
                      maxLength={500}
                    />
                  </label>
                  <label className="opportunity-field">
                    <span>Rol (opcional)</span>
                    <Input
                      type="text"
                      value={c.role ?? ""}
                      onChange={(e) => updateContact(idx, { role: e.target.value || null })}
                      maxLength={120}
                    />
                  </label>
                  <label className="opportunity-field opportunity-field--grow">
                    <span>Nota</span>
                    <Input
                      type="text"
                      value={c.note ?? ""}
                      onChange={(e) => updateContact(idx, { note: e.target.value || null })}
                      maxLength={500}
                    />
                  </label>
                  <label className="opportunity-field opportunity-field--checkbox">
                    <input
                      type="checkbox"
                      checked={c.is_primary}
                      onChange={(e) => updateContact(idx, { is_primary: e.target.checked })}
                    />
                    <span>Principal</span>
                  </label>
                </div>
                <Button
                  type="button"
                  className="link-button opportunity-contact-remove"
                  onClick={() => removeContact(idx)}
                  aria-label="Eliminar contacto"
                >
                  <Trash2 size={16} aria-hidden />
                </Button>
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
        <dl className="opportunity-origin-dl opportunity-origin-dl--compact">
          <div>
            <dt>Trabajo de búsqueda</dt>
            <dd>Job de Búsqueda: "{sourceJobLabel}"</dd>
          </div>
          <div>
            <dt>URL fuente</dt>
            <dd>
              {data.source_url ? (
                <a href={data.source_url} target="_blank" rel="noreferrer" className="lead-source-anchor">
                  Abrir enlace
                  <ExternalLink size={14} aria-hidden />
                </a>
              ) : (
                "—"
              )}
            </dd>
          </div>
        </dl>
      </Card>

      <div className="opportunity-ficha-twin-row opportunity-ficha-area-twin">
        <Card className="panel opportunity-card opportunity-bento-card opportunity-bitacora-card">
          <div className="opportunity-bitacora-head">
            <h2 className="opportunity-card-title opportunity-card-title--flush">Bitácora de actividad</h2>
            <div className="opportunity-bitacora-toolbar">
              <Button
                type="button"
                className="opportunity-icon-btn"
                aria-label="Ir al inicio del historial"
                title="Ir al inicio del historial"
                onClick={() => bitacoraScrollRef.current?.scrollTo({ top: 0, behavior: "smooth" })}
              >
                <ListFilter size={18} aria-hidden />
              </Button>
              <Button
                type="button"
                className="opportunity-icon-btn"
                aria-label="Añadir entrada"
                onClick={() => {
                  bitacoraTextareaRef.current?.focus();
                  bitacoraTextareaRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
                }}
              >
                <Plus size={18} aria-hidden />
              </Button>
            </div>
          </div>
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

        {canManageOpportunities && (
          <Card className="panel opportunity-card" style={{ marginTop: "1.5rem" }}>
            <h2 className="opportunity-card-title opportunity-card-title--flush danger-text">Zona peligrosa</h2>
            {confirmDelete ? (
              <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", marginTop: "0.75rem" }}>
                <Button
                  className="cta-button danger-button"
                  disabled={deleteMut.isPending}
                  onClick={() => deleteMut.mutate()}
                >
                  {deleteMut.isPending ? <Loader2 className="spin" size={14} aria-hidden /> : <Trash2 size={14} aria-hidden />}
                  Confirmar eliminación
                </Button>
                <Button className="link-button" onClick={() => setConfirmDelete(false)}>
                  Cancelar
                </Button>
                {deleteMut.isError && <span className="error-text">{(deleteMut.error as Error).message}</span>}
              </div>
            ) : (
              <Button
                className="link-button danger-text"
                style={{ marginTop: "0.75rem" }}
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 size={14} aria-hidden /> Eliminar esta oportunidad
              </Button>
            )}
          </Card>
        )}

      </div>
    </div>
  );
}
