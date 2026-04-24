export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

/**
 * Una señal que aborta si lo hace cualquiera de las dos (p. ej. cancelación de React Query + timeout).
 */
export function mergeAbortSignals(a: AbortSignal, b: AbortSignal): AbortSignal {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.any === "function") {
    return AbortSignal.any([a, b]);
  }
  const c = new AbortController();
  if (a.aborted || b.aborted) {
    c.abort();
    return c.signal;
  }
  const onAbort = (): void => {
    c.abort();
  };
  a.addEventListener("abort", onAbort);
  b.addEventListener("abort", onAbort);
  return c.signal;
}

/**
 * Combina about y resumen profesional de la API de perfil: evita duplicar si uno contiene al otro;
 * si aportan texto distinto, concatena (about primero).
 */
export function mergeProfileAboutText(about: string, professionalSummary: string, fallback: string): string {
  const aboutT = about.trim();
  const proT = professionalSummary.trim();
  if (aboutT && proT) {
    if (aboutT === proT) return aboutT;
    if (aboutT.includes(proT) || proT.includes(aboutT)) {
      return aboutT.length >= proT.length ? aboutT : proT;
    }
    return `${aboutT}\n\n${proT}`;
  }
  if (aboutT) return aboutT;
  if (proT) return proT;
  return fallback.trim() || "Sin resumen disponible.";
}

