from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID

from mle.clients.exa_client import ExaClient
from mle.clients.gemini_client import GeminiClient
from mle.core.config import get_settings
from mle.db.base import async_session_factory
from mle.db.models import Lead
from mle.repositories.leads_repository import LeadsRepository
from mle.schemas.leads import LeadRead

logger = logging.getLogger(__name__)

NO_DATA_ES = "No se encontró información adicional verificable en las fuentes recuperadas."


def _extract_results(search_response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_results = search_response.get("results", [])
    if isinstance(raw_results, list):
        return [r for r in raw_results if isinstance(r, dict)]
    return []


def _flatten_evidence(results: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for index, item in enumerate(results):
        url = str(item.get("url", "")).strip()
        title = str(item.get("title", "")).strip()
        highlights = item.get("highlights", [])
        if not isinstance(highlights, list):
            highlights = []
        hl_join = " | ".join(str(h) for h in highlights[:8])
        text = str(item.get("text", ""))[:2000]
        parts.append(f"[{index}] URL: {url}\nTitulo: {title}\nHighlights: {hl_join}\nTexto: {text}\n")
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


def _build_exa_payload(lead: Lead) -> dict[str, Any]:
    name = str(lead.full_name or "").strip()
    spec = str(lead.specialty or "").strip()
    city = str(lead.city or "").strip()
    country = str(lead.country or "").strip()
    li = str(lead.linkedin_url or "").strip()
    parts = [name, spec, city, country, "contacto email whatsapp sitio web linkedin facebook instagram"]
    if li:
        parts.append(li)
    query = " ".join(p for p in parts if p)
    return {
        "query": query[:900],
        "type": "deep",
        "numResults": 18,
        "contents": {
            "highlights": {
                "maxCharacters": 4500,
                "query": "extrae correos, telefonos, whatsapp, urls de linkedin facebook instagram y sitios web",
            }
        },
    }


def _proposer_prompt(evidence: str, lead: Lead) -> str:
    ctx = json.dumps(
        {
            "full_name": lead.full_name,
            "specialty": lead.specialty,
            "city": lead.city,
            "country": lead.country,
            "linkedin_url_known": lead.linkedin_url or "",
            "email_known": lead.email or "",
            "whatsapp_known": lead.whatsapp or "",
        },
        ensure_ascii=False,
    )
    return (
        "Eres analista de datos de contacto B2B medico. SOLO puedes usar datos que aparezcan literalmente en EVIDENCIA.\n"
        "Si un dato no esta escrito en EVIDENCIA, deja cadena vacia. No infieras ni completes.\n\n"
        f"CONTEXTO_LEAD_JSON: {ctx}\n\n"
        f"EVIDENCIA:\n{evidence}\n\n"
        "Devuelve SOLO JSON con claves exactas:\n"
        '{"description": "texto breve en español solo con hechos de EVIDENCIA, maximo 600 caracteres", '
        '"email": "", "whatsapp": "", "linkedin_url": ""}\n'
        "email y whatsapp y linkedin_url deben ser copias exactas de fragmentos de EVIDENCIA o vacios."
    )


def _reviewer_prompt(evidence: str, proposal: dict[str, Any]) -> str:
    proposal_txt = json.dumps(proposal, ensure_ascii=False)
    return (
        "Eres un auditor estricto anti-alucinaciones. Recibes EVIDENCIA (texto) y una PROPUESTA_JSON.\n"
        "Tu trabajo: para description_final, email_final, whatsapp_final, linkedin_url_final, copia SOLO valores "
        "que sean subcadenas exactas reproducibles desde EVIDENCIA o deja cadena vacia si no hay prueba.\n"
        "Si la propuesta inventa datos, rechazalos (cadena vacia).\n"
        "Incluye lista rejected con objetos {field, reason} en español para cada campo vaciado.\n\n"
        f"EVIDENCIA:\n{evidence}\n\nPROPUESTA_JSON:\n{proposal_txt}\n\n"
        "Devuelve SOLO JSON con claves exactas:\n"
        '{"description_final": "", "email_final": "", "whatsapp_final": "", "linkedin_url_final": "", '
        '"rejected": []}'
    )


def _gate_finals(
    evidence_lower: str,
    finals: dict[str, str],
) -> dict[str, str]:
    out = {k: (finals.get(k) or "").strip() for k in ("description_final", "email_final", "whatsapp_final", "linkedin_url_final")}
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


async def deep_enrich_lead(lead_id: UUID) -> LeadRead | None:
    settings = get_settings()
    async with async_session_factory() as session:
        repo = LeadsRepository(session)
        lead_orm = await repo.get_orm_by_id(lead_id)
        if lead_orm is None:
            return None

        exa_client = ExaClient(api_key=settings.exa_api_key)
        payload = _build_exa_payload(lead_orm)
        try:
            search_response = await exa_client.search(payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Exa fallo en deep enrich lead_id=%s: %s", lead_id, exc)
            await _persist_no_data(repo, lead_orm, reason="exa_error")
            refreshed = await repo.get_by_id(lead_id)
            return refreshed

        results = _extract_results(search_response)
        if not results:
            await _persist_no_data(repo, lead_orm, reason="sin_resultados_exa")
            return await repo.get_by_id(lead_id)

        evidence = _flatten_evidence(results)
        evidence_lower = evidence.lower()

        proposer = GeminiClient(api_key=settings.google_api_key, model_name=settings.google_model)
        reviewer = GeminiClient(api_key=settings.google_api_key, model_name=settings.google_reviewer_model)

        try:
            proposal = await proposer.complete_json_prompt(_proposer_prompt(evidence, lead_orm))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini proponente fallo: %s", exc)
            proposal = {"description": "", "email": "", "whatsapp": "", "linkedin_url": ""}

        try:
            reviewed = await reviewer.complete_json_prompt(_reviewer_prompt(evidence, proposal))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini revisora fallo: %s", exc)
            reviewed = {
                "description_final": "",
                "email_final": "",
                "whatsapp_final": "",
                "linkedin_url_final": "",
                "rejected": [{"field": "all", "reason": "revisora no disponible"}],
            }

        finals = _gate_finals(
            evidence_lower,
            {
                "description_final": str(reviewed.get("description_final", "")),
                "email_final": str(reviewed.get("email_final", "")),
                "whatsapp_final": str(reviewed.get("whatsapp_final", "")),
                "linkedin_url_final": str(reviewed.get("linkedin_url_final", "")),
            },
        )

        has_contact = any(
            [
                finals["email_final"],
                finals["whatsapp_final"],
                finals["linkedin_url_final"],
            ]
        )
        has_desc = bool(finals["description_final"])
        if not has_contact and not has_desc:
            await _persist_no_data(repo, lead_orm, reason="sin_datos_verificables", audit=reviewed.get("rejected"))
            return await repo.get_by_id(lead_id)

        base_reason = (lead_orm.score_reasoning or "").strip()
        enrich_block = finals["description_final"] if has_desc else NO_DATA_ES
        new_reasoning = (
            f"{base_reason}\n\n[Búsqueda extensiva]\n{enrich_block}".strip()
            if base_reason
            else f"[Búsqueda extensiva]\n{enrich_block}".strip()
        )

        existing_cites: list[dict[str, Any]] = []
        if isinstance(lead_orm.source_citations, list):
            existing_cites = [c for c in lead_orm.source_citations if isinstance(c, dict)]
        seen_urls = {str(c.get("url", "")).strip() for c in existing_cites if c.get("url")}
        for item in results:
            u = str(item.get("url", "")).strip()
            if u and u not in seen_urls:
                existing_cites.append(
                    {
                        "url": u,
                        "title": str(item.get("title", "") or "Fuente")[:240],
                        "confidence": "medium",
                        "source": "deep_enrich_exa",
                    }
                )
                seen_urls.add(u)

        updates: dict[str, Any] = {
            "score_reasoning": new_reasoning[:1000],
            "source_citations": existing_cites,
            "langsmith_metadata": {
                "last_deep_enrich": {
                    "status": "enriched" if (has_desc or has_contact) else "no_verified_data",
                    "message": "Datos verificados en fuentes recuperadas." if has_contact or has_desc else NO_DATA_ES,
                    "audit": reviewed.get("rejected", [])[:20],
                }
            },
        }

        if finals["email_final"] and not (lead_orm.email or "").strip():
            updates["email"] = finals["email_final"][:255]
        if finals["whatsapp_final"] and not (lead_orm.whatsapp or "").strip():
            updates["whatsapp"] = finals["whatsapp_final"][:30]
        if finals["linkedin_url_final"] and not (lead_orm.linkedin_url or "").strip():
            updates["linkedin_url"] = finals["linkedin_url_final"][:500]

        if not (lead_orm.primary_source_url or "").strip() and existing_cites:
            first_url = str(existing_cites[0].get("url", "")).strip()
            if first_url:
                updates["primary_source_url"] = first_url[:500]

        await repo.apply_field_updates(lead_id, updates)
        return await repo.get_by_id(lead_id)


async def _persist_no_data(repo: LeadsRepository, lead: Lead, reason: str, audit: Any = None) -> None:
    base = (lead.score_reasoning or "").strip()
    block = NO_DATA_ES
    new_reasoning = (
        f"{base}\n\n[Búsqueda extensiva]\n{block}".strip() if base else f"[Búsqueda extensiva]\n{block}".strip()
    )
    meta_patch = {
        "last_deep_enrich": {
            "status": "no_verified_data",
            "message": NO_DATA_ES,
            "reason": reason,
            "audit": audit if isinstance(audit, list) else [],
        }
    }
    await repo.apply_field_updates(
        lead.id,
        {
            "score_reasoning": new_reasoning[:1000],
            "langsmith_metadata": meta_patch,
        },
    )
