// Research browser for the art director (factory/artdirector.py): opens public pages in headless Chromium,
// saves a screenshot of each (the art director Reads them to SEE the visual references) and prints the page text.
//
// Usage: node browse.mjs <out_dir under work/research> <url> [url ...]   (max 6 urls per call)
// Nothing is downloaded except the screenshots; no logins, no cookies kept (fresh context every call).
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import cfg from "./config.mjs";

const [outArg, ...urls] = process.argv.slice(2);
const base = path.resolve(cfg.root, "work", "research");
const out = path.resolve(base, outArg || "misc");
if (!out.startsWith(base) || !urls.length) {
  console.error("usage: node browse.mjs <dir under work/research> <url> [url ...]");
  process.exit(2);
}
await mkdir(out, { recursive: true });
const libs = cfg.chromeLibs;
const browser = await chromium.launch({
  headless: true, env: { ...process.env, LD_LIBRARY_PATH: `${libs}:${process.env.LD_LIBRARY_PATH || ""}` },
});
const ctx = await browser.newContext({ viewport: { width: 1280, height: 1600 }, locale: "en-US" });
for (const [i, u] of urls.slice(0, 6).entries()) {
  if (!/^https:\/\//.test(u)) { console.log(`=== ${u}\nskipped: only https pages`); continue; }
  const page = await ctx.newPage();
  try {
    await page.goto(u, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(3500);
    // scroll once so lazy galleries load their thumbnails
    await page.evaluate(() => window.scrollBy(0, 900)); await page.waitForTimeout(1500);
    await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(500);
    const file = path.join(out, `${Date.now()}_${i}.png`);
    await page.screenshot({ path: file, fullPage: false });
    const text = await page.evaluate(() => document.body.innerText.replace(/\n{2,}/g, "\n").slice(0, 3000));
    console.log(`=== ${u}\nscreenshot: ${file}\n${text}\n`);
  } catch (e) {
    console.log(`=== ${u}\nfailed: ${String(e.message).split("\n")[0]}\n`);
  } finally {
    await page.close();
  }
}
await browser.close();
