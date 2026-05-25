"""Facebook page scraping — dismiss login modal + extract public data."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-extensions",
]


async def dismiss_facebook_modal(page) -> None:
    """Try to close the Facebook login/signup modal that blocks page content."""
    await page.wait_for_timeout(2_500)

    # Strategy 1: Click the X button using aria-label (works in most locales)
    for label in ("Cerrar", "Close", "Schließen", "Fechar"):
        try:
            el = await page.query_selector(f'div[aria-label="{label}"]')
            if el and await el.is_visible():
                await el.click()
                logger.info("Facebook modal dismissed via aria-label=%s", label)
                await page.wait_for_timeout(1_000)
                return
        except Exception:
            continue

    # Strategy 2: Find the close button inside the dialog via JS
    try:
        closed = await page.evaluate("""() => {
            // Find the dialog overlay
            const dialogs = document.querySelectorAll('div[role="dialog"]');
            for (const d of dialogs) {
                // Look for any clickable close-like element
                const closeBtn = d.querySelector('[aria-label="Cerrar"], [aria-label="Close"]')
                    || d.querySelector('svg')?.closest('div[role="button"]')
                    || d.querySelector('div[class*="x5an3"] div[role="button"]');
                if (closeBtn) {
                    closeBtn.click();
                    return true;
                }
            }
            // Try clicking the overlay backdrop itself
            const overlay = document.querySelector('div[class*="x1n2onr6"][class*="x1ja2u2z"]');
            if (overlay) {
                overlay.click();
                return true;
            }
            return false;
        }""")
        if closed:
            logger.info("Facebook modal dismissed via JS dialog click")
            await page.wait_for_timeout(1_000)
            return
    except Exception:
        pass

    # Strategy 3: Press Escape key
    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(1_000)
        # Check if modal is still there
        still_visible = await page.evaluate("""() => {
            return !!document.querySelector('div[role="dialog"]');
        }""")
        if not still_visible:
            logger.info("Facebook modal dismissed via Escape key")
            return
    except Exception:
        pass

    # Strategy 4: Remove the modal from DOM entirely via JS
    try:
        await page.evaluate("""() => {
            const dialogs = document.querySelectorAll('div[role="dialog"]');
            dialogs.forEach(d => d.remove());
            // Also remove overlay/backdrop
            const overlays = document.querySelectorAll('div[class*="x1n2onr6"][class*="x1ja2u2z"]');
            overlays.forEach(o => o.remove());
            // Re-enable scrolling on body
            document.body.style.overflow = 'auto';
            document.documentElement.style.overflow = 'auto';
        }""")
        logger.info("Facebook modal removed from DOM via JS")
    except Exception as exc:
        logger.warning("Failed to dismiss Facebook modal: %s", exc)
