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
    title: "Directores de compras empresariales",
    shortLabel: "Compras + LinkedIn",
    category: "LinkedIn",
    fullPrompt:
      "Directores de compras en empresas manufactureras LATAM con perfil LinkedIn activo, experiencia B2B y señales de contacto profesional",
  },
  {
    id: "li-2",
    focus: "linkedin",
    title: "Gerentes de TI empresas medianas",
    shortLabel: "TI Gerencial",
    category: "LinkedIn",
    fullPrompt:
      "Gerentes de TI o CTO en empresas medianas de Centroamérica con presencia en LinkedIn y datos de contacto verificables",
  },
  {
    id: "li-3",
    focus: "linkedin",
    title: "Directores de operaciones",
    shortLabel: "Operaciones",
    category: "LinkedIn",
    fullPrompt:
      "Directores de operaciones o VP de operaciones en empresas de LATAM con práctica profesional verificable en LinkedIn y contacto indirecto visible",
  },
  {
    id: "ig-1",
    focus: "instagram",
    title: "Negocios con Instagram Business",
    shortLabel: "Negocios IG",
    category: "Redes",
    fullPrompt:
      "Negocios y pequeñas empresas en LATAM con cuenta Instagram Business activa, contacto por WhatsApp visible en bio o publicaciones",
  },
  {
    id: "ig-2",
    focus: "instagram",
    title: "Emprendedores B2B en redes",
    shortLabel: "Emprendimiento social",
    category: "Redes",
    fullPrompt:
      "Emprendedores y startups en LATAM con presencia en Instagram o LinkedIn enlazado, que muestren modelo de negocio y formas de contacto",
  },
  {
    id: "gen-1",
    focus: "general",
    title: "Distribuidores mayoristas",
    shortLabel: "Distribución mayorista",
    category: "General",
    fullPrompt:
      "Distribuidores mayoristas o proveedores de servicios en Centroamérica con email corporativo, teléfono de ventas o formulario de contacto claro",
  },
  {
    id: "gen-2",
    focus: "general",
    title: "Empresas logística y transporte",
    shortLabel: "Logística",
    category: "General",
    fullPrompt:
      "Empresas de logística, transporte y distribución en LATAM con página de contacto clara y datos del responsable comercial o gerencia",
  },
  {
    id: "gen-3",
    focus: "general",
    title: "Excluir directorios masivos",
    shortLabel: "Sin Excel / directorios",
    category: "Calidad",
    fullPrompt:
      "Empresas y profesionales en LATAM con contacto directo y sitio web propio; excluir filas tipo Excel, directorios masivos sin dato de contacto individual y listados anónimos",
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
