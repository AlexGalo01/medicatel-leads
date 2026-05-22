from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field as PydanticField

from mle.clients.brave_client import BraveSearchClient
from mle.db.base import async_session_factory
from mle.repositories.url_scrape_jobs_repository import UrlScrapeJobsRepository
from mle.core.config import get_settings

logger = logging.getLogger(__name__)

_MAX_PAGES = 100

_BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-extensions",
]

_NAV_PLAN_PROMPT = """\
Eres un agente de navegación web. Se te dará:
1. La estructura de una página web (título, links de nav, inputs, botones)
2. Una instrucción del usuario

Analiza y devuelve la mejor acción para cumplir la instrucción.
Devuelve SOLO JSON, sin markdown:
{
  "strategy": "nav_link" | "search_input" | "scrape_directly",
  "nav_link_href": "URL exacta del link (solo si strategy=nav_link)",
  "nav_link_text": "texto del link (solo si strategy=nav_link)",
  "search_query": "términos de búsqueda (solo si strategy=search_input)",
  "reasoning": "explicación breve"
}

Prioridad de decisión:
1. Si hay un link de nav/menú que claramente coincide con la instrucción → nav_link
2. Si la instrucción implica buscar algo y hay input de búsqueda → search_input
3. Si la página ya tiene el contenido directamente → scrape_directly
"""

_EXTRACT_SYSTEM_PROMPT = """\
Eres un extractor de datos estructurados. Se te dará texto visible de una página web de directorio.

Extrae TODAS las entidades (médicos, clínicas, hospitales, empresas, etc.) que encuentres.
El texto puede incluir una sección "ENLACES DE PERFILES ENCONTRADOS" con líneas tipo:
  LINK: Nombre → https://ejemplo.com/perfil/nombre
Usa estas URLs como primary_url de cada entidad correspondiente.

Devuelve un objeto JSON con la clave "entries" que contiene un array de objetos con estas claves exactas:
- display_title: nombre completo
- primary_url: URL del perfil (tómala de la sección LINK si coincide con el nombre, sino "")
- snippet: especialidad, descripción, horario — máx 500 chars, sino null
- entity_type: tipo inferido (médico, clínica, hospital, empresa, etc.)
- city: ciudad si aparece, sino ""
- country: país si aparece, sino ""
- phones: lista de teléfonos encontrados (puede ser vacía)
- emails: lista de emails encontrados (puede ser vacía)
- whatsapp: lista de números de WhatsApp encontrados (busca "WhatsApp", "wa.me", números cerca de "asistente") (puede ser vacía)
- social_urls: lista de URLs de redes sociales (puede ser vacía)

Devuelve SOLO el JSON, sin markdown, sin explicación.
No inventes datos que no estén en el texto.
"""

_ENRICH_SYSTEM_PROMPT = """\
Visitas una página de perfil individual. Extrae la información de contacto.
Devuelve un objeto JSON con estas claves exactas:
- phones: lista de teléfonos (incluyendo extensiones, ej: "+504 2216-6400 ext. 3230")
- emails: lista de emails encontrados
- whatsapp: lista de números de WhatsApp (busca "WhatsApp", "wa.me/", números cerca de "asistente")
- assistant_name: nombre del asistente si aparece, sino ""
- schedule: horario de atención si aparece, sino ""
- location: ubicación exacta (piso, área, clínica) si aparece, sino ""

Devuelve SOLO el JSON, sin markdown, sin explicación.
No inventes datos que no estén en el texto.
"""

_SEARCH_INPUT_SELECTORS = [
    'input[type="search"]',
    'input[name*="search" i]',
    'input[name*="busca" i]',
    'input[name="q"]',
    'input[placeholder*="busca" i]',
    'input[placeholder*="search" i]',
    'input[placeholder*="doctor" i]',
    'input[placeholder*="nombre" i]',
    '.search input[type="text"]',
    '#search input',
]


class _ScrapedEntry(BaseModel):
    display_title: str = ""
    primary_url: str = ""
    snippet: str | None = None
    entity_type: str = ""
    city: str = ""
    country: str = ""
    phones: list[str] = PydanticField(default_factory=list)
    emails: list[str] = PydanticField(default_factory=list)
    whatsapp: list[str] = PydanticField(default_factory=list)
    social_urls: list[str] = PydanticField(default_factory=list)


