from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID
from urllib.parse import urlparse

from openai import AsyncOpenAI
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field as PydanticField

from mle.clients.brave_client import BraveSearchClient
from mle.db.base import async_session_factory
from mle.repositories.url_scrape_jobs_repository import UrlScrapeJobsRepository
from mle.repositories.scraping_sites_repository import ScrapingSitesRepository
from mle.core.config import get_settings

logger = logging.getLogger(__name__)

_MAX_PAGES = 10

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
Devuelve un objeto JSON con la clave "entries" que contiene un array de objetos con estas claves exactas:
- display_title: nombre completo
- primary_url: URL del perfil si aparece en el texto, sino ""
- snippet: especialidad, descripción, horario — máx 500 chars, sino null
- entity_type: tipo inferido (médico, clínica, hospital, empresa, etc.)
- city: ciudad si aparece, sino ""
- country: país si aparece, sino ""
- phones: lista de teléfonos encontrados (puede ser vacía)
- emails: lista de emails encontrados (puede ser vacía)
- social_urls: lista de URLs de redes sociales (puede ser vacía)

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

            # — Espera inicial + múltiples scrolls para infinite scroll —
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

            # — Extraer enlaces + teléfonos ocultos en atributos HTML —
            # inner_text() no captura href ni onclick; los extraemos explícitamente.
            link_data: list[dict] = await page.evaluate("""() => {
                const items = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const href = a.getAttribute('href') || '';
                    if (!href || href.startsWith('#') || href.startsWith('javascript')) return;
                    const text = (a.innerText || '').trim().replace(/\\s+/g, ' ').substring(0, 200);
                    // Buscar tel: en onclick de este elemento y sus hijos
                    let phone = null;
                    const candidates = [a, ...a.querySelectorAll('[onclick]')];
                    for (const el of candidates) {
                        const onclick = el.getAttribute('onclick') || '';
                        const m = onclick.match(/tel:([+\\d\\s\\-().]+)/);
                        if (m) { phone = m[1].trim(); break; }
                    }
                    items.push({ href, text, phone });
                });
                return items.slice(0, 600);
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
            if link_data:
                link_lines = []
                for item in link_data:
                    line = f"LINK href={item['href']} | text={item['text']}"
                    if item.get("phone"):
                        line += f" | phone={item['phone']}"
                    link_lines.append(line)
                parts.append("=== LINKS Y TELÉFONOS DEL DOM ===\n" + "\n".join(link_lines))
            parts.append("=== TEXTO DOM ===\n" + text)
            combined = "\n\n".join(parts)

            # Detect next page URL using common pagination patterns
            next_url: str | None = await page.evaluate("""() => {
                // Strategy 1: find .current / .active marker, get next sibling <a>
                const currentSelectors = [
                    '.page-numbers.current',
                    '.wp-pagenavi span.current',
                    '.pagination .active',
                    '[aria-current="page"]',
                ];
                for (const sel of currentSelectors) {
                    const current = document.querySelector(sel);
                    if (current) {
                        let el = current.nextElementSibling;
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
                        '.pagination .active', '[aria-current="page"]'];
                    for (const sel of currentSelectors) {
                        const cur = document.querySelector(sel);
                        if (cur) {
                            let el = cur.nextElementSibling;
                            while (el) {
                                if (el.tagName === 'A' && el.href) return el.href;
                                const a = el.querySelector && el.querySelector('a[href]');
                                if (a && a.href) return a.href;
                                el = el.nextElementSibling;
                            }
                        }
                    }
                    const nextSelectors = ['a.next', 'a[rel="next"]', '.page-numbers.next',
                        'a[class*="next"]', 'a[aria-label*="next" i]', 'a[aria-label*="siguiente" i]'];
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
        # Normalize field names: some prompts (e.g., DDH) return "url" instead of "primary_url"
        normalized = []
        for e in items:
            if isinstance(e, dict):
                if "url" in e and "primary_url" not in e:
                    e = {**e, "primary_url": e["url"]}
                normalized.append(e)
        return [_ScrapedEntry(**e) for e in normalized]
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
        })
    return preview


async def run_url_scrape_pipeline(job_id: UUID) -> None:
    settings = get_settings()

    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
        job = await repo.get_by_id(job_id)
        if job is None:
            logger.error("UrlScrapeJob not found job_id=%s", job_id)
            return
        await repo.update_status(job_id, "running", 10)

    brave_client = BraveSearchClient(api_key=settings.brave_search_api_key)

    all_entries: list[_ScrapedEntry] = []
    pages_loaded: list[tuple[str, str]] = []

    # --- Strategy 1: LLM-guided navigation ---
    try:
        pages_loaded = await asyncio.wait_for(
            _navigate_and_scrape(job.target_url, job.user_prompt, settings, job_id),
            timeout=180,
        )
        logger.info("LLM navigation found %d pages job_id=%s", len(pages_loaded), job_id)
    except Exception as exc:
        logger.warning("LLM navigation failed job_id=%s: %s", job_id, exc)

    # --- Strategy 2: Brave discovery + Playwright scraping ---
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

    # --- Fallback to Playwright if Brave found nothing ---
    if not pages_loaded:
        logger.info("No pages from Brave, using Playwright pagination job_id=%s", job_id)
        current_url: str | None = job.target_url
        page_num = 0

        while current_url and page_num < _MAX_PAGES:
            # Check if job was cancelled
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

    # --- Guardar resultado nivel 1 ---
    preview = _build_preview(all_entries)

    # Check if there are entries that need profile enrichment.
    # Enrich if:
    # 1. Any entry has URL but no contact (classic case), OR
    # 2. Job came from a scraping_site with enrich_prompt (site knows how to extract contacts from profiles)
    has_entries_with_url_no_contacts = any(
        item.get("url") and not item.get("phones") and not item.get("emails")
        for item in preview
    )

    # Load site to check for enrich_prompt
    site_has_enrich_prompt = False
    if job.scraping_site_id:
        async with async_session_factory() as session:
            sites_repo = ScrapingSitesRepository(session)
            site = await sites_repo.get(job.scraping_site_id)
            site_has_enrich_prompt = site is not None and bool(site.enrich_prompt)

    needs_enrichment = has_entries_with_url_no_contacts or (site_has_enrich_prompt and preview)

    if needs_enrichment:
        # Save partial results and continue with profile enrichment
        async with async_session_factory() as session:
            repo = UrlScrapeJobsRepository(session)
            await repo.update_status(
                job_id, "running", 50,
                metadata_json={
                    "scrape_results_preview": preview,
                    "entries_count": len(preview),
                    "pages_scraped": total_pages,
                    "stage": "enriching",
                },
            )
        logger.info("URL scrape level 1 done job_id=%s entries=%d — starting profile enrichment", job_id, len(all_entries))
        await run_url_scrape_enrichment(job_id)
    else:
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


async def run_url_scrape_enrichment(
    job_id: UUID, entry_indices: list[int] | None = None
) -> None:
    """
    Enrich URL scrape results by visiting individual profile URLs and extracting contact info.

    - Visits each entry's URL (level 2 scraping)
    - Extracts phones/emails from the profile page
    - Updates metadata_json with enriched entries
    - Changes stage to "enriched"
    """
    settings = get_settings()

    # Load job data in short-lived session
    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
        job = await repo.get(job_id)
        if not job or job.status not in ("running", "completed"):
            logger.warning("Enrichment job_id=%s not found or not in enriching state", job_id)
            return
        enrich_prompt = None
        if job.scraping_site_id:
            sites_repo = ScrapingSitesRepository(session)
            site = await sites_repo.get(job.scraping_site_id)
            if site and site.enrich_prompt:
                enrich_prompt = site.enrich_prompt
        preview = list(job.metadata_json.get("scrape_results_preview", []))
        target_url = job.target_url

    if not preview:
        logger.info("No results to enrich for job_id=%s", job_id)
        return

    # Determine which entries to enrich
    target_indices = set(entry_indices) if entry_indices else set(
        item["index"] for item in preview
        if item.get("url") and not item.get("phones") and not item.get("emails")
    )

    if not target_indices:
        logger.info("No entries need enrichment for job_id=%s", job_id)
        async with async_session_factory() as session:
            await UrlScrapeJobsRepository(session).update_metadata(job_id, {"stage": "done"})
        return

    enriched_count = 0
    total_target = len(target_indices)
    base_url_parts = urlparse(target_url)
    base_domain = f"{base_url_parts.scheme}://{base_url_parts.netloc}"

    contact_prompt = enrich_prompt or (
        "Extract all phone numbers, email addresses, and contact information "
        "for this professional. Return JSON with 'entries' array, each with "
        "'phones' and 'emails' arrays."
    )

    try:
        # Single browser instance for all profile pages
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, args=_BROWSER_ARGS)
            bpage = await browser.new_page()

            for item in preview:
                idx = item["index"]
                if idx not in target_indices:
                    continue

                url = item.get("url", "").strip()
                if not url:
                    enriched_count += 1
                    continue

                # Resolve relative URLs
                if url.startswith("/"):
                    url = base_domain + url
                elif not url.startswith(("http://", "https://")):
                    url = base_domain + "/" + url

                try:
                    # Fast profile page load — no full pipeline, just DOM text + links
                    await bpage.goto(url, wait_until="domcontentloaded", timeout=20_000)
                    await bpage.wait_for_timeout(1_000)

                    # Extract HTML links with phone + text (same structure as level 1)
                    link_data: list[dict] = await bpage.evaluate("""() => {
                        const items = [];
                        document.querySelectorAll('a[href]').forEach(a => {
                            const href = a.getAttribute('href') || '';
                            const text = (a.innerText || '').trim().replace(/\\s+/g, ' ').substring(0, 200);
                            let phone = null;
                            const candidates = [a, ...a.querySelectorAll('[onclick]')];
                            for (const el of candidates) {
                                const onclick = el.getAttribute('onclick') || '';
                                const m = onclick.match(/tel:([+\\d\\s\\-().]+)/);
                                if (m) { phone = m[1].trim(); break; }
                            }
                            items.push({ href, text, phone });
                        });
                        // Also grab mailto: links
                        document.querySelectorAll('a[href^="mailto:"]').forEach(a => {
                            items.push({ href: a.getAttribute('href'), text: (a.innerText||'').trim(), phone: null });
                        });
                        return items.slice(0, 300);
                    }""")

                    page_text = await bpage.inner_text("body")

                    # Build structured text for LLM
                    link_lines = []
                    for litem in link_data:
                        if litem.get("phone") or (litem.get("href", "").startswith("mailto:")):
                            line = f"LINK href={litem['href']} text={litem['text']}"
                            if litem.get("phone"):
                                line += f" phone={litem['phone']}"
                            link_lines.append(line)

                    combined = ""
                    if link_lines:
                        combined = "=== LINKS Y TELÉFONOS ===\n" + "\n".join(link_lines) + "\n\n"
                    combined += "=== TEXTO ===\n" + page_text[:8_000]

                    entries = await _extract_entries_with_llm(combined, contact_prompt, settings)

                    if entries:
                        first = entries[0]
                        existing_phones = item.get("phones", []) or []
                        new_phones = first.phones or []
                        item["phones"] = list(dict.fromkeys(existing_phones + new_phones))
                        item["emails"] = first.emails or []
                        logger.info(
                            "Enriched entry idx=%d url=%s phones=%d emails=%d",
                            idx, url, len(item["phones"]), len(item["emails"])
                        )

                except Exception as e:
                    logger.warning("Error enriching entry idx=%d url=%s: %s", idx, url, e)

                enriched_count += 1
                progress = 50 + int((enriched_count / total_target) * 45)

                # Persist after EACH entry so frontend sees updates in real time
                async with async_session_factory() as session:
                    await UrlScrapeJobsRepository(session).update_metadata(
                        job_id,
                        {"scrape_results_preview": preview, "enriched_count": enriched_count, "stage": "enriching"},
                        progress,
                    )

            await bpage.close()
            await browser.close()

        # Mark done
        async with async_session_factory() as session:
            await UrlScrapeJobsRepository(session).update_status(
                job_id, "completed", 100,
                metadata_json={
                    "scrape_results_preview": preview,
                    "enriched_count": enriched_count,
                    "entries_count": len(preview),
                    "stage": "done",
                },
            )
        logger.info("Enrichment done job_id=%s enriched=%d", job_id, enriched_count)

    except Exception as e:
        logger.error("Enrichment pipeline error job_id=%s: %s", job_id, e)
        async with async_session_factory() as session:
            await UrlScrapeJobsRepository(session).update_status(
                job_id, "error", 0, metadata_json={"error": str(e)}
            )
