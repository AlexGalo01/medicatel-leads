#!/usr/bin/env python3
"""Save Facebook session cookies for Playwright.

Usage:
    python backend/scripts/save_facebook_session.py

Opens a visible browser window. Log in to Facebook manually.
Once logged in, press Enter in the terminal to save the session.
"""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

SESSION_DIR = os.path.join(os.path.dirname(__file__), "..", "sessions")
OUTPUT_PATH = os.path.join(SESSION_DIR, "facebook_state.json")


async def main() -> None:
    os.makedirs(SESSION_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        await page.goto("https://www.facebook.com/")

        print("\n" + "=" * 60)
        print("  Inicia sesión en Facebook en la ventana del navegador.")
        print("  Cuando estés logueado, presiona ENTER aquí.")
        print("=" * 60 + "\n")

        await asyncio.get_event_loop().run_in_executor(None, input)

        await context.storage_state(path=OUTPUT_PATH)
        print(f"\n✓ Sesión guardada en: {OUTPUT_PATH}")

        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(1)
