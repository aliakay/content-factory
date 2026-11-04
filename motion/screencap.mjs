// Screen capture for the screen-demo line (headless Chromium).
//
//   node screencap.mjs survey <url> <out.json> <shot.png> [w=540] [h=960]
//       what the page offers: title, visible text, the clickable things with their labels, one screenshot
//   node screencap.mjs run <steps.json> <outdir> [w=540] [h=960]
//       plays the steps with a visible cursor and records the screen at 2x (outdir/raw.mp4, 30 fps); writes outdir/log.json
//       [{n, t0, t1, box: [x, y, w, h] as fractions of the viewport | null, ok, error}] and outdir/step_N.png
//
// steps.json: {"url": "...", "steps": [{"action": "click|type|hover|scroll|wait|goto", "target": "visible text",
//              "text": "typed text | url for goto", "hold": seconds to stay after the step}]}
import { chromium } from "playwright";
import { writeFile, mkdir, readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { lookup } from "node:dns/promises";
import net from "node:net";
import cfg from "./config.mjs";

const [mode, a, b, c, d, e] = process.argv.slice(2);
const launch = () => chromium.launch({
  headless: true,
  env: { ...process.env, LD_LIBRARY_PATH: `${cfg.chromeLibs}:${process.env.LD_LIBRARY_PATH || ""}` },
  args: ["--disable-dev-shm-usage"],
});

// a round cursor that follows the mouse and pulses on click (the headless browser draws none)
const CURSOR = `(() => {
  if (window.__cur) return;
  const s = document.createElement("style");
  s.textContent = "#__cur{position:fixed;z-index:2147483647;width:26px;height:26px;margin:-13px 0 0 -13px;border-radius:50%;" +
    "background:rgba(255,217,61,.55);border:2px solid #fff;box-shadow:0 0 0 2px rgba(0,0,0,.35);pointer-events:none;" +
    "transition:transform .15s ease-out;left:-50px;top:-50px}#__cur.down{transform:scale(.6)}";
  document.documentElement.appendChild(s);
  const c = document.createElement("div"); c.id = "__cur"; document.documentElement.appendChild(c); window.__cur = c;
  addEventListener("mousemove", (e) => { c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px"; }, true);
  addEventListener("mousedown", () => c.classList.add("down"), true);
  addEventListener("mouseup", () => c.classList.remove("down"), true);
})()`;

// only public addresses: the browser runs next to the Studio, so a page (or a redirect) must not reach this machine
const PRIVATE4 = [["0.0.0.0", 8], ["10.0.0.0", 8], ["100.64.0.0", 10], ["127.0.0.0", 8], ["169.254.0.0", 16],
                  ["172.16.0.0", 12], ["192.168.0.0", 16], ["198.18.0.0", 15], ["224.0.0.0", 3]];
const n4 = (ip) => ip.split(".").reduce((a, x) => a * 256 + +x, 0);
const isPrivate = (ip) => {
  if (net.isIPv4(ip)) return PRIVATE4.some(([base, bits]) => Math.floor(n4(ip) / 2 ** (32 - bits)) === Math.floor(n4(base) / 2 ** (32 - bits)));
  const v = ip.toLowerCase();
  if (v.startsWith("::ffff:")) return isPrivate(v.slice(7));
  return v === "::" || v === "::1" || /^(fc|fd|fe8|fe9|fea|feb|ff)/.test(v);
};
const verdict = new Map();
const allowed = async (url) => {
  let u;
  try { u = new URL(url); } catch { return false; }
  if (u.protocol === "data:" || u.protocol === "blob:") return true;
  if (!["http:", "https:"].includes(u.protocol)) return false;
  const host = u.hostname.replace(/^\[|\]$/g, "");
  if (!verdict.has(host)) {
    verdict.set(host, (async () => {
      if (host === "localhost" || host.endsWith(".localhost")) return false;
      try { return (await lookup(host, { all: true })).every((a) => !isPrivate(a.address)); } catch { return false; }
    })());
  }
  return verdict.get(host);
};
const guard = (ctx) => ctx.route("**/*", async (route) =>
  (await allowed(route.request().url())) ? route.continue() : route.abort("blockedbyclient"));

const find = async (page, target) => {
  for (const loc of [page.getByRole("button", { name: target }), page.getByRole("link", { name: target }),
                     page.getByLabel(target), page.getByPlaceholder(target), page.getByText(target)]) {
    const l = loc.first();
    if (await l.count().catch(() => 0)) return l;
  }
  return null;
};

if (mode === "survey") {
  const [url, out, shot, w = "540", h = "960"] = [a, b, c, d, e];
  const browser = await launch();
  const sctx = await browser.newContext({ viewport: { width: +w, height: +h } });
  await guard(sctx);
  const page = await sctx.newPage();
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForTimeout(1500);
  const info = await page.evaluate(() => {
    const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4; };
    const label = (el) => (el.innerText || el.value || el.getAttribute("aria-label") || el.placeholder || "").trim().replace(/\s+/g, " ").slice(0, 60);
    const items = [...document.querySelectorAll("a,button,input,textarea,select,[role=button],[role=tab]")].filter(vis)
      .map((el) => ({ tag: el.tagName.toLowerCase(), type: el.type || "", label: label(el) })).filter((x) => x.label).slice(0, 80);
    return { title: document.title, text: document.body.innerText.replace(/\s+/g, " ").slice(0, 4000), items };
  });
  await page.screenshot({ path: shot });
  await writeFile(out, JSON.stringify({ url: page.url(), ...info }));
  await browser.close();
} else if (mode === "run") {
  const [stepsPath, outdir, w = "540", h = "960"] = [a, b, c, d];
  const spec = JSON.parse(await readFile(stepsPath, "utf8"));
  await mkdir(outdir, { recursive: true });
  const W = +w, H = +h;
  const browser = await launch();
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
  await guard(ctx);
  const page = await ctx.newPage();
  await page.addInitScript(CURSOR);
  // CDP screencast: frames at device pixels, sent only when something changes, each with its own timestamp
  const cdp = await ctx.newCDPSession(page);
  const frames = [];
  let t00 = null;
  cdp.on("Page.screencastFrame", async (f) => {
    const ts = f.metadata.timestamp;
    if (t00 === null) t00 = ts;
    const file = path.join(outdir, `f_${String(frames.length).padStart(6, "0")}.jpg`);
    frames.push({ file, t: ts - t00 });
    writeFile(file, Buffer.from(f.data, "base64"));
    cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
  });
  const wall0 = Date.now() / 1000;
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 90, maxWidth: W * 2, maxHeight: H * 2, everyNthFrame: 1 });
  const now = () => Date.now() / 1000 - wall0;
  await page.goto(spec.url, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.evaluate(CURSOR);
  await page.mouse.move(W / 2, H / 2);
  await page.waitForTimeout(1200);
  const log = [];
  let n = 0;
  for (const st of spec.steps) {
    n += 1;
    const row = { n, t0: now(), box: null, ok: true, error: null };
    try {
      if (st.action === "goto") {
        await page.goto(st.text, { waitUntil: "domcontentloaded", timeout: 45000 });
      } else if (st.action === "scroll") {
        for (let i = 0; i < 12; i++) { await page.mouse.wheel(0, (+st.text || H * 0.8) / 12); await page.waitForTimeout(40); }
      } else if (st.action !== "wait") {
        const l = await find(page, st.target || "");
        if (!l) throw new Error(`not found: ${st.target}`);
        await l.scrollIntoViewIfNeeded({ timeout: 5000 });
        const r = await l.boundingBox();
        if (r) {
          row.box = [r.x / W, r.y / H, r.width / W, r.height / H].map((v) => Math.round(v * 1000) / 1000);
          await page.mouse.move(r.x + r.width / 2, r.y + r.height / 2, { steps: 18 });
          await page.waitForTimeout(250);
        }
        if (st.action === "click") await l.click({ timeout: 5000 });
        if (st.action === "type") { await l.click({ timeout: 5000 }); await page.keyboard.type(st.text || "", { delay: 70 }); }
      }
      await page.evaluate(CURSOR).catch(() => {});
    } catch (err) {
      row.ok = false; row.error = String(err.message || err).slice(0, 200);
    }
    await page.waitForTimeout(Math.round((st.hold ?? 1.5) * 1000));
    await page.screenshot({ path: path.join(outdir, `step_${n}.png`) }).catch(() => {});
    row.t1 = now();
    log.push(row);
  }
  const end = now();
  await cdp.send("Page.stopScreencast").catch(() => {});
  await page.waitForTimeout(300);
  await ctx.close();
  await browser.close();
  // frames hold until the next one; the first frame's wall time anchors the log (t00 is the first frame's timestamp)
  const lines = [];
  frames.forEach((f, i) => {
    const next = i + 1 < frames.length ? frames[i + 1].t : end;
    lines.push(`file '${path.basename(f.file)}'`, `duration ${Math.max(0.001, next - f.t).toFixed(3)}`);
  });
  if (frames.length) lines.push(`file '${path.basename(frames[frames.length - 1].file)}'`);
  await writeFile(path.join(outdir, "frames.txt"), lines.join("\n") + "\n");
  const r = spawnSync(cfg.ffmpeg, ["-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "frames.txt", "-vf",
    "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
    "raw.mp4"], { cwd: outdir });
  if (r.status !== 0) { console.error(String(r.stderr)); process.exit(1); }
  await writeFile(path.join(outdir, "log.json"), JSON.stringify(log));
} else {
  console.error("usage: node screencap.mjs survey|run ...");
  process.exit(2);
}
