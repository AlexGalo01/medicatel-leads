"""Enriquecimiento profundo de contactos: Exa (texto + /contents) + OpenCLI + Gemini reviewer.

La función central `enrich_lead_contacts` es pura (no toca DB) — se usa desde
`auto_enrich_node` en lotes y desde el wrapper legacy `deep_enrich_lead` por id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from mle.clients.exa_client import ExaClient, exa_contents_full_config, finalize_exa_search_payload
from mle.clients.gemini_client import GeminiClient
from mle.clients.opencli_client import OpenCliClient
from mle.core.config import Settings, effective_exa_search_timeout_seconds, get_settings
from mle.db.base import async_session_factory
from mle.db.models import Lead
from mle.repositories.leads_repository import LeadsRepository
from mle.schemas.leads import LeadRead

logger = logging.getLogger(__name__)

NO_DATA_ES = "No se encontró información adicional verificable en las fuentes recuperadas."


@dataclass
class LeadCore:
    """Campos mínimos de un lead para alimentar el enriquecimiento (independiente del ORM)."""

    full_name: str
    specialty: str
    city: str
    country: str
    entity_type: str = "person"  # "person" | "company"
    linkedin_url: str = ""
    email: str = ""
    whatsapp: str = ""
    phone: str = ""
    address: str = ""
    schedule_text: str = ""
    primary_source_url: str = ""


@dataclass
class EnrichmentResult:
    email: str = ""
    whatsapp: str = ""
    phone: str = ""
    address: str = ""
    schedule_text: str = ""
    website: str = ""
    facebook_url: str = ""
    instagram_url: str = ""
    linkedin_url: str = ""
    description: str = ""
    primary_source_url: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    enriched_sources: dict[str, Any] = field(default_factory=dict)
    audit: list[dict[str, Any]] = field(default_factory=list)
    status: str = "no_verified_data"
    message: str = ""


# ---------------- Exa helpers ----------------


def _extract_results(search_response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_results = search_response.get("results", [])
    if isinstance(raw_results, list):
        return [r for r in raw_results if isinstance(r, dict)]
    return []


def _flatten_evidence(results: list[dict[str, Any]]) -> str:
    MAX_HEAD = 1400
    MAX_TAIL = 600
    parts: list[str] = []
    for index, item in enumerate(results):
        url = str(item.get("url", "")).strip()
        title = str(item.get("title", "")).strip()
        highlights = item.get("highlights", [])
        if not isinstance(highlights, list):
            highlights = []
        hl_join = " | ".join(str(h) for h in highlights[:8])
        text = str(item.get("text", ""))
        if len(text) > MAX_HEAD + MAX_TAIL:
            text_slice = text[:MAX_HEAD] + "\n[...]\n" + text[-MAX_TAIL:]
        else:
            text_slice = text
        parts.append(f"[{index}] URL: {url}\nTitulo: {title}\nHighlights: {hl_join}\nTexto: {text_slice}\n")
    return "\n".join(parts)


def _digits_only(raw: str) -> str:
    return re.sub(r"\D+", "", raw)


def _email_in_evidence(email: str, evidence_lower: str) -> bool:
    normalized = email.strip().lower()
    if "@" not in normalized or len(normalized) < 5:
        return False
    return normalized in evidence_lower


def _phone_in_evidence(phone: str, evidence_lower: str) -> bool:
    digits = _digits_only(phone)
    if len(digits) < 8:
        return False
    ev_digits = _digits_only(evidence_lower)
    return digits in ev_digits


def _linkedin_in_evidence(url: str, evidence_lower: str) -> bool:
    u = url.strip().lower()
    if "linkedin.com" not in u:
        return False
    if u in evidence_lower:
        return True
    return u.rstrip("/") in evidence_lower


def _is_crawlable_personal_site(url: str) -> bool:
    """Devuelve True si la URL vale la pena hacer deep-fetch (excluye redes sociales y directorios)."""
    u = url.lower()
    excluded = [
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "twitter.com",
        "x.com",
        "doctoralia.com",
        "healthgrades.com",
        "zocdoc.com",
        "webmd.com",
        "yelp.com",
        "google.com",
        "youtube.com",
        "tiktok.com",
        "reddit.com",
    ]
    return not any(exc in u for exc in excluded)


def _extract_regex_contacts(text: str, source_url: str) -> list[dict[str, str]]:
    """Extrae emails y teléfonos del texto crudo con regex.

    Devuelve lista de {field: "email"|"phone"|"whatsapp", value, source_url}.
    """
    contacts: list[dict[str, str]] = []
    text_lower = text.lower()

    # Extraer emails
    email_pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    for match in re.finditer(email_pattern, text):
        email = match.group()
        if not any(x in email.lower() for x in ["@example.com", "@test.", "@fake"]):
            contacts.append({"field": "email", "value": email.strip(), "source_url": source_url})

    # Extraer teléfonos LATAM (Honduras: 7-8 dígitos, prefijos +504, (504), etc.)
    phone_patterns = [
        r"\+504\s?(?:\()?(\d{4})?(?:\))?\s?(\d{4})",  # +504 XXXX-XXXX
        r"\(504\)\s?(\d{4})?[\s\-]?(\d{4})",           # (504) XXXX-XXXX
        r"(?:tel|phone|teléfono|telefono)[\s:]*\(?(\d{4})[\s\-]?(\d{4})\)?",
        r"(?:^|\s)(\d{4})[\s\-](\d{4})(?:\s|$)",       # XXXX-XXXX en contexto
    ]

    found_phones: set[str] = set()
    for pattern in phone_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            groups = [g for g in match.groups() if g]
            phone_str = "".join(groups) if groups else ""
            digits = _digits_only(phone_str)
            if 7 <= len(digits) <= 8 and digits not in ["0000000", "00000000"]:
                phone_formatted = f"{digits[:4]}-{digits[4:]}" if len(digits) == 8 else digits
                found_phones.add(phone_formatted)

    for phone in found_phones:
        contacts.append({"field": "phone", "value": phone, "source_url": source_url})

    # Detectar WhatsApp (número cercano a la palabra "whatsapp")
    whatsapp_pattern = r"(?:whatsapp|wa\.me|whatsapp\.com)[:\s/]*(\+?\d{1,3}[\s\-]?\d{3,4}[\s\-]?\d{4})"
    for match in re.finditer(whatsapp_pattern, text, re.IGNORECASE):
        whatsapp = match.group(1)
        digits = _digits_only(whatsapp)
        if 7 <= len(digits) <= 15:
            # Preferir el que ya encontramos como phone
            if not any(c["field"] == "whatsapp" and c["value"] == digits for c in contacts):
                contacts.append({"field": "whatsapp", "value": digits, "source_url": source_url})

    # Deduplicar por (field, value)
    seen = set()
    unique_contacts = []
    for c in contacts:
        key = (c["field"], c["value"].lower())
        if key not in seen:
            seen.add(key)
            unique_contacts.append(c)

    return unique_contacts


def _build_exa_search_payload(lead: LeadCore, settings: Settings) -> dict[str, Any]:
    parts = [
        lead.full_name,
        lead.specialty,
        lead.city,
        lead.country,
        "contacto email whatsapp telefono direccion horario sitio web",
    ]
    if lead.linkedin_url:
        parts.append(lead.linkedin_url)
    query = " ".join(p.strip() for p in parts if p and p.strip())
    payload: dict[str, Any] = {
        "query": query[:900],
        "type": settings.exa_search_type,
        "numResults": 18,
        "contents": exa_contents_full_config(
            text_max_characters=settings.exa_text_max_characters,
            highlights_max_characters=settings.exa_highlights_max_characters,
            subpages=settings.exa_subpages,
        ),
    }
    return finalize_exa_search_payload(payload)


async def _exa_evidence(
    exa_client: ExaClient,
    lead: LeadCore,
    settings: Settings,
) -> tuple[list[dict[str, Any]], str, list[dict[str, str]]]:
    """Combina /contents sobre primary_source_url (si existe) + /search genérica.

    Retorna (results, evidence_para_llm, regex_contacts_directos).
    """
    results: list[dict[str, Any]] = []
    if lead.primary_source_url:
        try:
            contents_payload: dict[str, Any] = {
                "ids": [lead.primary_source_url],
                "text": {"maxCharacters": settings.exa_text_max_characters},
                "highlights": {"maxCharacters": settings.exa_highlights_max_characters},
                "subpages": settings.exa_subpages,
            }
            contents_response = await exa_client.get_contents(contents_payload)
            results.extend(_extract_results(contents_response))
        except Exception as exc:  # noqa: BLE001
            logger.info("Exa /contents para %s falló (degrade safe): %s", lead.primary_source_url, exc)

    try:
        search_payload = _build_exa_search_payload(lead, settings)
        search_response = await exa_client.search(search_payload)
        results.extend(_extract_results(search_response))
    except Exception as exc:  # noqa: BLE001
        logger.info("Exa /search para %s falló (degrade safe): %s", lead.full_name, exc)

    evidence = _flatten_evidence(results)

    # Extraer contacts con regex del texto completo (no truncado)
    regex_contacts: list[dict[str, str]] = []
    for item in results:
        if isinstance(item, dict) and item.get("text"):
            regex_contacts.extend(_extract_regex_contacts(item["text"], item.get("url", "")))
        # También extraer de subpages
        for sp in item.get("subpages", []) if isinstance(item, dict) else []:
            if isinstance(sp, dict) and sp.get("text"):
                regex_contacts.extend(_extract_regex_contacts(sp["text"], sp.get("url", "")))

    return results, evidence, regex_contacts


async def _deep_fetch_contacts(
    exa_client: ExaClient,
    search_results: list[dict[str, Any]],
    settings: Settings,
) -> list[dict[str, str]]:
    """Hace un get_contents() profundo (50K chars) sobre el top URL personal.

    Busca el primer resultado que no sea social media ni directory (ya fetched).
    Retorna lista de contactos extraídos con regex del texto completo.
    """
    if not search_results:
        return []

    # Filtrar URLs crawleables (excluir sociales, directorios, etc.)
    candidates = [
        r for r in search_results
        if isinstance(r, dict) and _is_crawlable_personal_site(r.get("url", ""))
    ]

    if not candidates:
        return []

    # Tomar el primer candidato
    target_url = candidates[0].get("url", "")
    if not target_url:
        return []

    try:
        payload: dict[str, Any] = {
            "ids": [target_url],
            "text": {"maxCharacters": 50000},
            "highlights": {"maxCharacters": 8000},
            "subpages": 3,
        }
        response = await exa_client.get_contents(payload)
        results = _extract_results(response)

        deep_contacts: list[dict[str, str]] = []
        for item in results:
            if isinstance(item, dict) and item.get("text"):
                deep_contacts.extend(_extract_regex_contacts(item["text"], item.get("url", "")))
            for sp in item.get("subpages", []) if isinstance(item, dict) else []:
                if isinstance(sp, dict) and sp.get("text"):
                    deep_contacts.extend(_extract_regex_contacts(sp["text"], sp.get("url", "")))

        return deep_contacts
    except Exception as exc:  # noqa: BLE001
        logger.info("Deep fetch para %s falló (degrade safe): %s", target_url, exc)
        return []


# ---------------- OpenCLI evidence ----------------


async def _opencli_evidence(
    opencli: OpenCliClient,
    lead: LeadCore,
    prefetched_maps: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lanza adapters OpenCLI en paralelo y retorna dict por fuente.

    Para empresas: query simplificada (solo nombre + ciudad).
    Para personas: query completa (nombre + especialidad + ciudad).
    Para empresas: Facebook e Instagram siempre habilitados.
    Si prefetched_maps está disponible, usa esos datos en lugar de llamar a Google Maps.
    """
    if not opencli.enabled:
        return {}

    is_company = lead.entity_type == "company"

    if is_company:
        # Para empresas: solo nombre + ciudad para no confundir Google Maps
        google_q = lead.full_name.strip()
        if lead.city:
            google_q = f"{google_q} {lead.city}".strip()
        maps_q = google_q
    else:
        # Para personas: nombre + especialidad + ciudad (comportamiento original)
        name_query = lead.full_name.strip()
        if lead.specialty:
            name_query = f"{name_query} {lead.specialty}".strip()
        if lead.city:
            name_query = f"{name_query} {lead.city}".strip()
        google_q = maps_q = name_query

    out: dict[str, Any] = {}

    # Si ya tenemos datos de Google Maps prefetched, usarlos directamente
    if prefetched_maps and isinstance(prefetched_maps, dict):
        out["google_maps"] = prefetched_maps
        tasks = {
            "google_search": opencli.google_search(google_q),
        }
    else:
        tasks = {
            "google_search": opencli.google_search(google_q),
            "google_maps": opencli.google_maps(maps_q),
        }

    # Doctoralia solo para personas
    if not is_company:
        tasks["doctoralia"] = opencli.doctoralia(lead.full_name, lead.specialty, lead.city)

    # Para empresas: Facebook e Instagram siempre activados
    # Para personas: solo si está habilitado en settings
    if is_company or opencli.include_facebook:
        tasks["facebook"] = opencli.facebook_page(google_q)
    if is_company or opencli.include_instagram:
        tasks["instagram"] = opencli.instagram_profile(google_q)

    keys = list(tasks.keys())
    values = await asyncio.gather(*tasks.values(), return_exceptions=True)

    for k, v in zip(keys, values, strict=False):
        if isinstance(v, Exception):
            logger.info("OpenCLI %s levantó excepción: %s", k, v)
            continue
        if isinstance(v, dict) and v:
            out[k] = v
    return out


