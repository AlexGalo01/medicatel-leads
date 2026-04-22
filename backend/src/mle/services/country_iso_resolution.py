"""Resolución heurística de país a ISO 3166-1 alpha-2 para Exa userLocation y criterios de relevancia."""

from __future__ import annotations

import re
from typing import Final

# (iso2, substrings en minúsculas)
_COUNTRY_SUBSTRINGS: Final[list[tuple[str, tuple[str, ...]]]] = [
    ("HN", ("honduras",)),
    ("GT", ("guatemala",)),
    ("SV", ("el salvador", "salvador")),
    ("NI", ("nicaragua",)),
    ("CR", ("costa rica",)),
    ("PA", ("panama", "panamá")),
    ("MX", ("mexico", "méxico")),
    (
        "US",
        (
            "united states",
            "usa",
            "estados unidos",
            "u.s.a",
            "eeuu",
            "ee.uu",
            "new jersey",
            "new york",
            "california",
            "texas",
            "florida",
            "massachusetts",
            "illinois",
            "pennsylvania",
            "ohio",
            "georgia",
            "virginia",
            "washington",
            "colorado",
            "arizona",
            "tennessee",
            "maryland",
            "minnesota",
            "wisconsin",
            "missouri",
            "connecticut",
            "south carolina",
            "alabama",
            "louisiana",
            "kentucky",
            "oregon",
            "oklahoma",
        ),
    ),
    ("CA", ("canada", "canadá")),
    ("CO", ("colombia",)),
    ("VE", ("venezuela",)),
    ("EC", ("ecuador",)),
    ("PE", ("peru", "perú")),
    ("CL", ("chile",)),
    ("AR", ("argentina",)),
    ("BR", ("brasil", "brazil")),
    ("BO", ("bolivia",)),
    ("PY", ("paraguay",)),
    ("UY", ("uruguay",)),
    ("ES", ("españa", "spain", "espana")),
    ("EG", ("egypt", "egipto", "misr", "daqahliyah", "mit ghamr", "cairo", "giza", "alexandria")),
    ("DE", ("germany", "alemania", "deutschland")),
    ("FR", ("france", "francia")),
    ("GB", ("united kingdom", "reino unido", "england", "uk", "u.k")),
    ("IN", ("india",)),
]

# Marcadores de texto para saber si el snippet ya afirma el país objetivo (evita falsos positivos).
TARGET_COUNTRY_MARKERS: Final[dict[str, tuple[str, ...]]] = {
    "HN": (
        "honduras",
        "tegucigalpa",
        "san pedro sula",
        "choloma",
        "la ceiba",
        "comayagua",
        "roatan",
        "rótan",
        "utila",
        "copan",
        "el progreso",
        "puerto cortes",
        "puerto cortés",
    ),
    "GT": ("guatemala", "ciudad de guatemala", "mixco", "quetzaltenango", "(gt)"),
    "SV": ("el salvador", "san salvador", "santa ana", "(sv)"),
    "NI": ("nicaragua", "managua", "(ni)"),
    "CR": ("costa rica", "san jose", "san josé", "(cr)"),
    "PA": ("panama", "panamá", "ciudad de panama", "(pa)"),
    "MX": ("mexico", "méxico", "cdmx", "guadalajara", "monterrey", "(mx)"),
}


def _normalize_blob(*parts: str) -> str:
    return " ".join(p.lower() for p in parts if p and str(p).strip())


def extract_parenthesized_iso_codes(text: str) -> list[str]:
    """Detecta códigos ISO de dos letras típicos en ubicaciones tipo 'City (HN)'."""
    if not text:
        return []
    found: list[str] = []
    for m in re.finditer(r"\(([A-Za-z]{2})\)", text):
        code = m.group(1).upper()
        if code.isalpha() and len(code) == 2:
            found.append(code)
    return found


def resolve_country_iso2_from_text(*parts: str) -> str | None:
    """
    Devuelve el primer ISO2 que coincida por nombre de país o por '(XX)' en el texto combinado.
    Orden: códigos entre paréntesis (último suele ser país en LinkedIn), luego substrings.
    """
    blob = _normalize_blob(*parts)
    if not blob.strip():
        return None

    codes = extract_parenthesized_iso_codes(blob)
    for code in reversed(codes):
        if code.isalpha() and len(code) == 2:
            return code

    for iso2, needles in _COUNTRY_SUBSTRINGS:
        for n in needles:
            if n in blob:
                return iso2
    return None


def blob_has_target_country_markers(blob: str, target_iso: str | None) -> bool:
    """True si el texto menciona explícitamente el país/ciudad objetivo (códigos ISO o marcadores)."""
    if not target_iso or len(target_iso) != 2:
        return False
    t = target_iso.strip().upper()
    bl = blob.lower()
    if f"({t.lower()})" in bl:
        return True
    for m in TARGET_COUNTRY_MARKERS.get(t, ()):
        if m in bl:
            return True
    return False


def first_matching_non_target_country_iso(blob: str, target_iso: str | None) -> str | None:
    """
    Si el texto menciona otro país (palabra completa) y no hay marcadores del país objetivo,
    devuelve un ISO2 candidato (el del needle más largo que coincida).
    """
    if not target_iso or len(target_iso) != 2:
        return None
    if blob_has_target_country_markers(blob, target_iso):
        return None
    t = target_iso.strip().upper()
    bl = blob.lower()
    best: tuple[int, str] | None = None  # (-len, iso2)
    for iso2, needles in _COUNTRY_SUBSTRINGS:
        if iso2 == t:
            continue
        for n in needles:
            if len(n) < 4:
                continue
            try:
                if re.search(rf"\b{re.escape(n)}\b", bl):
                    key = (-len(n), iso2)
                    if best is None or key < best:
                        best = key
            except re.error:
                continue
    return best[1] if best else None
