"""Facebook page scraping — dismiss login modal + extract public data."""
from __future__ import annotations

import logging

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

_BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-extensions",
]

# Selectors for the login modal close button (Facebook uses multiple variants)
_MODAL_CLOSE_SELECTORS = [
    'div[aria-label="Cerrar"]',
    'div[aria-label="Close"]',
    'div[role="dialog"] div[aria-label="Cerrar"]',
    'div[role="dialog"] div[aria-label="Close"]',
    'div[role="dialog"] [data-testid="royal_close_button"]',
    'div[role="dialog"] i.img[alt="Cerrar"]',
]


async def dismiss_facebook_modal(page) -> None:
    """Try to close the Facebook login modal if it appears."""
    await page.wait_for_timeout(2_000)
    for selector in _MODAL_CLOSE_SELECTORS:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                await el.click()
                logger.info("Facebook login modal dismissed via: %s", selector)
                await page.wait_for_timeout(1_000)
                return
        except Exception:
            continue
    # Fallback: try pressing Escape
    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        logger.info("Facebook login modal dismissed via Escape key")
    except Exception:
        pass


async def scrape_facebook_page(url: str) -> str:
    """Visit a Facebook page/profile URL and extract public text after dismissing login modal.

    Used by the enrichment pipeline when visiting individual FB pages found via Exa/Brave.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=_BROWSER_ARGS)
        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

            # Wait for content to render
            try:
                await page.wait_for_function(
                    "document.body.innerText.length > 300",
                    timeout=8_000,
                )
            except Exception:
                pass

            # Dismiss the login modal
            await dismiss_facebook_modal(page)

            # Scroll to load more content
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1_500)

            text = await page.inner_text("body")
            await context.close()
            return text
        finally:
            await browser.close()
