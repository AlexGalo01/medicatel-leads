#!/usr/bin/env node

import { chromium } from 'playwright';
import { Command } from 'commander';
import * as fs from 'fs';


const program = new Command();
program
  .option('--mode <mode>', 'google_search | google_maps', 'google_search')
  .option('--query <query>', 'Query string')
  .option('--state-file <path>', 'Browser state file', '/data/playwright-state.json')
  .option('--timeout <ms>', 'Timeout in milliseconds', '45000')
  .option('--chromium-path <path>', 'Path to Chromium binary', '/usr/bin/chromium')
  .parse();

const { mode, query, stateFile, chromiumPath } = program.opts();

async function extractFromJsonLd(jsonLd: unknown[], key: string): Promise<string | null> {
  for (const obj of jsonLd) {
    if (!obj || typeof obj !== 'object') continue;
    const record = obj as Record<string, unknown>;
    if (key === 'telephone' && record.telephone) {
      const tel = record.telephone;
      if (typeof tel === 'string') return tel;
      if (Array.isArray(tel) && tel.length > 0) return String(tel[0]);
    }
    if (key === 'address' && record.address) {
      const addr = record.address;
      if (typeof addr === 'string') return addr;
      if (typeof addr === 'object' && 'streetAddress' in addr) {
        return String((addr as Record<string, unknown>).streetAddress);
      }
    }
    if (key === 'url' && record.url) {
      const url = record.url;
      if (typeof url === 'string') return url;
      if (Array.isArray(url) && url.length > 0) return String(url[0]);
    }
  }
  return null;
}

async function scrapeKnowledgePanel(page: any, query: string): Promise<Record<string, unknown>> {
  try {
    await page.goto(`https://www.google.com/search?q=${encodeURIComponent(query)}`, {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    });

    // Wait for page to render
    await page.waitForTimeout(2000).catch(() => {});

    let phone: string | null = null;
    let address: string | null = null;
    let website: string | null = null;
    let hours: string | null = null;

    // Try JSON-LD structured data (most reliable)
    try {
      const jsonLdScripts = await page.$$eval('script[type="application/ld+json"]', (els: Element[]) =>
        els.map((e) => {
          try {
            return JSON.parse(e.textContent || '{}');
          } catch {
            return null;
          }
        }).filter(Boolean)
      );
      if (jsonLdScripts.length > 0) {
        phone = phone || (await extractFromJsonLd(jsonLdScripts, 'telephone'));
        address = address || (await extractFromJsonLd(jsonLdScripts, 'address'));
        website = website || (await extractFromJsonLd(jsonLdScripts, 'url'));
      }
    } catch {
      // Continue to other methods
    }

    // Try CSS selectors - use multiple variations for resilience
    try {
      phone = phone || (await page.$eval('[data-dtype="d3ph"]', (el: Element) => el.textContent?.trim() || null));
    } catch {
      // Try alternative selectors
      try {
        phone = phone || (await page.$eval('.wIdbqf .fl', (el: Element) => el.textContent?.trim() || null));
      } catch {
        // Continue
      }
    }

    try {
      address = address || (await page.$eval('[data-dtype="d3adr"]', (el: Element) => el.textContent?.trim() || null));
    } catch {
      try {
        address = address || (await page.$eval('.dbg0md', (el: Element) => el.textContent?.trim() || null));
      } catch {
        // Continue
      }
    }

    try {
      website = website || (await page.$eval('[data-dtype="d3wbg"] a', (el: Element) =>
        (el as HTMLAnchorElement).href || null
      ));
    } catch {
      try {
        website = website || (await page.$eval('a[data-dtype="d3lk"]', (el: Element) =>
          (el as HTMLAnchorElement).href || null
        ));
      } catch {
        // Continue
      }
    }

    try {
      hours = hours || (await page.$eval('[jsname="yRmGpb"]', (el: Element) => el.textContent?.trim() || null));
    } catch {
      try {
        hours = hours || (await page.$eval('.xpd.O9g5cc', (el: Element) => el.textContent?.trim() || null));
      } catch {
        // Continue
      }
    }

    return {
      phone: phone || null,
      address: address || null,
      website: website || null,
      hours: hours || null,
      source: 'playwright_search',
    };
  } catch (error) {
    console.error(`Error scraping Knowledge Panel: ${error}`);
    return { source: 'playwright_search', error: String(error) };
  }
}

