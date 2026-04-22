from __future__ import annotations

from typing import Any

from mle.clients.gemini_client import GeminiClient
from mle.core.config import get_settings

# Límites alineados con el prompt y la API; el truncado a fin de palabra evita comas o frases a medias.
PROFESSIONAL_SUMMARY_MAX_LEN = 400
ABOUT_MAX_LEN = 320


def _fallback_interpret(source_text: str) -> dict[str, str | None]:
    trimmed = source_text.strip()
    if not trimmed:
        return {
            "normalized_name": None,
            "normalized_company": None,
            "normalized_specialty": None,
        }

    name_part, _, rest = trimmed.partition("|")
    normalized_name = name_part.strip() or None
    remaining = rest.strip() if rest else ""
    normalized_company: str | None = None
    normalized_specialty: str | None = None

    if remaining:
        lower = remaining.lower()
        if " en " in lower:
            left, _, right = remaining.partition(" en ")
            normalized_specialty = left.strip() or None
            normalized_company = right.split("/")[0].strip() or None
        else:
            normalized_specialty = remaining.split("/")[0].strip() or None

    return {
        "normalized_name": normalized_name,
        "normalized_company": normalized_company,
        "normalized_specialty": normalized_specialty,
    }


async def interpret_profile_texts(texts: list[str]) -> list[dict[str, str | None]]:
    normalized_inputs = [text.strip() for text in texts if text.strip()]
    if not normalized_inputs:
        return []

    settings = get_settings()
    client = GeminiClient(api_key=settings.google_api_key, model_name=settings.google_model)
    prompt = (
        "Extrae nombre, empresa y especialidad de cada texto de perfil.\n"
        "Responde SOLO JSON con forma exacta:\n"
        '{"items":[{"source_text":"...","normalized_name":"...","normalized_company":"...","normalized_specialty":"..."}]}\n'
        "Reglas:\n"
        "- Si no puedes inferir un campo, usa null.\n"
        "- No inventes datos.\n"
        "- Conserva español.\n"
        f"Textos: {normalized_inputs}"
    )

    try:
        parsed = await client.complete_json_prompt(prompt)
        items = parsed.get("items")
        if not isinstance(items, list):
            raise ValueError("Respuesta invalida")

        by_source: dict[str, dict[str, str | None]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source_text", "")).strip()
            if not source:
                continue
            by_source[source] = {
                "normalized_name": str(item.get("normalized_name")).strip() or None
                if item.get("normalized_name") is not None
                else None,
                "normalized_company": str(item.get("normalized_company")).strip() or None
                if item.get("normalized_company") is not None
                else None,
                "normalized_specialty": str(item.get("normalized_specialty")).strip() or None
                if item.get("normalized_specialty") is not None
                else None,
            }

        response: list[dict[str, str | None]] = []
        for source in normalized_inputs:
            response.append(by_source.get(source) or _fallback_interpret(source))
        return response
    except Exception:
        return [_fallback_interpret(text) for text in normalized_inputs]


def _truncate_at_word_boundary(cleaned: str, max_len: int) -> str:
    """Recorta a max_len preferiendo el último espacio para no dejar oraciones a medias."""
    if len(cleaned) <= max_len:
        return cleaned
    head = cleaned[:max_len]
    last_space = head.rfind(" ")
    # Evita retroceder demasiado (p. ej. un solo término muy largo se corta duro)
    min_keep = min(40, max(12, max_len // 3))
    if last_space > min_keep:
        head = head[:last_space]
    return head.rstrip(" ,;:").strip() or head.strip()


def _sanitize_summary_text(
    value: Any,
    *,
    max_len: int = 260,
    at_word_boundary: bool = False,
) -> str | None:
    if value is None:
        return None
    cleaned = str(value).replace("\n", " ").replace("\r", " ")
    cleaned = " ".join(cleaned.split()).strip()
    cleaned = cleaned.lstrip("#-* ").strip()
    if not cleaned:
        return None
    if len(cleaned) <= max_len:
        return cleaned
    if at_word_boundary:
        return _truncate_at_word_boundary(cleaned, max_len)
    return cleaned[:max_len].strip()


def _strip_markdown_noise(text: str) -> str:
    """Quita encabezados tipo ## / ### al inicio de línea y viñetas sueltas."""
    import re

    if not text or not str(text).strip():
        return ""
    lines = [re.sub(r"^#{1,6}\s+", "", line).rstrip() for line in str(text).splitlines()]
    cleaned = "\n".join(lines)
    cleaned = cleaned.replace("•", " ")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def _strip_social_noise(text: str) -> str:
    cleaned = text
    replacements = (
        (r"\b\d+\s+connections?\b", ""),
        (r"\b\d+\s+followers?\b", ""),
        (r"\bconnections?\b", ""),
        (r"\bfollowers?\b", ""),
    )
    import re

    for pattern, repl in replacements:
        cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _looks_like_raw_cv_blob(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    markers = (
        "## experience",
        "total experience",
        "connections",
        "followers",
        "department:",
        "level:",
        "at ",
    )
    return any(marker in lowered for marker in markers) or len(text) > 240


def _extract_experiences_from_blob(text: str) -> list[dict[str, str | None]]:
    normalized = _strip_markdown_noise(text)
    if not normalized:
        return []
    parts = normalized.split(" Experience ")
    blob = parts[-1] if len(parts) > 1 else normalized
    chunks = [chunk.strip() for chunk in blob.split(" at ") if chunk.strip()]
    experiences: list[dict[str, str | None]] = []
    for i in range(0, len(chunks) - 1, 2):
        role = _sanitize_summary_text(chunks[i], max_len=80)
        organization = _sanitize_summary_text(chunks[i + 1], max_len=100)
        if role:
            experiences.append(
                {
                    "role": role,
                    "organization": organization,
                    "period": None,
                }
            )
        if len(experiences) >= 3:
            break
    return experiences


def _fallback_profile_summary(
    *,
    title: str,
    specialty: str | None,
    city: str | None,
    snippet: str | None,
) -> dict[str, Any]:
    normalized_specialty = _sanitize_summary_text(specialty, max_len=100)
    summary = normalized_specialty or _sanitize_summary_text(_strip_social_noise(snippet or ""), max_len=180) or _sanitize_summary_text(title, max_len=180)
    company = None
    base_text = f"{title} {snippet or ''}".strip()
    if " en " in base_text.lower():
        left, _, right = base_text.partition(" en ")
        if left and right:
            maybe_company = right.split("|")[0].split("/")[0].strip()
            company = _sanitize_summary_text(maybe_company, max_len=120)
    location = _sanitize_summary_text(city, max_len=120)
    return {
        "professional_summary": summary,
        "company": company,
        "location": location,
        "about": _sanitize_summary_text(
            _strip_social_noise(_strip_markdown_noise(summary or "")),
            max_len=ABOUT_MAX_LEN,
        ),
        "experiences": _extract_experiences_from_blob(snippet or title),
    }


async def extract_profile_summary(
    *,
    title: str,
    specialty: str | None = None,
    city: str | None = None,
    snippet: str | None = None,
) -> dict[str, Any]:
    normalized_title = title.strip()
    normalized_specialty = (specialty or "").strip()
    normalized_city = (city or "").strip()
    normalized_snippet = (snippet or "").strip()
    fallback = _fallback_profile_summary(
        title=normalized_title,
        specialty=normalized_specialty or None,
        city=normalized_city or None,
        snippet=normalized_snippet or None,
    )
    if not any([normalized_title, normalized_specialty, normalized_city, normalized_snippet]):
        return {
            "professional_summary": None,
            "company": None,
            "location": None,
            "about": None,
            "experiences": [],
            "confidence": "low",
            "notes": "sin_datos",
        }

    settings = get_settings()
    client = GeminiClient(api_key=settings.google_api_key, model_name=settings.google_model)
    prompt = (
        "Analiza un perfil y responde SOLO JSON valido con esta forma exacta:\n"
        '{"professional_summary":"...","about":"...","experiences":[{"role":"...","organization":"...","period":"..."}],"company":"...","location":"...","confidence":"high|medium|low","notes":"..."}\n'
        "Reglas estrictas:\n"
        f"- professional_summary: maximo {PROFESSIONAL_SUMMARY_MAX_LEN} caracteres, 1-2 frases, sin markdown. Termina frase completa (sin dejar comas o listas a medias).\n"
        f"- about: maximo {ABOUT_MAX_LEN} caracteres, resumen profesional 1-3 lineas, sin markdown. Termina frase completa.\n"
        "- experiences: 1 a 3 entradas maximo si existe evidencia.\n"
        "- company: solo organizacion/empresa principal o null.\n"
        "- location: ciudad/pais corto o null.\n"
        "- No copies bloques crudos de CV/LinkedIn.\n"
        "- Si no hay suficiente evidencia en algun campo, usa null.\n"
        "- Responde en espanol.\n"
        f"TITULO: {normalized_title}\n"
        f"ESPECIALIDAD: {normalized_specialty}\n"
        f"UBICACION: {normalized_city}\n"
        f"SNIPPET: {normalized_snippet}"
    )
    try:
        parsed = await client.complete_json_prompt(prompt)
        pro_stripped = _strip_social_noise(_strip_markdown_noise(str(parsed.get("professional_summary", ""))))
        about_stripped = _strip_social_noise(_strip_markdown_noise(str(parsed.get("about", ""))))
        is_blob = _looks_like_raw_cv_blob(pro_stripped)
        if is_blob:
            professional_summary = fallback.get("professional_summary")
            about = fallback.get("about")
        else:
            professional_summary = _sanitize_summary_text(
                pro_stripped, max_len=PROFESSIONAL_SUMMARY_MAX_LEN, at_word_boundary=True
            )
            about = _sanitize_summary_text(
                about_stripped, max_len=ABOUT_MAX_LEN, at_word_boundary=True
            )

        company = _sanitize_summary_text(parsed.get("company"), max_len=120)
        location = _sanitize_summary_text(parsed.get("location"), max_len=120)
        experiences_raw = parsed.get("experiences")
        experiences: list[dict[str, str | None]] = []
        if not is_blob and isinstance(experiences_raw, list):
            for item in experiences_raw:
                if not isinstance(item, dict):
                    continue
                role = _sanitize_summary_text(_strip_markdown_noise(str(item.get("role", ""))), max_len=90)
                organization = _sanitize_summary_text(_strip_markdown_noise(str(item.get("organization", ""))), max_len=120)
                period = _sanitize_summary_text(_strip_markdown_noise(str(item.get("period", ""))), max_len=60)
                if role:
                    experiences.append({"role": role, "organization": organization, "period": period})
                if len(experiences) >= 3:
                    break
        elif is_blob:
            experiences = list(fallback.get("experiences") or [])

        confidence_raw = str(parsed.get("confidence") or "").strip().lower()
        confidence = confidence_raw if confidence_raw in ("high", "medium", "low") else "low"
        notes = _sanitize_summary_text(parsed.get("notes"), max_len=120)
        if is_blob:
            confidence = "low"
            notes = "fallback_blob_detection"
        if not professional_summary:
            professional_summary = fallback.get("professional_summary")
        if not about:
            about = fallback.get("about") or professional_summary
        about = (
            _sanitize_summary_text(
                _strip_social_noise(_strip_markdown_noise(about or "")),
                max_len=ABOUT_MAX_LEN,
                at_word_boundary=True,
            )
            or about
        )
        if not company:
            company = fallback.get("company")
        if not location:
            location = fallback.get("location")
        if not experiences:
            experiences = fallback.get("experiences") or []
        return {
            "professional_summary": professional_summary,
            "company": company,
            "location": location,
            "about": about,
            "experiences": experiences,
            "confidence": confidence,
            "notes": notes,
        }
    except Exception:
        return {
            "professional_summary": fallback.get("professional_summary"),
            "company": fallback.get("company"),
            "location": fallback.get("location"),
            "about": fallback.get("about"),
            "experiences": fallback.get("experiences") or [],
            "confidence": "low",
            "notes": "fallback_exception",
        }