async def _discover_pages_via_brave(
    target_url: str,
    brave_client: BraveSearchClient,
) -> list[tuple[str, str]]:
    """Descubre páginas del directorio via Brave Search.

    Retorna lista de (page_text, source_url) deduplicada por URL.
    Si falla, retorna lista vacía (fallback a Playwright).
    """
    if not target_url.strip():
        return []

    try:
        domain = urlparse(target_url).netloc.lower()
        if not domain:
            return []

        # Construir query usando el path de la URL (no el user_prompt, que es instrucción para el LLM)
        path_keywords = urlparse(target_url).path.strip("/").replace("-", " ").replace("/", " ").strip()
        brave_query = f"site:{domain} {path_keywords}" if path_keywords else f"site:{domain}"

        # Buscar en Brave con hasta 2 páginas (40 resultados)
        results = await brave_client.web_search(
            query=brave_query,
            count=20,
            pages=2,
        )

        pages: dict[str, str] = {}  # Dedup por URL

        # Procesar resultados de Brave
        # Cada resultado tiene: url, title, text (description), highlights (lista de snippets)
        for item in results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            if not url or url in pages:
                continue

            # Combinar text (description) + highlights (extra_snippets)
            text_parts = []
            text = str(item.get("text", "")).strip()
            if text:
                text_parts.append(text)

            highlights = item.get("highlights")
            if isinstance(highlights, list):
                for h in highlights:
                    h_str = str(h).strip()
                    if h_str and h_str not in text_parts:
                        text_parts.append(h_str)

            combined_text = "\n".join(text_parts)
            if combined_text:
                pages[url] = combined_text

        logger.info(
            "Brave discover_pages target_url=%s domain=%s found=%s",
            target_url, domain, len(pages),
        )
        return [(text, url) for url, text in pages.items()]

    except Exception as exc:
        logger.warning("Brave discover_pages falló para %s (fallback a Playwright): %s", target_url, exc)
        return []


_API_KEYWORDS = ("doctor", "medic", "physician", "staff", "directory", "provider",
                  "specialist", "especialist", "personal", "empleado", "people")


async def _load_page_text_and_next_url(url: str) -> tuple[str, str | None]:
    """Load URL with a fresh Playwright browser, return (body_text, next_page_url).

    Estrategia multicapa:
    1. Intercepta respuestas JSON de APIs internas (SPAs que cargan datos vía XHR/fetch).
    2. Múltiples scrolls para activar infinite scroll / lazy loading.
    3. Extrae JSON embebido en <script> tags (Next.js, SSR, etc.).
    4. Combina todo: API data + DOM text para máxima cobertura.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=_BROWSER_ARGS)
        try:
            page = await browser.new_page()

            # — Interceptar respuestas JSON de la API —
            captured_api_chunks: list[str] = []

            async def _on_response(response: Any) -> None:
                try:
                    content_type = response.headers.get("content-type", "")
                    if response.status != 200 or "json" not in content_type:
                        return
                    resp_url = response.url.lower()
                    # Filtrar solo URLs que parecen datos de directorio/personas
                    if not any(kw in resp_url for kw in _API_KEYWORDS):
                        # También capturar rutas tipo /api/* con respuesta de lista
                        if "/api/" not in resp_url and "/graphql" not in resp_url:
                            return
                    body = await response.body()
                    if len(body) < 50:
                        return
                    snippet = body[:20_000].decode("utf-8", errors="replace")
                    captured_api_chunks.append(f"[API:{response.url}]\n{snippet}")
                    logger.debug("Captured API response: %s (%d bytes)", response.url, len(body))
                except Exception:
                    pass

            page.on("response", _on_response)

            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

            # — Espera a que SPAs rendericen contenido (Firebase, React, Vue, etc.) —
            try:
                await page.wait_for_function(
                    "document.body.innerText.length > 500",
                    timeout=8_000,
                )
            except Exception:
                pass  # Fallback: proceed with whatever loaded
            await page.wait_for_timeout(2_500)
            prev_height = -1
            for _ in range(5):
                height: int = await page.evaluate("document.body.scrollHeight")
                if height == prev_height:
                    break
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2_000)
                prev_height = height

            # — Extraer JSON embebido en <script> (Next.js __NEXT_DATA__, Nuxt, etc.) —
            embedded_json: list[str] = await page.evaluate("""() => {
                const results = [];
                const scripts = document.querySelectorAll(
                    'script[type="application/json"], script#__NEXT_DATA__, script[id*="data"]'
                );
                for (const s of scripts) {
                    const t = (s.textContent || '').trim();
                    if (t.length > 100 && t.length < 200000) results.push(t.slice(0, 15000));
                }
                return results;
            }""")

            # — DOM text —
            text = await page.inner_text("body")

            # — Extract profile/detail links from the page (for LLM to map to entries) —
            profile_links: list[str] = await page.evaluate("""() => {
                const links = [];
                const seen = new Set();
                // Cards, products, list items that link to profiles
                const anchors = document.querySelectorAll(
                    '.product a, .entry a, .card a, article a, ' +
                    '[class*="doctor"] a, [class*="medic"] a, [class*="profile"] a, ' +
                    'a.doctor-badge, a.doctor-card, a.doctor-card-modern, ' +
                    '.woocommerce a.woocommerce-LoopProduct-link, ' +
                    'a[href*="/dr/"], a[href*="/doctor" i], a[href*="/perfil"], a[href*="/profile"], a[href*="/medicos/"], a[href*="/Detalles/"]'
                );
                for (const a of anchors) {
                    const href = a.href || '';
                    const text = (a.innerText || '').trim().slice(0, 100);
                    if (href && !seen.has(href) && text.length > 2
                        && !href.includes('add-to-cart') && !href.includes('?add_to_wishlist')
                        && !href.includes('#') && !href.endsWith('.jpg') && !href.endsWith('.png')) {
                        seen.add(href);
                        links.push('LINK: ' + text + ' → ' + href);
                    }
                }
                return links.slice(0, 200);
            }""")

            # — Combinar todas las fuentes —
            parts: list[str] = []
            if captured_api_chunks:
                parts.append(
                    "=== DATOS API (JSON interceptado) ===\n"
                    + "\n---\n".join(captured_api_chunks[:5])
                )
            if embedded_json:
                parts.append(
                    "=== JSON EMBEBIDO EN PÁGINA ===\n"
                    + "\n---\n".join(embedded_json[:3])
                )
            if profile_links:
                parts.append(
                    "=== ENLACES DE PERFILES ENCONTRADOS ===\n"
                    + "\n".join(profile_links)
                )
            parts.append("=== TEXTO DOM ===\n" + text)
            combined = "\n\n".join(parts)

            # Detect next page URL using common pagination patterns
            next_url: str | None = await page.evaluate("""() => {
                // Strategy 1: find .current / .active marker, get next sibling <a>
                const currentSelectors = [
                    '.page-numbers.current',
                    '.wp-pagenavi span.current',
                    '.pagination .active',
                    '.pagination .page-item.active',
                    '.page-link.active',
                    '[aria-current="page"]',
                ];
                for (const sel of currentSelectors) {
                    const current = document.querySelector(sel);
                    if (current) {
                        // Walk up to the <li> if needed (Bootstrap pagination)
                        const li = current.closest('li') || current;
                        let el = li.nextElementSibling;
                        while (el) {
                            if (el.tagName === 'A' && el.href) return el.href;
                            const a = el.querySelector && el.querySelector('a[href]');
                            if (a && a.href) return a.href;
                            el = el.nextElementSibling;
                        }
                    }
                }
                // Strategy 2: explicit next/siguiente link
                const nextSelectors = [
                    'a.next', 'a[rel="next"]', '.page-numbers.next',
                    'a[class*="next"]',
                    'a[aria-label*="next" i]', 'a[aria-label*="siguiente" i]',
                    '.page-item a[aria-label*="Next" i]', '.page-item a[aria-label*="Siguiente" i]',
                    'a.page-link[aria-label*="Next" i]', 'a.page-link[aria-label*="Siguiente" i]',
                ];
                for (const sel of nextSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.href) return el.href;
                }
                return null;
            }""")

            return combined, next_url
        finally:
            await browser.close()


async def _scrape_url_text(url: str) -> str:
    """Scrape full visible text from a single URL using Playwright."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=_BROWSER_ARGS)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            # Dismiss Facebook login modal if present
            if "facebook.com" in url.lower():
                from mle.services.facebook_search_service import dismiss_facebook_modal
                await dismiss_facebook_modal(page)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1_500)
            return await page.inner_text("body")
        finally:
            await browser.close()