def _merge_opencli_contacts(opencli_results: dict[str, Any]) -> dict[str, str]:
    """Prioriza fuentes por confiabilidad: maps > search > doctoralia > redes.

    Extrae también URLs de redes sociales (facebook_url, instagram_url) desde profile_url.
    """
    priority = ["google_maps", "google_search", "doctoralia", "facebook", "instagram"]
    merged: dict[str, str] = {
        "phone": "",
        "address": "",
        "schedule_text": "",
        "website": "",
        "email": "",
        "facebook_url": "",
        "instagram_url": "",
    }

    for src in priority:
        data = opencli_results.get(src) or {}
        if not isinstance(data, dict):
            continue
        for target, candidates in (
            ("phone", ["phone"]),
            ("address", ["address"]),
            ("schedule_text", ["hours", "schedule_text"]),
            ("website", ["website"]),
            ("email", ["email"]),
        ):
            if merged[target]:
                continue
            for key in candidates:
                v = data.get(key)
                if isinstance(v, str) and v.strip():
                    merged[target] = v.strip()
                    break

    # Extraer URLs de redes sociales desde profile_url
    if not merged["facebook_url"]:
        fb_data = opencli_results.get("facebook") or {}
        if isinstance(fb_data, dict):
            profile_url = fb_data.get("profile_url")
            if isinstance(profile_url, str) and profile_url.strip():
                merged["facebook_url"] = profile_url.strip()

    if not merged["instagram_url"]:
        ig_data = opencli_results.get("instagram") or {}
        if isinstance(ig_data, dict):
            profile_url = ig_data.get("profile_url")
            if isinstance(profile_url, str) and profile_url.strip():
                merged["instagram_url"] = profile_url.strip()

    return merged