async function scrapeMapsPlace(page: any, query: string): Promise<Record<string, unknown>> {
  try {
    await page.goto(`https://www.google.com/maps/search/${encodeURIComponent(query)}`, {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    });

    // Wait for map to load
    await page.waitForTimeout(3000).catch(() => {});
    await page.waitForSelector('[role="region"]', { timeout: 10000 }).catch(() => {});

    let phone: string | null = null;
    let address: string | null = null;
    let website: string | null = null;
    let hours: string | null = null;

    // Try to find the first result in the list and get its details
    try {
      await page.click('div[data-item-id]', { timeout: 5000 }).catch(() => {});
    } catch {
      // Continue without clicking
    }

    // Multiple selector variations for resilience
    try {
      const phoneElement = await page.$('[aria-label*="Llamar"], [aria-label*="Phone"], [aria-label*="teléfono"]');
      if (phoneElement) {
        phone = (await phoneElement.textContent())?.trim() || null;
      }
    } catch {
      // Continue
    }

    try {
      const addressElement = await page.$('[aria-label*="Dirección"], [aria-label*="Address"], .EKp0qd');
      if (addressElement) {
        address = (await addressElement.textContent())?.trim() || null;
      }
    } catch {
      // Continue
    }

    try {
      const websiteElement = await page.$('[aria-label*="Sitio web"], [aria-label*="Website"], a[aria-label*="website"]');
      if (websiteElement) {
        website = (await websiteElement.getAttribute('href'))?.trim() || null;
      }
    } catch {
      // Continue
    }

    try {
      const hoursElement = await page.$('[aria-label*="Horario"], [aria-label*="Hours"], .OqJZkb');
      if (hoursElement) {
        hours = (await hoursElement.textContent())?.trim() || null;
      }
    } catch {
      // Continue
    }

    return {
      phone: phone || null,
      address: address || null,
      website: website || null,
      hours: hours || null,
      source: 'playwright_maps',
    };
  } catch (error) {
    console.error(`Error scraping Maps: ${error}`);
    return { source: 'playwright_maps', error: String(error) };
  }
}

async function main() {
  if (!query) {
    console.error('Error: --query is required');
    process.exit(1);
  }

  const browser = await chromium.launch({
    executablePath: chromiumPath,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled'],
  });

  let context;
  let storageState = undefined;

  try {
    if (fs.existsSync(stateFile)) {
      try {
        storageState = JSON.parse(fs.readFileSync(stateFile, 'utf-8'));
      } catch {
        // Ignore corrupt state file
      }
    }
  } catch {
    // Ignore
  }

  context = await browser.newContext({
    storageState: storageState || undefined,
    userAgent:
      'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  });

  const page = await context.newPage();

  let result: Record<string, unknown> = {};

  try {
    if (mode === 'google_search') {
      result = await scrapeKnowledgePanel(page, query);
    } else if (mode === 'google_maps') {
      result = await scrapeMapsPlace(page, query);
    } else {
      result = { error: `Unknown mode: ${mode}` };
    }
  } finally {
    try {
      const newState = await context.storageState();
      if (newState) {
        fs.writeFileSync(stateFile, JSON.stringify(newState, null, 2));
      }
    } catch (error) {
      // Ignore state save errors
    }

    await browser.close();
  }

  console.log(JSON.stringify(result));
}

main().catch((error) => {
  console.error(JSON.stringify({ error: String(error), source: 'playwright_error' }));
  process.exit(1);
});
