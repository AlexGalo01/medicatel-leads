from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

from langsmith import traceable

from mle.observability.langsmith_setup import (
    trace_inputs_gemini_expand_plan,
    trace_inputs_gemini_expand_query,
    trace_inputs_gemini_json_prompt,
    trace_inputs_gemini_score,
    trace_outputs_gemini_expand_query,
    trace_outputs_gemini_json_prompt,
    trace_outputs_gemini_score,
    trace_outputs_gemini_search_plan,
)

logger = logging.getLogger(__name__)

# Fallbacks tras el modelo configurado (GOOGLE_MODEL). Orden: versiones fijas y variantes
# ligeras antes de repetir alias -latest (suelen concentrar más tráfico y 429).
_MODEL_FALLBACKS: list[str] = [
    "gemini-2.0-flash-001",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
]

# Por modelo: tras varios 429/5xx se pasa al siguiente (fallback), no solo a reintentar el mismo.
_PER_MODEL_RETRY_DELAYS_SEC = (1.5, 4.0, 10.0)


class GeminiClient:
    """Async client para generateContent: reintentos con backoff por modelo y rotación ante 429/404."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-flash-latest",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def _candidate_models(self) -> list[str]:
        """Primero el configurado; después los fallbacks únicos."""
        seen: set[str] = set()
        out: list[str] = []
        for m in [self.model_name, *_MODEL_FALLBACKS]:
            if m and m not in seen:
                out.append(m)
                seen.add(m)
        return out

    async def _post_with_retry(
        self,
        client,  # type: ignore[no-untyped-def]
        request_body: dict[str, Any],
    ) -> dict[str, Any]:
        """POST: 404/403 → siguiente modelo; 429/5xx → backoff limitado y luego siguiente modelo."""
        headers = {"Content-Type": "application/json"}
        last_error: Exception | None = None
        max_attempts_per_model = 1 + len(_PER_MODEL_RETRY_DELAYS_SEC)

        for model in self._candidate_models():
            url = f"{self.base_url}/{model}:generateContent?key={self.api_key}"
            for attempt in range(max_attempts_per_model):
                if attempt > 0:
                    wait = _PER_MODEL_RETRY_DELAYS_SEC[attempt - 1]
                    jitter = random.uniform(0.0, 0.45)
                    await asyncio.sleep(wait + jitter)
                response = await client.post(url, headers=headers, json=request_body)
                status = response.status_code
                if status in (403, 404):
                    last_error = ValueError(f"Modelo no disponible ({status}): {model}")
                    logger.info("Gemini %s — siguiente modelo (era %s)", status, model)
                    break
                if status == 429:
                    last_error = ValueError(f"Gemini 429 en {model} (intento {attempt + 1}/{max_attempts_per_model})")
                    if attempt + 1 < max_attempts_per_model:
                        logger.info(
                            "Gemini 429 — retry model=%s attempt=%s/%s wait_next=%.1fs",
                            model,
                            attempt + 1,
                            max_attempts_per_model,
                            _PER_MODEL_RETRY_DELAYS_SEC[attempt],
                        )
                        continue
                    logger.info(
                        "Gemini 429 — agotado modelo=%s, probando siguiente candidato",
                        model,
                    )
                    break
                if 500 <= status < 600:
                    last_error = ValueError(f"Gemini server error {status} en {model}")
                    if attempt + 1 < max_attempts_per_model:
                        logger.info(
                            "Gemini %s — retry model=%s attempt=%s/%s",
                            status,
                            model,
                            attempt + 1,
                            max_attempts_per_model,
                        )
                        continue
                    break
                response.raise_for_status()
                return dict(response.json())

        if last_error is not None:
            raise last_error
        raise ValueError("No se pudo obtener respuesta válida de Gemini.")

    @traceable(
        name="gemini_score_lead",
        run_type="llm",
        process_inputs=trace_inputs_gemini_score,
        process_outputs=trace_outputs_gemini_score,
    )
    async def score_lead(self, lead_payload: dict[str, Any]) -> dict[str, Any]:
        import httpx

        prompt = self._build_prompt(lead_payload)
        request_body = {"contents": [{"parts": [{"text": prompt}]}]}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            payload = await self._post_with_retry(client, request_body)
        return self._parse_score_response(payload)

    @traceable(
        name="gemini_expand_search_query",
        run_type="llm",
        process_inputs=trace_inputs_gemini_expand_query,
        process_outputs=trace_outputs_gemini_expand_query,
    )
    async def expand_search_query(
        self,
        *,
        user_query: str,
        contact_channels: list[str],
        search_focus: str,
        notes: str | None,
    ) -> dict[str, Any]:
        import httpx

        prompt = self._build_expansion_prompt(
            user_query=user_query,
            contact_channels=contact_channels,
            search_focus=search_focus,
            notes=notes,
        )
        request_body = {"contents": [{"parts": [{"text": prompt}]}]}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            payload = await self._post_with_retry(client, request_body)
        return self._parse_expansion_response(payload)

    @traceable(
        name="gemini_expand_search_plan",
        run_type="llm",
        process_inputs=trace_inputs_gemini_expand_plan,
        process_outputs=trace_outputs_gemini_search_plan,
    )
    async def expand_search_plan(
        self,
        *,
        user_query: str,
        contact_channels: list[str],
        search_focus: str,
        notes: str | None,
    ) -> dict[str, Any]:
        import httpx

        prompt = self._build_search_plan_prompt(
            user_query=user_query,
            contact_channels=contact_channels,
            search_focus=search_focus,
            notes=notes,
        )
        request_body = {"contents": [{"parts": [{"text": prompt}]}]}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            payload = await self._post_with_retry(client, request_body)
        raw_text = self._raw_text_from_payload(payload)
        return self._parse_json_object_from_text(raw_text)

    @traceable(
        name="gemini_complete_json_prompt",
        run_type="llm",
        process_inputs=trace_inputs_gemini_json_prompt,
        process_outputs=trace_outputs_gemini_json_prompt,
    )
    async def complete_json_prompt(self, prompt: str) -> dict[str, Any]:
        """Genera una respuesta JSON arbitraria a partir de un prompt (sin plantilla fija)."""
        import httpx

        request_body = {"contents": [{"parts": [{"text": prompt}]}]}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            payload = await self._post_with_retry(client, request_body)
        raw_text = self._raw_text_from_payload(payload)
        return self._parse_json_object_from_text(raw_text)

    def _build_search_plan_prompt(
        self,
        *,
        user_query: str,
        contact_channels: list[str],
        search_focus: str,
        notes: str | None,
    ) -> str:
        channels_txt = ", ".join(contact_channels) if contact_channels else "email, whatsapp, linkedin"
        notes_block = f"Notas del usuario: {notes}\n" if notes else ""
        focus_hint = {
            "linkedin": "Prioriza perfiles y URLs de LinkedIn y señales de contacto corporativo.",
            "instagram": "Prioriza redes visuales y bios con WhatsApp o enlaces.",
            "general": "Balance entre web, directorios y redes; datos de contacto verificables.",
        }.get(search_focus.lower(), "Balance razonable entre fuentes.")

        return (
            "Eres un planificador de busqueda web para Exa (motor neuronal). "
            "Debes producir un plan en español, agnostico al sector (salud, retail, servicios, etc.).\n"
            f"Consulta del usuario: {user_query}\n"
            f"Canales deseados: {channels_txt}\n"
            f"Enfoque: {search_focus}. {focus_hint}\n"
            f"{notes_block}"
            "Reglas: main_query y additional_queries deben estar en español; si el usuario mezcla idiomas, prioriza términos y sinónimos en español para favorecer fuentes y páginas en español (sin añadir 'español' o 'Spanish' a propósito al final de cada frase de forma rígida).\n"
            "Reglas: main_query debe ser rico y ejecutable (sin inventar nombres propios inexistentes en la consulta). "
            "additional_queries debe tener 0 a 6 variaciones (sinonimos, ubicacion, rubro alternativo, "
            "intención de contacto). Si falta un dato crítico (ej. ciudad cuando el usuario busca locales), "
            "rellena clarifying_question; si aun asi puedes buscar en amplio, deja main_query util.\n"
            "exa_category solo puede ser null, \"people\" (profesionales / perfiles) o \"company\" (empresas / "
            "organizaciones). Si no aplica, null.\n"
            "PATRÓN ESPECIAL - Búsqueda de empleados de empresa: "
            "Si la consulta busca empleados, personal, equipo, trabajadores o staff de una empresa concreta "
            "(ej. 'empleados de Empresa1', 'trabajadores de Clínica X'), devuelve company_anchor con: "
            "company_name (nombre exacto) y anchor_query (query corta para encontrar la empresa, ej. 'Empresa1 empresa sitio oficial LinkedIn'). "
            "En ese caso, main_query y additional_queries deben ser específicas para empleados (ej. '[Empresa]' empleados perfiles LinkedIn'). "
            "Si no es búsqueda de empleados de empresa específica, company_anchor debe ser null.\n"
            "Devuelve SOLO JSON con las claves exactas:\n"
            '{"entity_type": "texto corto del tipo de entidad inferido o vacio", '
            '"geo": {"country": "", "city": ""}, '
            '"main_query": "consulta larga lista para Exa", '
            '"additional_queries": ["..."], '
            '"required_channels": ["email","whatsapp","linkedin"], '
            '"negative_constraints": "texto opcional", '
            '"clarifying_question": null, '
            '"exa_category": null, '
            '"company_anchor": null}\n'
            "required_channels debe reflejar los canales deseados (subconjunto de los solicitados)."
        )

    def _build_expansion_prompt(
        self,
        *,
        user_query: str,
        contact_channels: list[str],
        search_focus: str,
        notes: str | None,
    ) -> str:
        channels_txt = ", ".join(contact_channels) if contact_channels else "email, whatsapp, linkedin"
        notes_block = f"Notas del usuario: {notes}\n" if notes else ""
        focus_hint = {
            "linkedin": "Prioriza perfiles y URLs de LinkedIn, titulos profesionales y señales de contacto corporativo.",
            "instagram": "Prioriza presencia en Instagram o redes visuales, bios con WhatsApp o enlaces, sin inventar handles.",
            "general": "Balance entre web, directorios moderados y redes; prioriza datos de contacto verificables.",
        }.get(search_focus.lower(), "Balance razonable entre fuentes.")

        return (
            "Eres un asistente que reformula consultas de prospeccion B2B medica para un buscador web (Exa). "
            "Debes producir texto de busqueda en español, concretos y ejecutables.\n"
            f"Consulta original: {user_query}\n"
            f"Canales solicitados por el usuario: {channels_txt}\n"
            f"Enfoque: {search_focus}. {focus_hint}\n"
            f"{notes_block}"
            "Instrucciones: indica de forma explicita como priorizar email frente a whatsapp segun lo que pida el usuario; "
            "menciona LinkedIn si aplica. Redacta expanded_query en español; si el input está en otro idioma, traduce o adapta términos al español de negocio para Exa, favoreciendo resultados y webs en español.\n"
            "Si las notas piden excluir listados tipo Excel o directorios masivos, "
            "incorporalo en negative_constraints.\n"
            "Devuelve SOLO un JSON con las claves exactas:\n"
            '{"expanded_query": "texto largo optimizado para busqueda web", '
            '"channel_instructions": "una frase sobre prioridad email/whatsapp/linkedin", '
            '"negative_constraints": "frase opcional sobre exclusiones"}\n'
            "expanded_query debe ser rico en sinonimos y filtros de calidad (minimo 80 caracteres si el input lo permite)."
        )

    def _build_prompt(self, lead_payload: dict[str, Any]) -> str:
        lead_text = json.dumps(lead_payload, ensure_ascii=False)
        return (
            "Evalua la calidad de este lead medico. "
            "Devuelve SOLO JSON con formato: "
            '{"score": numero_0_a_10, "reasoning": "texto_corto_en_espanol"}. '
            f"Lead: {lead_text}"
        )

    def _raw_text_from_payload(self, payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini no devolvio candidatos.")

        first_candidate = candidates[0]
        content = first_candidate.get("content", {})
        parts = content.get("parts", [])
        if not parts:
            raise ValueError("Gemini no devolvio contenido parseable.")

        return str(parts[0].get("text", "")).strip()

    def _parse_json_object_from_text(self, raw_text: str) -> dict[str, Any]:
        json_start = raw_text.find("{")
        json_end = raw_text.rfind("}")
        if json_start < 0 or json_end < 0:
            raise ValueError("Gemini devolvio respuesta no JSON.")
        return dict(json.loads(raw_text[json_start : json_end + 1]))

    def _parse_score_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_text = self._raw_text_from_payload(payload)
        score_payload = self._parse_json_object_from_text(raw_text)
        score = float(score_payload.get("score", 0))
        reasoning = str(score_payload.get("reasoning", "Sin justificacion.")).strip()
        return {"score": max(0.0, min(score, 10.0)), "reasoning": reasoning}

    def _parse_expansion_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_text = self._raw_text_from_payload(payload)
        parsed = self._parse_json_object_from_text(raw_text)
        expanded = str(parsed.get("expanded_query", "")).strip()
        if not expanded:
            raise ValueError("expanded_query vacio.")
        return {
            "expanded_query": expanded,
            "channel_instructions": str(parsed.get("channel_instructions", "")).strip() or None,
            "negative_constraints": str(parsed.get("negative_constraints", "")).strip() or None,
        }