async def _fetch_pages_content(
    url_pairs: list[tuple[str, str]],
    job_id: UUID,
) -> list[tuple[str, str]]:
    """Given (snippet, url) pairs from Brave, scrape full content with Playwright."""
    results: list[tuple[str, str]] = []
    for _, url in url_pairs:
        try:
            text = await asyncio.wait_for(_scrape_url_text(url), timeout=45)
            if text.strip():
                results.append((text, url))
                logger.info("Scraped %d chars from %s job_id=%s", len(text), url, job_id)
        except Exception as exc:
            logger.warning("Failed to scrape %s job_id=%s: %s", url, job_id, exc)
    return results


async def _capture_page_structure(page: Any) -> str:
    """Capture structured info from page: nav links, inputs, buttons."""
    structure = await page.evaluate("""() => {
        const navLinks = Array.from(
            document.querySelectorAll('nav a, header a, .navbar a, .menu a, .nav a')
        ).slice(0, 40).map(a => ({
            text: a.innerText.trim().replace(/\\s+/g, ' '),
            href: a.href
        })).filter(a => a.text && a.text.length < 80);

        const inputs = Array.from(
            document.querySelectorAll('input:not([type=hidden]), textarea')
        ).map(i => ({ type: i.type, name: i.name, placeholder: i.placeholder }));

        const buttons = Array.from(
            document.querySelectorAll('button, a.btn, a[class*="button"]')
        ).slice(0, 20).map(b => ({ text: b.innerText.trim().replace(/\\s+/g, ' ') }))
         .filter(b => b.text);

        const headings = Array.from(
            document.querySelectorAll('h1, h2')
        ).slice(0, 5).map(h => h.innerText.trim());

        return JSON.stringify({
            title: document.title,
            headings,
            nav_links: navLinks,
            inputs,
            buttons,
        });
    }""")
    return structure