# ---------------- Prompts ----------------


def _proposer_prompt(evidence: str, lead: LeadCore, opencli_contacts: dict[str, str]) -> str:
    ctx = json.dumps(
        {
            "full_name": lead.full_name,
            "specialty": lead.specialty,
            "city": lead.city,
            "country": lead.country,
            "linkedin_url_known": lead.linkedin_url,
            "email_known": lead.email,
            "whatsapp_known": lead.whatsapp,
            "opencli_phone": opencli_contacts.get("phone", ""),
            "opencli_address": opencli_contacts.get("address", ""),
            "opencli_hours": opencli_contacts.get("schedule_text", ""),
        },
        ensure_ascii=False,
    )
    return (
        "Eres analista de datos de contacto B2B médico. SOLO puedes usar datos que aparezcan literalmente en EVIDENCIA.\n"
        "Si un dato no está escrito en EVIDENCIA, deja cadena vacía. No infieras ni completes.\n\n"
        f"CONTEXTO_LEAD_JSON: {ctx}\n\n"
        f"EVIDENCIA:\n{evidence}\n\n"
        "Devuelve SOLO JSON con claves exactas:\n"
        '{"description": "texto breve en español solo con hechos de EVIDENCIA, máximo 600 caracteres", '
        '"email": "", "whatsapp": "", "linkedin_url": ""}\n'
        "email, whatsapp y linkedin_url deben ser copias exactas de fragmentos de EVIDENCIA o vacíos."
    )


