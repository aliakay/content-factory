// Deterministic HTML -> transparent video renderer (headless Chromium + ffmpeg).
//
// Usage: node render.mjs <page.html> <out.mov> <duration_s> [fps=30] [w=1080] [h=1920] [--opaque] [--scale=0.5]
//        [--shots=t1,t2 [--lint=boxes.json]] [--cues=cues.json]
//
// The page must define `window.render(t)` (draw the state at t seconds; may return a Promise) and may set
// `window.ready` (a Promise) before the first frame. Each frame is captured with a transparent background and
// piped to ffmpeg as PNG; output is ProRes 4444 with alpha, ready to overlay on footage.
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import cfg from "./config.mjs";

const [page_, out, durS, fpsS = "30", wS = "1080", hS = "1920", ...flags] = process.argv.slice(2);
if (!page_ || !out || !durS) {
  console.error("usage: node render.mjs <page.html> <out.mov> <duration_s> [fps] [w] [h] [--opaque]");
  process.exit(2);
}
const fps = Number(fpsS), W = Number(wS), H = Number(hS), frames = Math.round(Number(durS) * fps);
const opaque = flags.includes("--opaque");
const scale = Number((flags.find((f) => f.startsWith("--scale=")) || "--scale=1").slice(8));
const shots = (flags.find((f) => f.startsWith("--shots=")) || "").slice(8).split(",").filter(Boolean).map(Number);
const cuesOut = (flags.find((f) => f.startsWith("--cues=")) || "").slice(7);   // write the page's sound cues (window.cues)
const lintOut = (flags.find((f) => f.startsWith("--lint=")) || "").slice(7);   // with --shots: text boxes per shot (window.lintBoxes)
const readOut = (flags.find((f) => f.startsWith("--readcheck=")) || "").slice(12);   // visible texts every 0.2 s + motion lint
const libs = cfg.chromeLibs;

// ES modules don't load from file://, so serve the project root on a loopback-only port for the page
const ROOT = cfg.root;
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
                ".ttf": "font/ttf", ".png": "image/png", ".jpg": "image/jpeg", ".json": "application/json" };
const server = createServer(async (req, res) => {
  const p = path.resolve(ROOT, "." + decodeURIComponent(req.url.split("?")[0].split("#")[0]));
  if (!p.startsWith(ROOT)) { res.writeHead(403).end(); return; }
  try { res.writeHead(200, { "Content-Type": TYPES[path.extname(p)] || "application/octet-stream" }).end(await readFile(p)); }
  catch { res.writeHead(404).end(); }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch({
  headless: true,
  env: { ...process.env, LD_LIBRARY_PATH: `${libs}:${process.env.LD_LIBRARY_PATH || ""}` },
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--disable-dev-shm-usage"],
});
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: scale });
page.on("pageerror", (e) => console.error("page error:", e.message));
page.on("console", (m) => { if (m.type() === "error") console.error("console error:", m.text()); });
const [file, hash = ""] = page_.split("#");
await page.goto(base + "/" + path.relative(ROOT, path.resolve(file)) + (hash ? "#" + hash : ""));
await page.waitForFunction(() => typeof window.render === "function", null, { timeout: 30000 });
await page.evaluate(async () => { if (window.ready) await window.ready; if (document.fonts) await document.fonts.ready; });

if (cuesOut) {
  const { writeFile } = await import("node:fs/promises");
  const c = await page.evaluate(() => (typeof window.cues === "function" ? window.cues() : { sfx: [], music: [] }));
  await writeFile(cuesOut, JSON.stringify(c));
}

if (readOut) {   // no screenshots: which texts are readable when, and what the timeline says about the motion
  const { writeFile } = await import("node:fs/promises");
  const samples = [];
  for (let t = 0; t < Number(durS); t += 0.2) {
    await page.evaluate((x) => window.render(x), t);
    const b = await page.evaluate(() => (window.lintBoxes ? window.lintBoxes().boxes.map((x) => [x.scene, x.text]) : []));
    samples.push([+t.toFixed(2), b]);
  }
  const motion = await page.evaluate(() => (window.lintMotion ? window.lintMotion() : []));
  await writeFile(readOut, JSON.stringify({ step: 0.2, samples, motion }));
  await browser.close(); server.close(); process.exit(0);
}

if (shots.length) {  // --shots=t1,t2: PNGs of those moments into the directory `out` (no video)
  const { mkdir, writeFile } = await import("node:fs/promises");
  await mkdir(out, { recursive: true });
  const lint = {};
  for (const t of shots) {
    await page.evaluate((x) => window.render(x), t);
    const file = `${out}/shot_${t.toFixed(2).padStart(6, "0")}.png`;
    await page.screenshot({ path: file, type: "png" });
    if (lintOut) lint[t.toFixed(2)] = { file, ...(await page.evaluate(() => (window.lintBoxes ? window.lintBoxes() : { boxes: [] }))) };
  }
  if (lintOut) await writeFile(lintOut, JSON.stringify(lint));
  await browser.close(); server.close(); process.exit(0);
}

const ffmpeg = spawn(cfg.ffmpeg, [
  "-v", "error", "-y", "-f", "image2pipe", "-framerate", String(fps), "-i", "-",
  ...(opaque ? ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16"]
             : ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-alpha_bits", "8"]),
  out,
], { stdio: ["pipe", "inherit", "inherit"] });

const t0 = Date.now();
for (let i = 0; i < frames; i++) {
  await page.evaluate((t) => window.render(t), i / fps);
  const png = await page.screenshot({ type: "png", omitBackground: !opaque });
  if (!ffmpeg.stdin.write(png)) await new Promise((r) => ffmpeg.stdin.once("drain", r));
}
ffmpeg.stdin.end();
await new Promise((r) => ffmpeg.on("close", r));
await browser.close();
server.close();
console.log(`${out} · ${frames} frames · ${((Date.now() - t0) / 1000).toFixed(1)}s`);
