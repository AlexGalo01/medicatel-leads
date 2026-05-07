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


async def _load_page_text_and_next_url(url: str) -> tuple[str, str | None]:
    """Load URL with a fresh Playwright browser, return (body_text, next_page_url)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=_BROWSER_ARGS)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1_500)

            text = await page.inner_text("body")

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

            return text, next_url
        finally:
            await browser.close()


async def _scrape_url_text(url: str) -> str:
    """Scrape full visible text from a single URL using Playwright."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=_BROWSER_ARGS)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30_000)
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
    """Use LLM to decide navigation strategy based on page structure and user prompt."""
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": _NAV_PLAN_PROMPT},
            {"role": "user", "content": f"Instrucción: {user_prompt}\n\nEstructura de la página:\n{page_snapshot}"},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except Exception:
        return {"strategy": "scrape_directly", "reasoning": "parse error"}


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
            await page.goto(target_url, wait_until="networkidle", timeout=30_000)
            await page.wait_for_timeout(1_500)

            # 1. Capture page structure
            snapshot = await _capture_page_structure(page)
            logger.info("Page snapshot captured, %d chars job_id=%s", len(snapshot), job_id)

            # 2. LLM decides navigation strategy
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
                            await page.goto(href, wait_until="networkidle", timeout=30_000)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10_000)
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
                            await page.wait_for_load_state("networkidle", timeout=15_000)
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
                            while (el) { if (el.tagName === 'A' && el.href) return el.href; el = el.nextElementSibling; }
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
                await page.goto(next_url, wait_until="networkidle", timeout=30_000)
                await page.wait_for_timeout(1_500)
        finally:
            await browser.close()
    return results


async def _extract_entries_with_llm(
    page_text: str, user_prompt: str, settings: Any
) -> list[_ScrapedEntry]:
    """Send page text to OpenAI and return parsed entries."""
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    user_message = (
        f"Instrucción adicional: {user_prompt}\n\n"
        f"Texto de la página:\n---\n{page_text[:60_000]}\n---"
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
    try:
        parsed = json.loads(raw)
        items: list = parsed.get("entries", []) if isinstance(parsed, dict) else []
        return [_ScrapedEntry(**e) for e in items if isinstance(e, dict)]
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("LLM parse error: %s | raw=%s", exc, raw[:300])
        return []


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

    if pages_loaded:
        try:
            page_texts = [text for text, _ in pages_loaded]
            extractions = await asyncio.gather(*[
                asyncio.wait_for(
                    _extract_entries_with_llm(text, job.user_prompt, settings),
                    timeout=120,
                )
                for text in page_texts[:_MAX_PAGES]
            ], return_exceptions=True)

            for idx, extraction in enumerate(extractions):
                if isinstance(extraction, list):
                    all_entries.extend(extraction)
                    logger.info(
                        "Page %d: %d entries extracted (total=%d) job_id=%s",
                        idx + 1, len(extraction), len(all_entries), job_id,
                    )
                elif isinstance(extraction, Exception):
                    logger.error("Page %d LLM failed job_id=%s: %s", idx + 1, job_id, extraction)
                    if idx == 0:
                        async with async_session_factory() as session:
                            repo = UrlScrapeJobsRepository(session)
                            await repo.update_status(
                                job_id, "error", 45,
                                metadata_json={"error": str(extraction), "stage": "llm_extract"},
                            )
                        return
        except Exception as exc:
            logger.error("LLM extraction batch failed job_id=%s: %s", job_id, exc)
            async with async_session_factory() as session:
                repo = UrlScrapeJobsRepository(session)
                await repo.update_status(
                    job_id, "error", 45,
                    metadata_json={"error": str(exc), "stage": "llm_batch_extract"},
                )
            return

    # --- Check if cancelled before final save ---
    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
        current_job = await repo.get_by_id(job_id)
        if current_job and current_job.status == "cancelled":
            logger.info("Job cancelled before final save job_id=%s", job_id)
            return

    # --- Save final results ---
    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
        preview = _build_preview(all_entries)
        await repo.update_status(
            job_id, "completed", 100,
            metadata_json={
                "scrape_results_preview": preview,
                "entries_count": len(preview),
                "pages_scraped": len(pages_loaded),
                "stage": "done",
            },
        )

    logger.info("URL scrape done job_id=%s pages=%d entries=%d", job_id, len(pages_loaded), len(all_entries))