def _reviewer_prompt(evidence: str, proposal: dict[str, Any]) -> str:
    proposal_txt = json.dumps(proposal, ensure_ascii=False)
    return (
        "Eres un auditor estricto anti-alucinaciones. Recibes EVIDENCIA (texto) y una PROPUESTA_JSON.\n"
        "Tu trabajo: para description_final, email_final, whatsapp_final, linkedin_url_final, copia SOLO valores "
        "que sean subcadenas exactas reproducibles desde EVIDENCIA o deja cadena vacía si no hay prueba.\n"
        "Si la propuesta inventa datos, rechazalos (cadena vacía).\n"
        "Incluye lista rejected con objetos {field, reason} en español para cada campo vaciado.\n\n"
        f"EVIDENCIA:\n{evidence}\n\nPROPUESTA_JSON:\n{proposal_txt}\n\n"
        "Devuelve SOLO JSON con claves exactas:\n"
        '{"description_final": "", "email_final": "", "whatsapp_final": "", "linkedin_url_final": "", '
        '"rejected": []}'
    )


def _gate_finals(evidence_lower: str, finals: dict[str, str]) -> dict[str, str]:
    out = {
        k: (finals.get(k) or "").strip()
        for k in ("description_final", "email_final", "whatsapp_final", "linkedin_url_final")
    }
    desc = out["description_final"]
    if desc and desc.lower() not in evidence_lower:
        out["description_final"] = ""
    em = out["email_final"]
    if em and not _email_in_evidence(em, evidence_lower):
        out["email_final"] = ""
    wa = out["whatsapp_final"]
    if wa and not _phone_in_evidence(wa, evidence_lower):
        out["whatsapp_final"] = ""
    li = out["linkedin_url_final"]
    if li and not _linkedin_in_evidence(li, evidence_lower):
        out["linkedin_url_final"] = ""
    return out


