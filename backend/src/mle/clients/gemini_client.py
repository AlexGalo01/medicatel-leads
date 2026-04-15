from __future__ import annotations

import json
from typing import Any


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
                return self._parse_response(payload)

        if last_error is not None:
            raise last_error
        raise ValueError("No se pudo obtener respuesta valida de Gemini.")

    def _build_prompt(self, lead_payload: dict[str, Any]) -> str:
        lead_text = json.dumps(lead_payload, ensure_ascii=False)
        return (
            "Evalua la calidad de este lead medico. "
            "Devuelve SOLO JSON con formato: "
            '{"score": numero_0_a_10, "reasoning": "texto_corto_en_espanol"}. '
            f"Lead: {lead_text}"
        )

    def _parse_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        candidates = payload.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini no devolvio candidatos.")

        first_candidate = candidates[0]
        content = first_candidate.get("content", {})
        parts = content.get("parts", [])
        if not parts:
            raise ValueError("Gemini no devolvio contenido parseable.")

        raw_text = str(parts[0].get("text", "")).strip()
        json_start = raw_text.find("{")
        json_end = raw_text.rfind("}")
        if json_start < 0 or json_end < 0:
            raise ValueError("Gemini devolvio respuesta no JSON.")

        score_payload = json.loads(raw_text[json_start : json_end + 1])
        score = float(score_payload.get("score", 0))
        reasoning = str(score_payload.get("reasoning", "Sin justificacion.")).strip()
        return {"score": max(0.0, min(score, 10.0)), "reasoning": reasoning}

