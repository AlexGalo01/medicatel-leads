from __future__ import annotations

import json
from typing import Any

from langsmith import traceable

from mle.observability.langsmith_setup import trace_inputs_gemini_score, trace_outputs_gemini_score


class GeminiClient:
    """Minimal async client for Gemini generateContent endpoint."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-1.5-flash-latest",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    @traceable(
        name="gemini_score_lead",
        run_type="llm",
        process_inputs=trace_inputs_gemini_score,
        process_outputs=trace_outputs_gemini_score,
    )
    async def score_lead(self, lead_payload: dict[str, Any]) -> dict[str, Any]:
        import httpx

        prompt = self._build_prompt(lead_payload)
        request_body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                    ]
                }
            ]
        }
        model_candidates = [
            self.model_name,
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash",
            "gemini-2.0-flash",
        ]
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            last_error: Exception | None = None
            for model in model_candidates:
                request_url = f"{self.base_url}/{model}:generateContent?key={self.api_key}"
                response = await client.post(request_url, headers=headers, json=request_body)
                if response.status_code == 404:
                    last_error = ValueError(f"Modelo no encontrado: {model}")
                    continue
                response.raise_for_status()
                payload = dict(response.json())
                return self._parse_score_response(payload)

        if last_error is not None:
            raise last_error
        raise ValueError("No se pudo obtener respuesta valida de Gemini.")

    @traceable(name="gemini_expand_search_query", run_type="llm")
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
        request_body = {
            "contents": [{"parts": [{"text": prompt}]}],
        }
        model_candidates = [
            self.model_name,
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash",
            "gemini-2.0-flash",
        ]
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            last_error: Exception | None = None
            for model in model_candidates:
                request_url = f"{self.base_url}/{model}:generateContent?key={self.api_key}"
                response = await client.post(request_url, headers=headers, json=request_body)
                if response.status_code == 404:
                    last_error = ValueError(f"Modelo no encontrado: {model}")
                    continue
                response.raise_for_status()
                payload = dict(response.json())
                return self._parse_expansion_response(payload)

        if last_error is not None:
            raise last_error
        raise ValueError("No se pudo obtener respuesta valida de Gemini.")

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
            "menciona LinkedIn si aplica. Si las notas piden excluir listados tipo Excel o directorios masivos, "
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

    async def complete_json_prompt(self, prompt: str) -> dict[str, Any]:
        """Genera una respuesta JSON arbitraria a partir de un prompt (sin plantilla fija)."""
        import httpx

        request_body = {"contents": [{"parts": [{"text": prompt}]}]}
        model_candidates = [
            self.model_name,
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash",
            "gemini-2.0-flash",
        ]
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            last_error: Exception | None = None
            for model in model_candidates:
                request_url = f"{self.base_url}/{model}:generateContent?key={self.api_key}"
                response = await client.post(request_url, headers=headers, json=request_body)
                if response.status_code == 404:
                    last_error = ValueError(f"Modelo no encontrado: {model}")
                    continue
                response.raise_for_status()
                payload = dict(response.json())
                raw_text = self._raw_text_from_payload(payload)
                return self._parse_json_object_from_text(raw_text)

        if last_error is not None:
            raise last_error
        raise ValueError("No se pudo obtener respuesta valida de Gemini.")