# ---------------- Core enrichment function ----------------


async def enrich_lead_contacts(
    lead: LeadCore,
    *,
    exa_client: ExaClient,
    opencli: OpenCliClient,
    proposer: GeminiClient,
    reviewer: GeminiClient,
    settings: Settings | None = None,
    prefetched_maps: dict[str, Any] | None = None,
) -> EnrichmentResult:
    """Enriquece un lead con Exa (evidencia textual) + OpenCLI (contactos estructurados) + Gemini reviewer.

    Función pura: no persiste en DB. El caller decide qué hacer con el resultado.
    Si prefetched_maps está disponible, usa esos datos en lugar de llamar a Google Maps de nuevo.
    """
    st = settings or get_settings()

    # Ejecutar exa y opencli en paralelo usando create_task para mejor control
    exa_task = asyncio.create_task(_exa_evidence(exa_client, lead, st))
    opencli_task = asyncio.create_task(_opencli_evidence(opencli, lead, prefetched_maps=prefetched_maps))

    # Esperar a que exa termine, luego lanzar deep_fetch en paralelo con opencli
    exa_results, evidence, regex_contacts = await exa_task
    deep_fetch_task = asyncio.create_task(_deep_fetch_contacts(exa_client, exa_results, st))

    # Esperar a opencli y deep_fetch en paralelo
    opencli_results, deep_contacts = await asyncio.gather(opencli_task, deep_fetch_task)

    # Combinar todos los contactos directos (regex + deep_fetch), deduplicar
    all_direct_contacts = regex_contacts + deep_contacts
    seen = set()
    unique_direct_contacts = []
    for c in all_direct_contacts:
        key = (c["field"], c["value"].lower())
        if key not in seen:
            seen.add(key)
            unique_direct_contacts.append(c)

    opencli_merged = _merge_opencli_contacts(opencli_results)

    result = EnrichmentResult(enriched_sources=opencli_results)

    # Contactos estructurados (Google Knowledge Panel, Maps, etc.) tienen preferencia directa.
    if opencli_merged["phone"] and not lead.phone:
        result.phone = opencli_merged["phone"][:40]
    if opencli_merged["address"] and not lead.address:
        result.address = opencli_merged["address"][:500]
    if opencli_merged["schedule_text"] and not lead.schedule_text:
        result.schedule_text = opencli_merged["schedule_text"][:500]
    if opencli_merged["website"]:
        result.website = opencli_merged["website"][:500]
    if opencli_merged["facebook_url"]:
        result.facebook_url = opencli_merged["facebook_url"][:500]
    if opencli_merged["instagram_url"]:
        result.instagram_url = opencli_merged["instagram_url"][:500]

    # Aplicar contactos extraídos con regex del texto completo (prioridad: OpenCLI > regex > LLM)
    for direct_contact in unique_direct_contacts:
        field = direct_contact.get("field", "")
        value = direct_contact.get("value", "").strip()
        source_url = direct_contact.get("source_url", "")

        if field == "email" and not result.email and not lead.email and value:
            result.email = value[:255]
            result.citations.append({
                "url": source_url,
                "title": f"Email (regex extraction)",
                "confidence": "high",
                "source": "direct_regex",
            })
        elif field == "phone" and not result.phone and not lead.phone and value:
            result.phone = value[:40]
            result.citations.append({
                "url": source_url,
                "title": f"Phone (regex extraction)",
                "confidence": "high",
                "source": "direct_regex",
            })
        elif field == "whatsapp" and not result.whatsapp and not lead.whatsapp and value:
            result.whatsapp = value[:30]
            result.citations.append({
                "url": source_url,
                "title": f"WhatsApp (regex extraction)",
                "confidence": "high",
                "source": "direct_regex",
            })

    # Si no hay evidencia ni de Exa ni de OpenCLI, termina no_verified_data.
    if not evidence.strip() and not any([result.phone, result.address, result.schedule_text]):
        result.message = NO_DATA_ES
        return result

    # Gemini proposer + reviewer sobre evidencia Exa.
    if evidence.strip():
        try:
            proposal = await proposer.complete_json_prompt(_proposer_prompt(evidence, lead, opencli_merged))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini proponente falló: %s", exc)
            proposal = {"description": "", "email": "", "whatsapp": "", "linkedin_url": ""}

        try:
            reviewed = await reviewer.complete_json_prompt(_reviewer_prompt(evidence, proposal))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini revisora falló: %s", exc)
            reviewed = {
                "description_final": "",
                "email_final": "",
                "whatsapp_final": "",
                "linkedin_url_final": "",
                "rejected": [{"field": "all", "reason": "revisora no disponible"}],
            }

        finals = _gate_finals(
            evidence.lower(),
            {
                "description_final": str(reviewed.get("description_final", "")),
                "email_final": str(reviewed.get("email_final", "")),
                "whatsapp_final": str(reviewed.get("whatsapp_final", "")),
                "linkedin_url_final": str(reviewed.get("linkedin_url_final", "")),
            },
        )

        if finals["email_final"] and not lead.email:
            result.email = finals["email_final"][:255]
        if finals["whatsapp_final"] and not lead.whatsapp:
            result.whatsapp = finals["whatsapp_final"][:30]
        if finals["linkedin_url_final"] and not lead.linkedin_url:
            result.linkedin_url = finals["linkedin_url_final"][:500]
        result.description = finals["description_final"]
        result.audit = list(reviewed.get("rejected") or [])[:20]

    # Fallback: OpenCLI también puede haber encontrado email (sin evidencia LLM pero adapter determinista).
    if opencli_merged["email"] and not lead.email and not result.email:
        result.email = opencli_merged["email"][:255]

    # Citations: URLs de Exa.
    citations: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in exa_results:
        u = str(item.get("url", "")).strip()
        if u and u not in seen_urls:
            citations.append(
                {
                    "url": u,
                    "title": str(item.get("title", "") or "Fuente")[:240],
                    "confidence": "medium",
                    "source": "auto_enrich_exa",
                }
            )
            seen_urls.add(u)
    result.citations = citations
    if citations and not lead.primary_source_url:
        result.primary_source_url = str(citations[0].get("url", ""))[:500]

    has_contact = any([result.email, result.whatsapp, result.linkedin_url, result.phone, result.address])
    has_desc = bool(result.description)
    if has_contact or has_desc or result.schedule_text:
        result.status = "enriched"
        result.message = "Datos verificados en fuentes recuperadas."
    else:
        result.status = "no_verified_data"
        result.message = NO_DATA_ES
    return result


