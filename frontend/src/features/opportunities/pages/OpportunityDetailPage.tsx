import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  Building2,
  Check,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Copy,
  ExternalLink,
  FileText,
  Loader2,
  Mail,
  MapPin,
  MessageSquare,
  PenLine,
  Phone,
  Plus,
  Presentation,
  Search,
  Trash2,
  X,
} from "lucide-react";

import {
  enrichOpportunity,
  getDirectory,
  getSearchJobStatus,
  getUrlScrapeJobStatus,
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

const AVATAR_PALETTE = [
  { bg: "#EEF2FF", color: "#4338CA" },
  { bg: "#F0FDF4", color: "#166534" },
  { bg: "#FFF7ED", color: "#9A3412" },
  { bg: "#FDF4FF", color: "#7E22CE" },
  { bg: "#F0F9FF", color: "#0369A1" },
  { bg: "#FFF1F2", color: "#9F1239" },
];

function getAvatarStyle(text: string) {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[h % AVATAR_PALETTE.length];
}

function initials(text: string): string {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

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

function contactKindIconEl(kind: OpportunityContactKind): JSX.Element {
  switch (kind) {
    case "email": return <Mail size={15} />;
    case "phone": return <Phone size={15} />;
    case "whatsapp": return <MessageSquare size={15} />;
    case "linkedin": return <ExternalLink size={15} />;
    default: return <ClipboardList size={15} />;
  }
}

function BitacoraStageIcon({ stage }: { stage: string }): JSX.Element {
  const key = stage as OpportunityStageKey;
  const iconProps = { size: 16, strokeWidth: 2, "aria-hidden": true as const };
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
  const [editingExpIndex, setEditingExpIndex] = useState<number | null>(null);
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
  const directoryStepsLoading = Boolean(data?.directory_id && directoryQuery.isLoading);

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

  const scrapeJobQuery = useQuery({
    queryKey: ["scrape-job-status", data?.scrape_job_id],
    queryFn: () => getUrlScrapeJobStatus(data!.scrape_job_id!),
    enabled: Boolean(data?.scrape_job_id),
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
      const aiCompany = profileSummaryQuery.data?.company?.trim() || "";
      setCompanyDraft(["null", "undefined", "N/A", "n/a"].includes(aiCompany) ? "" : aiCompany);
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
    const i = OPPORTUNITY_STAGES_ORDER.indexOf(stageDraft || data.stage);
    return i >= 0 ? i : 0;
  }, [data, stageDraft]);

  const journeyFillPct = useMemo(() => {
    const n = OPPORTUNITY_STAGES_ORDER.length;
    if (n <= 1) return 0;
    return (stageIndex / (n - 1)) * 100;
  }, [stageIndex]);

  // journeyFillPct is computed but used only for reference; keep to avoid lint issues
  void journeyFillPct;

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
    if (!stageDraft || data.terminated_at) return;
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
  const storedProfileOverrides = data.profile_overrides ?? {};
  const profileIaPending = profileSummaryQuery.isPending && !cvDirty;
  const aboutFieldWaitingIa = profileIaPending && !objectHasOwn(storedProfileOverrides, "about");
  const locationFieldWaitingIa = profileIaPending && !objectHasOwn(storedProfileOverrides, "location");
  const experienceFromOverride =
    objectHasOwn(storedProfileOverrides, "experiences") &&
    Array.isArray(storedProfileOverrides.experiences) &&
    (storedProfileOverrides.experiences?.length ?? 0) > 0;

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

  const avatarStyle = getAvatarStyle(data.title || "?");
  const companyDisplay = companyDraft && companyDraft !== "null" && companyDraft !== "undefined" ? companyDraft : null;

  const sectionLabelStyle: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 600,
    color: "#9CA3AF",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
  };

  const editBtnStyle: React.CSSProperties = {
    width: 26,
    height: 26,
    borderRadius: 6,
    border: "1px solid #E8E8EC",
    background: "white",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#6B7280",
    flexShrink: 0,
  };

  const iconActionBtnStyle: React.CSSProperties = {
    padding: "3px 6px",
    borderRadius: 4,
    border: "1px solid #E8E8EC",
    background: "white",
    cursor: "pointer",
    color: "#6B7280",
    display: "flex",
    alignItems: "center",
    fontSize: 12,
  };

  const inlineInputStyle: React.CSSProperties = {
    width: "100%",
    border: "none",
    borderBottom: "1px solid #E8E8EC",
    padding: "2px 0",
    fontSize: 13,
    background: "transparent",
    outline: "none",
    color: "#374151",
    fontFamily: "inherit",
  };

  return (
    <div className="opp-detail-v2">
      {/* ── Header ── */}
      <div className="opp-detail-header">
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <Link to="/opportunities" className="opp-detail-back-btn">
            <ChevronLeft size={15} /> Oportunidades
          </Link>
          <ChevronRight size={13} style={{ color: "#D0D0D8", flexShrink: 0 }} />
          <span style={{ fontSize: 14, fontWeight: 500, color: "#374151", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 320 }}>
            {data.title}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {data.terminated_at ? (
            <span style={{ fontSize: 13, fontWeight: 500, padding: "5px 14px", borderRadius: 20, background: data.terminated_outcome === "won" ? "#DCFCE7" : "#FEE2E2", color: data.terminated_outcome === "won" ? "#166534" : "#9F1239" }}>
              {data.terminated_outcome === "won" ? "Concluida" : "No válida"}
            </span>
          ) : (
            <>
              <button
                type="button"
                style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", fontSize: 13, fontWeight: 600, borderRadius: 8, border: "none", background: "#10B981", color: "white", cursor: "pointer" }}
                onClick={() => setConfirmConcluded(true)}
              >
                <Check size={14} /> Marcar como Ganada
              </button>
              <button
                type="button"
                style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", fontSize: 13, fontWeight: 600, borderRadius: 8, border: "1px solid #FECACA", background: "white", color: "#EF4444", cursor: "pointer" }}
                onClick={() => setConfirmInvalid(true)}
              >
                Marcar como Perdida
              </button>
            </>
          )}
        </div>
      </div>

      {/* ── Content ── */}
      <div className="opp-detail-content">
        <div className="opp-detail-grid">

          {/* ═══ LEFT COLUMN ═══ */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

            {/* Hero card */}
            <div className="opp-detail-card">
              <div style={{ padding: "20px 24px 22px" }}>
                <div style={{ display: "flex", gap: 18, alignItems: "flex-start" }}>
                  {/* Avatar */}
                  <div style={{ width: 72, height: 72, borderRadius: "50%", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22, fontWeight: 700, background: avatarStyle.bg, color: avatarStyle.color }}>
                    {initials(data.title || "?")}
                  </div>
                  <div style={{ flex: 1, minWidth: 0, paddingTop: 2 }}>
                    <input
                      type="text"
                      value={titleDraft}
                      onChange={(e) => setTitleDraft(e.target.value)}
                      onBlur={() => {
                        if (titleDraft.trim() !== data.title && titleDraft.trim()) {
                          patchMut.mutate({ title: titleDraft.trim() });
                        } else {
                          setTitleDraft(data.title || "");
                        }
                      }}
                      style={{ fontSize: 18, fontWeight: 700, color: "#0A0A0A", border: "none", outline: "none", background: "transparent", width: "100%", padding: 0, lineHeight: "1.3", fontFamily: "inherit" }}
                      placeholder="Nombre"
                    />
                    {data.specialty && (
                      <p style={{ margin: "3px 0 0", fontSize: 13, color: "#4F46E5", fontWeight: 500 }}>{data.specialty}</p>
                    )}
                    {companyDisplay && (
                      <p style={{ margin: "5px 0 0", fontSize: 13, color: "#6B7280", display: "flex", alignItems: "center", gap: 4 }}>
                        <Building2 size={12} /> {companyDisplay}
                      </p>
                    )}
                    {locationDraft && (
                      <p style={{ margin: "3px 0 0", fontSize: 13, color: "#6B7280", display: "flex", alignItems: "center", gap: 4 }}>
                        <MapPin size={12} /> {locationDraft}
                      </p>
                    )}
                  </div>
                  {data.source_url && (
                    <a
                      href={data.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title="Ver fuente original"
                      style={{ width: 30, height: 30, borderRadius: 7, border: "1px solid #E8E8EC", background: "white", display: "flex", alignItems: "center", justifyContent: "center", color: "#6B6B6B", flexShrink: 0 }}
                    >
                      <ExternalLink size={14} />
                    </a>
                  )}
                </div>
                <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
                  {data.owner && (
                    <p style={{ margin: 0, fontSize: 12, color: "#9B9BA8" }}>
                      A cargo: <span style={{ fontWeight: 500, color: "#6B7280" }}>{data.owner.display_name}</span>
                    </p>
                  )}
                  {directoryQuery.data && (
                    <p style={{ margin: 0, fontSize: 12, color: "#9B9BA8", display: "flex", alignItems: "center", gap: 4 }}>
                      Lista: <span style={{ fontWeight: 500, color: "#4F46E5" }}>{directoryQuery.data.name}</span>
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Contacts card */}
            <div className="opp-detail-card">
              <div className="opp-detail-card-header">
                <span style={{ fontSize: 14, fontWeight: 600, color: "#0A0A0A" }}>Contactos</span>
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    type="button"
                    className="dboard-btn"
                    onClick={() => { setEnrichModalOpen(true); setEnrichStageIdx(0); enrichMut.reset(); enrichMut.mutate(); }}
                  >
                    <Search size={13} /> Enriquecer
                  </button>
                  <button type="button" className="dboard-btn" onClick={() => addContactRow()}>
                    <Plus size={13} /> Añadir
                  </button>
                </div>
              </div>
              {contactsDraft.length === 0 ? (
                <p style={{ margin: 0, padding: "16px 20px", fontSize: 13, color: "#9B9BA8" }}>
                  Sin contactos. Añade correos, teléfonos u otros canales.
                </p>
              ) : (
                <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                  {contactsDraft.map((c, idx) => (
                    <li key={c.id || idx} className="opp-contact-row">
                      <div style={{ display: "flex", alignItems: "flex-start", gap: 10, flex: 1, minWidth: 0 }}>
                        <span style={{ color: "#6B7280", flexShrink: 0, paddingTop: 2 }}>
                          {contactKindIconEl(c.kind)}
                        </span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <Select
                            value={c.kind}
                            onChange={(e) => updateContact(idx, { kind: e.target.value as OpportunityContactKind })}
                            className="ui-select--minimal-bold"
                            style={{ marginBottom: 4 }}
                          >
                            {CONTACT_KINDS.map((k) => (
                              <option key={k} value={k}>{contactKindLabel[k].toUpperCase()}</option>
                            ))}
                          </Select>
                          {c.kind === "linkedin" && (isUrl(c.value) || c.value?.includes("linkedin.com")) ? (
                            <a href={c.value.startsWith("http") ? c.value : `https://${c.value}`} target="_blank" rel="noreferrer" style={{ fontSize: 13, color: "#4F46E5", fontWeight: 500, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}>
                              {data.title || "Ver perfil"} <ExternalLink size={11} />
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
                          {(() => {
                            const note = c.note && c.note !== "None" && c.note !== "null" ? c.note : null;
                            if (!note) return null;
                            return isUrl(note) ? (
                              <a href={note} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: "#9B9BA8", display: "flex", alignItems: "center", gap: 3, marginTop: 2 }}>
                                <ExternalLink size={10} /> Ver fuente
                              </a>
                            ) : (
                              <Input
                                type="text"
                                value={note}
                                onChange={(e) => updateContact(idx, { note: e.target.value || null })}
                                maxLength={500}
                                placeholder="Nota o fuente"
                                className="ui-input--minimal-meta"
                              />
                            );
                          })()}
                        </div>
                      </div>
                      <div className="opp-contact-row-actions">
                        {c.value && !isUrl(c.value) && (
                          <button
                            type="button"
                            title="Copiar"
                            onClick={() => navigator.clipboard.writeText(c.value)}
                            style={{ width: 26, height: 26, borderRadius: 6, border: "1px solid #E8E8EC", background: "white", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: "#6B7280" }}
                          >
                            <Copy size={12} />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => removeContact(idx)}
                          title="Eliminar"
                          style={{ width: 26, height: 26, borderRadius: 6, border: "1px solid #FECACA", background: "white", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: "#EF4444" }}
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {contactsDirty && (
                <div style={{ padding: "12px 20px", borderTop: "1px solid #F0F0F4" }}>
                  <Button
                    type="button"
                    className="cta-button"
                    style={{ fontSize: 13, padding: "7px 16px" }}
                    disabled={contactsMut.isPending}
                    onClick={() => contactsMut.mutate(contactsDraft)}
                  >
                    {contactsMut.isPending ? <Loader2 className="spin" size={14} aria-hidden /> : null} Guardar contactos
                  </Button>
                </div>
              )}
            </div>

            {/* Bio / CV card */}
            <div className="opp-detail-card">
              <div className="opp-detail-card-header">
                <span style={{ fontSize: 14, fontWeight: 600, color: "#0A0A0A" }}>Perfil</span>
                <Button
                  type="button"
                  className="cta-button"
                  style={{ fontSize: 12, padding: "5px 14px" }}
                  disabled={profileCvMut.isPending}
                  onClick={() => saveProfileCv()}
                >
                  {profileCvMut.isPending ? <Loader2 className="spin" size={13} aria-hidden /> : null} Guardar perfil
                </Button>
              </div>
              <div style={{ padding: "16px 20px 20px", display: "flex", flexDirection: "column", gap: 18 }}>
                {profileIaPending && (
                  <p style={{ margin: 0, fontSize: 12, color: "#9B9BA8", display: "flex", alignItems: "center", gap: 6 }}>
                    <Loader2 className="spin" size={13} aria-hidden /> Generando resumen con IA…
                  </p>
                )}
                {profileCvMut.isError && (
                  <p style={{ margin: 0, fontSize: 12, color: "#EF4444" }}>No se pudo guardar el perfil.</p>
                )}

                {data.contact_type === "company" ? (
                  <div>
                    {data.snippet ? <p style={{ margin: 0, fontSize: 13, color: "#6B7280", lineHeight: "1.6" }}>{data.snippet}</p> : <p style={{ margin: 0, fontSize: 13, color: "#9B9BA8" }}>Sin descripción.</p>}
                  </div>
                ) : (
                  <>
                    {/* Resumen */}
                    <div>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                        <span style={sectionLabelStyle}>Resumen</span>
                        {editingSection !== "about" && (
                          <button type="button" style={editBtnStyle} onClick={() => setEditingSection("about")} aria-label="Editar resumen">
                            <PenLine size={12} />
                          </button>
                        )}
                      </div>
                      {editingSection === "about" ? (
                        <div>
                          <textarea
                            ref={aboutTextareaRef}
                            value={aboutDraft}
                            onChange={(e) => { setCvDirty(true); setAboutDraft(e.target.value); }}
                            onInput={(e) => { const t = e.currentTarget; t.style.height = "auto"; t.style.height = `${t.scrollHeight}px`; }}
                            rows={1}
                            maxLength={8000}
                            spellCheck
                            readOnly={aboutFieldWaitingIa}
                            aria-busy={aboutFieldWaitingIa}
                            placeholder={aboutFieldWaitingIa ? "Generando resumen…" : "Añade descripción profesional..."}
                            style={{ width: "100%", border: "1px solid #E8E8EC", borderRadius: 6, padding: "6px 8px", fontSize: 13, lineHeight: "1.6", color: "#374151", background: "white", resize: "none", boxSizing: "border-box", fontFamily: "inherit", outline: "none", overflow: "hidden" }}
                          />
                          <div style={{ display: "flex", gap: 6, marginTop: 6, justifyContent: "flex-end" }}>
                            <button type="button" style={iconActionBtnStyle} onClick={() => setEditingSection(null)} title="Cancelar"><X size={13} /></button>
                            <button type="button" style={{ ...iconActionBtnStyle, color: "#4F46E5" }} disabled={profileCvMut.isPending} onClick={() => saveProfileCv()} title="Guardar"><Check size={13} /></button>
                          </div>
                        </div>
                      ) : aboutFieldWaitingIa ? (
                        <p style={{ margin: 0, fontSize: 13, color: "#9B9BA8", display: "flex", alignItems: "center", gap: 4 }}>
                          <Loader2 className="spin" size={12} aria-hidden /> Generando…
                        </p>
                      ) : (
                        <p style={{ margin: 0, fontSize: 13, lineHeight: "1.6", color: "#374151" }}>
                          {aboutDraft || <span style={{ color: "#9B9BA8" }}>Sin descripción.</span>}
                        </p>
                      )}
                    </div>

                    {/* Experiencia */}
                    <div>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                        <span style={sectionLabelStyle}>Experiencia</span>
                      </div>
                      {profileIaPending && !experienceFromOverride ? (
                        <p style={{ margin: 0, fontSize: 13, color: "#9B9BA8", display: "flex", alignItems: "center", gap: 4 }}>
                          <Loader2 className="spin" size={12} aria-hidden /> Cargando experiencia…
                        </p>
                      ) : (
                        <div>
                          {experiencesDraft.length === 0 && editingExpIndex === null && (
                            <p style={{ margin: "0 0 6px", fontSize: 13, color: "#9B9BA8" }}>Sin experiencia estructurada.</p>
                          )}
                          {experiencesDraft.map((exp, i) =>
                            editingExpIndex === i ? (
                              <div key={i} style={{ padding: "8px 10px", border: "1px solid #E8E8EC", borderRadius: 8, marginBottom: 6, background: "#FAFAFA" }}>
                                <input
                                  autoFocus
                                  value={exp.role}
                                  onChange={(e) => setExperiencesDraft((prev) => prev.map((x, j) => j === i ? { ...x, role: e.target.value } : x))}
                                  placeholder="Cargo / Rol"
                                  style={inlineInputStyle}
                                />
                                <input
                                  value={exp.organization}
                                  onChange={(e) => setExperiencesDraft((prev) => prev.map((x, j) => j === i ? { ...x, organization: e.target.value } : x))}
                                  placeholder="Organización"
                                  style={{ ...inlineInputStyle, fontSize: 11, color: "#6B7280", marginTop: 4 }}
                                />
                                <input
                                  value={exp.period}
                                  onChange={(e) => setExperiencesDraft((prev) => prev.map((x, j) => j === i ? { ...x, period: e.target.value } : x))}
                                  placeholder="Período"
                                  style={{ ...inlineInputStyle, fontSize: 11, color: "#6B7280", marginTop: 4 }}
                                />
                                <div style={{ display: "flex", gap: 6, marginTop: 8, alignItems: "center" }}>
                                  <button type="button" style={{ ...iconActionBtnStyle, color: "#EF4444" }} onClick={() => { setExperiencesDraft((prev) => prev.filter((_, j) => j !== i)); setEditingExpIndex(null); }}>
                                    <Trash2 size={12} />
                                  </button>
                                  <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
                                    <button type="button" style={iconActionBtnStyle} onClick={() => setEditingExpIndex(null)}><X size={12} /></button>
                                    <button type="button" style={{ ...iconActionBtnStyle, color: "#4F46E5" }} disabled={profileCvMut.isPending} onClick={() => { saveExperiences(); setEditingExpIndex(null); }}><Check size={12} /></button>
                                  </div>
                                </div>
                              </div>
                            ) : (
                              <div key={`${exp.role}-${i}`} style={{ display: "flex", alignItems: "flex-start", gap: 4, marginBottom: 6, paddingLeft: 4 }}>
                                <span style={{ color: "#9B9BA8", fontSize: 13, lineHeight: "1.5" }}>•</span>
                                <div style={{ flex: 1 }}>
                                  <strong style={{ fontSize: 13, fontWeight: 600 }}>{exp.role || <span style={{ color: "#9B9BA8" }}>Sin cargo</span>}</strong>
                                  <span style={{ fontSize: 12, color: "#6B7280", display: "block" }}>
                                    {[exp.organization || null, exp.period || null].filter(Boolean).join(" · ") || "Sin detalle"}
                                  </span>
                                </div>
                                <button type="button" style={editBtnStyle} onClick={() => setEditingExpIndex(i)} aria-label="Editar experiencia">
                                  <PenLine size={11} />
                                </button>
                              </div>
                            )
                          )}
                          <button
                            type="button"
                            className="link-button"
                            style={{ fontSize: "0.8rem", marginTop: 4 }}
                            onClick={() => { setExperiencesDraft((prev) => [...prev, { role: "", organization: "", period: "" }]); setEditingExpIndex(experiencesDraft.length); }}
                          >
                            <Plus size={13} /> Añadir experiencia
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Ubicación */}
                    <div>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                        <span style={sectionLabelStyle}>Ubicación</span>
                        <button type="button" style={editBtnStyle} onClick={() => setEditingSection(editingSection === "location" ? null : "location")} aria-label={editingSection === "location" ? "Cerrar edición" : "Editar ubicación"}>
                          <PenLine size={12} />
                        </button>
                      </div>
                      {editingSection === "location" ? (
                        <Input
                          value={locationDraft}
                          placeholder={locationFieldWaitingIa ? "Generando o usando ciudad de la ficha…" : LOCATION_PLACEHOLDER}
                          readOnly={locationFieldWaitingIa}
                          aria-busy={locationFieldWaitingIa}
                          onChange={(e) => { setCvDirty(true); setLocationDraft(e.target.value); }}
                          maxLength={500}
                          className="opportunity-summary-location-input"
                        />
                      ) : (
                        <p style={{ margin: 0, fontSize: 13, color: "#6B7280" }}>{locationDraft || LOCATION_PLACEHOLDER}</p>
                      )}
                    </div>

                    {/* Empresa */}
                    <div>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                        <span style={sectionLabelStyle}>Empresa</span>
                        <button type="button" style={editBtnStyle} onClick={() => setEditingSection(editingSection === "company" ? null : "company")} aria-label={editingSection === "company" ? "Cerrar edición" : "Editar empresa"}>
                          <PenLine size={12} />
                        </button>
                      </div>
                      {editingSection === "company" ? (
                        <div style={{ display: "flex", gap: 8 }}>
                          <Input value={companyDraft} onChange={(e) => setCompanyDraft(e.target.value)} placeholder="Empresa u organización" maxLength={120} className="opportunity-summary-location-input" />
                          <Button type="button" className="cta-button" style={{ fontSize: "0.8rem", padding: "4px 12px", whiteSpace: "nowrap" }} disabled={profileCvMut.isPending} onClick={saveCompany}>
                            {profileCvMut.isPending ? <Loader2 className="spin" size={13} /> : null} Guardar
                          </Button>
                        </div>
                      ) : (
                        <p style={{ margin: 0, fontSize: 13, color: "#6B7280" }}>{companyDisplay ?? "No especificada"}</p>
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Origen card */}
            <div className="opp-detail-card">
              <div className="opp-detail-card-header">
                <span style={{ fontSize: 14, fontWeight: 600, color: "#0A0A0A" }}>Origen</span>
              </div>
              <div style={{ padding: "12px 20px 16px", display: "flex", flexDirection: "column", gap: 4 }}>
                <p style={{ margin: 0, fontSize: 13, color: "#6B7280" }}>
                  {data.job_id
                    ? `Búsqueda: "${sourceJobLabel}"`
                    : data.scrape_job_id
                      ? "Importada desde URL"
                      : data.source_url
                        ? "Encontrada en búsqueda"
                        : "Creada manualmente"}
                </p>
                {data.scrape_job_id && scrapeJobQuery.data?.target_url ? (
                  <p style={{ margin: 0, fontSize: 12, color: "#9B9BA8" }}>
                    URL:{" "}
                    <a href={scrapeJobQuery.data.target_url} target="_blank" rel="noreferrer" style={{ color: "#4F46E5", textDecoration: "none" }}>
                      {(() => { try { return new URL(scrapeJobQuery.data.target_url).hostname; } catch { return scrapeJobQuery.data.target_url; } })()}
                    </a>
                  </p>
                ) : null}
                {data.source_url ? (
                  <p style={{ margin: 0, fontSize: 12, color: "#9B9BA8" }}>
                    Fuente:{" "}
                    <a href={data.source_url} target="_blank" rel="noreferrer" style={{ color: "#4F46E5", textDecoration: "none" }}>
                      {(() => { try { return new URL(data.source_url).hostname; } catch { return data.source_url; } })()}
                    </a>
                  </p>
                ) : null}
              </div>
            </div>

          </div>{/* end left column */}

          {/* ═══ RIGHT COLUMN ═══ */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

            {/* Confirm concluded – shows at top when active */}
            {confirmConcluded && (
              <div className="opp-detail-card" style={{ borderColor: "#86EFAC" }}>
                <div style={{ padding: "16px 20px" }}>
                  <p style={{ margin: "0 0 10px", fontSize: 14, fontWeight: 600, color: "#166534" }}>Confirmar cierre ganado</p>
                  <textarea
                    value={concludeNote}
                    onChange={(e) => setConcludeNote(e.target.value)}
                    placeholder="Nota de cierre (opcional)…"
                    rows={2}
                    maxLength={4000}
                    style={{ width: "100%", marginBottom: 10, fontSize: 13, border: "1px solid #BBF7D0", borderRadius: 8, padding: "8px 10px", boxSizing: "border-box", fontFamily: "inherit", outline: "none" }}
                  />
                  <div style={{ display: "flex", gap: 6 }}>
                    <Button type="button" className="cta-button" style={{ fontSize: 13, background: "#10B981", borderColor: "#10B981" }} disabled={concludeMut.isPending} onClick={() => concludeMut.mutate(concludeNote || undefined)}>
                      {concludeMut.isPending ? <Loader2 className="spin" size={13} /> : null} Confirmar
                    </Button>
                    <Button type="button" style={{ fontSize: 13 }} onClick={() => setConfirmConcluded(false)}>Cancelar</Button>
                  </div>
                </div>
              </div>
            )}

            {/* Recorrido card */}
            <div className="opp-detail-card">
              <div className="opp-detail-card-header">
                <span style={{ fontSize: 14, fontWeight: 600, color: "#0A0A0A" }}>Recorrido</span>
              </div>
              <div style={{ padding: "16px 20px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
                {directoryStepsLoading ? (
                  <p style={{ margin: 0, fontSize: 13, color: "#9B9BA8", display: "flex", alignItems: "center", gap: 6 }}>
                    <Loader2 className="spin" size={13} aria-hidden /> Cargando flujo…
                  </p>
                ) : useDirectorySteps ? (() => {
                  const rawIdx = allDirSteps.findIndex((s) => s.id === data.current_step_id);
                  const currentStepIdx = rawIdx >= 0 ? rawIdx : 0;
                  const effectiveStepId = rawIdx >= 0 ? data.current_step_id : allDirSteps[0]?.id;
                  const nextStepId = allDirSteps[currentStepIdx + 1]?.id;
                  return (
                    <>
                      <div>
                        {allDirSteps.map((step, idx) => {
                          const done = idx < currentStepIdx;
                          const current = step.id === effectiveStepId;
                          const isLast = idx === allDirSteps.length - 1;
                          return (
                            <div key={step.id} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
                                <div style={{ width: 22, height: 22, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, background: done ? "#10B981" : current ? "#4F46E5" : "#F3F4F6", color: done || current ? "white" : "#9CA3AF", flexShrink: 0 }}>
                                  {done ? <Check size={11} strokeWidth={3} /> : idx + 1}
                                </div>
                                {!isLast && <div style={{ width: 2, height: 20, background: done ? "#10B981" : "#E5E7EB", margin: "2px auto" }} />}
                              </div>
                              <div style={{ paddingTop: 3, paddingBottom: isLast ? 0 : 22, minWidth: 0 }}>
                                <span style={{ fontSize: 13, fontWeight: current ? 600 : 400, color: current ? "#4F46E5" : done ? "#374151" : "#9CA3AF", lineHeight: "1.3" }}>
                                  {step.name}
                                </span>
                                {step.is_terminal && (
                                  <span style={{ fontSize: 11, color: step.is_won ? "#10B981" : "#EF4444", display: "block" }}>
                                    {step.is_won ? "Ganada" : "Perdida"}
                                  </span>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      {!data.terminated_at && (
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                          {nextStepId && (
                            <Button
                              type="button"
                              className="cta-button"
                              style={{ fontSize: 13, padding: "8px 12px" }}
                              disabled={moveStepMut.isPending}
                              onClick={() => moveStepMut.mutate(nextStepId)}
                            >
                              {moveStepMut.isPending ? <Loader2 className="spin" size={13} aria-hidden /> : null} Avanzar Etapa
                            </Button>
                          )}
                          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                            <div style={{ flex: 1, position: "relative" }}>
                              <select
                                value={stepDraft}
                                onChange={(e) => setStepDraft(e.target.value)}
                                style={{
                                  width: "100%",
                                  appearance: "none",
                                  WebkitAppearance: "none",
                                  padding: "8px 32px 8px 12px",
                                  fontSize: 13,
                                  border: "1px solid #E2E8F0",
                                  borderRadius: 8,
                                  background: "white",
                                  color: stepDraft ? "#374151" : "#9CA3AF",
                                  cursor: "pointer",
                                  outline: "none",
                                  fontFamily: "inherit",
                                  boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
                                }}
                              >
                                <option value="">Mover a etapa…</option>
                                {allDirSteps.map((s) => (
                                  <option key={s.id} value={s.id}>{s.name}</option>
                                ))}
                              </select>
                              <ChevronRight size={14} style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%) rotate(90deg)", color: "#9CA3AF", pointerEvents: "none" }} />
                            </div>
                            {stepDraft && (
                              <Button type="button" className="cta-button" style={{ fontSize: 13, padding: "8px 14px", whiteSpace: "nowrap" }} disabled={moveStepMut.isPending} onClick={() => { if (stepDraft) moveStepMut.mutate(stepDraft); }}>
                                {moveStepMut.isPending ? <Loader2 className="spin" size={12} aria-hidden /> : null} Mover
                              </Button>
                            )}
                          </div>
                        </div>
                      )}
                    </>
                  );
                })() : (
                  <>
                    <div>
                      {OPPORTUNITY_STAGES_ORDER.map((key, idx) => {
                        const done = idx < stageIndex;
                        const current = idx === stageIndex;
                        const isLast = idx === OPPORTUNITY_STAGES_ORDER.length - 1;
                        return (
                          <div key={key} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
                              <button
                                type="button"
                                disabled={Boolean(data.terminated_at)}
                                onClick={() => { if (!data.terminated_at) setStageDraft(key); }}
                                style={{ width: 22, height: 22, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, background: done ? "#10B981" : current ? "#4F46E5" : "#F3F4F6", color: done || current ? "white" : "#9CA3AF", border: "none", cursor: data.terminated_at ? "default" : "pointer", padding: 0, flexShrink: 0 }}
                                aria-current={current ? "step" : undefined}
                              >
                                {done ? <Check size={11} strokeWidth={3} /> : idx + 1}
                              </button>
                              {!isLast && <div style={{ width: 2, height: 20, background: done ? "#10B981" : "#E5E7EB", margin: "2px auto" }} />}
                            </div>
                            <div style={{ paddingTop: 3, paddingBottom: isLast ? 0 : 22 }}>
                              <span style={{ fontSize: 13, fontWeight: current ? 600 : 400, color: current ? "#4F46E5" : done ? "#374151" : "#9CA3AF" }}>
                                {opportunityJourneyLabelShort[key]}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    {!data.terminated_at && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        <Select value={stageDraft} onChange={(e) => setStageDraft(e.target.value as OpportunityStageKey)} style={{ fontSize: "0.85rem", width: "100%" }}>
                          {OPPORTUNITY_STAGES_ORDER.map((key) => (
                            <option key={key} value={key}>{opportunityStageLabel[key]}</option>
                          ))}
                        </Select>
                        <input
                          type="text"
                          value={stageNote}
                          onChange={(e) => setStageNote(e.target.value)}
                          placeholder="Nota (opcional)"
                          maxLength={500}
                          style={{ width: "100%", padding: "6px 10px", border: "1px solid #E8E8EC", borderRadius: 7, fontSize: 13, color: "#374151", background: "white", outline: "none", boxSizing: "border-box", fontFamily: "inherit" }}
                        />
                        <Button type="button" className="cta-button" style={{ fontSize: 13 }} disabled={patchMut.isPending} onClick={onSaveStage}>
                          {patchMut.isPending ? <Loader2 className="spin" size={13} aria-hidden /> : null} Guardar fase
                        </Button>
                      </div>
                    )}
                  </>
                )}
                {data.terminated_at && (
                  <p style={{ margin: 0, fontSize: 13, color: "#9B9BA8" }}>
                    Oportunidad {data.terminated_outcome === "won" ? "concluida" : "marcada como no válida"}.
                  </p>
                )}
              </div>
            </div>

            {/* Bitácora card */}
            <div className="opp-detail-card">
              <div className="opp-detail-card-header">
                <span style={{ fontSize: 14, fontWeight: 600, color: "#0A0A0A" }}>Bitácora</span>
              </div>
              <div ref={bitacoraScrollRef} style={{ maxHeight: 300, overflowY: "auto" }}>
                {timelineNewestFirst.length === 0 ? (
                  <p style={{ margin: 0, padding: "16px 20px", fontSize: 13, color: "#9B9BA8" }}>Sin actividad registrada.</p>
                ) : (
                  <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                    {timelineNewestFirst.map((entry, idx) => (
                      <li key={`${entry.at}-${idx}`} style={{ display: "flex", gap: 12, padding: "11px 20px", borderBottom: "1px solid #F4F4F6" }}>
                        <span className="opportunity-bitacora-feed-marker" style={{ marginTop: 2, flexShrink: 0 }}>
                          <BitacoraStageIcon stage={entry.stage} />
                        </span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 500, color: "#0A0A0A" }}>
                            {opportunityStageLabel[entry.stage as OpportunityStageKey] ?? entry.stage}
                          </div>
                          <div style={{ fontSize: 11, color: "#9B9BA8", display: "flex", gap: 8, marginTop: 1 }}>
                            <time dateTime={entry.at}>{formatWhen(entry.at)}</time>
                            <span>{entry.author}</span>
                          </div>
                          {entry.text && (
                            <p style={{ margin: "4px 0 0", fontSize: 13, color: "#6B7280", lineHeight: "1.5" }}>{entry.text}</p>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div style={{ padding: "12px 20px", borderTop: "1px solid #F0F0F4", display: "flex", flexDirection: "column", gap: 8 }}>
                <textarea
                  ref={bitacoraTextareaRef}
                  value={bitacoraText}
                  onChange={(e) => setBitacoraText(e.target.value)}
                  rows={2}
                  maxLength={4000}
                  placeholder="Registra una interacción o seguimiento…"
                  style={{ width: "100%", border: "1px solid #E8E8EC", borderRadius: 8, padding: "8px 10px", fontSize: 13, color: "#374151", background: "white", resize: "vertical", boxSizing: "border-box", outline: "none", fontFamily: "inherit" }}
                />
                <Button
                  type="button"
                  className="cta-button"
                  style={{ fontSize: 13, alignSelf: "flex-start" }}
                  disabled={bitacoraMut.isPending || !bitacoraText.trim()}
                  onClick={() => bitacoraMut.mutate(bitacoraText.trim())}
                >
                  {bitacoraMut.isPending ? <Loader2 className="spin" size={14} aria-hidden /> : null} Añadir
                </Button>
              </div>
            </div>

            {/* Confirmar perdida */}
            {confirmInvalid && !data.terminated_at && (
              <div className="opp-detail-card" style={{ borderColor: "#FCA5A5" }}>
                <div style={{ padding: "16px 20px" }}>
                  <p style={{ margin: "0 0 10px", fontSize: 14, fontWeight: 600, color: "#9F1239" }}>Confirmar: Marcar como Perdida</p>
                  <textarea
                    value={invalidNote}
                    onChange={(e) => setInvalidNote(e.target.value)}
                    placeholder="Motivo (opcional)…"
                    rows={2}
                    maxLength={4000}
                    style={{ width: "100%", marginBottom: 10, fontSize: 13, border: "1px solid #FCA5A5", borderRadius: 8, padding: "8px 10px", boxSizing: "border-box", fontFamily: "inherit", outline: "none" }}
                  />
                  <div style={{ display: "flex", gap: 6 }}>
                    <Button type="button" className="cta-button danger-button" style={{ fontSize: 13 }} disabled={terminateMut.isPending} onClick={() => terminateMut.mutate(invalidNote || undefined)}>
                      {terminateMut.isPending ? <Loader2 className="spin" size={13} /> : null} Confirmar
                    </Button>
                    <Button type="button" style={{ fontSize: 13 }} onClick={() => setConfirmInvalid(false)}>Cancelar</Button>
                  </div>
                </div>
              </div>
            )}

          </div>{/* end right column */}

        </div>
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