async def _plan_page_navigation(
    page_snapshot: str, user_prompt: str, settings: Any
) -> dict[str, Any]:
    """Use LLM to decide navigation strategy. Gemini primary, OpenAI fallback."""
    import httpx

    user_content = f"Instrucción: {user_prompt}\n\nEstructura de la página:\n{page_snapshot}"
    full_prompt = _NAV_PLAN_PROMPT + "\n\n" + user_content

    def _parse(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if "```" in text:
                text = text[: text.rfind("```")]
        try:
            return json.loads(text)
        except Exception:
            return {"strategy": "scrape_directly", "reasoning": "parse error"}

    # Gemini primero
    if settings.google_api_key:
        try:
            body = {"contents": [{"parts": [{"text": full_prompt}]}]}
            gemini_url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{settings.google_model}:generateContent?key={settings.google_api_key}"
            )
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(gemini_url, json=body, headers={"Content-Type": "application/json"})
                r.raise_for_status()
                raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return _parse(raw)
        except Exception as exc:
            logger.warning("Gemini nav plan falló: %r", exc)

    # Fallback: OpenAI
    if settings.openai_api_key:
        try:
            oai = AsyncOpenAI(api_key=settings.openai_api_key)
            response = await oai.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": _NAV_PLAN_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            return _parse(response.choices[0].message.content or "{}")
        except Exception as exc:
            logger.warning("OpenAI nav plan falló: %r", exc)

    return {"strategy": "scrape_directly", "reasoning": "sin LLM disponible"}