def _lead_to_core(lead: Lead) -> LeadCore:
    return LeadCore(
        full_name=str(lead.full_name or ""),
        specialty=str(lead.specialty or ""),
        city=str(lead.city or ""),
        country=str(lead.country or ""),
        entity_type="person",  # Default; el auto_enrich_node puede sobrescribir
        linkedin_url=str(lead.linkedin_url or ""),
        email=str(lead.email or ""),
        whatsapp=str(lead.whatsapp or ""),
        phone=str(lead.phone or ""),
        address=str(lead.address or ""),
        schedule_text=str(lead.schedule_text or ""),
        primary_source_url=str(lead.primary_source_url or ""),
    )


def build_lead_updates(lead: Lead, enrichment: EnrichmentResult) -> dict[str, Any]:
    """Convierte un EnrichmentResult en un diff aplicable por LeadsRepository.apply_field_updates."""
    updates: dict[str, Any] = {}

    if enrichment.email and not (lead.email or "").strip():
        updates["email"] = enrichment.email
    if enrichment.whatsapp and not (lead.whatsapp or "").strip():
        updates["whatsapp"] = enrichment.whatsapp
    if enrichment.linkedin_url and not (lead.linkedin_url or "").strip():
        updates["linkedin_url"] = enrichment.linkedin_url
    if enrichment.phone and not (lead.phone or "").strip():
        updates["phone"] = enrichment.phone
    if enrichment.address and not (lead.address or "").strip():
        updates["address"] = enrichment.address
    if enrichment.schedule_text and not (lead.schedule_text or "").strip():
        updates["schedule_text"] = enrichment.schedule_text
    if enrichment.website and not (lead.website or "").strip():
        updates["website"] = enrichment.website
    if enrichment.facebook_url and not (lead.facebook_url or "").strip():
        updates["facebook_url"] = enrichment.facebook_url
    if enrichment.instagram_url and not (lead.instagram_url or "").strip():
        updates["instagram_url"] = enrichment.instagram_url

    if enrichment.citations:
        existing = lead.source_citations if isinstance(lead.source_citations, list) else []
        existing_normalized = [c for c in existing if isinstance(c, dict)]
        seen_urls = {str(c.get("url", "")).strip() for c in existing_normalized if c.get("url")}
        merged = list(existing_normalized)
        for c in enrichment.citations:
            u = str(c.get("url", "")).strip()
            if u and u not in seen_urls:
                merged.append(c)
                seen_urls.add(u)
        updates["source_citations"] = merged

    if enrichment.primary_source_url and not (lead.primary_source_url or "").strip():
        updates["primary_source_url"] = enrichment.primary_source_url[:500]

    if enrichment.enriched_sources:
        base = dict(lead.enriched_sources or {})
        base.update(enrichment.enriched_sources)
        updates["enriched_sources"] = base

    base_reason = (lead.score_reasoning or "").strip()
    enrich_block = enrichment.description if enrichment.description else NO_DATA_ES
    new_reasoning = (
        f"{base_reason}\n\n[Búsqueda extensiva]\n{enrich_block}".strip()
        if base_reason
        else f"[Búsqueda extensiva]\n{enrich_block}".strip()
    )
    updates["score_reasoning"] = new_reasoning[:1000]

    updates["langsmith_metadata"] = {
        "last_deep_enrich": {
            "status": enrichment.status,
            "message": enrichment.message,
            "audit": enrichment.audit,
        }
    }
    return updates


async def deep_enrich_lead(lead_id: UUID) -> LeadRead | None:
    """Wrapper legacy para el endpoint manual: carga lead, enriquece, persiste."""
    settings = get_settings()
    async with async_session_factory() as session:
        repo = LeadsRepository(session)
        lead_orm = await repo.get_orm_by_id(lead_id)
        if lead_orm is None:
            return None

        exa_client = ExaClient(
            api_key=settings.exa_api_key,
            timeout_seconds=effective_exa_search_timeout_seconds(settings),
        )
        opencli = OpenCliClient(settings)
        proposer = GeminiClient(api_key=settings.google_api_key, model_name=settings.google_model)
        reviewer = GeminiClient(api_key=settings.google_api_key, model_name=settings.google_reviewer_model)

        enrichment = await enrich_lead_contacts(
            _lead_to_core(lead_orm),
            exa_client=exa_client,
            opencli=opencli,
            proposer=proposer,
            reviewer=reviewer,
            settings=settings,
        )
        updates = build_lead_updates(lead_orm, enrichment)
        await repo.apply_field_updates(lead_id, updates)
        return await repo.get_by_id(lead_id)
