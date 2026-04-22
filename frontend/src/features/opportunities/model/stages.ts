import type { OpportunityContactKind, OpportunityResponseOutcome, OpportunityStageKey } from "../../../types";

export const OPPORTUNITY_STAGES_ORDER: readonly OpportunityStageKey[] = [
  "first_contact",
  "presentation",
  "response",
  "documents_wait",
  "agreement_sign",
  "medicatel_profile",
] as const;

export const opportunityStageLabel: Record<OpportunityStageKey, string> = {
  first_contact: "Primer contacto",
  presentation: "Presentación",
  response: "Respuesta",
  documents_wait: "Espera de documentos",
  agreement_sign: "Firma de convenio",
  medicatel_profile: "Creación de perfil Medicatel",
};

/** Etiquetas breves solo para la línea horizontal del embudo en ficha. */
export const opportunityJourneyLabelShort: Record<OpportunityStageKey, string> = {
  first_contact: "Primer contacto",
  presentation: "Presentación",
  response: "Respuesta",
  documents_wait: "Entrega doc.",
  agreement_sign: "Firma convenio",
  medicatel_profile: "Perfil Medicatel",
};

export const responseOutcomeLabel: Record<OpportunityResponseOutcome, string> = {
  pending: "Pendiente",
  positive: "Afirmativa",
  negative: "Negativa",
};

export const contactKindLabel: Record<OpportunityContactKind, string> = {
  email: "Correo",
  phone: "Teléfono",
  whatsapp: "WhatsApp",
  linkedin: "LinkedIn",
  other: "Otro",
};
