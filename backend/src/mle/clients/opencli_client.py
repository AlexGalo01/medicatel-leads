"""Async wrapper para OpenCLI (`@jackwener/opencli`) como fuente de contactos.

OpenCLI convierte sitios web en CLIs deterministas reutilizando sesión de Chrome.
Usamos tres adaptadores principales:
- `google search` → Knowledge Panel (phone/address/hours)
- `google-maps`  → Ficha de negocio (phone/address/hours/reviews)
- `doctoralia`   → Directorio médico (custom adapter; alternativa: Exa includeDomains)

Fallos se degradan a `{}` — el pipeline no debe tumbar un lead si OpenCLI falla.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
from typing import Any

from mle.core.config import Settings

logger = logging.getLogger(__name__)


class OpenCliError(Exception):
    """Error no fatal de OpenCLI (timeout, exit != 0, JSON inválido)."""


class OpenCliClient:
    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.opencli_enabled)
        self.binary = settings.opencli_binary_path
        self.chrome_profile = settings.opencli_chrome_profile_path
        self.timeout = int(settings.opencli_timeout_seconds)
        self.include_facebook = bool(settings.opencli_include_facebook)
        self.include_instagram = bool(settings.opencli_include_instagram)

    async def _run(self, args: list[str]) -> dict[str, Any]:
        """Ejecuta `opencli <args> --json` async. Retorna dict parseado o levanta OpenCliError."""
        if not self.enabled:
            return {}
        cmd = [self.binary, *args, "--json"]
        env_args: list[str] = []
        if self.chrome_profile:
            env_args = ["--profile", self.chrome_profile]
        full_cmd = [*cmd[:1], *env_args, *cmd[1:]]
        logger.debug("opencli invoke: %s", shlex.join(full_cmd))
        try:
            proc = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            logger.warning("OpenCLI binary no encontrado: %s", exc)
            return {}
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise OpenCliError(f"timeout tras {self.timeout}s para {' '.join(args)}") from None

        if proc.returncode != 0:
            err = (stderr.decode("utf-8", errors="replace") or "").strip()[:500]
            raise OpenCliError(f"exit={proc.returncode} stderr={err}")

        payload = (stdout or b"").decode("utf-8", errors="replace").strip()
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise OpenCliError(f"JSON inválido: {exc}") from exc

    async def _run_safe(self, label: str, args: list[str]) -> dict[str, Any]:
        """`_run` con degrade-safe: ante cualquier error, retorna {} y loguea."""
        if not self.enabled:
            return {}
        try:
            return await self._run(args)
        except OpenCliError as exc:
            logger.info("OpenCLI %s falló (degrade safe): %s", label, exc)
            return {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenCLI %s error inesperado: %s", label, exc)
            return {}

    async def google_search(self, query: str) -> dict[str, Any]:
        """Knowledge Panel de Google (teléfono, dirección, horario, sitio web)."""
        if not query.strip():
            return {}
        raw = await self._run_safe("google_search", ["google", "search", query])
        return _normalize_google_knowledge_panel(raw, source="google_search")

    async def google_maps(self, query: str) -> dict[str, Any]:
        """Ficha de negocio en Google Maps (phone/address/hours/reviews)."""
        if not query.strip():
            return {}
        raw = await self._run_safe("google_maps", ["google-maps", "search", query])
        return _normalize_google_maps(raw, source="google_maps")

    async def doctoralia(self, name: str, specialty: str, city: str) -> dict[str, Any]:
        """Ficha en Doctoralia (directorio médico). Requiere adapter custom instalado."""
        q = " ".join(part for part in (name, specialty, city) if part and part.strip())
        if not q.strip():
            return {}
        raw = await self._run_safe("doctoralia", ["doctoralia", "search", q])
        return _normalize_doctoralia(raw, source="doctoralia")

    async def facebook_page(self, query: str) -> dict[str, Any]:
        """Opt-in via settings.opencli_include_facebook."""
        if not self.include_facebook or not query.strip():
            return {}
        raw = await self._run_safe("facebook", ["facebook", "page", query])
        return _normalize_generic_contact(raw, source="facebook")

    async def instagram_profile(self, query: str) -> dict[str, Any]:
        """Opt-in via settings.opencli_include_instagram."""
        if not self.include_instagram or not query.strip():
            return {}
        raw = await self._run_safe("instagram", ["instagram", "profile", query])
        return _normalize_generic_contact(raw, source="instagram")


def _first_str(d: dict[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _normalize_google_knowledge_panel(raw: dict[str, Any], source: str) -> dict[str, Any]:
    """Extrae contactos del output de `opencli google search`.

    Acepta variaciones del shape del adapter: `knowledge_panel`, `panel`, top-level.
    """
    if not raw:
        return {}
    panel = raw.get("knowledge_panel") or raw.get("panel") or raw
    if not isinstance(panel, dict):
        panel = {}
    return {
        "phone": _first_str(panel, "phone", "telephone", "telefono"),
        "address": _first_str(panel, "address", "formatted_address", "direccion"),
        "hours": _first_str(panel, "hours", "opening_hours", "horario", "schedule"),
        "website": _first_str(panel, "website", "url", "sitio_web"),
        "email": _first_str(panel, "email", "correo"),
        "title": _first_str(panel, "title", "name", "nombre"),
        "source": source,
        "raw": raw,
    }


def _normalize_google_maps(raw: dict[str, Any], source: str) -> dict[str, Any]:
    if not raw:
        return {}
    place = raw.get("place") or raw.get("result") or raw
    if not isinstance(place, dict):
        place = {}
    return {
        "phone": _first_str(place, "phone", "international_phone", "telephone"),
        "address": _first_str(place, "address", "formatted_address", "direccion"),
        "hours": _first_str(place, "hours", "opening_hours", "horario"),
        "website": _first_str(place, "website", "url"),
        "rating": place.get("rating"),
        "reviews_count": place.get("reviews_count") or place.get("user_ratings_total"),
        "source": source,
        "raw": raw,
    }


def _normalize_doctoralia(raw: dict[str, Any], source: str) -> dict[str, Any]:
    if not raw:
        return {}
    doc = raw.get("doctor") or raw.get("profile") or raw
    if not isinstance(doc, dict):
        doc = {}
    return {
        "phone": _first_str(doc, "phone", "telefono"),
        "address": _first_str(doc, "address", "direccion"),
        "specialty": _first_str(doc, "specialty", "especialidad"),
        "rating": doc.get("rating"),
        "profile_url": _first_str(doc, "profile_url", "url"),
        "source": source,
        "raw": raw,
    }


def _normalize_generic_contact(raw: dict[str, Any], source: str) -> dict[str, Any]:
    if not raw:
        return {}
    return {
        "phone": _first_str(raw, "phone"),
        "email": _first_str(raw, "email"),
        "website": _first_str(raw, "website", "url"),
        "address": _first_str(raw, "address"),
        "profile_url": _first_str(raw, "profile_url", "page_url", "url", "link"),
        "source": source,
        "raw": raw,
    }
