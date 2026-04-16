import type { SearchFocus } from "../types";

export type { SearchFocus };

export interface SearchSuggestionTemplate {
  id: string;
  focus: SearchFocus;
  title: string;
  shortLabel: string;
  fullPrompt: string;
  category?: string;
}

const ALL_SUGGESTIONS: SearchSuggestionTemplate[] = [
  {
    id: "li-1",
    focus: "linkedin",
    title: "Cardiólogos en LinkedIn",
    shortLabel: "Cardiología + LinkedIn",
    category: "LinkedIn",
    fullPrompt:
      "Cardiólogos en Honduras con perfil público en LinkedIn, experiencia hospitalaria y señales de contacto profesional",
  },
  {
    id: "li-2",
    focus: "linkedin",
    title: "Directores médicos",
    shortLabel: "Director médico",
    category: "LinkedIn",
    fullPrompt:
      "Directores médicos o jefes de clínica en Centroamérica con presencia en LinkedIn y datos de contacto verificables",
  },
  {
    id: "li-3",
    focus: "linkedin",
    title: "Oncólogos privados",
    shortLabel: "Oncología privada",
    category: "LinkedIn",
    fullPrompt:
      "Oncólogos en práctica privada en Tegucigalpa u otras ciudades de Honduras, priorizar URLs de LinkedIn y biografías profesionales",
  },
  {
    id: "ig-1",
    focus: "instagram",
    title: "Clínicas con Instagram",
    shortLabel: "Clínica + IG",
    category: "Redes",
    fullPrompt:
      "Clínicas privadas en Honduras con cuenta activa de Instagram, agenda o contacto por WhatsApp visible en la bio o publicaciones",
  },
  {
    id: "ig-2",
    focus: "instagram",
    title: "Dermatólogos en redes",
    shortLabel: "Dermatología social",
    category: "Redes",
    fullPrompt:
      "Dermatólogos con presencia en Instagram o TikTok enlazado, que muestren consultorio y formas de reserva o contacto",
  },
  {
    id: "gen-1",
    focus: "general",
    title: "Distribuidores equipo médico",
    shortLabel: "Distribución médica",
    category: "General",
    fullPrompt:
      "Distribuidores de equipo médico en Centroamérica con email corporativo, teléfono o formulario de contacto claro",
  },
  {
    id: "gen-2",
    focus: "general",
    title: "Hospitales con ginecología",
    shortLabel: "Ginecología hospital",
    category: "General",
    fullPrompt:
      "Hospitales con área de ginecología y obstetricia en Honduras, buscar página de staff o contacto de admisiones",
  },
  {
    id: "gen-3",
    focus: "general",
    title: "Excluir listados masivos",
    shortLabel: "Sin Excel / directorios",
    category: "Calidad",
    fullPrompt:
      "Médicos especialistas en Honduras con perfil propio o sitio web de consultorio; excluir filas tipo Excel, directorios masivos sin dato de contacto directo y listados anónimos",
  },
  {
    id: "gen-4",
    focus: "general",
    title: "WhatsApp prioritario",
    shortLabel: "WhatsApp primero",
    category: "General",
    fullPrompt:
      "Doctores y clínicas en Honduras donde se priorice encontrar número de WhatsApp de contacto o recepción verificable",
  },
];

function dayOfYear(date: Date): number {
  const start = Date.UTC(date.getUTCFullYear(), 0, 0);
  const diff = date.getTime() - start;
  return Math.floor(diff / 86400000);
}

function hashString(input: string): number {
  let h = 0;
  for (let i = 0; i < input.length; i += 1) {
    h = (h << 5) - h + input.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
}

/** Rota sugerencias de forma estable por día UTC y foco. */
export function getRotatedSuggestions(
  focus: SearchFocus,
  count: number,
  date: Date = new Date(),
): SearchSuggestionTemplate[] {
  const pool = ALL_SUGGESTIONS.filter((item) => item.focus === focus);
  const fallback = ALL_SUGGESTIONS;
  const source = pool.length > 0 ? pool : fallback;
  const seed = dayOfYear(date) + hashString(focus) * 997;
  const ordered = [...source].sort((a, b) => {
    const ka = `${seed}-${a.id}`;
    const kb = `${seed}-${b.id}`;
    return hashString(ka) - hashString(kb);
  });
  return ordered.slice(0, Math.min(count, ordered.length));
}

export function defaultChannelsForFocus(focus: SearchFocus): string[] {
  if (focus === "linkedin") {
    return ["email", "whatsapp", "linkedin"];
  }
  if (focus === "instagram") {
    return ["email", "whatsapp", "linkedin"];
  }
  return ["email", "whatsapp", "linkedin"];
}