async def _navigate_and_scrape(
    target_url: str,
    user_prompt: str,
    settings: Any,
    job_id: UUID,
) -> list[tuple[str, str]]:
    """Navigate using LLM-guided strategy and scrape results with pagination."""
    results: list[tuple[str, str]] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=_BROWSER_ARGS)
        try:
            page = await browser.new_page()
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(1_500)

            # 1. Capture page structure
            snapshot = await _capture_page_structure(page)
            logger.info("Page snapshot captured, %d chars job_id=%s", len(snapshot), job_id)

            # 2. Si la página ya tiene contenido sustancial, no navegar — evita que el LLM
            #    navegue a una URL sin query params (ej. /medicos sin ?all=true) perdiendo resultados.
            current_body_len: int = await page.evaluate("document.body.innerText.length")
            if current_body_len > 2_000:
                strategy = "scrape_directly"
                logger.info(
                    "Page already has content (%d chars), skipping LLM nav job_id=%s",
                    current_body_len, job_id,
                )
            else:
                # LLM decides navigation strategy only when page seems empty / form-only
                plan = await _plan_page_navigation(snapshot, user_prompt, settings)
                strategy = plan.get("strategy", "scrape_directly")
                logger.info("Nav plan: strategy=%s reasoning=%r job_id=%s",
                            strategy, plan.get("reasoning"), job_id)

            # 3. Execute strategy
            if strategy == "nav_link":
                href = plan.get("nav_link_href", "")
                link_text = plan.get("nav_link_text", "")
                if href:
                    clicked = False
                    try:
                        el = await page.query_selector(f'a[href="{href}"]')
                        if not el:
                            clicked = await page.evaluate(
                                f"""() => {{
                                    const links = document.querySelectorAll('nav a, header a, .navbar a, .menu a');
                                    for (const a of links) {{
                                        if (a.innerText.trim().toLowerCase().includes('{link_text.lower()}')) {{
                                            a.click(); return true;
                                        }}
                                    }}
                                    return false;
                                }}"""
                            )
                        else:
                            await el.click()
                            clicked = True
                    except Exception as exc:
                        logger.warning("Nav click failed job_id=%s: %s", job_id, exc)

                    if clicked or href:
                        if not clicked:
                            await page.goto(href, wait_until="domcontentloaded", timeout=30_000)
                        try:
                            await page.wait_for_load_state("load", timeout=10_000)
                        except Exception:
                            pass
                        await page.wait_for_timeout(2_000)

            elif strategy == "search_input":
                query = plan.get("search_query", "")
                if query:
                    search_input = None
                    for selector in _SEARCH_INPUT_SELECTORS:
                        el = await page.query_selector(selector)
                        if el and await el.is_visible():
                            search_input = el
                            break
                    if search_input:
                        await search_input.click()
                        await search_input.fill(query)
                        submitted = False
                        for btn_sel in ['button[type="submit"]', 'form button', 'button[class*="search" i]']:
                            btn = await page.query_selector(btn_sel)
                            if btn and await btn.is_visible():
                                await btn.click()
                                submitted = True
                                break
                        if not submitted:
                            await search_input.press("Enter")
                        try:
                            await page.wait_for_load_state("load", timeout=15_000)
                        except Exception:
                            pass
                        await page.wait_for_timeout(3_000)

            # 4. Scrape + paginate
            page_count = 0
            while page_count < _MAX_PAGES:
                page_count += 1
                current_url = page.url
                text = await page.inner_text("body")
                if text.strip():
                    results.append((text, current_url))
                    logger.info("Nav page %d: %d chars job_id=%s", page_count, len(text), job_id)

                next_url: str | None = await page.evaluate("""() => {
                    const currentSelectors = ['.page-numbers.current', '.wp-pagenavi span.current',
                        '.pagination .active', '.pagination .page-item.active',
                        '.page-link.active', '[aria-current="page"]'];
                    for (const sel of currentSelectors) {
                        const cur = document.querySelector(sel);
                        if (cur) {
                            const li = cur.closest('li') || cur;
                            let el = li.nextElementSibling;
                            while (el) {
                                if (el.tagName === 'A' && el.href) return el.href;
                                const a = el.querySelector && el.querySelector('a[href]');
                                if (a && a.href) return a.href;
                                el = el.nextElementSibling;
                            }
                        }
                    }
                    const nextSelectors = ['a.next', 'a[rel="next"]', '.page-numbers.next',
                        'a[class*="next"]', 'a[aria-label*="next" i]', 'a[aria-label*="siguiente" i]',
                        '.page-item a[aria-label*="Next" i]', '.page-item a[aria-label*="Siguiente" i]',
                        'a.page-link[aria-label*="Next" i]', 'a.page-link[aria-label*="Siguiente" i]'];
                    for (const sel of nextSelectors) {
                        const el = document.querySelector(sel);
                        if (el && el.href) return el.href;
                    }
                    return null;
                }""")

                if not next_url or next_url == current_url:
                    break
                await page.goto(next_url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(1_500)
        finally:
            await browser.close()
    return results


def _parse_llm_json(raw: str) -> list[_ScrapedEntry]:
    """Parsea la respuesta JSON del LLM y retorna lista de entradas."""
    # Limpiar markdown fences si el LLM los añade
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    try:
        parsed = json.loads(text)
        items: list = parsed.get("entries", []) if isinstance(parsed, dict) else []
        return [_ScrapedEntry(**e) for e in items if isinstance(e, dict)]
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("LLM parse error: %s | raw=%s", exc, raw[:300])
        return []


async def _extract_with_gemini(
    page_text: str, user_prompt: str, settings: Any
) -> list[_ScrapedEntry]:
    """Extrae entradas usando Gemini vía REST (mismo patrón que GeminiClient)."""
    import httpx

    prompt = (
        f"{_EXTRACT_SYSTEM_PROMPT}\n\n"
        f"Instrucción adicional: {user_prompt}\n\n"
        f"Texto de la página:\n---\n{page_text[:35_000]}\n---"
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.google_model}:generateContent?key={settings.google_api_key}"
    )
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=body, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        payload = response.json()

    raw = payload["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_llm_json(raw)


async def _extract_with_openai(
    page_text: str, user_prompt: str, settings: Any
) -> list[_ScrapedEntry]:
    """Extrae entradas usando OpenAI."""
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    user_message = (
        f"Instrucción adicional: {user_prompt}\n\n"
        f"Texto de la página:\n---\n{page_text[:35_000]}\n---"
    )
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or ""
    return _parse_llm_json(raw)


async def _extract_entries_with_llm(
    page_text: str, user_prompt: str, settings: Any
) -> list[_ScrapedEntry]:
    """Extrae entradas usando Gemini (primario) con fallback a OpenAI."""
    # Gemini primero — es el LLM principal configurado y ya funcional
    if settings.google_api_key:
        try:
            return await _extract_with_gemini(page_text, user_prompt, settings)
        except Exception as exc:
            logger.warning("Gemini extraction falló, intentando OpenAI: %r", exc)

    # Fallback: OpenAI
    if settings.openai_api_key:
        return await _extract_with_openai(page_text, user_prompt, settings)

    raise RuntimeError("Sin proveedor LLM configurado para extracción URL")


def _build_preview(entries: list[_ScrapedEntry]) -> list[dict[str, Any]]:
    preview = []
    for i, entry in enumerate(entries[:200]):
        preview.append({
            "index": i + 1,
            "title": entry.display_title[:500],
            "url": entry.primary_url[:2000],
            "snippet": entry.snippet[:2000] if entry.snippet else None,
            "city": entry.city[:120],
            "phones": entry.phones,
            "emails": entry.emails,
            "whatsapp": entry.whatsapp,
        })
    return preview


def _is_pdf_url(url: str) -> bool:
    """Detecta si la URL apunta a un PDF."""
    parsed = urlparse(url.split("?")[0].split("#")[0])
    return parsed.path.lower().endswith(".pdf")


async def _download_and_extract_pdf(url: str) -> list[tuple[str, str]]:
    """Descarga un PDF via httpx y extrae texto de cada página con pdfplumber."""
    import pdfplumber
    import tempfile
    import os

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

    # Guardar a archivo temporal
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(response.content)
        tmp_path = tmp.name

    try:
        pages: list[tuple[str, str]] = []
        with pdfplumber.open(tmp_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                # También extraer tablas como texto
                tables = page.extract_tables() or []
                for table in tables:
                    for row in table:
                        if row:
                            cells = [str(c or "").strip() for c in row]
                            text += "\n" + " | ".join(cells)
                if text.strip():
                    pages.append((text, f"{url}#page={i + 1}"))
        logger.info("PDF extracted %d pages with text from %s", len(pages), url)
        return pages
    finally:
        os.unlink(tmp_path)


async def run_url_scrape_pipeline(job_id: UUID) -> None:
    settings = get_settings()

    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
        job = await repo.get_by_id(job_id)
        if job is None:
            logger.error("UrlScrapeJob not found job_id=%s", job_id)
            return
        await repo.update_status(job_id, "running", 10)

    all_entries: list[_ScrapedEntry] = []
    pages_loaded: list[tuple[str, str]] = []

    # --- PDF branch: download + pdfplumber ---
    if _is_pdf_url(job.target_url):
        try:
            logger.info("Detected PDF URL, downloading job_id=%s", job_id)
            pages_loaded = await asyncio.wait_for(
                _download_and_extract_pdf(job.target_url),
                timeout=120,
            )
            logger.info("PDF: %d pages extracted job_id=%s", len(pages_loaded), job_id)
        except Exception as exc:
            logger.error("PDF download/extract failed job_id=%s: %s", job_id, exc)
            async with async_session_factory() as session:
                repo = UrlScrapeJobsRepository(session)
                await repo.update_status(
                    job_id, "error", 10,
                    metadata_json={"error": str(exc), "stage": "pdf_download"},
                )
            return
    else:
        # --- Web scraping strategies (existing flow) ---
        brave_client = BraveSearchClient(api_key=settings.brave_search_api_key)

        # Strategy 1: LLM-guided navigation
        try:
            pages_loaded = await asyncio.wait_for(
                _navigate_and_scrape(job.target_url, job.user_prompt, settings, job_id),
                timeout=180,
            )
            logger.info("LLM navigation found %d pages job_id=%s", len(pages_loaded), job_id)
        except Exception as exc:
            logger.warning("LLM navigation failed job_id=%s: %s", job_id, exc)

        # Strategy 2: Brave discovery + Playwright scraping
        if not pages_loaded:
            try:
                brave_url_pairs = await asyncio.wait_for(
                    _discover_pages_via_brave(job.target_url, brave_client),
                    timeout=60,
                )
                logger.info("Brave discovered %d URLs job_id=%s", len(brave_url_pairs), job_id)
                if brave_url_pairs:
                    pages_loaded = await _fetch_pages_content(brave_url_pairs[:_MAX_PAGES], job_id)
                    logger.info("Scraped full content for %d pages job_id=%s", len(pages_loaded), job_id)
            except asyncio.TimeoutError:
                logger.warning("Brave discover timeout, falling back to Playwright job_id=%s", job_id)
            except Exception as exc:
                logger.warning("Brave discover failed (fallback to Playwright) job_id=%s: %s", job_id, exc)

        # Strategy 3: Playwright pagination fallback
        if not pages_loaded:
            logger.info("No pages from Brave, using Playwright pagination job_id=%s", job_id)
            current_url: str | None = job.target_url
            page_num = 0

            while current_url and page_num < _MAX_PAGES:
                async with async_session_factory() as session:
                    repo = UrlScrapeJobsRepository(session)
                    current_job = await repo.get_by_id(job_id)
                    if current_job and current_job.status == "cancelled":
                        logger.info("Job cancelled during Playwright phase job_id=%s", job_id)
                        return
                page_num += 1
                progress = min(10 + page_num * 12, 85)

                async with async_session_factory() as session:
                    repo = UrlScrapeJobsRepository(session)
                    await repo.update_status(job_id, "running", progress)

                try:
                    page_text, next_url = await asyncio.wait_for(
                        _load_page_text_and_next_url(current_url),
                        timeout=45,
                    )
                    pages_loaded.append((page_text, current_url))
                except asyncio.TimeoutError:
                    logger.warning("Playwright page %d load timed out, stopping job_id=%s", page_num, job_id)
                    break
                except Exception as exc:
                    logger.error("Playwright page %d load failed job_id=%s: %s", page_num, job_id, exc)
                    if page_num == 1:
                        async with async_session_factory() as session:
                            repo = UrlScrapeJobsRepository(session)
                            await repo.update_status(
                                job_id, "error", progress,
                                metadata_json={"error": str(exc), "stage": "page_load"},
                            )
                        return
                    break

                current_url = next_url

    # --- Check if cancelled before LLM extraction ---
    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
        current_job = await repo.get_by_id(job_id)
        if current_job and current_job.status == "cancelled":
            logger.info("Job cancelled before LLM extraction job_id=%s", job_id)
            return
        await repo.update_status(job_id, "running", 45)

    # --- Extracción secuencial: página a página, guardando resultados progresivamente ---
    page_texts = [(text, url) for text, url in pages_loaded[:_MAX_PAGES]]
    total_pages = len(page_texts)

    for idx, (text, _) in enumerate(page_texts):
        # Cancelación
        async with async_session_factory() as session:
            repo = UrlScrapeJobsRepository(session)
            current_job = await repo.get_by_id(job_id)
            if current_job and current_job.status == "cancelled":
                logger.info("Job cancelled during LLM extraction job_id=%s", job_id)
                return

        try:
            entries = await asyncio.wait_for(
                _extract_entries_with_llm(text, job.user_prompt, settings),
                timeout=150,
            )
        except Exception as exc:
            logger.error("Page %d LLM failed job_id=%s: %r", idx + 1, job_id, exc)
            if idx == 0 and not all_entries:
                async with async_session_factory() as session:
                    repo = UrlScrapeJobsRepository(session)
                    await repo.update_status(
                        job_id, "error", 45,
                        metadata_json={"error": str(exc), "stage": "llm_extract"},
                    )
                return
            # Para páginas 2+, continuar con las siguientes aunque falle una
            continue

        all_entries.extend(entries)
        logger.info(
            "Page %d/%d: %d entries extracted (total=%d) job_id=%s",
            idx + 1, total_pages, len(entries), len(all_entries), job_id,
        )

        # Guardar progreso parcial después de cada página
        progress = 45 + int((idx + 1) / total_pages * 50)
        preview = _build_preview(all_entries)
        async with async_session_factory() as session:
            repo = UrlScrapeJobsRepository(session)
            await repo.update_status(
                job_id, "running", progress,
                metadata_json={
                    "scrape_results_preview": preview,
                    "entries_count": len(preview),
                    "pages_scraped": idx + 1,
                    "pages_total": total_pages,
                    "stage": "extracting",
                },
            )

    # --- Guardar resultado final ---
    preview = _build_preview(all_entries)
    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
        await repo.update_status(
            job_id, "completed", 100,
            metadata_json={
                "scrape_results_preview": preview,
                "entries_count": len(preview),
                "pages_scraped": total_pages,
                "stage": "done",
            },
        )

    logger.info("URL scrape done job_id=%s pages=%d entries=%d", job_id, total_pages, len(all_entries))


async def _enrich_single_profile(url: str, enrich_prompt: str | None, settings: Any) -> dict[str, Any]:
    """Visita una URL de perfil y extrae contactos usando LLM."""
    try:
        text = await asyncio.wait_for(_scrape_url_text(url), timeout=30)
        if not text or len(text.strip()) < 50:
            return {}
    except Exception as exc:
        logger.warning("Enrich scrape failed for %s: %s", url, exc)
        return {}

    system_prompt = enrich_prompt or _ENRICH_SYSTEM_PROMPT
    user_message = f"{system_prompt}\n\nTexto de la página:\n---\n{text[:20_000]}\n---"

    import httpx

    # Gemini primero
    if settings.google_api_key:
        try:
            body = {"contents": [{"parts": [{"text": user_message}]}]}
            gemini_url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{settings.google_model}:generateContent?key={settings.google_api_key}"
            )
            async with httpx.AsyncClient(timeout=45.0) as client:
                r = await client.post(gemini_url, json=body, headers={"Content-Type": "application/json"})
                r.raise_for_status()
                raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return _parse_enrich_json(raw)
        except Exception as exc:
            logger.warning("Gemini enrich failed for %s: %s", url, exc)

    # Fallback: OpenAI
    if settings.openai_api_key:
        try:
            oai = AsyncOpenAI(api_key=settings.openai_api_key)
            response = await oai.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Texto de la página:\n---\n{text[:20_000]}\n---"},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            return _parse_enrich_json(raw)
        except Exception as exc:
            logger.warning("OpenAI enrich failed for %s: %s", url, exc)

    return {}


def _parse_enrich_json(raw: str) -> dict[str, Any]:
    """Parsea la respuesta JSON del LLM de enriquecimiento."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if "```" in text:
            text = text[: text.rfind("```")]
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return {}
        return {
            "phones": parsed.get("phones", []) or [],
            "emails": parsed.get("emails", []) or [],
            "whatsapp": parsed.get("whatsapp", []) or [],
            "assistant_name": parsed.get("assistant_name", ""),
            "schedule": parsed.get("schedule", ""),
            "location": parsed.get("location", ""),
        }
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Enrich parse error: %s | raw=%s", exc, raw[:300])
        return {}


async def run_url_scrape_enrichment(job_id: UUID, entry_indices: list[int] | None = None) -> None:
    """Enriquecimiento de nivel 2: visita URLs de perfil para extraer contactos directos."""
    settings = get_settings()

    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
        job = await repo.get_by_id(job_id)
        if job is None:
            logger.error("Enrich: job not found job_id=%s", job_id)
            return

    meta = job.metadata_json if isinstance(job.metadata_json, dict) else {}
    preview_raw = meta.get("scrape_results_preview") or []
    if not isinstance(preview_raw, list) or not preview_raw:
        logger.warning("Enrich: no preview items job_id=%s", job_id)
        async with async_session_factory() as session:
            repo = UrlScrapeJobsRepository(session)
            await repo.update_status(job_id, "completed", 100)
        return

    # Buscar enrich_prompt del ScrapingSite vinculado (por dominio)
    enrich_prompt: str | None = None
    try:
        from mle.repositories.scraping_sites_repository import ScrapingSitesRepository
        target_domain = urlparse(job.target_url).netloc.lower()
        async with async_session_factory() as session:
            sites_repo = ScrapingSitesRepository(session)
            all_sites = await sites_repo.list_all()
            for site in all_sites:
                if target_domain in urlparse(site.url).netloc.lower():
                    enrich_prompt = site.enrich_prompt
                    break
    except Exception as exc:
        logger.warning("Could not load enrich_prompt: %s", exc)

    # Filtrar items a enriquecer
    indices_set = set(entry_indices) if entry_indices else None
    items_to_enrich = []
    for item in preview_raw:
        if not isinstance(item, dict):
            continue
        idx = item.get("index", 0)
        url = item.get("url", "").strip()
        if not url:
            continue
        if indices_set is not None and idx not in indices_set:
            continue
        items_to_enrich.append((idx, item))

    if not items_to_enrich:
        logger.info("Enrich: no items with URLs to enrich job_id=%s", job_id)
        async with async_session_factory() as session:
            repo = UrlScrapeJobsRepository(session)
            await repo.update_status(job_id, "completed", 100)
        return

    logger.info("Enrich: starting %d profiles job_id=%s", len(items_to_enrich), job_id)

    # Construir mapa idx→preview_item para actualizar in-place
    preview_map: dict[int, dict] = {item.get("index", 0): item for item in preview_raw if isinstance(item, dict)}

    enriched_count = 0
    total = len(items_to_enrich)

    for i, (idx, item) in enumerate(items_to_enrich):
        # Check cancellation
        async with async_session_factory() as session:
            repo = UrlScrapeJobsRepository(session)
            current = await repo.get_by_id(job_id)
            if current and current.status == "cancelled":
                logger.info("Enrich cancelled job_id=%s", job_id)
                return

        profile_url = item.get("url", "")
        # Resolve relative URLs
        if profile_url.startswith("/"):
            parsed = urlparse(job.target_url)
            profile_url = f"{parsed.scheme}://{parsed.netloc}{profile_url}"

        logger.info("Enrich %d/%d: visiting %s", i + 1, total, profile_url)

        contacts = await _enrich_single_profile(profile_url, enrich_prompt, settings)

        if contacts:
            # Merge contacts into preview item
            existing = preview_map.get(idx, item)
            if contacts.get("phones"):
                existing_phones = existing.get("phones", [])
                existing["phones"] = list(dict.fromkeys(existing_phones + contacts["phones"]))
            if contacts.get("emails"):
                existing_emails = existing.get("emails", [])
                existing["emails"] = list(dict.fromkeys(existing_emails + contacts["emails"]))
            if contacts.get("whatsapp"):
                existing_wa = existing.get("whatsapp", [])
                existing["whatsapp"] = list(dict.fromkeys(existing_wa + contacts["whatsapp"]))
            # Enrich snippet with extra data
            extra_parts = []
            if contacts.get("assistant_name"):
                extra_parts.append(f"Asistente: {contacts['assistant_name']}")
            if contacts.get("schedule"):
                extra_parts.append(f"Horario: {contacts['schedule']}")
            if contacts.get("location"):
                extra_parts.append(f"Ubicación: {contacts['location']}")
            if extra_parts:
                current_snippet = existing.get("snippet") or ""
                existing["snippet"] = (current_snippet + " | " + " | ".join(extra_parts))[:2000]
            enriched_count += 1

        # Update progress
        progress = int((i + 1) / total * 100)
        updated_preview = list(preview_map.values())
        async with async_session_factory() as session:
            repo = UrlScrapeJobsRepository(session)
            await repo.update_status(
                job_id, "running", progress,
                metadata_json={
                    **meta,
                    "scrape_results_preview": updated_preview,
                    "entries_count": len(updated_preview),
                    "stage": "enriching",
                },
            )

        # Rate limit: wait between requests
        await asyncio.sleep(1.5)

    # Final save
    final_preview = list(preview_map.values())
    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
        await repo.update_status(
            job_id, "completed", 100,
            metadata_json={
                **meta,
                "scrape_results_preview": final_preview,
                "entries_count": len(final_preview),
                "stage": "done",
            },
        )

    logger.info("Enrich done job_id=%s enriched=%d/%d", job_id, enriched_count, total)
