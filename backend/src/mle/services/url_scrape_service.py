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

from mle.clients.exa_client import ExaClient, exa_contents_full_config
from mle.db.base import async_session_factory
from mle.repositories.url_scrape_jobs_repository import UrlScrapeJobsRepository
from mle.core.config import effective_exa_search_timeout_seconds, get_settings

logger = logging.getLogger(__name__)

_MAX_PAGES = 10

_BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-extensions",
]

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


async def _discover_pages_via_exa(
    target_url: str,
    user_prompt: str,
    settings: Any,
    exa_client: ExaClient,
) -> list[tuple[str, str]]:
    """Descubre páginas del directorio via Exa en paralelo.

    Retorna lista de (page_text, source_url) deduplicada por URL.
    Si falla, retorna lista vacía (fallback a Playwright).
    """
    if not target_url.strip():
        return []

    try:
        domain = urlparse(target_url).netloc.lower()
        if not domain:
            return []

        # Task 1: Obtener la página principal + subpáginas
        contents_payload: dict[str, Any] = {
            "ids": [target_url],
            "text": {"maxCharacters": 60000},
            "highlights": {"maxCharacters": 5000},
            "subpages": 5,
        }

        # Task 2: Buscar más páginas del directorio via keyword search en el dominio
        search_query = user_prompt[:500] if user_prompt.strip() else "directorio médico clínica hospital"
        search_payload: dict[str, Any] = {
            "query": search_query,
            "type": "keyword",
            "numResults": min(_MAX_PAGES, 30),
            "includeDomains": [domain],
            "contents": exa_contents_full_config(
                text_max_characters=60000,
                highlights_max_characters=5000,
                subpages=0,
            ),
        }

        # Ejecutar en paralelo
        results = await asyncio.gather(
            exa_client.get_contents(contents_payload),
            exa_client.search(search_payload),
            return_exceptions=True,
        )

        pages: dict[str, str] = {}  # Dedup por URL

        # Procesar contenidos de la página principal
        if isinstance(results[0], dict):
            contents_response = results[0]
            for item in contents_response.get("results", []):
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url", "")).strip()
                text = str(item.get("text", "")).strip()
                if url and text:
                    pages[url] = text

            # Procesar subpáginas
            for item in contents_response.get("results", []):
                if not isinstance(item, dict):
                    continue
                for subpage in item.get("subpages", []):
                    if not isinstance(subpage, dict):
                        continue
                    url = str(subpage.get("url", "")).strip()
                    text = str(subpage.get("text", "")).strip()
                    if url and text:
                        pages[url] = text

        # Procesar resultados de búsqueda
        if isinstance(results[1], dict):
            search_response = results[1]
            for item in search_response.get("results", []):
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url", "")).strip()
                text = str(item.get("text", "")).strip()
                if url and text and url not in pages:
                    pages[url] = text

        logger.info(
            "Exa discover_pages target_url=%s domain=%s found=%s",
            target_url, domain, len(pages),
        )
        return list(pages.items())

    except Exception as exc:
        logger.warning("Exa discover_pages falló para %s (fallback a Playwright): %s", target_url, exc)
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

    exa_client = ExaClient(
        api_key=settings.exa_api_key,
        timeout_seconds=effective_exa_search_timeout_seconds(settings),
    )

    all_entries: list[_ScrapedEntry] = []
    pages_loaded: list[tuple[str, str]] = []

    # --- Try Exa first (faster, parallel) ---
    try:
        pages_loaded = await asyncio.wait_for(
            _discover_pages_via_exa(job.target_url, job.user_prompt, settings, exa_client),
            timeout=60,
        )
        logger.info("Exa discovered %d pages job_id=%s", len(pages_loaded), job_id)
    except asyncio.TimeoutError:
        logger.warning("Exa discover timeout, falling back to Playwright job_id=%s", job_id)
    except Exception as exc:
        logger.warning("Exa discover failed (fallback to Playwright) job_id=%s: %s", job_id, exc)

    # --- Fallback to Playwright if Exa found nothing ---
    if not pages_loaded:
        logger.info("No pages from Exa, using Playwright pagination job_id=%s", job_id)
        current_url: str | None = job.target_url
        page_num = 0

        while current_url and page_num < _MAX_PAGES:
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

    # --- LLM extraction in parallel for all pages ---
    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
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
