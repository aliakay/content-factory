/* Content Factory Studio — single-page app (no framework, no build step).
   Every interaction goes through data-act / data-change attributes and one delegated listener, so no user value is
   ever pasted into inline JavaScript. Views render into #app; the poller re-renders only when the data changed and
   keeps whatever the creator is typing (drafts) and any video that is playing. */
"use strict";

// ---------------- core ----------------
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (n) => (n == null ? "—" : Number(n).toLocaleString("tr-TR"));
const sec = (s) => (s == null ? "—" : (Math.round(s * 10) / 10).toLocaleString("tr-TR") + " sn");
const usd = (v) => "$" + (Math.round((v || 0) * 100) / 100).toLocaleString("tr-TR", { minimumFractionDigits: 2 });
function ago(iso) { if (!iso) return ""; const d = (Date.now() - new Date(iso)) / 1000; if (d < 60) return "az önce"; if (d < 3600) return Math.floor(d / 60) + " dk önce"; if (d < 86400) return Math.floor(d / 3600) + " sa önce"; return Math.floor(d / 86400) + " gün önce"; }
function dt(iso) { return iso ? new Date(iso).toLocaleString("tr-TR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : ""; }
function toast(m, bad) { const t = $("#toast"); t.textContent = m; t.className = "on" + (bad ? " bad" : ""); clearTimeout(t._t); t._t = setTimeout(() => (t.className = ""), 3600); }
async function api(p) { const r = await fetch(p); if (r.status === 401) { location.href = "/login"; return new Promise(() => {}); } const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || "HTTP " + r.status); return j; }
async function post(p, b) { const r = await fetch(p, { method: "POST", headers: { "Content-Type": "application/json", "X-Studio": "1" }, body: JSON.stringify(b || {}) }); if (r.status === 401) { location.href = "/login"; return new Promise(() => {}); } const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || "HTTP " + r.status); return j; }
async function upload(p, file, headers, onprog) {
  return new Promise((res, rej) => {
    const x = new XMLHttpRequest(); x.open("POST", p); x.setRequestHeader("X-Studio", "1");
    x.setRequestHeader("X-Filename", encodeURIComponent(file.name));
    for (const [k, v] of Object.entries(headers || {})) x.setRequestHeader(k, v);
    x.upload.onprogress = (e) => e.lengthComputable && onprog && onprog(e.loaded / e.total);
    x.onload = () => { let j = {}; try { j = JSON.parse(x.responseText); } catch (e) {} x.status === 200 ? res(j) : rej(new Error(j.error || "yükleme hatası")); };
    x.onerror = () => rej(new Error("yükleme hatası")); x.send(file);
  });
}
const store = { get(k, d) { try { const v = localStorage.getItem("cf." + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
                set(k, v) { try { localStorage.setItem("cf." + k, JSON.stringify(v)); } catch (e) {} } };
function copy(text) { (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).catch(() => { const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove(); }); toast("Kopyalandı"); }
const q = (k) => new URLSearchParams(location.hash.split("?")[1] || "").get(k);

// ---------------- icons (stroke, 24px grid) ----------------
const I = (d, extra = "") => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ${extra}>${d}</svg>`;
const ICON = {
  spark: I('<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>'),
  board: I('<rect x="3" y="4" width="5" height="16" rx="1.5"/><rect x="10" y="4" width="5" height="11" rx="1.5"/><rect x="17" y="4" width="4" height="7" rx="1.5"/>'),
  book: I('<path d="M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2z"/><path d="M4 21V5"/><path d="M9 7h6"/>'),
  compass: I('<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>'),
  chart: I('<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/>'),
  film: I('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>'),
  ref: I('<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>'),
  palette: I('<path d="M12 3a9 9 0 100 18c1.1 0 1.6-.8 1.6-1.6 0-.5-.2-.9-.5-1.2-.3-.3-.5-.7-.5-1.2 0-.9.7-1.6 1.6-1.6H16a5 5 0 005-5c0-4.1-4-7.4-9-7.4z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7" r="1"/><circle cx="15" cy="7.5" r="1"/>'),
  pin: I('<path d="M12 21s-7-6.2-7-11.5A7 7 0 0112 2.5a7 7 0 017 7C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>'),
  mic: I('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0014 0M12 18v3"/>'),
  coin: I('<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>'),
  user: I('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0116 0"/>'),
  radar: I('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12l6-6"/>'),
  search: I('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'),
  sun: I('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
  moon: I('<path d="M20 14.5A8 8 0 019.5 4 8 8 0 1020 14.5z"/>'),
  plus: I('<path d="M12 5v14M5 12h14"/>'),
  send: I('<path d="M5 12h14M13 6l6 6-6 6"/>'),
  menu: I('<path d="M4 7h16M4 12h16M4 17h16"/>'),
  gear: I('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/>'),
  play: I('<path d="M7 4l13 8-13 8z"/>'),
  back: I('<path d="M15 6l-6 6 6 6"/>'),
  chev: I('<path d="M9 6l6 6-6 6"/>'),
  check: I('<path d="M5 12.5l4.5 4.5L19 7.5"/>'),
  download: I('<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>'),
  copy: I('<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 00-2-2H6a2 2 0 00-2 2v8a2 2 0 002 2h2"/>'),
  trash: I('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>'),
  layers: I('<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>'),
  clip: I('<path d="M21 11.5l-8.6 8.6a5 5 0 01-7-7l8.5-8.6a3.4 3.4 0 014.8 4.8l-8.6 8.6a1.7 1.7 0 01-2.4-2.4l7.9-7.9"/>'),
  wand: I('<path d="M15 4V2M15 10V8M11 6h2M17 6h2M4 20L14 10"/><path d="M18 14l.5 1.5L20 16l-1.5.5L18 18l-.5-1.5L16 16l1.5-.5z"/>'),
};

// ---------------- labels ----------------
const STAGES = [["idea", "Fikir"], ["voice", "Ses"], ["preview", "Önizleme"], ["ready", "Hazır"], ["published", "Yayında"], ["rejected", "Reddedildi"]];
const SL = Object.fromEntries(STAGES);
const PL = { youtube: "YouTube", tiktok: "TikTok", instagram: "Instagram" };
const plat = (p) => PL[p] || p || "—";
const JOBTR = { p_ideas: "fikir üretimi", p_voice: "ses + önizleme", p_preview: "önizleme", p_render: "final render + QA", p_revise: "revizyon", p_design: "hareket tasarımı", p_direct: "art direction", p_verify: "doğrulama", p_plan: "düzenleme planı", p_plan_apply: "plan uygulama", p_music: "müzik + önizleme", p_plates: "çizimler + tasarım", plan: "planlayıcı", series_bible: "seri kitabı", series_cast: "karakter sayfaları", series_episode: "bölüm yazımı", ingest: "albüm indirme", analyze: "analiz", describe: "klip açıklama", radar: "radar", trends: "trendler", yt_stats: "YouTube istatistik", ref_lib: "referans analizi", discover: "günlük keşif", style_extract: "stil çıkarma", avatar_check: "avatar kontrolü", eleven_voices: "sesleri okuma", voice_add: "ses ekleme", talk_new: "konuşma videosu kurgusu", catalog_demos: "katalog örnek klipleri" };
const KIND = { footage: ["🎞", "Çekimli"], explainer: ["✍️", "Konu"], series: ["📚", "Seri"] };
const LOOKS = [["auto", "✨ Otomatik", "Opus sahneleri kendisi tasarlar"], ["illustrated", "🖌 Çizimli", "AI illüstrasyon + kamera + işaretler"], ["tech", "🌌 Tech", "koyu lacivert, neon vurgu"], ["paper", "📰 Paper", "Vox tarzı kâğıt"]];
const THEME_TR = { gezi: "Gezi", vlog: "Vlog", manzara: "Manzara", motivasyon: "Motivasyon", "diğer": "Diğer" };
const CORNER_TR = { tl: "sol üst", tr: "sağ üst", bl: "sol alt", br: "sağ alt" };

// ---------------- state ----------------
const S = { channels: [], ch: store.get("channel", null), formats: [], styles: [], me: null, jobs: [], drafts: {}, view: null, sig: null, comp: { prompt: store.get("composer", ""), att: { ...(store.get("pins", []).length ? { pins: store.get("pins", []), pin_mode: store.get("pinMode", "add") } : {}) }, plan: null } };
const chan = (id) => S.channels.find((c) => c.id === id);
const cur = () => chan(S.ch) || S.channels[0] || null;
function fmtName(id) { const f = S.formats.find((x) => x.id === id); return f ? f.name_tr : id; }
function initials(n) { return String(n || "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase(); }
function chAvatar(c, cls = "") { return c && c.logo_url ? `<img src="${esc(c.logo_url)}" alt="">` : `<span class="${cls}">${esc(initials(c ? c.name : "?"))}</span>`; }
function setChannel(id) { S.ch = id; store.set("channel", id); paintChannel(); }
function paintChannel() { const c = cur(); document.documentElement.style.setProperty("--ch", c ? c.color : "var(--accent)"); }
function stageBadge(s) { return `<span class="badge stage st-${s}"><i class="dot"></i>${esc(SL[s] || s)}</span>`; }
function thumb(p) { return p.thumb_url || (p.thumb ? `/thumb/clip/${encodeURIComponent(p.thumb)}?t=${p.thumb_t || 0}` : ""); }

// ---------------- shell ----------------
const NAV = [
  ["#/", "spark", "Stüdyo"], ["#/hat", "board", "Üretim panosu"], ["#/katalog", "layers", "Teknik kataloğu"], ["#/seriler", "book", "Seriler"], ["#/kesif", "compass", "Keşif"], ["#/takip", "chart", "Takip"],
  null,
  ["#/videolar", "film", "Videolar"], ["#/stiller", "palette", "Stiller"], ["#/referanslar", "ref", "Referanslar"], ["#/yerler", "pin", "Yerler & çekimler"],
  null,
  ["#/ses", "mic", "Ses & avatar"], ["#/butce", "coin", "Bütçe"], ["#/sinyal", "radar", "Sinyaller"], ["#/hesaplar", "user", "Hesaplar"],
];
function navHtml(path) {
  let grp = 0;
  const lbl = ["Üretim", "Kütüphane", "Sistem"];
  let out = `<div class="navlbl">${lbl[0]}</div>`;
  for (const n of NAV) {
    if (!n) { grp++; out += `<div class="navlbl">${lbl[grp]}</div>`; continue; }
    const on = path === n[0] || (n[0] === "#/hat" && path.startsWith("#/p/")) || (n[0] === "#/seriler" && path.startsWith("#/s/"));
    out += `<a class="nav ${on ? "on" : ""}" href="${n[0]}">${ICON[n[1]]}${n[2]}</a>`;
  }
  return out;
}
function renderShell() {
  const path = location.hash.split("?")[0] || "#/";
  const c = cur();
  const pend = (id) => { const ch = chan(id); const k = ch && ch.counts ? (ch.counts.idea || 0) + (ch.counts.voice || 0) : 0; return k ? `<span class="dotn">${k}</span>` : ""; };
  $("#rail").innerHTML = `<a class="logo-mark tip" data-tip="Stüdyo" href="#/">CF</a><hr>` +
    S.channels.map((x) => `<a class="chav tip ${x.id === S.ch && (path.startsWith("#/c/") || path === "#/" || path === "#/hat") ? "on" : ""}" style="--c:${esc(x.color)}" data-tip="${esc(x.name)}" href="#/c/${esc(x.id)}" data-act="pickChannel" data-id="${esc(x.id)}"><i class="pip"></i>${chAvatar(x)}${pend(x.id)}</a>`).join("") +
    `<a class="chav add tip" data-tip="Yeni kanal" href="#/kanal-yeni">+</a>`;
  $("#side").innerHTML = `<a class="ch-head" href="${c ? "#/c/" + esc(c.id) : "#/"}" style="text-decoration:none"><span class="chav" style="width:38px;height:38px;border-radius:12px;--c:${esc(c ? c.color : "")}">${chAvatar(c)}</span>
      <div style="min-width:0"><div class="nm">${esc(c ? c.name : "Kanal yok")}</div><div class="sub">${c ? esc(modeTr(c.mode)) + " · " + (c.lang || "en").toUpperCase() : ""}</div></div></a>
    ${navHtml(path)}
    <div class="foot"><button class="iconbtn" data-act="theme" title="Tema">${document.documentElement.dataset.theme === "light" ? ICON.moon : ICON.sun}</button>
      <span class="tiny faint">${S.me && S.me.login ? "👤 " + esc(S.me.name) : ""}</span></div>`;
  const running = S.jobs.filter((j) => j.status === "running" || j.status === "queued");
  $("#top").innerHTML = `<div class="crumb" id="crumb"></div><span class="sp"></span>
    <button class="searchbtn" data-act="palette">${ICON.search}<span>Ara ya da git…</span><kbd>⌘K</kbd></button>
    <span class="jobs-ind ${running.length ? "on" : ""}" data-act="go" data-href="#/">${running.length ? `<span class="spin"></span>${running.length} iş sürüyor` : "işler boşta"}</span>
    <button class="iconbtn" data-act="theme" title="Tema">${document.documentElement.dataset.theme === "light" ? ICON.moon : ICON.sun}</button>`;
  $("#mtop").innerHTML = `<button class="iconbtn" data-act="drawer">${ICON.menu}</button>
    <button class="chpick" data-act="drawer"><span class="chav" style="width:30px;height:30px;font-size:12px">${chAvatar(c)}</span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(c ? c.name : "Stüdyo")}</span></button>
    <span class="sp"></span>${running.length ? `<span class="jobs-ind on"><span class="spin"></span>${running.length}</span>` : ""}
    <button class="iconbtn" data-act="palette">${ICON.search}</button>`;
  const tab = (href, ic, t) => `<a href="${href}" class="${path === href ? "on" : ""}">${ICON[ic]}${t}</a>`;
  $("#tabbar").innerHTML = tab("#/", "spark", "Stüdyo") + tab("#/hat", "board", "Pano") + `<button data-act="newPrompt"><span class="plus">${ICON.plus}</span></button>` + tab("#/kesif", "compass", "Keşif") + `<button data-act="drawer">${ICON.menu}Menü</button>`;
  $("#drawerPanel").innerHTML = `<div class="navlbl">Kanallar</div><div class="chlist">${S.channels.map((x) => `<a class="chav ${x.id === S.ch ? "on" : ""}" style="--c:${esc(x.color)};flex:none" href="#/c/${esc(x.id)}" data-act="pickChannel" data-id="${esc(x.id)}">${chAvatar(x)}</a>`).join("")}<a class="chav add" href="#/kanal-yeni" style="flex:none">+</a></div>${navHtml(path)}
    <div class="foot mt16"><button class="btn sm" data-act="theme">${document.documentElement.dataset.theme === "light" ? "🌙 Koyu" : "☀️ Açık"} tema</button></div>`;
}
function crumb(parts) { const el = $("#crumb"); if (el) el.innerHTML = parts.map((p, i) => (i === parts.length - 1 ? `<b>${esc(p)}</b>` : `<span>${esc(p)}</span><span class="faint">/</span>`)).join(" "); document.title = parts[parts.length - 1] + " · Content Factory"; }
function modeTr(m) { return { footage: "çekimli", topic: "çekimsiz", mixed: "karışık" }[m] || m; }

// ---------------- router + poller ----------------
const ROUTES = {};
let pollT = null, routeSeq = 0;
function keepDrafts() { for (const el of $$("[data-keep]")) S.drafts[el.dataset.keep] = el.type === "checkbox" ? el.checked : el.value; }
function restoreDrafts() { for (const el of $$("[data-keep]")) { const v = S.drafts[el.dataset.keep]; if (v !== undefined) { if (el.type === "checkbox") el.checked = v; else el.value = v; } } }
function playing() { return $$("#app video, #app audio").some((v) => !v.paused && !v.ended); }
async function route(opts = {}) {
  clearTimeout(pollT);
  const seq = ++routeSeq;
  const h = location.hash || "#/";
  const path = h.split("?")[0];
  let view = ROUTES[path], arg = null;
  for (const [re, fn] of [[/^#\/p\/(\d+)/, viewProd], [/^#\/c\/([\w-]+)/, viewChannel], [/^#\/s\/(\d+)/, viewSeries]]) { const m = path.match(re); if (m) { view = fn; arg = m[1]; } }
  view = view || viewHome;
  if (!opts.poll) { S.drafts = {}; S.sig = null; }
  renderShell();
  try {
    const r = await view(arg, opts);
    if (seq !== routeSeq) return;
    if (r && r.poll) pollT = setTimeout(() => route({ poll: true }), r.poll);
  } catch (e) { if (!opts.poll) $("#app").innerHTML = `<div class="note err">Yüklenemedi: ${esc(e.message)}</div>`; }
}
/* paint(): put the view's html in place unless nothing changed; keep drafts and a playing video */
function paint(html, sig) {
  if (sig !== undefined && sig === S.sig) return false;
  if (S.sig !== null && playing()) return false;
  keepDrafts(); S.sig = sig === undefined ? null : sig;
  const y = window.scrollY;
  $("#app").innerHTML = html; restoreDrafts();
  if (S.sigKeepScroll) window.scrollTo(0, y);
  return true;
}
window.addEventListener("hashchange", () => { window.scrollTo(0, 0); closeDrawer(); route(); });

// ---------------- events ----------------
const ACT = {};
document.addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-act]");
  if (!el) return;
  const fn = ACT[el.dataset.act];
  if (!fn) return;
  if (el.tagName === "BUTTON" || el.dataset.prevent) ev.preventDefault();
  Promise.resolve(fn(el, ev)).catch((e) => toast(e.message, 1));
});
document.addEventListener("change", (ev) => { const el = ev.target.closest("[data-change]"); if (el && ACT[el.dataset.change]) Promise.resolve(ACT[el.dataset.change](el, ev)).catch((e) => toast(e.message, 1)); });
document.addEventListener("input", (ev) => { const el = ev.target.closest("[data-input]"); if (el && ACT[el.dataset.input]) ACT[el.dataset.input](el, ev); });
document.addEventListener("keydown", (ev) => {
  if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "k") { ev.preventDefault(); openPalette(); }
  // player keys (when not typing): space / k play-pause, j / l -1 / +1 s, , / . one frame, f fullscreen
  const typing = /INPUT|TEXTAREA|SELECT/.test((document.activeElement || {}).tagName || "");
  const v = !typing && !ev.metaKey && !ev.ctrlKey && ($("#modal.on video") || $("#app video"));
  if (v && [" ", "k", "j", "l", ",", ".", "f"].includes(ev.key)) {
    ev.preventDefault();
    if (ev.key === " " || ev.key === "k") v.paused ? v.play() : v.pause();
    if (ev.key === "j") v.currentTime = Math.max(0, v.currentTime - 1);
    if (ev.key === "l") v.currentTime = Math.min(v.duration || 1e9, v.currentTime + 1);
    if (ev.key === ",") { v.pause(); v.currentTime = Math.max(0, v.currentTime - 1 / 30); }
    if (ev.key === ".") { v.pause(); v.currentTime += 1 / 30; }
    if (ev.key === "f" && v.requestFullscreen) v.requestFullscreen();
  }
  if (ev.key === "Escape") { closeModal(); closePalette(); closeDrawer(); $$(".pop").forEach((p) => p.remove()); }
  if (ev.key === "Enter" && (ev.metaKey || ev.ctrlKey) && ev.target.id === "prompt") ACT.plan();
});
ACT.go = (el) => { location.hash = el.dataset.href; };
ACT.pickChannel = (el) => setChannel(el.dataset.id);
ACT.theme = () => { const r = document.documentElement; r.dataset.theme = r.dataset.theme === "light" ? "dark" : "light"; store.set("theme", r.dataset.theme); try { localStorage.setItem("cf.theme", r.dataset.theme); } catch (e) {} renderShell(); };
ACT.drawer = () => $("#drawer").classList.toggle("on");
function closeDrawer() { $("#drawer").classList.remove("on"); }
ACT.closeModal = () => closeModal();
ACT.newPrompt = () => { location.hash = "#/"; setTimeout(() => $("#prompt") && $("#prompt").focus(), 80); };
function openVideo(src, photo) { $("#modalBody").innerHTML = photo ? `<img src="${esc(src)}" alt="">` : `<video src="${esc(src)}" controls autoplay playsinline></video>`; $("#modal").classList.add("on"); }
function closeModal() { $("#modal").classList.remove("on"); $("#modalBody").innerHTML = ""; }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
ACT.open = (el) => openVideo(el.dataset.src, el.dataset.photo === "1");
ACT.copy = (el) => copy(el.dataset.text || "");

// ---------------- command palette ----------------
let palSel = 0, palItems = [];
function openPalette() { $("#palette").classList.add("on"); const i = $("#palQ"); i.value = ""; i.focus(); palSearch(""); }
function closePalette() { $("#palette").classList.remove("on"); }
$("#palette").addEventListener("click", (e) => { if (e.target.id === "palette") closePalette(); });
ACT.palette = () => openPalette();
async function palSearch(t) {
  const pages = NAV.filter(Boolean).map((n) => ({ kind: "sayfa", label: n[2], href: n[0] })).filter((x) => !t || x.label.toLowerCase().includes(t.toLowerCase()));
  const acts = [{ kind: "eylem", label: "✨ Yeni üretim (prompt yaz)", href: "#/" }, { kind: "eylem", label: "＋ Yeni kanal", href: "#/kanal-yeni" }].filter((x) => !t || x.label.toLowerCase().includes(t.toLowerCase()));
  let found = [];
  try { found = await api("/api/search?q=" + encodeURIComponent(t)); } catch (e) {}
  palItems = [...acts, ...found, ...pages].slice(0, 30); palSel = 0; palDraw();
}
function palDraw() { $("#palRes").innerHTML = palItems.map((x, i) => `<a class="it ${i === palSel ? "on" : ""}" href="${esc(x.href)}" data-act="palGo"><span class="k">${esc(x.kind)}</span><span>${esc(x.label)}</span>${x.stage ? `<span class="sp"></span>${stageBadge(x.stage)}` : ""}</a>`).join("") || `<div class="it faint">Sonuç yok</div>`; }
ACT.palGo = () => closePalette();
$("#palQ").addEventListener("input", (e) => palSearch(e.target.value));
$("#palQ").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown") { palSel = Math.min(palItems.length - 1, palSel + 1); palDraw(); e.preventDefault(); }
  if (e.key === "ArrowUp") { palSel = Math.max(0, palSel - 1); palDraw(); e.preventDefault(); }
  if (e.key === "Enter" && palItems[palSel]) { location.hash = palItems[palSel].href; closePalette(); }
});

// ---------------- shared pieces ----------------
function pcard(p) {
  const c = chan(p.channel_id);
  const k = KIND[p.kind] || KIND.footage;
  const t = thumb(p);
  return `<a class="pc st-${p.stage}" href="#/p/${p.prod_id}" style="--c:${esc(c ? c.color : "transparent")}"><i class="stripe"></i>
    <div class="cv">${t ? `<img loading="lazy" src="${esc(t)}" alt="">` : `<div class="glyph">${k[0]}</div>`}
      <div class="tag"><span class="badge glass">${k[0]} ${esc(k[1])}</span>${p.aspect === "16:9" ? '<span class="badge glass">16:9</span>' : ""}</div>
      ${p.duration ? `<span class="dur">${sec(p.duration)}</span>` : ""}</div>
    <div class="bd"><div class="t">${esc(p.title)}</div>${p.hook ? `<div class="h">${esc(p.hook)}</div>` : ""}
      <div class="ft">${stageBadge(p.stage)}${c ? `<span class="badge">${esc(c.name)}</span>` : ""}${p.series ? `<span class="badge">Bölüm ${esc(p.series.episode)}</span>` : ""}${p.warn ? `<span class="badge warn">⚠ ${p.warn}</span>` : ""}</div>
      ${p.busy ? `<div class="busy"><span class="spin"></span>${esc(JOBTR[p.busy.kind] || p.busy.kind)}</div>` : ""}</div></a>`;
}
function inrow(p) {
  const t = thumb(p);
  return `<a class="inrow" href="#/p/${p.prod_id}">${t ? `<img class="th" loading="lazy" src="${esc(t)}" alt="">` : `<div class="th" style="display:grid;place-items:center">${(KIND[p.kind] || KIND.footage)[0]}</div>`}
    <div style="min-width:0;flex:1"><div class="tt">${esc(p.title)}</div><div class="nx">${stageBadge(p.stage)} <span>👉 ${esc(p.next || "")}</span></div></div><span class="go">${ICON.chev}</span></a>`;
}
function jobLine(j) {
  const st = j.status === "running" || j.status === "queued" ? '<span class="spin" style="color:var(--accent)"></span>' : j.status === "failed" ? '<span class="bad">●</span>' : '<span class="ok">●</span>';
  return `<div class="jobline">${st}<b>#${j.job_id}</b><span>${esc(JOBTR[j.kind] || j.kind)}</span><span class="sp"></span><span class="tiny faint">${ago(j.finished_at || j.started_at)}</span></div>
    ${j.result && j.status !== "running" ? `<div class="tiny muted" style="margin:-4px 0 6px 24px">${esc(j.result)}</div>` : ""}
    ${j.tail && j.status !== "done" ? `<pre class="log">${esc(j.tail)}</pre>` : ""}`;
}
function seg(name, opts, curv, act = "segPick") { return `<div class="seg">${opts.map(([v, t]) => `<button class="${String(curv) === String(v) ? "on" : ""}" data-act="${act}" data-name="${esc(name)}" data-v="${esc(v)}">${t}</button>`).join("")}</div>`; }
function spark(h) { if (!h || h.length < 2) return ""; const v = h.map((x) => x.views), mx = Math.max(...v), mn = Math.min(...v), W = 90, H = 24; const pts = v.map((y, i) => `${((i / (v.length - 1)) * W).toFixed(1)},${(H - 2 - (mx === mn ? 0.5 : (y - mn) / (mx - mn)) * (H - 4)).toFixed(1)}`).join(" "); return `<svg class="spark" width="${W}" height="${H}"><polyline points="${pts}" fill="none" stroke="var(--ch)" stroke-width="1.6"/></svg>`; }

// ================= Stüdyo (home): composer -> plan -> start =================
const EXAMPLES = [
  "Eibsee çekimlerimden, kendi sesimle anlattığım 30 saniyelik sakin bir hikâye",
  "Hava durumu uygulamaları neden yanılıyor gibi görünür? Çizimli, kamera hareketli anlat",
  "Bir deniz feneri bekçisi robot ve martı arkadaşı hakkında 6 bölümlük çizgi film serisi",
  "Bugünün en ilginç yapay zekâ makalesini 3 bilgiyle anlat, yatay YouTube videosu olarak",
  "Seriler sayfasındaki seriden sıradaki bölümü üret",
];
async function viewHome(_, opts) {
  const ch = S.ch;
  const [o, plans] = await Promise.all([api("/api/overview" + (opts.poll ? "" : "")), api("/api/plans")]);
  S.jobs = o.jobs; renderShell(); crumb(["Stüdyo"]);
  const gone = store.get("dismissedPlans", []);
  const live = plans.find((p) => (p.status === "thinking" || p.status === "ready") && !gone.includes(p.plan_id));
  if (!S.comp.plan && live) S.comp.plan = live.plan_id;
  const plan = S.comp.plan ? plans.find((p) => p.plan_id === S.comp.plan) || (await api("/api/plan/" + S.comp.plan).catch(() => null)) : null;
  const c = cur();
  const hour = new Date().getHours();
  const hello = hour < 6 ? "İyi geceler" : hour < 12 ? "Günaydın" : hour < 18 ? "İyi günler" : "İyi akşamlar";
  const pend = o.pending;
  const html = `
  <section class="hero">
    <div class="tiny faint" style="font-weight:700;letter-spacing:.08em;text-transform:uppercase">${esc(hello)}${S.me && S.me.name ? ", " + esc(S.me.name) : ""} · ${o.made_this_month} video bu ay</div>
    <h1>Bugün ne <span class="serif">üretelim?</span></h1>
    <p class="lead">Ne istediğini yaz, elindekini ekle. Seçtiğin model isteğini anlar, bir plan önerir; onaylarsan fabrika çalışır. Kredi harcayan her adım ayrıca onayını bekler.</p>
    ${composerHtml(c)}
    <div id="planBox">${plan ? planHtml(plan) : ""}</div>
  </section>
  <div class="homegrid mt24">
    <div>
      <h2>Senden bekleyenler <span class="faint">${pend.length}</span></h2>
      <div class="inbox">${pend.slice(0, 8).map(inrow).join("") || `<div class="empty"><div class="big">🌤</div>Şu an senden bekleyen bir şey yok.</div>`}</div>
      <h2>Son üretimler</h2>
      <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(210px,1fr))">${o.recent.slice(0, 8).map(pcard).join("") || '<div class="empty">Henüz üretim yok</div>'}</div>
    </div>
    <div>
      <h2>Kanallar</h2>
      <div class="grid">${S.channels.map((x) => `<a class="card hover row nowrap" href="#/c/${esc(x.id)}" style="text-decoration:none;padding:12px">
        <span class="chav" style="width:40px;height:40px;border-radius:12px;--c:${esc(x.color)}">${chAvatar(x)}</span>
        <div style="min-width:0;flex:1"><div style="font-weight:680">${esc(x.name)}</div><div class="tiny muted">${esc(modeTr(x.mode))} · ${["idea", "voice", "preview", "ready", "published"].map((s) => (x.counts || {})[s] || 0).join(" / ")}</div></div>
        <span class="faint">${ICON.chev}</span></a>`).join("")}</div>
      <h2>İşler</h2>
      <div class="card flat" style="padding:6px 14px">${o.jobs.map(jobLine).join("") || '<div class="tiny faint" style="padding:10px 0">Henüz iş yok</div>'}</div>
      <h2>Bütçe</h2>
      <div class="card flat"><div class="row"><span class="small muted">ElevenLabs bu ay</span><span class="sp"></span><b class="mono">${num(o.budget.spent)} / ${num(o.budget.cap)}</b></div>
        <div class="bar mt8"><i style="width:${Math.min(100, (o.budget.spent / o.budget.cap) * 100)}%"></i></div>
        <div class="row mt12 small"><span class="muted">Takip edilen izlenme</span><span class="sp"></span><b class="mono">${num(o.tracking.total_views)}</b></div></div>
    </div>
  </div>`;
  const sig = JSON.stringify([o.pending.map((p) => [p.prod_id, p.stage, p.busy]), o.recent.map((p) => [p.prod_id, p.updated_at]), o.jobs.map((j) => [j.job_id, j.status]), plan && [plan.status, plan.plan], S.comp.att]);
  paint(html, sig);
  wireComposer();
  const thinking = plan && plan.status === "thinking";
  if (thinking) $(".composer") && $(".composer").classList.add("thinking");
  return { poll: thinking ? 2500 : o.busy ? 5000 : 20000 };
}
function composerHtml(c) {
  const a = S.comp.att;
  const chips = [];
  if (a.places && a.places.length) chips.push(`<span class="chip on" data-act="attClear" data-k="places">📍 ${a.places.length} yer <span class="x">✕</span></span>`);
  if (a.refs && a.refs.length) chips.push(`<span class="chip on" data-act="attClear" data-k="refs">🎞 ${a.refs.length} referans <span class="x">✕</span></span>`);
  if (a.series_id) chips.push(`<span class="chip on" data-act="attClear" data-k="series_id">📚 seri #${esc(a.series_id)} <span class="x">✕</span></span>`);
  if (a.links && a.links.length) chips.push(`<span class="chip on" data-act="attClear" data-k="links">🔗 ${a.links.length} link <span class="x">✕</span></span>`);
  if (a.talk) chips.push(`<span class="chip on" data-act="attClear" data-k="talk">🎙 ${esc(a.talk_name || "konuşma videosu")} <span class="x">✕</span></span>`);
  if (a.pins && a.pins.length) chips.push(`<a class="chip on" style="text-decoration:none" href="#/katalog" title="${esc(a.pins.join(", "))}">📌 ${a.pins.length} teknik</a><span class="chip" data-act="pinMode" title="Opus seçtiklerine ekleyebilir mi?">${a.pin_mode === "only" ? "🔒 sadece bunlar" : "✨ Opus ekleyebilir"}</span><span class="chip" data-act="pinsClear">✕</span>`);
  return `<div class="composer" id="composer"><div class="inner">
    <textarea id="prompt" data-keep="prompt" data-input="promptInput" placeholder="${esc(EXAMPLES[Math.floor(Date.now() / 60000) % EXAMPLES.length])}">${esc(S.comp.prompt)}</textarea>
    ${chips.length ? `<div class="att-row">${chips.join("")}</div>` : ""}
    <div class="tools">
      <button class="attach" data-act="attPick" data-k="places">${ICON.pin}Çekimler</button>
      <button class="attach" data-act="attPick" data-k="refs">${ICON.ref}Referans</button>
      <button class="attach" data-act="attPick" data-k="series_id">${ICON.book}Seri</button>
      <button class="attach" data-act="attPick" data-k="links">${ICON.clip}Link</button>
      <button class="attach" data-act="talkPick" title="Kameraya konuştuğun ham videoyu seçtiğin model kurgular">🎙 Konuşma videosu</button>
      <a class="attach" style="text-decoration:none" href="#/katalog" title="Teknikleri örnek kliplerle gör; istediklerini sabitle ya da Opus seçsin">${ICON.layers}Teknik${a.pins && a.pins.length ? ` (${a.pins.length})` : ""}</a>
      <button class="attach ${a.quick ? "on" : ""}" data-act="quickToggle" title="Hızlı plan: araştırma, eskizler ve eleştirmen olmadan tek çağrı">${a.quick ? "⚡ hızlı plan" : "🎬 tam ekip"}</button>
      <span class="attach" style="cursor:default">📺 ${esc(c ? c.name : "kanal")}</span>
      <span class="sp"></span><span class="tiny faint" style="margin-right:6px">⌘⏎</span>
      <button class="send" data-act="plan" title="Planla">${ICON.send}</button>
    </div></div></div>
    <div class="suggest">${EXAMPLES.slice(0, 4).map((e) => `<button data-act="example" data-text="${esc(e)}">${esc(e)}</button>`).join("")}</div>`;
}
function wireComposer() {
  const ta = $("#prompt"); if (!ta) return;
  const box = $("#composer");
  ta.addEventListener("focus", () => box.classList.add("focus"));
  ta.addEventListener("blur", () => box.classList.remove("focus"));
  const fit = () => { ta.style.height = "auto"; ta.style.height = Math.min(320, ta.scrollHeight) + "px"; };
  ta.addEventListener("input", fit); fit();
}
ACT.promptInput = (el) => { S.comp.prompt = el.value; store.set("composer", el.value); };
ACT.example = (el) => { S.comp.prompt = el.dataset.text; const ta = $("#prompt"); ta.value = el.dataset.text; ta.focus(); store.set("composer", el.dataset.text); };
ACT.attClear = (el) => { delete S.comp.att[el.dataset.k]; S.sig = null; route({ poll: true }); };
ACT.attPick = async (el) => {
  $$(".pop").forEach((p) => p.remove());
  const k = el.dataset.k, a = S.comp.att;
  const pop = document.createElement("div"); pop.className = "pop";
  if (k === "places") {
    const places = await api("/api/places");
    pop.innerHTML = `<h3>Hangi çekimler?</h3><div class="chips">${places.map((p) => `<span class="chip ${(a.places || []).includes(p.place_id) ? "on" : ""}" data-act="attToggle" data-k="places" data-v="${p.place_id}">${esc(p.name)} <span class="faint">${p.n}</span></span>`).join("") || '<span class="muted small">Henüz çekim yok: Yerler sayfasından iCloud albümü ekle.</span>'}</div>`;
  } else if (k === "refs") {
    const { refs } = await api("/api/refs");
    pop.innerHTML = `<h3>Stil referansı (en fazla 3)</h3><div class="row nowrap" style="overflow-x:auto;gap:8px">${refs.map((r) => `<div data-act="attToggle" data-k="refs" data-v="${esc(r.ref_id)}" style="cursor:pointer;flex:none;width:86px"><img src="/thumb/ref?id=${encodeURIComponent(r.ref_id)}" style="width:86px;height:140px;object-fit:cover;border-radius:10px;border:2px solid ${(a.refs || []).includes(r.ref_id) ? "var(--ch)" : "transparent"}"><div class="tiny faint">${esc((r.title || "").slice(0, 18))}</div></div>`).join("") || '<span class="muted small">Referans yok</span>'}</div>`;
  } else if (k === "series_id") {
    const ss = await api("/api/series");
    pop.innerHTML = `<h3>Hangi seri?</h3><div class="grid">${ss.map((s) => `<div class="row" style="cursor:pointer" data-act="attSet" data-k="series_id" data-v="${s.series_id}"><b>${esc(s.title)}</b><span class="tiny muted">${s.made}/${s.episodes} bölüm · ${esc(s.status)}</span></div>`).join("") || '<span class="muted small">Henüz seri yok: “… hakkında bir seri” diye yazman yeter.</span>'}</div>`;
  } else {
    pop.innerHTML = `<h3>Link (kaynak, makale, referans)</h3><div class="row nowrap"><input type="url" id="attLink" placeholder="https://…"><button class="btn sm" data-act="attLink">Ekle</button></div>`;
  }
  el.parentElement.appendChild(pop);
  setTimeout(() => document.addEventListener("click", function off(e) { if (!pop.contains(e.target) && e.target !== el) { pop.remove(); document.removeEventListener("click", off); } }), 0);
};
ACT.quickToggle = () => { S.comp.att.quick = !S.comp.att.quick; if (!S.comp.att.quick) delete S.comp.att.quick; S.sig = null; route({ poll: true }); };
ACT.talkPick = () => {
  const inp = document.createElement("input"); inp.type = "file"; inp.accept = "video/mp4,video/quicktime,.mp4,.mov,.m4v";
  inp.onchange = async () => {
    const f = inp.files[0]; if (!f) return;
    toast("Yükleniyor… " + f.name);
    try {
      const r = await upload("/api/refs/upload", f, { "X-Talk": "1" }, (k) => { const t = $("#toast"); t.textContent = `Yükleniyor %${Math.round(k * 100)}`; t.className = "on"; });
      S.comp.att.talk = r.file; S.comp.att.talk_name = f.name; S.sig = null; toast("Video eklendi: şimdi ne istediğini yaz ve planla");
      route({ poll: true });
    } catch (e) { toast(e.message, 1); }
  };
  inp.click();
};
ACT.attToggle = (el) => {
  const k = el.dataset.k, v = k === "places" ? Number(el.dataset.v) : el.dataset.v, a = S.comp.att;
  a[k] = a[k] || []; a[k] = a[k].includes(v) ? a[k].filter((x) => x !== v) : [...a[k], v].slice(k === "refs" ? -3 : -50);
  el.classList.toggle("on"); if (k === "refs") el.querySelector("img").style.borderColor = a[k].includes(v) ? "var(--ch)" : "transparent";
  S.sig = null;
};
ACT.attSet = (el) => { S.comp.att[el.dataset.k] = Number(el.dataset.v); $$(".pop").forEach((p) => p.remove()); S.sig = null; route({ poll: true }); };
ACT.attLink = () => { const v = $("#attLink").value.trim(); if (!/^https?:\/\//.test(v)) return toast("Geçerli bir link yaz", 1); S.comp.att.links = [...(S.comp.att.links || []), v]; $$(".pop").forEach((p) => p.remove()); S.sig = null; route({ poll: true }); };
ACT.plan = async () => {
  const prompt = ($("#prompt") || {}).value || "";
  const att = { ...S.comp.att, channel: S.ch };
  if (S.comp.att.links) att.links = S.comp.att.links;
  const r = await post("/api/plan", { prompt, attachments: att });
  S.comp.plan = r.plan_id; S.sig = null;
  $("#planBox").innerHTML = planHtml({ status: "thinking", plan_id: r.plan_id, prompt });
  $(".composer").classList.add("thinking");
  setTimeout(() => route({ poll: true }), 1500);
};
function planHtml(row) {
  if (row.status === "thinking") {
    const pr = ((row.plan || {}).progress || []).filter((x) => x.status !== "skip");
    const ic = { wait: "○", run: '<span class="spin"></span>', ok: "✓", fail: "✕" };
    return `<div class="plan"><div class="thinking"><span class="orb"></span><div style="flex:1"><div style="font-weight:650">Yönetmen ekibi çalışıyor<span class="typing"></span></div>
      ${pr.length ? `<div class="col mt8" style="gap:4px">${pr.map((x) => `<div class="row small" style="gap:8px;opacity:${x.status === "wait" ? 0.45 : 1}"><span style="width:16px;display:inline-grid;place-items:center">${ic[x.status] || ""}</span><span>${esc(x.tr)}</span>${x.detail ? `<span class="tiny muted">· ${esc(x.detail)}</span>` : ""}${x.seconds ? `<span class="tiny faint">${x.seconds} sn</span>` : ""}</div>`).join("")}</div>`
        : `<div class="small muted">Araştırma, hafıza, 3 yaklaşım, eskizler ve eleştirmen (~2-5 dk; hızlı planda ~30 sn).</div>`}</div></div></div>`;
  }
  if (row.status === "failed") return `<div class="plan"><div class="ph"><div class="ic">!</div><div><div class="say">Plan çıkarılamadı</div><div class="small muted">${esc(row.error || "")}</div></div></div><div class="pf"><button class="btn sm" data-act="plan">Tekrar dene</button><button class="btn sm ghost" data-act="planDismiss">Kapat</button></div></div>`;
  if (row.status === "started") return `<div class="plan"><div class="ph"><div class="ic">✓</div><div style="flex:1"><div class="say">Başladı: ${esc((row.plan || {}).kind_tr || "")}</div><div class="small muted">İşler kuyrukta (#${(row.job_ids || []).join(", #")}). Hazır olanlar “Senden bekleyenler”de görünür.${(row.plan || {}).kind === "series_new" ? ` Seri kitabı yazılıyor: <a href="#/s/${esc(row.plan.series.id)}">seriyi aç →</a>` : ""}</div></div></div><div class="pf"><button class="btn sm" data-act="planDismiss">Yeni bir şey üret</button></div></div>`;
  if (row.status === "cancelled") return "";
  const p = row.plan || {};
  const presets = S.formats.filter((f) => f.status === "ready" && f.mode === ({ footage: "footage", topic: "topic" }[p.kind] || "series"));
  const looks = [...LOOKS.map((l) => [l[0], l[1]]), ...S.styles.filter((s) => s.status === "approved").map((s) => ["custom:" + s.id, "🎨 " + s.id])];
  const steps = p.steps_tr && p.steps_tr.length ? p.steps_tr : defaultSteps(p);
  const pay = (t) => /kredi|onay|ses|çizim|müzik|karakter/i.test(t);
  return `<div class="plan" data-plan="${row.plan_id}">
    <div class="ph"><div class="ic">${{ footage: "🎞", topic: "✍️", series_new: "📚", series_episode: "🎬", talk: "🎙" }[p.kind] || "✨"}</div>
      <div style="flex:1;min-width:0"><div class="tiny faint" style="font-weight:700;letter-spacing:.06em;text-transform:uppercase">Plan · ${esc(p.kind_tr || "")}${p.fallback ? " · yedek plan (AI çağrısı başarısız)" : ""}</div>
        <div class="say">${esc(p.understood_tr || row.prompt || "")}</div></div>
      <button class="iconbtn" data-act="planDismiss" title="Kapat">✕</button></div>
    ${(p.questions_tr || []).length || p.question_tr ? `<div style="padding:12px 20px 0"><div class="note warn">${[...(p.questions_tr || []), ...(p.question_tr ? [p.question_tr] : [])].map((x) => "❓ " + esc(x)).join("<br>")}<div class="tiny muted" style="margin-top:4px">Cevabı aşağıdaki brief'e ekleyebilir ya da yeni bir prompt yazabilirsin.</div></div></div>` : ""}
    <div class="pb"><div class="col" style="gap:14px">
      <div class="field"><span>Tür</span>${seg("kind", [["footage", "🎞 Çekimli"], ["topic", "✍️ Konu"], ["series_new", "📚 Yeni seri"], ["series_episode", "🎬 Seri bölümü"], ...((row.attachments || {}).talk ? [["talk", "🎙 Konuşma kurgusu"]] : [])], p.kind, "planSet")}</div>
      ${artDirHtml(row, p)}
      <div class="row" style="gap:12px;align-items:flex-start">
        <label class="field" style="flex:1;min-width:160px"><span>Kanal</span><select data-change="planSel" data-name="channel">${S.channels.map((c) => `<option value="${esc(c.id)}" ${c.id === p.channel ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
        ${p.kind === "footage" || p.kind === "topic" ? `<label class="field" style="flex:1;min-width:160px"><span>Tarz</span><select data-change="planSel" data-name="format">${presets.map((f) => `<option value="${esc(f.id)}" ${f.id === p.format ? "selected" : ""}>${esc(f.name_tr)}</option>`).join("")}</select></label>` : ""}
      </div>
      ${p.kind === "topic" || p.kind === "series_new" ? `<div class="field"><span>Görünüm</span><div class="chips">${(p.kind === "series_new" ? looks.filter((l) => l[0] === "illustrated") : looks).map(([k, t]) => `<span class="chip ${p.look === k ? "on" : ""}" data-act="planSet" data-name="look" data-v="${esc(k)}">${esc(t)}</span>`).join("")}</div></div>` : ""}
      ${p.kind === "series_new" ? `<div class="row" style="gap:12px;align-items:flex-start"><label class="field" style="flex:1;min-width:150px"><span>Çizim dili</span><select data-change="planSeries" data-name="style">${Object.entries(SERIES_STYLES).map(([k, t]) => `<option value="${k}" ${p.series.style === k ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></label>
        <label class="field" style="width:110px"><span>Bölüm</span><input type="number" min="2" max="20" value="${p.series.episodes}" data-change="planSeries" data-name="episodes"></label>
        <label class="field" style="width:120px"><span>Bölüm süresi</span><input type="number" min="30" max="120" step="5" value="${p.series.ep_seconds}" data-change="planSeries" data-name="ep_seconds"></label>
        <label class="field" style="width:110px"><span>Dil</span><select data-change="planSeries" data-name="lang"><option value="tr" ${p.series.lang === "tr" ? "selected" : ""}>Türkçe</option><option value="en" ${p.series.lang === "en" ? "selected" : ""}>English</option></select></label></div>` : ""}
      <div class="row" style="gap:16px">
        <div class="field"><span>Kadraj</span>${seg("aspect", [["9:16", "▯ 9:16"], ["16:9", "▭ 16:9"]], p.aspect, "planSet")}</div>
        ${p.kind === "footage" ? `<div class="field"><span>Fikir sayısı</span>${seg("n", [1, 2, 3, 4, 5].map((n) => [n, n]), p.n, "planSet")}</div>
          <div class="field"><span>Anlatım</span>${seg("narrate", [["auto", "🤖 Otomatik"], ["on", "🎙 Var"], ["off", "🌿 Yok"]], p.narrate, "planSet")}</div>` : ""}
      </div>
      <label class="field"><span>Brief (yazara giden metin)</span><textarea data-keep="brief-${row.plan_id}" data-change="planSel" data-name="brief" style="min-height:90px">${esc(p.brief || "")}</textarea></label>
      ${(p.alternatives || []).length ? `<div class="field"><span>Alternatifler</span><div class="chips">${p.alternatives.map((a, i) => `<span class="chip" data-act="planAlt" data-i="${i}">↺ ${esc(a.label_tr)}</span>`).join("")}</div></div>` : ""}
    </div><div>
      <h3>Nasıl ilerleyecek</h3>
      <div class="pipe">${steps.map((t, i) => `<div class="st ${pay(t) ? "pay" : ""}"><span class="n">${i + 1}</span><div><div class="t">${esc(t)}</div>${pay(t) ? '<div class="d">kredi harcar · ayrı onayınla</div>' : ""}</div></div>`).join("")}</div>
      <h3 class="mt16">Tahmini maliyet</h3>
      <div class="costs">${((p.costs || {}).lines || []).map((l) => `<div class="ln"><span class="muted">${esc(l.label)}</span><b>~${num(l.credits)} kr</b></div>`).join("") || '<div class="muted small">ElevenLabs kredisi yok</div>'}
        ${(p.costs || {}).render ? `<div class="ln"><span class="muted">⏱ Render (${p.costs.render.seconds} sn, bu makinede${p.costs.render.measured ? "" : ", kaba"})</span><b>önizleme ${esc(p.costs.render.preview)} · final ${esc(p.costs.render.final)}</b></div>${p.costs.render.blur > 1 ? '<div class="ln tiny faint"><span>hareket bulanıklığı açık: final ×' + p.costs.render.blur + " örnek</span></div>" : ""}` : ""}
        <div class="ln tiny faint"><span>Seçili CLI</span><b style="font-weight:500">${esc((p.costs || {}).claude || "")}</b></div>
        ${p.team ? `<div class="ln tiny faint"><span>Planlama ekibi${p.team.quick ? " (hızlı)" : ""}</span><b style="font-weight:500">~${usd(p.team.cost_usd)}</b></div>` : ""}</div>
    </div></div>
    <div class="pf"><button class="btn accent" data-act="planStart">${ICON.check}Planı onayla ve başlat</button><button class="btn ghost" data-act="planCancel">Vazgeç</button><span class="sp"></span><span class="tiny faint">Hiçbir şey kredi harcamadan başlamaz.</span></div>
  </div>`;
}
function artDirHtml(row, p) {
  const tl = p.technique_labels || [], tr = p.treatments || [], bm = p.benchmark || {};
  const byArea = {};
  for (const t of tl) (byArea[t.area_tr] = byArea[t.area_tr] || []).push(t);
  return `<div class="field"><span>Art direction (planner'ın yönetmen notu, düzenlenebilir)</span>
      <textarea data-change="planSel" data-name="direction" style="min-height:84px" placeholder="Konsept, görsel dünya, hareket, ses, imza anı, final…">${esc(p.direction || "")}</textarea>
      ${bm.learn ? `<div class="tiny muted mt8">🎬 Referans: ${esc(bm.learn)}${bm.avoid ? ` · <span class="faint">almayacağımız: ${esc(bm.avoid)}</span>` : ""}</div>` : ""}</div>
    ${p.memory_tr || (p.research || {}).insight ? `<div class="note mt8 small">${(p.research || {}).insight ? `🔎 <b>Ana fikir:</b> ${esc(p.research.insight)}${p.research.misconception ? `<br><span class="muted">Yaygın yanlış: ${esc(p.research.misconception)}</span>` : ""}<br>` : ""}${p.memory_tr ? `🧠 <span class="muted">${esc(p.memory_tr)}</span>` : ""}</div>` : ""}
    ${tr.length ? `<div class="field"><span>Üç yaklaşım${p.critic ? " · eleştirmen: " + esc(p.critic.summary_tr || "") : " (birini seç)"}</span>
      <div style="display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(170px,1fr))">${tr.map((t, i) => treatCard(t, i, p)).join("")}</div></div>` : ""}
    <div class="field"><span>Teknikler (planner birleştirdi · ✕ ile çıkar, ＋ ile ekle)${p.seconds ? ` · hedef ~${p.seconds} sn` : ""}</span>
      ${Object.entries(byArea).map(([a, ts]) => `<div class="tiny faint mt8">${esc(a)}</div><div class="chips">${ts.map((t) => `<span class="chip on" data-act="planTech" data-id="${esc(t.id)}" data-op="del" title="${esc(t.why || t.id)}">${t.pinned ? "📌 " : ""}${esc(t.tr)} <span class="x">✕</span></span>`).join("")}</div>${ts.some((t) => t.why) ? `<div class="tiny muted mt8">${ts.filter((t) => t.why).map((t) => `<b>${esc(t.tr)}:</b> ${esc(t.why)}`).join("<br>")}</div>` : ""}`).join("") || '<div class="tiny muted">Teknik seçilmedi</div>'}
      <div class="chips mt8"><span class="chip" data-act="planTechPick" data-kind="${esc(p.kind === "talk" ? "talk" : p.kind === "footage" ? "footage" : "topic")}">＋ teknik ekle</span></div></div>`;
}
function treatCard(t, i, p) {
  const on = (p.chosen || 0) === i, sk = t.sketch || {}, sc = t.score || {};
  const img = (sk.stills || []).slice(-1)[0];
  const bar = (k, tr) => sc[k] != null ? `<span class="tiny" title="${tr}">${tr} <b>${sc[k]}</b></span>` : "";
  return `<div class="card flat" data-act="planTreat" data-i="${i}" style="cursor:pointer;min-width:0;padding:10px;border:2px solid ${on ? "var(--ch)" : "transparent"}">
    <div class="row" style="gap:6px"><span class="chip ${on ? "on" : ""}">${i + 1}</span><b class="small" style="flex:1">${esc(t.label_tr)}</b>${p.recommended === i ? '<span class="badge">⭐ önerilen</span>' : ""}</div>
    ${img ? `<img src="/media/plans/${esc(img)}" data-act="open" data-src="/media/plans/${esc(img)}" data-photo="1" style="width:100%;max-height:340px;margin-top:8px;border-radius:10px;aspect-ratio:${p.aspect === "16:9" ? "16/9" : "9/16"};object-fit:cover" alt="">`
      : sk.error ? `<div class="tiny muted mt8">eskiz çizilemedi</div>` : ""}
    <div class="tiny muted mt8">${esc(t.idea_tr || "")}</div>
    <div class="row mt8" style="gap:8px;flex-wrap:wrap">${bar("clarity", "anlaşılır")}${bar("hook", "hook")}${bar("novelty", "yenilik")}${bar("feasibility", "yapılabilir")}${t.novelty != null ? `<span class="tiny faint" title="son videolara göre ölçülen yenilik">🧠 ${Math.round(t.novelty * 100)}% yeni</span>` : ""}</div>
    ${sc.why_tr ? `<div class="tiny mt8">${esc(sc.why_tr)}</div>` : ""}</div>`;
}
ACT.planTreat = (el) => planUpdate({ treatment: Number(el.dataset.i) });
ACT.planTech = async (el) => {
  const id = $("[data-plan]").dataset.plan; const row = await api("/api/plan/" + id);
  let ts = row.plan.techniques || [];
  ts = el.dataset.op === "del" ? ts.filter((x) => x !== el.dataset.id) : [...ts, el.dataset.id];
  $$(".pop").forEach((x) => x.remove());
  await planUpdate({ techniques: ts });
};
ACT.planTechPick = async (el) => {
  $$(".pop").forEach((p) => p.remove());
  const chips = await api("/api/techniques?kind=" + encodeURIComponent(el.dataset.kind));
  const by = {}; for (const c of chips) (by[c.area_tr] = by[c.area_tr] || []).push(c);
  const pop = document.createElement("div"); pop.className = "pop"; pop.style.maxHeight = "60vh"; pop.style.overflowY = "auto";
  pop.innerHTML = `<h3>Teknik ekle</h3>${Object.entries(by).map(([a, cs]) => `<div class="tiny faint mt8">${esc(a)}</div><div class="chips">${cs.map((c) => `<span class="chip" data-act="planTech" data-id="${esc(c.id)}" data-op="add">${esc(c.tr)}</span>`).join("")}</div>`).join("")}`;
  el.parentElement.appendChild(pop);
  setTimeout(() => document.addEventListener("click", function off(e) { if (!pop.contains(e.target) && e.target !== el) { pop.remove(); document.removeEventListener("click", off); } }), 0);
};
const SERIES_STYLES = { cartoon: "Çizgi film", storybook: "Masal kitabı", anime: "Anime", flat_vector: "Düz vektör", cinematic: "Dizi / sinematik", comic: "Çizgi roman", pixel: "8-bit piksel", papercut: "Kâğıt kesik", claymation: "Kil animasyon", bauhaus: "Bauhaus", vaporwave: "Vaporwave", inkwash: "Mürekkep" };
function defaultSteps(p) {
  return {
    footage: ["Seçili model çekimlerinden fikirleri yazar", "Sen bir fikri onaylarsın", "Art director kurguyu ve efektleri tasarlar", "Ses (varsa): kredi tahmini + onay", "Önizleme → final render + QA"],
    topic: ["Seçili model konuyu araştırır, kaynaklı metni yazar", p.look === "illustrated" ? "Çizimler: kredi tahmini + onay" : "Sahneler tasarlanır", "Ses: kredi tahmini + onay", "Önizleme → final render + QA"],
    series_new: ["Seçili model seri kitabını yazar: dünya, karakterler, bölümler", "Kitabı okursun, düzeltir ya da onaylarsın", "Karakter sayfaları: kredi tahmini + onay", "Her bölüm ayrı üretim olur (çizim + ses onaylı)"],
    series_episode: ["Seçili model bölümü kitaptan uyarlar", "Çizimler: kredi tahmini + onay", "Karakter sesleri: kredi tahmini + onay", "Önizleme → final render"],
    talk: ["Videon transkript edilir; boşluk, ıı, tekrar ve yarım kalan cümleler bulunur", "Seçili model kurguyu çıkarır: hook, sıra, punch-in, B-roll, altyazı renkleri", "Kurgu planını onaylarsın (tutulan / kesilen cümleler)", "Önizleme → final render (ses temizliği, müzik, -14 LUFS) + QA"],
  }[p.kind] || [];
}
let planTimer = null;
async function planUpdate(changes) {
  const box = $("[data-plan]"); if (!box) return;
  const id = box.dataset.plan;
  const r = await post(`/api/plan/${id}/update`, { changes });
  S.sig = null; $("#planBox").innerHTML = planHtml(r);
}
ACT.planSet = (el) => planUpdate({ [el.dataset.name]: el.dataset.name === "n" ? Number(el.dataset.v) : el.dataset.v });
ACT.planSel = (el) => { clearTimeout(planTimer); planTimer = setTimeout(() => planUpdate({ [el.dataset.name]: el.value }), 150); };
ACT.planSeries = (el) => planUpdate({ series: { [el.dataset.name]: el.type === "number" ? Number(el.value) : el.value } });
ACT.planAlt = async (el) => { const id = $("[data-plan]").dataset.plan; const row = await api("/api/plan/" + id); const alt = row.plan.alternatives[Number(el.dataset.i)]; if (alt) await planUpdate(alt.changes || {}); };
ACT.planStart = async () => {
  const id = $("[data-plan]").dataset.plan;
  const brief = $("[data-plan] textarea"); if (brief) await post(`/api/plan/${id}/update`, { changes: { brief: brief.value } });
  const r = await post(`/api/plan/${id}/start`);
  S.comp.prompt = ""; store.set("composer", ""); S.comp.att = {};
  toast("Başladı · " + (r.plan.kind_tr || "")); S.sig = null;
  if (r.plan.kind === "series_new") location.hash = "#/s/" + r.plan.series.id; else route();
};
ACT.planCancel = async () => { const id = $("[data-plan]").dataset.plan; await post(`/api/plan/${id}/cancel`); S.comp.plan = null; S.sig = null; route(); };
ACT.planDismiss = () => { if (S.comp.plan) store.set("dismissedPlans", [...store.get("dismissedPlans", []), S.comp.plan].slice(-50)); S.comp.plan = null; $("#planBox").innerHTML = ""; S.sig = null; };
ACT.segPick = (el) => { const seg = el.parentElement; $$("button", seg).forEach((b) => b.classList.toggle("on", b === el)); };

// ================= Üretim panosu (kanban) =================
function boardHtml(ps) {
  const lanes = STAGES.filter((s) => s[0] !== "rejected").map(([k, l]) => {
    const items = ps.filter((p) => p.stage === k);
    return `<div class="lane st-${k}"><div class="lh"><i class="dot" style="background:var(--c)"></i>${l}<span class="n">${items.length}</span></div><div class="ls">${items.map(pcard).join("") || '<div class="tiny faint" style="padding:8px">—</div>'}</div></div>`;
  }).join("");
  const rej = ps.filter((p) => p.stage === "rejected");
  return `<div class="board">${lanes}</div>${rej.length ? `<details class="mt16"><summary class="muted small">Reddedilenler (${rej.length})</summary><div class="grid mt12" style="grid-template-columns:repeat(auto-fill,minmax(220px,1fr))">${rej.map(pcard).join("")}</div></details>` : ""}`;
}
ROUTES["#/hat"] = async () => {
  const f = q("ch") || store.get("boardFilter", "");
  const ps = await api("/api/productions" + (f ? "?channel=" + encodeURIComponent(f) : ""));
  crumb(["Üretim panosu"]);
  const html = `<div class="row"><div><h1>Üretim panosu</h1><p class="lead">Her video aynı hattan geçer: fikir → ses (kredi onayı) → önizleme → final + QA → yayın.</p></div><span class="sp"></span><button class="btn accent" data-act="newPrompt">${ICON.plus}Yeni üretim</button></div>
    <div class="chips mt16"><span class="chip ${!f ? "on" : ""}" data-act="boardFilter" data-v="">Hepsi · ${ps.length && !f ? ps.length : ""}</span>${S.channels.map((c) => `<span class="chip ${f === c.id ? "on" : ""}" data-act="boardFilter" data-v="${esc(c.id)}"><i class="dot" style="background:${esc(c.color)}"></i>${esc(c.name)}</span>`).join("")}</div>
    <div class="mt16">${boardHtml(ps)}</div>`;
  paint(html, JSON.stringify(ps.map((p) => [p.prod_id, p.updated_at, p.busy])) + f);
  return { poll: ps.some((p) => p.busy) ? 5000 : 30000 };
};
ACT.boardFilter = (el) => { store.set("boardFilter", el.dataset.v); S.sig = null; route(); };

// ================= Kanal =================
async function viewChannel(id) {
  setChannel(id);
  const c = await api("/api/channels/" + encodeURIComponent(id));
  renderShell();
  const tab = q("tab") || "pano";
  crumb(["Kanallar", c.name]);
  const o = c.overview, t = c.tracking;
  const handles = Object.entries(c.handles || {}).map(([k, v]) => `<span class="badge solid">${plat(k)} ${esc(v)}</span>`).join("");
  const tabs = [["pano", "Pano"], ["seriler", "Seriler"], ["takip", "Takip"], ["kesif", "Keşif"], ["ayarlar", "Marka & ayarlar"]];
  let body = "";
  if (tab === "pano") body = boardHtml(o.recent.length ? await api("/api/productions?channel=" + encodeURIComponent(id)) : []);
  else if (tab === "seriler") body = seriesGrid(c.series, id);
  else if (tab === "takip") body = trackingHtml(t);
  else if (tab === "kesif") body = await discoverHtml(id);
  else body = channelSettings(c);
  const html = `<div class="chhero" style="--ch:${esc(c.color)}">
      <div class="row nowrap" style="gap:18px;align-items:center"><div class="lg">${chAvatar(c)}</div>
        <div style="min-width:0;flex:1"><div class="tiny faint" style="font-weight:700;text-transform:uppercase;letter-spacing:.08em">${esc(modeTr(c.mode))} kanal · ${(c.lang || "en").toUpperCase()}</div>
          <h1 style="margin-top:2px">${esc(c.name)}</h1><div class="small muted" style="margin-top:4px;max-width:720px">${esc(c.description || "Açıklama yok: Marka & ayarlar sekmesinden kanalın neyi anlattığını yaz; fikir üretimi buna göre yapılır.")}</div>
          <div class="row mt8">${handles}</div></div>
        <button class="btn accent" data-act="newPrompt">${ICON.plus}Üret</button></div>
      <div class="kpis mt16">
        <div class="kpi"><div class="l">Senden bekleyen</div><div class="v">${o.pending.length}</div></div>
        <div class="kpi"><div class="l">Üretimde</div><div class="v">${(o.counts.idea || 0) + (o.counts.voice || 0) + (o.counts.preview || 0)}</div></div>
        <div class="kpi"><div class="l">Hazır / yayında</div><div class="v">${(o.counts.ready || 0)} / ${(o.counts.published || 0)}</div></div>
        <div class="kpi"><div class="l">Toplam izlenme</div><div class="v">${num(t.views)}</div></div>
      </div></div>
    <div class="tabs">${tabs.map(([k, l]) => `<a class="${k === tab ? "on" : ""}" href="#/c/${esc(id)}?tab=${k}">${l}</a>`).join("")}</div>
    <div id="chbody">${body}</div>`;
  paint(html, tab === "ayarlar" ? JSON.stringify([c.updated_at, c.logo_url, tab]) : JSON.stringify([o.recent.map((p) => [p.prod_id, p.updated_at, p.busy]), t.views, tab, c.series.map((s) => [s.series_id, s.status, s.made])]));
  if (tab === "ayarlar") wireSettings(c);
  return { poll: tab === "ayarlar" ? 0 : o.busy ? 5000 : 30000 };
}
function trackingHtml(t) {
  return `<div class="kpis"><div class="kpi"><div class="l">Paylaşım</div><div class="v">${t.posts}</div></div><div class="kpi"><div class="l">İzlenme</div><div class="v">${num(t.views)}</div></div><div class="kpi"><div class="l">En iyi video</div><div class="v">${num(t.best)}</div></div></div>
  ${t.rows.length ? `<div class="card pad0 mt16" style="overflow-x:auto"><table><thead><tr><th>Video</th><th>Platform</th><th class="num">İzlenme</th><th>Trend</th></tr></thead><tbody>${t.rows.map((x) => `<tr><td><b>${esc(x.prod_title || x.title || "—")}</b><div class="tiny faint"><a href="${esc(x.url)}" target="_blank" rel="noopener">link</a> · ${dt(x.posted_at)}</div></td><td>${plat(x.platform)}</td><td class="num">${num(x.views)}</td><td>${spark(x.history)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty mt16">Bu kanalda takip edilen paylaşım yok. Hazır bir videonun sayfasından linkini ekle.</div>`}
  <div class="mt12"><a class="btn sm" href="#/takip">Tüm takip →</a></div>`;
}
function phoneHtml(c, aspect) {
  const wide = aspect === "16:9";
  const w = c.watermark, size = Math.round(w.size * 100);
  const box = { tl: "left:5.5%;top:10.5%", tr: "right:16%;top:10.5%", bl: "left:5.5%;bottom:20%", br: "right:16%;bottom:20%" };
  const boxW = { tl: "left:3%;top:5%", tr: "right:3%;top:5%", bl: "left:3%;bottom:7%", br: "right:3%;bottom:7%" };
  const pos = (wide ? boxW : box)[w.corner];
  const logo = c.logo_url ? `<img class="wm" src="${esc(c.logo_url)}" style="${pos};width:${size}%;opacity:${w.on ? w.opacity : 0.12}" alt="">` : `<div class="wm" style="${pos};width:${size}%;aspect-ratio:1;background:${esc(c.color)};opacity:${w.on ? w.opacity : 0.15};display:grid;place-items:center;font-weight:900;color:#111;font-size:11px">${esc(initials(c.name))}</div>`;
  const zones = wide ? "" : `<div class="zone" style="left:0;right:0;top:0;height:9%"></div><div class="zone" style="right:0;top:42%;bottom:20%;width:14%"></div><div class="zone" style="left:0;right:0;bottom:0;height:19%"></div>
    <div class="ui" style="top:3.5%;left:0;right:0;text-align:center">Takip · Sana özel</div><div class="ui" style="right:4%;top:48%;line-height:2.1;text-align:center">♥<br>💬<br>↗</div><div class="ui" style="left:5%;bottom:9%">@${esc(String((c.handles || {}).tiktok || "kanal").replace(/^@/, ""))}</div>`;
  const hots = ["tl", "tr", "bl", "br"].map((k) => { const p = (wide ? boxW : box)[k]; return `<div class="hot" style="${p}" data-act="wmCorner" data-v="${k}">${CORNER_TR[k]}</div>`; }).join("");
  return `<div class="phone ${wide ? "wide" : ""}">${zones}${hots}${logo}</div>`;
}
function channelSettings(c) {
  const looks = [...LOOKS, ...S.styles.filter((s) => s.status === "approved").map((s) => ["custom:" + s.id, "🎨 " + s.id, ""])];
  const cats = { ai: "Yapay zekâ", tech: "Teknoloji", science: "Bilim", finance: "Finans", world: "Dünya", papers: "Makaleler" };
  return `<div class="split"><div class="col" style="gap:16px">
    <div class="card"><h3>Kimlik</h3><div class="grid" style="grid-template-columns:1fr 1fr">
      <label class="field"><span>Kanal adı</span><input type="text" id="c_name" value="${esc(c.name)}"></label>
      <label class="field"><span>Renk</span><div class="row nowrap"><input type="color" id="c_color" value="${esc(c.color)}" style="width:52px;height:42px;padding:3px;border-radius:10px;background:var(--bg2);border:1px solid var(--line)"><input type="text" value="${esc(c.color)}" disabled></div></label>
      <label class="field"><span>Tür</span><select id="c_mode">${[["footage", "Çekimli (kendi çekimlerin)"], ["topic", "Çekimsiz (konu anlatımı)"], ["mixed", "Karışık"]].map(([k, t]) => `<option value="${k}" ${c.mode === k ? "selected" : ""}>${t}</option>`).join("")}</select></label>
      <label class="field"><span>Ekran dili</span><select id="c_lang"><option value="en" ${c.lang === "en" ? "selected" : ""}>English</option><option value="tr" ${c.lang === "tr" ? "selected" : ""}>Türkçe</option></select></label></div>
      <label class="field mt12"><span>Kanal ne anlatıyor? (fikir ve senaryo üretimine gider)</span><textarea id="c_desc" placeholder="ör. Alplerde kendi çektiğim sakin seyahat videoları; gerçek yerler, gerçek saatler…">${esc(c.description || "")}</textarea></label>
      <label class="field mt12"><span>Kitle</span><input type="text" id="c_aud" value="${esc(c.audience || "")}"></label>
      <div class="grid mt12" style="grid-template-columns:repeat(3,1fr)">${["tiktok", "youtube", "instagram"].map((k) => `<label class="field"><span>${plat(k)}</span><input type="text" id="h_${k}" value="${esc((c.handles || {})[k] || "")}" placeholder="@hesap"></label>`).join("")}</div>
    </div>
    <div class="card"><h3>Varsayılanlar</h3><div class="row" style="gap:18px;align-items:flex-start">
      <div class="field"><span>Kadraj</span>${seg("d_aspect", [["9:16", "▯ 9:16"], ["16:9", "▭ 16:9"]], c.defaults.aspect)}</div>
      <div class="field"><span>Anlatım (çekimli)</span>${seg("d_narrate", [["auto", "Claude"], ["on", "Var"], ["off", "Yok"]], c.defaults.narrate)}</div></div>
      <div class="field mt12"><span>Görünüm (çekimsiz)</span><div class="chips" id="d_look">${looks.map(([k, t]) => `<span class="chip ${c.defaults.look === k ? "on" : ""}" data-act="chipOne" data-v="${esc(k)}">${esc(t)}</span>`).join("")}</div></div>
      <div class="field mt12"><span>Keşif kategorileri (bu kanalın Keşif sekmesinde görünür)</span><div class="chips" id="d_disc">${Object.entries(cats).map(([k, t]) => `<span class="chip ${(c.discover || []).includes(k) ? "on" : ""}" data-act="chipMany" data-v="${k}">${t}</span>`).join("")}</div></div>
    </div>
    <div class="row"><button class="btn accent" data-act="chSave" data-id="${esc(c.id)}">${ICON.check}Kaydet</button><span class="sp"></span><button class="btn danger ghost sm" data-act="chDelete" data-id="${esc(c.id)}">${ICON.trash}Kanalı sil</button></div>
  </div>
  <div class="col sticky" style="gap:16px">
    <div class="card"><h3>Logo</h3>
      <div class="row nowrap" style="gap:14px"><div class="chav" style="width:64px;height:64px;border-radius:18px;flex:none">${chAvatar(c)}</div>
        <label class="drop" style="flex:1" id="logoDrop">${c.logo_url ? "Değiştirmek için bırak ya da tıkla" : "PNG (şeffaf) / JPG / WEBP bırak ya da tıkla"}<input type="file" accept="image/*" id="logoFile" style="display:none"></label></div>
      ${c.logo_url ? `<button class="btn sm ghost mt8" data-act="logoDel" data-id="${esc(c.id)}">Logoyu kaldır</button>` : ""}</div>
    <div class="card"><div class="row"><h3 style="margin:0">Videolarda logo</h3><span class="sp"></span><label class="switch"><input type="checkbox" id="wm_on" ${c.watermark.on ? "checked" : ""}><i></i></label></div>
      <div class="tiny muted mt8">Köşeye dokun: kırmızı alanlar TikTok / Shorts arayüzünün kapladığı yerler. Logo her render'da (önizleme dahil) eklenir.</div>
      <div class="row mt12" style="justify-content:center;gap:16px" id="phones">${phoneHtml(c, "9:16")}</div>
      <div class="grid mt12" style="grid-template-columns:1fr 1fr"><label class="field"><span>Boyut</span><input type="range" min="4" max="25" value="${Math.round(c.watermark.size * 100)}" id="wm_size"></label>
        <label class="field"><span>Opaklık</span><input type="range" min="20" max="100" value="${Math.round(c.watermark.opacity * 100)}" id="wm_op"></label></div></div>
    <div class="card"><div class="row"><h3 style="margin:0">Bitiş kartı</h3><span class="sp"></span><label class="switch"><input type="checkbox" id="oc_on" ${c.outro.on ? "checked" : ""}><i></i></label></div>
      <div class="tiny muted mt8">Videonun son karesi bulanıklaşır, ortada logo ve kanal adı belirir.</div>
      <div class="grid mt12" style="grid-template-columns:1fr 110px"><label class="field"><span>Yazı</span><input type="text" id="oc_text" value="${esc(c.outro.text || "")}" placeholder="${esc(c.name)}"></label>
        <label class="field"><span>Süre (sn)</span><input type="number" id="oc_sec" min="1" max="4" step="0.1" value="${c.outro.seconds}"></label></div></div>
  </div></div>`;
}
function wireSettings(c) {
  const st = { corner: c.watermark.corner };
  const redraw = () => { const cc = { ...c, watermark: { on: $("#wm_on").checked, corner: st.corner, size: $("#wm_size").value / 100, opacity: $("#wm_op").value / 100 } }; $("#phones").innerHTML = phoneHtml(cc, "9:16"); };
  ACT.wmCorner = (el) => { st.corner = el.dataset.v; redraw(); };
  ["#wm_on", "#wm_size", "#wm_op"].forEach((s) => $(s).addEventListener("input", redraw));
  $("#c_color").addEventListener("input", (e) => { e.target.nextElementSibling.value = e.target.value; document.documentElement.style.setProperty("--ch", e.target.value); });
  const drop = $("#logoDrop"), file = $("#logoFile");
  const send = async (f) => { if (!f) return; drop.textContent = "Yükleniyor…"; await upload(`/api/channels/${encodeURIComponent(c.id)}/logo`, f, {}); await reloadChannels(); toast("Logo kaydedildi"); S.sig = null; route(); };
  drop.addEventListener("click", () => file.click());
  file.addEventListener("change", () => send(file.files[0]).catch((e) => toast(e.message, 1)));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); send(e.dataTransfer.files[0]).catch((x) => toast(x.message, 1)); });
  ACT.chSave = async () => {
    const segv = (n) => ($(`.seg [data-name="${n}"].on`) || {}).dataset;
    const body = { name: $("#c_name").value, color: $("#c_color").value, mode: $("#c_mode").value, lang: $("#c_lang").value,
      description: $("#c_desc").value, audience: $("#c_aud").value,
      handles: Object.fromEntries(["tiktok", "youtube", "instagram"].map((k) => [k, $("#h_" + k).value])),
      watermark: { on: $("#wm_on").checked, corner: st.corner, size: $("#wm_size").value / 100, opacity: $("#wm_op").value / 100 },
      outro: { on: $("#oc_on").checked, text: $("#oc_text").value, seconds: Number($("#oc_sec").value) },
      defaults: { aspect: (segv("d_aspect") || {}).v, narrate: (segv("d_narrate") || {}).v, look: ($("#d_look .chip.on") || {}).dataset?.v },
      discover: $$("#d_disc .chip.on").map((x) => x.dataset.v) };
    await post(`/api/channels/${encodeURIComponent(c.id)}/update`, body);
    await reloadChannels(); toast("Kanal kaydedildi"); S.sig = null; route();
  };
}
ACT.chipOne = (el) => { $$(".chip", el.parentElement).forEach((x) => x.classList.toggle("on", x === el)); };
ACT.chipMany = (el) => el.classList.toggle("on");
ACT.logoDel = async (el) => { await post(`/api/channels/${encodeURIComponent(el.dataset.id)}/logo_delete`); await reloadChannels(); S.sig = null; route(); };
ACT.chDelete = async (el) => {
  const others = S.channels.filter((c) => c.id !== el.dataset.id);
  if (!others.length) return toast("Son kanal silinemez", 1);
  if (!confirm(`Bu kanal silinsin mi? Videoları ve paylaşımları “${others[0].name}” kanalına taşınır.`)) return;
  await post(`/api/channels/${encodeURIComponent(el.dataset.id)}/delete`, { move_to: others[0].id });
  await reloadChannels(); setChannel(others[0].id); location.hash = "#/c/" + others[0].id;
};
ROUTES["#/kanal-yeni"] = async () => {
  crumb(["Kanallar", "Yeni kanal"]);
  paint(`<div style="max-width:640px"><h1>Yeni <span class="serif">kanal</span></h1><p class="lead">Her kanal kendi dilini, nişini, logosunu ve varsayılanlarını taşır. Videolar, seriler ve takip kanal içinde toplanır.</p>
    <div class="card mt16 col" style="gap:12px"><label class="field"><span>Kanal adı</span><input type="text" id="n_name" placeholder="ör. Psikoloji Notları"></label>
      <div class="field"><span>Tür</span>${seg("n_mode", [["footage", "🎞 Çekimli"], ["topic", "✍️ Çekimsiz"], ["mixed", "Karışık"]], "topic")}</div>
      <div class="field"><span>Dil</span>${seg("n_lang", [["en", "English"], ["tr", "Türkçe"]], "en")}</div>
      <label class="field"><span>Kanal ne anlatıyor?</span><textarea id="n_desc" placeholder="Fikir üretimi bu açıklamaya göre yapılır"></textarea></label>
      <label class="field"><span>Renk</span><input type="color" id="n_color" value="#a78bfa" style="width:60px;height:42px;padding:3px;border-radius:10px"></label>
      <button class="btn accent" data-act="chCreate">${ICON.plus}Kanalı oluştur</button></div></div>`);
};
ACT.chCreate = async () => {
  const v = (n) => ($(`.seg [data-name="${n}"].on`) || {}).dataset.v;
  const c = await post("/api/channels", { name: $("#n_name").value, mode: v("n_mode"), lang: v("n_lang"), description: $("#n_desc").value, color: $("#n_color").value });
  await reloadChannels(); setChannel(c.id); location.hash = `#/c/${c.id}?tab=ayarlar`;
};
async function reloadChannels() { S.channels = await api("/api/channels"); if (!chan(S.ch) && S.channels[0]) setChannel(S.channels[0].id); renderShell(); }

// ================= Üretim detayı =================
async function viewProd(id) {
  const p = await api("/api/production/" + id);
  const d = p.data, f = p.format_info, tl = p.timeline || {};
  const c = p.channel || cur();
  if (c && c.id !== S.ch) { setChannel(c.id); renderShell(); }
  crumb([c ? c.name : "Kanal", p.title]);
  const order = f.voice ? ["idea", "voice", "preview", "ready", "published"] : ["idea", "preview", "ready", "published"];
  const ci = order.indexOf(p.stage);
  const isEx = d.kind === "explainer", wide = d.aspect === "16:9";
  const html = `
  <div class="row"><a class="btn ghost sm" href="${c ? "#/c/" + esc(c.id) : "#/hat"}">${ICON.back}${esc(c ? c.name : "Pano")}</a><span class="sp"></span>
    ${stageBadge(p.stage)}<span class="badge">${esc(f.name_tr)}</span>${d.series ? `<a class="badge" href="#/s/${esc(d.series.id)}">📚 ${esc(d.series.title || "seri")} · bölüm ${esc(d.series.episode)}</a>` : ""}</div>
  <div class="ptitle"><div style="flex:1;min-width:0"><h1>${esc(p.title)}</h1>${d.hook ? `<div class="lead">“${esc(d.hook)}”</div>` : ""}</div></div>
  <div class="stepper st-${p.stage}">${order.map((s, i) => `<div class="${i < ci ? "done" : i === ci ? "cur" : ""}"><i></i>${SL[s]}</div>`).join("")}</div>
  <div class="split">
    <div class="col" style="gap:14px">
      ${p.busy ? `<div class="note warn"><div class="row"><span class="spin" style="color:var(--accent)"></span><b>${esc(JOBTR[p.busy.kind] || p.busy.kind)} sürüyor…</b></div>${p.busy.tail ? `<pre class="log">${esc(p.busy.tail)}</pre>` : ""}</div>` : ""}
      ${controlsCard(p)}
      <div class="card"><div class="kv"><div>Hook</div><div><b>${esc(d.hook || "")}</b></div><div>Ne anlatıyor</div><div>${esc(d.logline || "")}</div>
        <div>Neden tutabilir</div><div class="muted">${esc(d.why || "")} <span class="faint tiny">(hipotez)</span></div>
        ${d.content_fit != null ? `<div>Çekim uyumu</div><div>${esc(d.content_fit)}/10 <span class="muted small">${esc(d.fit_reason || "")}</span></div>` : ""}</div></div>
      ${recipeCard(p)}${talkCard(p)}
      ${p.data.kind === "talk" ? "" : storyboard(p)}
      ${platesCard(p)}${motionCard(p)}${directionCard(p)}${soundCard(p)}
      ${!isEx && d.kind !== "talk" ? refsCard(p) : ""}${musicCard(p)}
      ${voiceEdit(p)}${d.kind === "talk" ? "" : textEdit(p)}${postEdit(p)}
      ${factsCard(p)}${claimsCard(p)}
    </div>
    <div class="col sticky" style="gap:14px">
      ${actionCard(p, wide)}
      <div class="card"><h3>Geçmiş</h3><div class="hist">${p.history.slice().reverse().map((h) => `<div><time>${dt(h.at)}</time><span><b>${esc(h.event)}</b> ${esc(h.detail || "")}</span></div>`).join("")}</div></div>
      <div class="card flat"><button class="btn danger sm" data-act="delProd" data-id="${id}">${ICON.trash}Kalıcı olarak sil</button><div class="tiny faint mt8">Fikri/videoyu ve dosyalarını diskten kaldırır.</div></div>
    </div>
  </div>`;
  paint(html, JSON.stringify([p.updated_at, p.busy && p.busy.tail, p.stage]));
  return { poll: p.busy ? 4000 : 0 };
}
function controlsCard(p) {
  const d = p.data, done = ["ready", "published", "rejected"].includes(p.stage), isEx = d.kind === "explainer";
  const looks = [...LOOKS, ...S.styles.filter((s) => s.status === "approved").map((s) => ["custom:" + s.id, "🎨 " + s.id, ""])];
  const lookNow = d.look_pack === "html" ? (d.illustrated ? "illustrated" : "auto") : d.look_pack || "tech";
  return `<div class="card"><div class="row" style="gap:18px;align-items:flex-start">
    ${p.stage !== "rejected" ? `<div class="field"><span>Kadraj ${["ready", "published"].includes(p.stage) ? "(diğerini seçersen kopya açılır)" : ""}</span>${seg("aspect", [["9:16", "▯ 9:16"], ["16:9", "▭ 16:9"]], d.aspect || "9:16", "setAspect")}</div>` : ""}
    <label class="field" style="min-width:170px"><span>Kanal</span><select data-change="setChannelOf" data-id="${p.prod_id}">${S.channels.map((c) => `<option value="${esc(c.id)}" ${c.id === (p.channel || {}).id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
    ${(p.channel || {}).logo_url ? `<div class="field"><span>Logo katmanı</span><label class="switch"><input type="checkbox" data-change="setBrand" data-id="${p.prod_id}" ${p.brand_on ? "checked" : ""}><i></i></label></div>` : ""}
  </div>
  ${isEx && !done && ["auto", "illustrated"].includes(lookNow) ? `<div class="field mt12"><span>Anlatım grameri (Opus bu dille tasarlar)</span><div class="chips">${GRAMMARS.map(([k, t]) => `<span class="chip ${(d.grammar || "auto") === k ? "on" : ""}" data-act="setGrammar" data-id="${p.prod_id}" data-v="${k}">${t}</span>`).join("")}</div></div>` : ""}
  ${isEx && !done && !d.series ? `<div class="field mt12"><span>Görünüm</span><div class="chips">${looks.map(([k, t]) => `<span class="chip ${lookNow === k ? "on" : ""}" data-act="setLook" data-id="${p.prod_id}" data-v="${esc(k)}">${esc(t)}</span>`).join("")}</div></div>` : ""}
  </div>`;
}
function storyboard(p) {
  const d = p.data, tl = p.timeline || {};
  const isEx = d.kind === "explainer", total = tl.total || 1, spec = tl.spec || {}, starts = tl.starts || [];
  let segs, shots;
  if (isEx) {
    const sc = spec.scenes || [];
    segs = sc.map((s) => `<div class="seg" style="left:${(s.start / total) * 100}%;width:${((s.end - s.start) / total) * 100}%"></div>`).join("");
    shots = sc.map((s, i) => {
      const src = d.scenes[i] || {}, bg = src.bg, sb = s.bg;
      const plate = (p.plates || {})[s.id];
      if (d.motion) {   // Opus-designed HTML scenes: show the rendered frame and the spoken lines, not the script-stage plan
        const mid = (s.start + s.end) / 2, [a, b] = src.lines || s.lines || [0, -1];
        const said = ((d.voice || {}).lines || []).slice(a, b + 1);
        const frame = p.preview || p.output ? `<img loading="lazy" src="/thumb/prod/${p.prod_id}?t=${mid.toFixed(1)}&v=${encodeURIComponent(p.updated_at)}" data-act="open" data-src="/thumb/prod/${p.prod_id}?t=${mid.toFixed(1)}&v=${encodeURIComponent(p.updated_at)}" data-photo="1" alt="">`
          : `<div class="ph" style="display:grid;place-items:center;padding:10px;text-align:center"><span class="faint">önizlemeden sonra</span></div>`;
        return `<div class="shot ${d.aspect === "16:9" ? "wide" : ""}" style="${d.aspect === "16:9" ? "" : "width:150px"}">${frame}<div class="m"><b>${i + 1}</b> · ${esc(s.id)} · ${sec(s.end - s.start)} <span class="faint">@${s.start.toFixed(1)}s</span></div>
          ${said.map((l) => `<div class="m">“${esc(l)}”</div>`).join("")}</div>`;
      }
      const pic = plate ? `<img loading="lazy" src="${esc(plate)}" data-act="open" data-src="${esc(plate)}" data-photo="1" alt="">`
        : sb ? (sb.type === "clip" ? `<img loading="lazy" src="/thumb/clip/${encodeURIComponent((bg || {}).clip_id || "")}?t=${(sb.in || 0) + 0.5}" alt="">` : `<img loading="lazy" src="/media/stock/${encodeURIComponent(String(sb.file).split("/").pop())}" alt="">`)
        : `<div class="ph" style="display:grid;place-items:center;padding:10px;text-align:center" class="tiny">${src.plate ? "🖌 " + esc(src.plate.prompt.slice(0, 90)) : '<span class="faint">düz arka plan</span>'}</div>`;
      return `<div class="shot ${d.aspect === "16:9" ? "wide" : ""}" style="${d.aspect === "16:9" ? "" : "width:150px"}">${pic}<div class="m"><b>${i + 1}</b> · ${esc(s.id)} · ${sec(s.end - s.start)}</div>
        ${src.plate ? `<div class="m">🎥 ${esc(src.plate.camera)}${src.plate.same_place_as ? " · ↳ " + esc(src.plate.same_place_as) : ""}${(src.plate.cast || []).length ? " · 👤 " + esc(src.plate.cast.join(", ")) : ""}</div>` : ""}
        ${bg && bg.type === "image" ? `<div class="m">📷 ${esc((bg.author || "?").slice(0, 26))} · ${esc(bg.license || "")}</div>` : ""}
        ${(s.elements || []).map((e) => `<div class="m">${esc(e.type)}${e.text || e.big || e.question ? ": " + esc(String(e.text || e.big || e.question).replace(/\n/g, " ").slice(0, 40)) : ""} <span class="faint">@${typeof e.at === "number" ? e.at.toFixed(1) : esc(e.at)}s</span></div>`).join("")}</div>`;
    }).join("");
  } else {
    const ss = spec.shots || [];
    segs = ss.map((s, i) => { const st = starts[i] || 0, en = i + 1 < starts.length ? starts[i + 1] : total; return `<div class="seg" style="left:${(st / total) * 100}%;width:${((en - st) / total) * 100}%"></div>`; }).join("");
    shots = (d.shots || []).map((s, i) => { const sp = ss[i] || {}; const dur = sp.video ? (sp.out - sp.in) / (sp.speed || 1) : sp.dur;
      return `<div class="shot"><img loading="lazy" src="/thumb/clip/${encodeURIComponent(s.clip_id)}?t=${s.in != null ? s.in + 0.5 : 0}" alt=""><div class="m"><b>${i + 1}</b> · ${sec(dur)}${sp.speed && sp.speed < 1 ? " · yavaş" : ""}${s.enter && s.enter !== "cut" ? " · " + esc(s.enter) : ""}${s.audio ? " · J/L" : ""}<br>${esc(s.clip_id)}</div>${s.text ? `<div class="tx">“${esc(s.text)}”</div>` : ""}${s.shows ? `<div class="m">${esc(s.shows)}</div>` : ""}</div>`; }).join("");
  }
  const txts = (spec.text || []).map((t) => `<div class="txt" title="${esc(t.text)}" style="left:${(t.start / total) * 100}%;width:${Math.max(0.5, ((t.end - t.start) / total) * 100)}%"></div>`).join("");
  return `<div class="card"><div class="row"><h3 style="margin:0">Storyboard</h3><span class="sp"></span><span class="small muted">${isEx ? (spec.scenes || []).length + " sahne" : (spec.shots || []).length + " çekim"} · ${sec(tl.total)}</span></div>
    <div class="tl">${segs}${txts}</div><div class="tiny faint">${isEx ? (d.motion ? "sahneler · videodan kareler ve söylenen cümleler" : "sahneler") : "üst: çekimler · alt: ekrandaki yazılar"}</div>
    <div class="strip mt12">${shots}</div>
    ${(tl.warn || []).length ? `<div class="note warn mt12">${tl.warn.map((w) => "⚠ " + esc(w)).join("<br>")}</div>` : ""}
    ${tl.error ? `<div class="note err mt12">${esc(tl.error)}</div>` : ""}</div>`;
}
function platesCard(p) {
  const e = p.plates_estimate; if (!e) return "";
  const d = p.data, ready = Object.keys(p.plates || {}).length;
  if (!e.images) return `<div class="card"><div class="row"><h3 style="margin:0">🖌 Çizimler</h3><span class="sp"></span><span class="badge ok">${ready} çizim hazır</span></div>
    <div class="thumbs mt12">${Object.entries(p.plates || {}).map(([sid, u]) => `<div style="flex:none;position:relative"><img src="${esc(u)}" data-act="open" data-src="${esc(u)}" data-photo="1" alt="">${["ready", "published"].includes(p.stage) || p.busy ? "" : `<button class="btn sm glass" style="position:absolute;right:6px;bottom:6px" data-act="rerollPlate" data-id="${p.prod_id}" data-scene="${esc(sid)}" title="Bu çizimi yeniden üret">↻ ${esc(sid)}</button>`}</div>`).join("")}</div>
    ${d.art_style ? `<div class="tiny faint mt8">Stil: ${esc(d.art_style.slice(0, 220))}</div>` : ""}</div>`;
  return `<div class="card actcard" style="--c:var(--warn)"><h3>🖌 Çizimler · kredi onayı</h3>
    <div class="small muted">Her sahne kilitli stilde bir illüstrasyon üzerinde durur${d.series ? "; karakterler seri sayfasındaki karakter sayfalarından çizilir" : ""}. Çizimler bitince Opus kamera hareketlerini ve işaretleri tasarlar.</div>
    ${d.art_style ? `<div class="note info mt8 small">🎨 ${esc(d.art_style)}</div>` : ""}
    <div class="kv mt12"><div>Görsel</div><div>${e.images} adet (${ready} hazır)</div><div>Tahmin</div><div><b>~${num(e.credits)} kredi</b></div><div>Bu ay</div><div>${num(e.budget.spent)} → ${num(e.budget.after)} / ${num(e.budget.cap)}</div></div>
    ${e.budget.ok ? "" : `<div class="note err mt8">${esc(e.budget.why || "Aylık tavan aşılır")}</div>`}
    <button class="btn accent block mt12" ${p.busy || !e.budget.ok ? "disabled" : ""} data-act="approvePlates" data-id="${p.prod_id}" data-credits="${e.credits}">🖌 Çizimleri üret (~${num(e.credits)} kredi)</button></div>`;
}
function motionCard(p) {
  const m = p.data.motion; if (!m) return "";
  return `<div class="card"><h3>🎬 Opus'un tasarladığı hareket</h3><div class="small">${esc(m.concept)}</div>
    <div class="tiny faint mt8">Her sahne HTML/GSAP ile yazıldı · ${(m.log || []).length} kontrol turu · ~${usd(m.cost_usd)}${(m.errors || []).length ? " · uyarı: " + esc(m.errors[0]) : ""}</div>
    ${(m.lint || []).length ? `<div class="note warn mt8 tiny">${m.lint.map((x) => "📐 " + esc(x)).join("<br>")}</div>` : `<div class="tiny faint mt8">📐 Yerleşim + okunabilirlik + hareket kontrolü temiz</div>`}
    ${m.energy && m.energy.still_share != null ? `<div class="tiny ${(m.gates || []).length ? "note warn" : "faint"} mt8">⚡ Taslak render ölçümü: kareların %${Math.round(100 * m.energy.still_share)}'i duruyor · en uzun duraklama ${m.energy.longest_hold_s} sn · 10 sn'de ${m.energy.cuts_per_10s} kesme${(m.gates || []).length ? "<br>" + m.gates.map((g) => "⛔ " + esc(g)).join("<br>") : " · kapılar geçti"}</div>` : ""}
    ${(m.sheets || []).length ? `<div class="thumbs mt12">${m.sheets.map((x) => `<img src="/media/art/${esc(x)}?v=${encodeURIComponent(p.updated_at)}" data-act="open" data-src="/media/art/${esc(x)}" data-photo="1" style="height:220px" alt="">`).join("")}</div>`
      : `<div class="thumbs mt12">${(m.shots || []).map((x) => `<img src="/media/art/${esc(x)}?v=${encodeURIComponent(p.updated_at)}" data-act="open" data-src="/media/art/${esc(x)}" data-photo="1" style="height:220px" alt="">`).join("")}</div>`}
    <div class="tiny mt8">${(m.refs || []).map((r) => `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title || r.url)}</a> <span class="faint">(${esc(r.takeaway || "")})</span>`).join(" · ")}</div>
    ${!["ready", "published", "rejected"].includes(p.stage) ? `<button class="btn sm mt12" data-act="redesign" data-id="${p.prod_id}">${ICON.wand}Yeniden tasarla</button>` : ""}</div>`;
}
function recipeCard(p) {
  const r = p.recipe || {}; if (!r.direction && !(r.techniques || []).length) return "";
  const by = {}; for (const t of r.techniques || []) (by[t.area_tr] = by[t.area_tr] || []).push(t);
  return `<div class="card"><h3>🎨 Tarif (art direction + teknikler)</h3>${r.direction ? `<div class="small">${esc(r.direction)}</div>` : ""}
    ${Object.entries(by).map(([a, ts]) => `<div class="tiny faint mt8">${esc(a)}</div><div class="chips">${ts.map((t) => `<span class="chip on" title="${esc(t.id)}">${esc(t.tr)}</span>`).join("")}</div>`).join("")}
    ${r.seconds ? `<div class="tiny faint mt8">hedef süre ${esc(r.seconds.join ? r.seconds.join("-") : r.seconds)} sn</div>` : ""}</div>`;
}
function talkCard(p) {
  const t = p.talk; if (!t) return "";
  if (t.error) return `<div class="card"><h3>🎙 Kurgu planı</h3><div class="note err">${esc(t.error)}</div></div>`;
  const flag = { retake: "tekrar çekim", false_start: "yarım cümle", filler_only: "sadece ıı" };
  return `<div class="card"><h3>🎙 Kurgu planı</h3>
    <div class="small">Ham ${sec(t.raw_s)} → tutulan ~${sec(t.kept_s)} · ${t.faces ? "yüz takibi var" : "yüz takibi yok (ortalı kadraj)"} · vurgu rengi <span class="swatch" style="background:${esc(t.accent || "#ffd93d")}"></span> ${t.fallback ? `<span class="badge">yedek kurgu (${esc(t.fallback)})</span>` : ""}</div>
    ${t.hook ? `<div class="mt8"><b>Hook:</b> “${esc(t.hook)}”${(t.hook_options || []).length ? ` <span class="tiny muted">diğerleri: ${t.hook_options.map((h) => "“" + esc(h) + "”").join(" · ")}</span>` : ""}</div>` : ""}
    <div class="talk mt12" style="max-height:340px;overflow:auto">${t.phrases.map((ph) => `<div class="row" style="gap:8px;align-items:flex-start;opacity:${ph.kept ? 1 : 0.45}">
      <span class="tiny faint" style="width:70px;flex:none">${ph.t[0].toFixed(1)}–${ph.t[1].toFixed(1)}s</span>
      <span class="badge" style="flex:none">${ph.kept ? "#" + ph.pos : "kesildi"}</span>
      <span class="small" style="${ph.kept ? "" : "text-decoration:line-through"}">${esc(ph.text)}${ph.flags.length ? ` <span class="tiny" style="color:var(--warn)">(${ph.flags.map((f) => flag[f] || f).join(", ")})</span>` : ""}${ph.fillers ? ` <span class="tiny faint">${ph.fillers} ıı</span>` : ""}</span></div>`).join("")}</div>
    ${(t.broll || []).length ? `<div class="mt12"><b class="small">Kodla B-roll</b>${t.broll.map((b) => `<div class="tiny">▣ ${esc(b.kind)} · “${esc(b.text)}”${b.label ? " · " + esc(b.label) : ""} <span class="faint">(cümle #${b.id})</span></div>`).join("")}</div>` : ""}
    <div class="tiny muted mt8">${(t.punch || []).length} punch-in · renk ${esc(t.grade || "")} · anahtar kelimeler: ${esc(((t.keywords || {}).key || []).join(", "))}</div>
    <div class="tiny faint mt8">Değiştirmek için “değişiklik iste” kutusuna yaz (örn. “şu cümleyi at”, “hook'u 2. seçenek yap”).</div></div>`;
}
function soundCard(p) {
  const s = (p.qa || {}).sound; if (!s) return "";
  const f = s.findings || [], m = s.metrics || {};
  return `<div class="card"><h3>👂 Ses kontrolü (miks ölçüldü, dinlenmedi)</h3>
    <div class="tiny muted">${m.lufs != null ? `${m.lufs} LUFS · ${m.true_peak} dBTP · ` : ""}${m.effects != null ? `${m.effects} efekt · ` : ""}${m.loudest_at != null ? `en yüksek an ${m.loudest_at} sn (%${Math.round((m.loudest_share || 0) * 100)})` : ""}</div>
    ${f.length ? `<div class="note warn mt8 small">${f.map((x) => `${x.severity === "fail" ? "⛔" : x.severity === "warn" ? "⚠" : "ℹ"} ${esc(x.detail)}`).join("<br>")}</div>` : `<div class="note ok mt8 small">Bulgu yok</div>`}
    ${p.sound_sheet ? `<img class="mt12" src="${esc(p.sound_sheet)}?v=${encodeURIComponent(p.updated_at)}" data-act="open" data-src="${esc(p.sound_sheet)}" data-photo="1" style="width:100%;border-radius:10px" alt="">` : ""}</div>`;
}
function directionCard(p) {
  const x = p.data.direction; if (!x) return "";
  const BT = { hook: "Hook", arc: "Akış", look: "Görünüm", type: "Tipografi", rhythm: "Ritim", sound: "Ses" };
  return `<div class="card"><h3>🎨 Art direction</h3><div class="small">${esc(x.concept || "")}</div>
    ${Object.entries(x.brief || {}).map(([k, v]) => `<div class="tiny mt8"><b>${esc(BT[k] || k)}:</b> ${esc(v)}</div>`).join("")}
    ${(x.signature || []).length ? `<div class="tiny mt12"><b>İmza hareketler</b>${x.signature.map((s) => `<div>• ${esc(s.move)} <span class="faint">(${esc(s.where || "")})</span> — ${esc(s.why || "")}</div>`).join("")}</div>` : ""}
    ${(x.seen || []).length ? `<div class="tiny faint mt12">Araştırırken baktığı sayfalar</div><div class="thumbs mt8">${x.seen.map((f) => `<img src="/media/research/${esc(f)}" data-act="open" data-src="/media/research/${esc(f)}" data-photo="1" style="height:140px" alt="">`).join("")}</div>` : ""}
    ${(x.frames || []).length ? `<div class="tiny faint mt12">Kendi kontrolü (${x.review && x.review.ok ? "onayladı" : "düzeltti: " + esc((x.review?.problems || []).join("; "))})</div><div class="thumbs mt8">${x.frames.map((f) => `<img src="/media/artstills/${esc(f)}" data-act="open" data-src="/media/artstills/${esc(f)}" data-photo="1" style="height:140px" alt="">`).join("")}</div>` : ""}
    ${(x.learned || []).length ? `<div class="tiny mt8">📚 Kütüphaneye eklediği beceriler: ${x.learned.map(esc).join(", ")}</div>` : ""}
    <div class="row mt12"><span class="tiny faint">${esc(x.at || "")} · ~${usd(x.cost_usd)}</span><span class="sp"></span>${!["ready", "published", "rejected"].includes(p.stage) ? `<button class="btn sm" data-act="redirect" data-id="${p.prod_id}">${ICON.wand}Yeniden yönet</button>` : ""}</div></div>`;
}
function refsCard(p) {
  const look = p.data.look;
  return `<div class="card"><div class="row"><h3 style="margin:0">Stil referansları</h3><span class="sp"></span><a class="btn sm" href="#/referanslar?pick=${p.prod_id}">${p.refs.length ? "Değiştir" : "Referans ekle"}</a></div>
    ${p.refs.length ? `<div class="thumbs mt12">${p.refs.map((r) => `<img src="/thumb/ref?id=${encodeURIComponent(r.ref_id)}" data-act="open" data-src="/media/ref?id=${encodeURIComponent(r.ref_id)}" data-photo="${r.kind === "photo" ? 1 : 0}" style="height:130px" alt="">`).join("")}</div>` : `<div class="small muted mt8">Referans yok: art director kendi araştırmasıyla yönetir.</div>`}
    ${look ? `<div class="row mt8">${[look.frame, "renk: " + look.grade, "grain " + look.grain, Math.round(look.bpm) + " BPM"].map((t) => `<span class="badge">${esc(t)}</span>`).join("")}</div>` : ""}</div>`;
}
function musicCard(p) {
  if (["ready", "published", "rejected"].includes(p.stage) && !p.data.music_take) return "";
  const m = p.data.music_take, e = p.music_estimate || {}, id = p.prod_id;
  if (m) return `<div class="card"><div class="row"><h3 style="margin:0">🎵 Müzik</h3><span class="sp"></span><span class="badge ok">${Math.round(m.bpm)} BPM · ${num(m.credits)} kredi</span></div>
    <audio controls preload="none" src="/media/${esc(m.file)}" style="width:100%;margin-top:10px"></audio><div class="tiny faint">${esc(m.prompt)}</div>
    ${p.busy ? "" : `<button class="btn sm ghost mt8" data-act="act" data-id="${id}" data-a="drop_music">Müziği kaldır</button>`}</div>`;
  if (e.error) return "";
  return `<div class="card"><h3>🎵 Müzik</h3><div class="small muted">${p.data.look ? `Kesmeler ${Math.round(p.data.look.bpm)} BPM ızgarasında. Videoya özel enstrümantal üretirsen kesmeler gerçek beat'lere oturur.` : "Klibin kendi sesi var; istersen videoya özel enstrümantal bir parça üret, doğal ses altta kalır."}</div>
    <textarea id="mprompt" data-keep="mprompt-${id}" class="mt8">${esc(e.prompt || "")}</textarea>
    <div class="kv small mt8"><div>Süre</div><div>${e.seconds} sn</div><div>Tahmin</div><div><b>~${num(e.credits)} kredi</b></div><div>Bu ay</div><div>${num(e.budget?.spent)} → ${num(e.budget?.after)} / ${num(e.budget?.cap)}</div></div>
    <button class="btn block mt12" ${p.busy || !e.budget?.ok ? "disabled" : ""} data-act="approveMusic" data-id="${id}" data-credits="${e.credits}">🎵 Müzik üret (~${num(e.credits)} kredi)</button></div>`;
}
function voiceEdit(p) {
  const d = p.data, f = p.format_info; if (!f.voice) return "";
  const ready = d.voice_take && d.voice_take.text === (d.voice?.lines || []).join(" ");
  const sp = (d.voice || {}).speakers || [];
  const names = Object.fromEntries(((p.series_info || {}).characters || []).map((c) => [c.id, c.name]));
  return `<div class="card"><div class="row"><h3 style="margin:0">Ses metni ${sp.length ? "(konuşan + satır)" : "(altyazı = bu satırlar)"}</h3><span class="sp"></span>${ready ? '<span class="badge ok">ses hazır</span>' : '<span class="badge">ses yok</span>'}</div>
    <div class="lines mt12" id="vlines">${(d.voice?.lines || []).map((l, i) => `<div class="row nowrap">${sp.length ? `<span class="badge" style="min-width:86px;justify-content:center">${esc(sp[i] === "narrator" ? "anlatıcı" : names[sp[i]] || sp[i])}</span>` : ""}<input type="text" data-keep="vl-${p.prod_id}-${i}" value="${esc(l)}"></div>`).join("")}${sp.length ? "" : `<input type="text" data-keep="vl-${p.prod_id}-new" placeholder="+ yeni satır">`}</div>
    ${d.voice_take && d.voice_take.file ? `<audio controls preload="none" src="/media/${esc(d.voice_take.file)}" style="width:100%;margin-top:10px"></audio>` : ""}</div>`;
}
function textEdit(p) {
  const d = p.data, f = p.format_info; if (f.voice || d.kind === "explainer") return "";
  return `<div class="card"><h3>Ekran yazıları (çekim başına)</h3><div class="lines" id="stexts">${(d.shots || []).map((s, i) => `<div class="row nowrap"><span class="faint small" style="width:22px">${i + 1}</span><input type="text" data-keep="st-${p.prod_id}-${i}" value="${esc(s.text || "")}" placeholder="${i === 0 ? "hook (" + esc(d.hook || "") + ")" : "(yazı yok)"}"></div>`).join("")}</div></div>`;
}
function postEdit(p) {
  const d = p.data, f = p.format_info, po = d.post || {}, id = p.prod_id;
  return `<div class="card"><h3>Paylaşım metni</h3><div class="lines">
    <input type="text" id="e_title" data-keep="e_title-${id}" value="${esc(p.title)}" placeholder="Başlık">
    <input type="text" id="e_hook" data-keep="e_hook-${id}" value="${esc(d.hook || "")}" placeholder="Hook">
    ${d.end_card != null || f.voice ? `<input type="text" id="e_end" data-keep="e_end-${id}" value="${esc(d.end_card || "")}" placeholder="Son konum satırı">` : ""}
    <textarea id="e_caption" data-keep="e_caption-${id}" placeholder="Açıklama">${esc(po.caption || "")}</textarea>
    <input type="text" id="e_tags" data-keep="e_tags-${id}" value="${esc(po.hashtags || "")}" placeholder="#etiketler">
    <input type="text" id="e_loc" data-keep="e_loc-${id}" value="${esc(po.location || "")}" placeholder="Konum">
    <input type="text" id="e_music" data-keep="e_music-${id}" value="${esc(po.music || "")}" placeholder="Müzik önerisi"></div>
    <div class="row mt12"><button class="btn" ${p.busy ? "disabled" : ""} data-act="saveEdits" data-id="${id}" data-voice="${f.voice ? 1 : 0}">💾 Kaydet</button>
      <button class="btn ghost sm" data-act="copy" data-text="${esc((po.caption || "") + "\n\n" + (po.hashtags || ""))}">${ICON.copy}Kopyala</button>
      <span class="tiny faint">Ses metni değişirse ses adımı ve kredi onayı tekrar gelir.</span></div></div>`;
}
function factsCard(p) {
  const d = p.data; if (d.kind !== "explainer" || d.series) return "";
  return `<div class="card"><h3>Araştırma · kaynaklar</h3>${(d.facts || []).map((x) => `<div class="small mt8">• ${esc(x.claim)} ${x.source ? `<a class="tiny" href="${esc(x.source)}" target="_blank" rel="noopener">${esc(x.source.replace(/^https?:\/\//, "").slice(0, 42))}</a>` : '<span class="bad">kaynak yok</span>'}${x.note ? `<div class="tiny faint">${esc(x.note)}</div>` : ""}</div>`).join("") || '<div class="muted small">kaynak yok</div>'}
    ${(d.credits || []).length ? `<h3 class="mt16">Görsel kaynakları (açık lisans)</h3>${d.credits.map((c) => `<div class="small mt8">📷 ${esc(String(c.title).slice(0, 46))} · ${esc(c.author || "?")} · ${esc(c.license)} <a class="tiny" href="${esc(c.url)}" target="_blank" rel="noopener">kaynak</a></div>`).join("")}` : ""}
    <div class="tiny faint mt8">Konu: ${esc(d.topic || "")}</div></div>`;
}
function claimsCard(p) {
  const d = p.data; if (!(d.claims || []).length) return "";
  const V = { supported: "✅", partly: "🟡", unsupported: "⚠️", false: "❌" };
  return `<div class="card"><div class="row"><h3 style="margin:0">Doğrulanacak iddialar</h3><span class="sp"></span>${p.busy ? "" : `<button class="btn sm" data-act="act" data-id="${p.prod_id}" data-a="verify">🔎 Doğrula</button>`}</div>
    ${d.claims.map((c) => `<div class="small mt8">• ${esc(c.claim)}</div>`).join("")}
    ${p.verification ? `<div class="mt12">${(p.verification.verdicts || []).map((v) => `<div class="small mt8">${V[v.verdict] || "•"} ${esc(v.claim)} <span class="muted">— ${esc(v.note || "")}</span>${v.safer_wording ? `<div class="tiny faint">Daha güvenli: ${esc(v.safer_wording)}</div>` : ""}${(v.sources || []).slice(0, 2).map((s) => ` <a class="tiny" href="${esc(s.url)}" target="_blank" rel="noopener">${esc((s.title || "kaynak").slice(0, 40))}</a>`).join("")}</div>`).join("")}</div>` : ""}</div>`;
}
// explainers: the video's language (script, on-screen text, voice); switching rewrites the script, no credits
function langPick(p) {
  const d = p.data;
  if (d.kind !== "explainer" || !["idea", "voice"].includes(p.stage)) return "";
  const cur = d.lang || "en";
  return `<div class="field mt12"><span>Dil</span><div class="chips">${[["tr", "Türkçe"], ["en", "İngilizce"]].map(([k, t]) => `<span class="chip ${cur === k ? "on" : ""}" data-act="setLang" data-id="${p.prod_id}" data-v="${k}">${t}</span>`).join("")}</div><div class="tiny faint">Değiştirirsen metin o dilde yeniden yazılır ve ses o dilin sesine geçer (kredi harcanmaz).</div></div>`;
}
function actionCard(p, wide) {
  const d = p.data, f = p.format_info, est = p.estimate, id = p.prod_id;
  let a = "";
  if (p.busy) a = `<div class="card"><h3>Çalışıyor</h3><div class="small muted">${esc(JOBTR[p.busy.kind] || p.busy.kind)} bitince burada sıradaki adım çıkar.</div></div>`;
  else if (p.stage === "idea") a = `<div class="card actcard st-idea"><h3>Karar</h3><div class="small muted">${f.voice ? "Onaylarsan ses metni ve kredi tahmini gelir." : "Onaylarsan önizleme render'ı otomatik başlar."}</div>
    <div class="kv small mt12"><div>🎙 Anlatım</div><div>${f.voice ? `${(d.voice?.lines || []).length} satır · ~${num(est?.credits || 0)} kredi` : "yok (doğal ses)"}</div><div>🎵 Müzik</div><div>${d.music?.prompt ? "tarif hazır · ~" + num(p.music_estimate?.credits || 0) + " kredi" : "tarif yok"}</div>${p.plates_estimate ? `<div>🖌 Çizimler</div><div>${p.plates_estimate.images} görsel · ~${num(p.plates_estimate.credits)} kredi</div>` : ""}</div>
    ${langPick(p)}<button class="btn accent block mt12" data-act="act" data-id="${id}" data-a="approve_idea">${ICON.check}Fikri onayla</button>${reviseBox(p)}${rejectBox(p)}</div>`;
  else if (p.stage === "voice") a = `<div class="card actcard st-voice"><h3>Ses · kredi onayı</h3>
    <div class="kv mt8"><div>Metin</div><div>${est.chars} karakter</div><div>Tahmin</div><div><b>~${num(est.credits)} kredi</b></div><div>Bu ay</div><div>${num(est.budget.spent)} → ${num(est.budget.after)} / ${num(est.budget.cap)}</div></div>
    ${est.budget.ok ? "" : `<div class="note err mt8">${esc(est.budget.why || "Aylık tavan aşılır")}</div>`}
    ${langPick(p)}
    ${(p.eleven_accounts || []).length > 1 ? `<label class="field mt12"><span>Kredi bu hesaptan düşer</span><select data-change="setEleven" data-id="${id}">${p.eleven_accounts.map((x) => `<option value="${esc(x.id)}" ${x.id === p.eleven_account ? "selected" : ""}>💳 ${esc(x.name)}${x.mine ? "" : " (paylaşılan)"}</option>`).join("")}</select></label>` : ""}
    ${d.cast_voices && Object.keys(d.cast_voices).length > 1 ? `<div class="tiny muted mt12">🎭 Karakter sesleri seri sayfasından: ${Object.keys(d.cast_voices).map(esc).join(", ")}</div>` : `<label class="field mt12"><span>Ses</span><select data-change="setVoice" data-id="${id}">${(p.voices || []).map((v) => `<option value="${esc(v.voice_id)}" ${(d.voice_id || p.default_voice || (p.voices[0] || {}).voice_id) === v.voice_id ? "selected" : ""}>🎙 ${esc(v.name)}${v.language ? " · " + esc(v.language) : ""}</option>`).join("")}</select></label>`}
    ${p.plates_estimate && p.plates_estimate.images ? `<div class="note warn mt12 small">Önce çizimler: soldaki Çizimler kartından onayla.</div>` : ""}
    <button class="btn accent block mt12" ${est.budget.ok ? "" : "disabled"} data-act="approveVoice" data-id="${id}" data-credits="${est.credits}">🎙 Sesi üret (~${num(est.credits)} kredi)</button>
    <div class="tiny faint mt8">Ses bitince önizleme otomatik hazırlanır.</div>${reviseBox(p)}${rejectBox(p)}</div>`;
  else if (p.stage === "preview") a = `<div class="card actcard st-preview"><h3>Önizleme</h3>${p.preview ? `<div class="player ${wide ? "wide" : ""}"><video src="/media/${esc(p.preview)}?v=${encodeURIComponent(p.updated_at)}" controls playsinline preload="metadata"></video></div>
    <div class="tiny faint mt8">Hızlı taslak (düşük kalite): kurguyu ve yazıları değerlendir.</div>
    ${!p.claims_ok ? `<div class="note warn mt12">Doğrulanmamış iddialar var. <button class="btn sm" data-act="act" data-id="${id}" data-a="verify">Doğrula</button><label class="chk mt8"><input type="checkbox" id="force"> yine de render et</label></div>` : ""}
    ${p.render_eta ? `<div class="tiny muted mt12">⏱ Final render bu makinede ${esc(p.render_eta.final)} sürer${p.render_eta.blur > 1 ? ` (hareket bulanıklığı ×${p.render_eta.blur})` : ""}${p.render_eta.measured ? "" : " · kaba tahmin"}</div>` : ""}
    <button class="btn accent block mt12" data-act="approveRender" data-id="${id}">${ICON.check}Onayla, final render</button>`
    : `${p.plates_estimate && p.plates_estimate.images ? `<div class="note warn small">Önce çizimler gerekiyor.</div>` : ""}<button class="btn block mt8" data-act="act" data-id="${id}" data-a="preview">${ICON.play}Önizleme oluştur</button>`}${reviseBox(p)}${rejectBox(p)}</div>`;
  else if (p.stage === "ready" || p.stage === "published") { const vid = p.output ? `/media/out/${p.output}/${p.output}.mp4` : "";
    a = `<div class="card actcard st-${p.stage}"><h3>${p.stage === "ready" ? "Hazır" : "Yayında"}</h3>${vid ? `<div class="player ${wide ? "wide" : ""}"><video src="${esc(vid)}" controls playsinline preload="metadata"></video></div>
      <div class="row mt12"><a class="btn sm" href="${esc(vid)}?dl=1">${ICON.download}İndir</a>${p.caption_copy ? `<button class="btn sm" data-act="copy" data-text="${esc(p.caption_copy)}">${ICON.copy}Açıklama + etiketler</button>` : ""}</div>` : ""}
      ${(p.thumbs || []).length ? `<h3 class="mt16">Kapak adayları</h3><div class="grid mt8" style="grid-template-columns:repeat(3,1fr);gap:6px">${p.thumbs.map((f) => `<a href="/media/out/${esc(p.output)}/${esc(f)}?dl=1" title="indir"><img src="/media/out/${esc(p.output)}/${esc(f)}?v=${encodeURIComponent(p.updated_at)}" style="width:100%;border-radius:10px;aspect-ratio:${wide ? "16/9" : "9/16"};object-fit:cover" alt=""></a>`).join("")}</div><div class="tiny faint mt8">Videodan seçilen en net kareler, kanal renginle. Dokun: indir.</div>` : ""}
      ${qaBox(p.qa)}
      <h3 class="mt16">Paylaştın mı? Linki ekle</h3><div class="row nowrap"><input id="purl" type="url" placeholder="YouTube / TikTok / Instagram linki"><button class="btn sm accent" data-act="publish" data-id="${id}">Ekle</button></div>
      ${p.posts.length ? `<div class="mt12 small">${p.posts.map((x) => `<div class="row mt8"><b>${plat(x.platform)}</b><a class="muted tiny" href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.url.slice(0, 44))}…</a><span class="sp"></span>${x.latest ? num(x.latest.views) + " izlenme" : "—"}</div>`).join("")}</div>` : ""}
      ${p.stage === "ready" ? `<details class="mt12"><summary class="muted small">Yine de değişiklik iste</summary>${reviseBox(p)}</details>` : ""}</div>`; }
  else if (p.stage === "rejected") a = `<div class="card"><h3>Reddedildi</h3><button class="btn" data-act="act" data-id="${id}" data-a="restore">↩ Geri al</button></div>`;
  return a;
}
function qaBox(qa) {
  if (!qa) return ""; const t = qa.technical || {}, v = qa.visual || {};
  return `<div class="note ${qa.pass ? "ok" : "warn"} mt12"><b>${qa.pass ? "✅ QA geçti" : "🔎 QA bulguları"}</b> · ${sec(t.duration)} · ${t.lufs ?? "—"} LUFS · tepe ${t.true_peak_db ?? "—"} dBFS
    ${(t.problems || []).map((x) => `<div class="bad">• ${esc(x)}</div>`).join("")}
    ${(v.issues || []).map((i) => `<div class="mt8">• <b>${esc(i.severity)}</b> @${esc(i.time)}s ${esc(i.problem)}<div class="tiny faint">öneri: ${esc(i.fix)}</div></div>`).join("")}
    ${v.summary ? `<div class="tiny muted mt8">${esc(v.summary)}</div>` : ""}</div>`;
}
function reviseBox(p) {
  const pl = (p.data || {}).edit_plan, id = p.prod_id;
  const K = { script: "📝 Metin", design: "🎨 Tasarım", voice: "🎙 Ses" };
  if (pl) return `<div class="mt16"><h3>Düzenleme planı</h3><div class="tiny faint">“${esc(pl.feedback)}”</div><div class="small mt8">${esc(pl.summary_tr)}</div>
    ${pl.steps.map((s, i) => `<label class="chk mt8" style="align-items:flex-start"><input type="checkbox" class="pstep" value="${esc(s.id)}" checked><span><b>${i + 1}. ${K[s.id] || esc(s.id)}</b> — ${esc(s.title_tr)}<div class="tiny muted">${esc(s.why_tr)}</div></span></label>`).join("")}
    <button class="btn accent block mt12" data-act="applyPlan" data-id="${id}">${ICON.check}Planı onayla ve uygula</button><button class="btn ghost sm mt8" data-act="act" data-id="${id}" data-a="discard_plan">Planı sil</button></div>`;
  return `<div class="mt16"><h3>Geri bildirim / düzenleme</h3><textarea id="fb" data-keep="fb-${id}" placeholder="ör. 'hook zayıf, ilk sahne çarpıcı olsun', 'sadece tasarım değişsin'"></textarea>
    <button class="btn block mt8" data-act="planEdit" data-id="${id}">🧭 Opus plan çıkarsın</button><div class="tiny faint mt8">Önce hangi katmanların (metin / tasarım / ses) yenileneceği planlanır; onaylamadan hiçbir şey değişmez.</div></div>`;
}
function rejectBox(p) { return `<details class="mt12"><summary class="muted small">Reddet</summary><input id="rr" type="text" placeholder="Neden? (isteğe bağlı)" class="mt8"><label class="chk mt8"><input type="checkbox" id="rl"> Ders olarak kaydet</label><button class="btn danger sm mt8" data-act="reject" data-id="${p.prod_id}">Reddet</button></details>`; }

async function pact(id, action, extra) { const r = await post(`/api/production/${id}/action`, { action, ...(extra || {}) }); S.sig = null; return r; }
ACT.act = async (el) => { await pact(el.dataset.id, el.dataset.a); toast("Tamam"); route(); };
ACT.reject = async (el) => { await pact(el.dataset.id, "reject", { reason: $("#rr").value, lesson: $("#rl").checked }); toast("Reddedildi"); route(); };
ACT.approveVoice = async (el) => { if (!confirm(`ElevenLabs ~${el.dataset.credits} kredi harcanacak. Onaylıyor musun?`)) return; await pact(el.dataset.id, "approve_voice", { approved: Number(el.dataset.credits) }); toast("Ses üretiliyor"); route(); };
ACT.approveMusic = async (el) => { if (!confirm(`ElevenLabs ~${el.dataset.credits} kredi harcanacak. Onaylıyor musun?`)) return; await pact(el.dataset.id, "approve_music", { approved: Number(el.dataset.credits), prompt: $("#mprompt").value }); toast("Müzik üretiliyor"); route(); };
ACT.approvePlates = async (el) => { if (!confirm(`ElevenLabs ~${el.dataset.credits} kredi harcanacak (çizimler). Onaylıyor musun?`)) return; await pact(el.dataset.id, "approve_plates", { approved: Number(el.dataset.credits) }); toast("Çizimler üretiliyor"); route(); };
ACT.approveRender = async (el) => { await pact(el.dataset.id, "approve_render", { force: !!($("#force") || {}).checked }); toast("Final render başladı"); route(); };
ACT.publish = async (el) => { await pact(el.dataset.id, "publish", { url: $("#purl").value }); toast("Paylaşım eklendi"); route(); };
ACT.planEdit = async (el) => { await pact(el.dataset.id, "plan_edit", { feedback: $("#fb").value }); delete S.drafts["fb-" + el.dataset.id]; toast("Opus plan çıkarıyor"); route(); };
ACT.applyPlan = async (el) => { const steps = $$(".pstep:checked").map((i) => i.value); if (!steps.length) return toast("En az bir adım seç", 1); if (steps.includes("script") && !steps.includes("design") && !confirm("Metin değişince sahneler yeniden tasarlanır. Devam?")) return; await pact(el.dataset.id, "apply_plan", { steps }); route(); };
ACT.redesign = async (el) => { const n = prompt("Neyi beğenmedin / ne istiyorsun? (boş = baştan farklı bir tasarım)"); if (n === null) return; await pact(el.dataset.id, "redesign", { note: n }); route(); };
ACT.redirect = async (el) => { const n = prompt("Ne değişsin? (boş = art director baştan farklı bir yön dener)"); if (n === null) return; await pact(el.dataset.id, "direct", { note: n }); route(); };
const GRAMMARS = [["auto", "🤖 Opus seçsin"], ["kurzgesagt", "🪐 Kurzgesagt"], ["vox", "📰 Vox"], ["whiteboard", "✏️ Beyaz tahta"], ["3b1b", "📐 3Blue1Brown"], ["storytime", "📖 Hikâye"], ["kinetic", "🔤 Kinetik yazı"], ["keynote", "🖥 Keynote"], ["finance", "📈 Finans"]];
ACT.rerollPlate = async (el) => {
  const note = prompt(`“${el.dataset.scene}” çizimi yeniden üretilecek (~1 görsel kredisi, ~210 kredi). Ne değişsin? (boş = aynı tarif, yeni çekim)`);
  if (note === null) return;
  await pact(el.dataset.id, "reroll_plate", { scene: el.dataset.scene, note, approved: 260 }); toast("Çizim yeniden üretiliyor"); route();
};
ACT.setGrammar = async (el) => { await pact(el.dataset.id, "set_grammar", { grammar: el.dataset.v }); toast("Gramer: " + el.textContent.trim() + " · yeniden tasarımda kullanılır"); route(); };
ACT.setLook = async (el) => { await pact(el.dataset.id, "set_look", { look: el.dataset.v }); route(); };
ACT.setChannelOf = async (el) => { await pact(el.dataset.id, "set_channel", { channel: el.value }); await reloadChannels(); toast("Kanal değişti"); route(); };
ACT.setBrand = async (el) => { await pact(el.dataset.id, "set_brand", { on: el.checked }); toast(el.checked ? "Logo katmanı açık" : "Logo katmanı kapalı"); route(); };
ACT.setLang = async (el) => { if (el.classList.contains("on")) return; await pact(el.dataset.id, "set_lang", { lang: el.dataset.v }); toast(el.dataset.v === "tr" ? "Türkçeye çevriliyor" : "İngilizceye çevriliyor"); route(); };
ACT.setVoice = async (el) => { await pact(el.dataset.id, "set_voice", { voice_id: el.value }); route(); };
ACT.setEleven = async (el) => { await pact(el.dataset.id, "set_eleven", { account: el.value }); route(); };
ACT.setAspect = async (el) => {
  const id = (location.hash.match(/#\/p\/(\d+)/) || [])[1]; if (!id) return;
  const r = await pact(id, "set_aspect", { aspect: el.dataset.v });
  toast(r.redirect ? "Yeni kopya açıldı, önizleme hazırlanıyor" : "Kadraj değişti");
  if (r.redirect) location.hash = "#/p/" + r.redirect; else route();
};
ACT.saveEdits = async (el) => {
  const id = el.dataset.id;
  const edit = { title: $("#e_title").value, hook: $("#e_hook").value, caption: $("#e_caption").value, hashtags: $("#e_tags").value, location: $("#e_loc").value, music: $("#e_music").value };
  if ($("#e_end")) edit.end_card = $("#e_end").value;
  if (el.dataset.voice === "1") edit.voice_lines = $$("#vlines input").map((i) => i.value);
  else if ($("#stexts")) edit.shot_texts = $$("#stexts input").map((i) => i.value);
  await pact(id, "save", { edit });
  for (const k of Object.keys(S.drafts)) if (k.includes("-" + id)) delete S.drafts[k];
  toast("Kaydedildi"); route();
};
ACT.delProd = async (el) => { if (!confirm("Bu üretim ve tüm dosyaları kalıcı olarak silinsin mi? Geri alınamaz.")) return; const r = await pact(el.dataset.id, "delete"); toast("Silindi · " + r.freed_mb + " MB boşaldı"); location.hash = "#/hat"; };

// ================= Seriler =================
const SER_STATUS = { writing: "kitap yazılıyor", bible: "kitap onayını bekliyor", casting: "karakter sayfaları", ready: "bölüm üretimine hazır", failed: "hata" };
function seriesGrid(list, ch) {
  return `<div class="row"><div class="small muted">Bir seri = bir hikâye dünyası. Önce mini kitap yazılır, sonra aynı karakterlerle bölüm bölüm videolar.</div><span class="sp"></span><button class="btn sm accent" data-act="newSeries">${ICON.plus}Yeni seri</button></div>
  <div class="grid mt16" style="grid-template-columns:repeat(auto-fill,minmax(260px,1fr))">${list.map((s) => `<a class="card hover" href="#/s/${s.series_id}" style="text-decoration:none;padding:0;overflow:hidden">
    <div style="aspect-ratio:16/9;background:linear-gradient(135deg,color-mix(in srgb,var(--ch) 30%,var(--surface3)),var(--surface2));display:grid;place-items:center;font-size:44px;overflow:hidden">${s.cover ? `<img src="/media/assets/${esc(s.cover.split("assets/").pop())}" style="width:100%;height:100%;object-fit:cover" alt="">` : "📚"}</div>
    <div style="padding:14px"><div class="serif" style="font-size:24px;line-height:1.1">${esc(s.title)}</div><div class="small muted mt8" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">${esc(s.logline || "")}</div>
      <div class="row mt12"><span class="badge">${esc(SER_STATUS[s.status] || s.status)}</span><span class="badge">${s.characters} karakter</span><span class="badge">${s.made}/${s.episodes} bölüm</span></div></div></a>`).join("") || `<div class="empty"><div class="big">📚</div>Henüz seri yok. Stüdyo'da “… hakkında bir seri” yazman yeter.</div>`}</div>`;
}
ACT.newSeries = () => { S.comp.prompt = "Şu konuda 6 bölümlük çizgi film serisi: "; store.set("composer", S.comp.prompt); location.hash = "#/"; setTimeout(() => { const t = $("#prompt"); if (t) { t.focus(); t.setSelectionRange(t.value.length, t.value.length); } }, 100); };
ROUTES["#/seriler"] = async () => { const list = await api("/api/series"); crumb(["Seriler"]); paint(`<h1>Seri<span class="serif">ler</span></h1><p class="lead">Karakterler ve çizim dili sabit, hikâye bölüm bölüm ilerler.</p><div class="mt16">${seriesGrid(list)}</div>`, JSON.stringify(list)); return { poll: list.some((s) => s.status === "writing") ? 6000 : 0 }; };
async function viewSeries(id) {
  const s = await api("/api/series/" + id);
  const d = s.data, st = s.status;
  if (s.channel && s.channel.id !== S.ch) { setChannel(s.channel.id); renderShell(); }
  crumb([s.channel ? s.channel.name : "Seriler", s.title]);
  const steps = [["writing", "Kitap"], ["bible", "Onay"], ["casting", "Karakterler"], ["ready", "Bölümler"]];
  const ix = steps.findIndex((x) => x[0] === st);
  const flow = `<div class="flow mt12">${steps.map(([k, t], i) => `<span class="f ${i < ix ? "done" : i === ix ? "cur" : ""}">${i < ix ? "✓ " : ""}${t}</span>${i < steps.length - 1 ? '<span class="ar">→</span>' : ""}`).join("")}</div>`;
  const voices = s.voices || [];
  const vsel = (who, curv) => `<select data-change="serVoice" data-id="${s.series_id}" data-who="${esc(who)}"><option value="">— ses seç —</option>${voices.map((v) => `<option value="${esc(v.voice_id)}" ${v.voice_id === curv ? "selected" : ""}>🎙 ${esc(v.name)}${v.language ? " · " + esc(v.language) : ""}</option>`).join("")}</select>`;
  const e = s.cast_estimate;
  let main = "";
  if (st === "writing") main = `<div class="card mt16"><div class="thinking" style="padding:6px 0"><span class="orb"></span><div><b>Claude seri kitabını yazıyor<span class="typing"></span></b><div class="small muted">Dünya, karakterler, bölüm bölüm hikâye (~3-6 dk).</div></div></div></div>`;
  else if (st === "failed") main = `<div class="note err mt16">Kitap yazılamadı. ${s.busy ? "" : `<button class="btn sm" data-act="serRevise" data-id="${s.series_id}" data-retry="1">Tekrar dene</button>`}</div>`;
  if (d.characters) main += `
    <h2>Karakterler <span class="faint">${d.characters.length}</span></h2>
    <div class="cast">${d.characters.map((c) => `<div class="char"><div class="pic">${s.sheets[c.id] ? `<img src="${esc(s.sheets[c.id])}" data-act="open" data-src="${esc(s.sheets[c.id])}" data-photo="1" alt="">` : "👤"}</div>
      <div class="bd"><div style="font-weight:750">${esc(c.name)} <span class="tiny faint">${esc(c.id)}</span></div><div class="tiny muted">${esc(c.role)}</div><div class="tiny mt8">${esc(c.look)}</div>
      ${st !== "writing" ? `<div class="mt8">${vsel(c.id, c.voice_id)}</div>` : ""}<div class="tiny faint mt8">${esc(c.voice_hint || "")}</div></div></div>`).join("")}</div>
    ${st === "casting" ? `<div class="card mt16 actcard" style="--c:var(--warn)"><div class="row"><div><b>Karakter sayfaları</b><div class="small muted">Her karakter için bir referans çizim: bölümlerde karakterler bundan çizilir, böylece hep aynı kalırlar.</div></div><span class="sp"></span>
      <button class="btn accent" ${s.busy || !e.budget.ok ? "disabled" : ""} data-act="serCast" data-id="${s.series_id}" data-credits="${e.credits}">🎨 ${e.images} sayfa üret (~${num(e.credits)} kredi)</button></div></div>` : ""}
    <div class="card mt16"><div class="row"><b>🎙 Anlatıcı</b><span class="tiny muted">${esc((d.narrator || {}).voice_hint || "")}</span><span class="sp"></span><div style="min-width:220px">${vsel("narrator", (d.narrator || {}).voice_id)}</div></div></div>
    <h2>Bölümler <span class="faint">${(d.episodes || []).length}</span></h2>
    <div class="eps">${(d.episodes || []).map((ep) => { const pm = s.episodes_made[ep.n]; return `<div class="ep"><div class="n">${ep.n}</div><div style="min-width:0"><div style="font-weight:700">${esc(ep.title)}</div><div class="tiny muted">${esc(ep.logline)}${ep.cliffhanger ? ` · <i>${esc(ep.cliffhanger)}</i>` : ""}</div>${pm ? `<div class="row mt8">${stageBadge(pm.stage)}${pm.busy ? `<span class="badge"><span class="spin"></span>${esc(JOBTR[pm.busy.kind] || "")}</span>` : ""}</div>` : ""}</div>
      ${pm ? `<a class="btn sm" href="#/p/${pm.prod_id}">Aç ${ICON.chev}</a>` : `<button class="btn sm ${st === "ready" ? "accent" : ""}" ${st !== "ready" || s.busy ? "disabled" : ""} data-act="serEpisode" data-id="${s.series_id}" data-n="${ep.n}">🎬 Üret</button>`}</div>`; }).join("")}</div>
    <h2>Kitap</h2>
    ${d.world ? `<div class="note info small">${esc(d.world)}</div>` : ""}
    <div class="mt12">${(d.chapters || []).map((c, i) => `<details class="chap" ${i === 0 ? "open" : ""}><summary><span class="num">${c.n}</span><div><div style="font-weight:700;font-size:16px">${esc(c.title)}</div><div class="small muted">${esc(c.summary)}</div></div></summary><div class="book mt12">${esc(c.text).split(/\n+/).map((x) => `<p>${x}</p>`).join("")}</div></details>`).join("")}</div>
    ${d.art_style ? `<h2>Çizim dili</h2><div class="note info small">🎨 ${esc(d.art_style)}</div>` : ""}`;
  const html = `<div class="row"><a class="btn ghost sm" href="${s.channel ? "#/c/" + esc(s.channel.id) + "?tab=seriler" : "#/seriler"}">${ICON.back}Seriler</a></div>
    <div class="chhero mt12"><div class="tiny faint" style="font-weight:700;text-transform:uppercase;letter-spacing:.08em">Seri · ${esc(s.styles[d.style] || d.style)} · ${esc(d.aspect)} · ${(d.lang || "en").toUpperCase()} · ~${esc(d.ep_seconds)} sn/bölüm</div>
      <h1 class="serif" style="font-size:46px;font-weight:400;margin-top:6px">${esc(s.title)}</h1><div class="lead">${esc(d.logline || d.topic)}</div>${flow}
      ${s.busy ? `<div class="row mt12 small"><span class="spin" style="color:var(--accent)"></span>${esc(JOBTR[s.busy.kind] || s.busy.kind)} sürüyor…</div>` : ""}
      ${["bible", "casting", "ready"].includes(st) && !s.busy ? `<div class="row mt16">${st === "bible" ? `<button class="btn accent" data-act="serApprove" data-id="${s.series_id}">${ICON.check}Kitabı onayla</button>` : ""}
        <input type="text" id="serfb" data-keep="serfb-${s.series_id}" placeholder="Kitapta ne değişsin? ör. 'martı daha komik olsun, 2. bölüm daha gerilimli'" style="flex:1;min-width:240px"><button class="btn" data-act="serRevise" data-id="${s.series_id}">✍️ Yeniden yaz</button></div>` : ""}
    </div>${main}`;
  paint(html, JSON.stringify([s.updated_at, s.busy, Object.values(s.episodes_made).map((p) => [p.stage, p.busy])]));
  return { poll: s.busy || st === "writing" || Object.values(s.episodes_made).some((p) => p.busy) ? 5000 : 0 };
}
ACT.serApprove = async (el) => { await post(`/api/series/${el.dataset.id}/approve`); toast("Kitap onaylandı"); S.sig = null; route(); };
ACT.serRevise = async (el) => { const fb = el.dataset.retry ? "Write the bible again from the premise." : $("#serfb").value; await post(`/api/series/${el.dataset.id}/revise`, { feedback: fb }); toast("Kitap yeniden yazılıyor"); S.sig = null; route(); };
ACT.serCast = async (el) => { if (!confirm(`ElevenLabs ~${el.dataset.credits} kredi harcanacak (karakter sayfaları). Onaylıyor musun?`)) return; await post(`/api/series/${el.dataset.id}/cast`, { approved: Number(el.dataset.credits) }); toast("Karakter sayfaları üretiliyor"); S.sig = null; route(); };
ACT.serVoice = async (el) => { await post(`/api/series/${el.dataset.id}/voice`, { who: el.dataset.who, voice_id: el.value || null }); toast("Ses kaydedildi"); };
ACT.serEpisode = async (el) => { await post(`/api/series/${el.dataset.id}/episode`, { n: Number(el.dataset.n) }); toast(`Bölüm ${el.dataset.n} yazılıyor`); S.sig = null; route(); };

// ================= Stiller =================
ROUTES["#/stiller"] = async () => {
  const list = await api("/api/styles"); S.styles = list; crumb(["Stiller"]);
  const sw = (c) => (c ? `<span class="swatch" style="background:rgb(${c.join(",")})"></span>` : "");
  paint(`<div class="row"><div><h1>Stil<span class="serif">ler</span></h1><p class="lead">Beğendiğin bir görselden ya da videodan renk, tipografi, yerleşim ve hareket dili çıkarılır. Önizlemeyi beğenirsen onayla; onaylı stiller her üretimde seçilebilir.</p></div></div>
    <div class="card mt16"><h3>Referanstan yeni stil</h3><div class="row"><label class="drop" style="flex:1;min-width:240px" id="styleDrop">Görsel (PNG/JPG/WEBP) ya da video (MP4/MOV) bırak ya da tıkla<input type="file" id="styleFile" accept="image/*,video/*" style="display:none"></label>
      <input type="text" id="styleNote" placeholder="Ne alınsın? ör. 'sadece renkler ve yazı tipi'" style="flex:1;min-width:220px"></div><div class="tiny faint mt8" id="styleProg">Video referansından kesme hızı ve hareket ölçülür; ~1-2 dk.</div></div>
    <div class="grid mt16" style="grid-template-columns:repeat(auto-fill,minmax(300px,1fr))">${list.map((s) => `<div class="card stylecard"><div class="row"><b>${esc(s.id)}</b><span class="sp"></span><span class="badge ${s.status === "approved" ? "ok" : "warn"}">${s.status === "approved" ? "onaylı" : "taslak"}</span></div>
      <div class="stills mt12">${(s.stills || []).map((x) => `<img src="/media/styles/${esc(x.split("data/styles/").pop())}?v=1" data-act="open" data-src="/media/styles/${esc(x.split("data/styles/").pop())}" data-photo="1" alt="">`).join("") || '<div class="tiny faint">önizleme yok</div>'}</div>
      <div class="row mt12">${sw(s.bg)}${sw(s.text)}${sw(s.accent)}${sw(s.hot)}${sw(s.highlight)}<span class="tiny muted">${esc(s.font ? s.font.replace(/\[.*|\.ttf|-Regular/g, "") : "Inter Tight")}${s.motion ? " · " + esc(s.motion.entrance || "") + " · " + esc(s.motion.pace || "") : ""}${s.measured_motion ? " · " + s.measured_motion.cuts_per_s + " kesme/sn" : ""}</span></div>
      <div class="tiny muted mt8">${esc(s.notes || "")}</div>
      <div class="row mt12">${s.status !== "approved" ? `<button class="btn sm accent" data-act="styleOp" data-op="approve" data-id="${esc(s.id)}">${ICON.check}Onayla</button>` : ""}<button class="btn sm" data-act="styleOp" data-op="stills" data-id="${esc(s.id)}">↻ Önizleme</button><span class="sp"></span><button class="btn sm ghost danger" data-act="styleOp" data-op="delete" data-id="${esc(s.id)}">${ICON.trash}</button></div></div>`).join("") || '<div class="empty">Henüz stil yok</div>'}</div>`, JSON.stringify(list));
  const drop = $("#styleDrop"), file = $("#styleFile");
  const send = async (f) => { if (!f) return; const r = await upload("/api/refs/upload", f, { "X-Style": "1", "X-Style-Note": encodeURIComponent($("#styleNote").value) }, (x) => ($("#styleProg").textContent = "Yükleniyor… %" + Math.round(x * 100))); toast("Stil çıkarılıyor (#" + r.job_id + ")"); $("#styleProg").textContent = "Çıkarılıyor… sayfa ~1 dk sonra yenilenir."; setTimeout(() => { S.sig = null; route(); }, 70000); };
  drop.addEventListener("click", () => file.click()); file.addEventListener("change", () => send(file.files[0]).catch((e) => toast(e.message, 1)));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); }); drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); send(e.dataTransfer.files[0]).catch((x) => toast(x.message, 1)); });
};
ACT.styleOp = async (el) => { if (el.dataset.op === "delete" && !confirm("Bu stil silinsin mi?")) return; S.styles = await post(`/api/styles/${encodeURIComponent(el.dataset.id)}/${el.dataset.op}`); toast("Tamam"); S.sig = null; route(); };

// ================= Keşif =================
async function discoverHtml(ch) {
  const reg = S.dreg || "";
  const d = await api("/api/discover?" + new URLSearchParams({ ...(ch ? { channel: ch } : {}), ...(reg ? { region: reg } : {}) }));
  const CAT = d.categories || {}, REG = d.regions || {};
  const runs = (d.runs || []).filter((r) => !reg || (r.scope || "global").split(":")[0] === reg);
  const runLine = (r) => `${esc(r.scope || "global")} ${dt(r.at)} · ${r.items} haber → ${r.candidates} aday → ${r.cards} kart · ${usd(r.cost_usd)}${r.note ? " · " + esc(r.note) : ""}`;
  const tabs = [["", "Tümü"], ...Object.entries(REG)].map(([k, t]) => `<span class="chip ${reg === k ? "on" : ""}" data-act="discRegion" data-v="${k}">${esc(t)}</span>`).join("");
  return `<div class="row"><div class="chips">${tabs}</div><span class="sp"></span><button class="btn sm" data-act="runDiscover">↻ Şimdi tara${reg ? " · " + esc(REG[reg] || reg) : ""}</button></div>
  <div class="tiny faint mt8">${runs.length ? runs.map(runLine).join("<br>") : "Henüz tarama yok"} · tekrar kontrolü: ${esc(d.embed || "")}</div>
  <div class="grid mt16" style="grid-template-columns:repeat(auto-fill,minmax(320px,1fr))">${d.cards.map((c) => `<div class="card dcard" style="${c.status === "skipped" ? "opacity:.45" : ""}">
    <div class="row" style="gap:6px"><span class="badge ${c.region === "tr" ? "warn" : ""}">${esc(REG[c.region] || c.region || "")}</span><span class="badge solid">${esc(CAT[c.category] || c.category)}</span><span class="badge">skor ${(c.score || 0).toFixed(1)}</span><span class="badge">${(c.signals || {}).source_count || 1} kaynak</span>${(c.signals || {}).trend_term ? `<span class="badge ok">↗ trend: ${esc(c.signals.trend_term)}</span>` : ""}
      ${c.paper ? `<span class="badge ${c.paper.kind === "preprint" ? "warn" : "ok"}">${c.paper.kind === "preprint" ? "preprint · " + esc(c.paper.server || "") : "hakemli · " + esc(c.paper.journal || c.paper.venue || "")}</span>` : ""}
      ${(c.flags || []).filter((f) => f !== "preprint").map((f) => `<span class="badge bad">${esc(f)}</span>`).join("")}</div>
    <div style="font-weight:700;font-size:16px;line-height:1.3" class="mt8">${esc(c.title)}</div>
    <div class="small">“${esc(c.hook)}”</div><div class="tiny muted">${(c.beats || []).map(esc).join(" → ")}</div>
    <div class="tiny muted">🎨 ${esc(c.visual_idea || "")}</div><div class="tiny faint">Neden şimdi: ${esc(c.why_now || "")}</div>
    ${(c.signals || {}).related_to ? `<div class="tiny warn">↺ Benzerini yaptın: ${esc(c.signals.related_to)}</div>` : ""}
    <div class="tiny">${(c.sources || []).map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.source)}</a>`).join(" · ")}${c.paper && c.paper.oa_url ? ` · <a href="${esc(c.paper.oa_url)}" target="_blank" rel="noopener">📄 makale</a>` : ""}</div>
    <div class="row mt8">${c.status === "picked" ? `<span class="badge">seçildi${c.channel_id ? " · " + esc((chan(c.channel_id) || {}).name || "") : ""}</span>` : c.status === "skipped" ? '<span class="tiny faint">geçildi</span>' : `${pickButtons(c, ch)}<button class="btn sm ghost" data-act="skipCard" data-id="${c.card_id}">Geç</button>`}</div></div>`).join("") || '<div class="empty">Kart yok. “Şimdi tara” ile başlat.</div>'}</div>`;
}
ROUTES["#/kesif"] = async () => { crumb(["Keşif"]); const body = await discoverHtml(""); paint(`<h1>Keş<span class="serif">if</span></h1><p class="lead">Global ve Türkiye haber, spor, teknoloji, bilim ve makale akışları her gün konu konu taranır; aynı hikâye ve daha önce yaptıkların elenir, kalanlar puanlanıp fikir kartı olur.</p><div class="mt16">${body}</div>`, body.length + ""); };
ACT.discRegion = async (el) => { S.dreg = el.dataset.v; S.sig = null; route(); };
ACT.runDiscover = async () => { await post("/api/discover/run", S.dreg ? { region: S.dreg } : {}); toast("Tarama başladı (~2 dk)"); setTimeout(() => { S.sig = null; route(); }, 90000); };
// the video language is chosen on the card: the card's own language first (Türkiye cards -> Türkçe)
function pickButtons(c, ch) {
  const first = c.lang || (c.region === "tr" ? "tr" : "en");
  return [first, first === "tr" ? "en" : "tr"].map((l, i) => `<button class="btn sm ${i ? "" : "accent"}" data-act="pickCard" data-id="${c.card_id}" data-ch="${esc(ch || "")}" data-lang="${l}">${l === "tr" ? "Türkçe üret" : "İngilizce üret"}</button>`).join("");
}
ACT.pickCard = async (el) => { const c = el.dataset.ch || S.ch; const r = await post(`/api/discover/card/${el.dataset.id}/pick`, { channel: c, lang: el.dataset.lang }); toast("Araştırma + senaryo başladı (#" + r.job_id + ")"); S.sig = null; route(); };
ACT.skipCard = async (el) => { await post(`/api/discover/card/${el.dataset.id}/skip`); S.sig = null; route(); };

// ================= Takip =================
ROUTES["#/takip"] = async () => {
  const [{ posts, summary }, lib] = await Promise.all([api("/api/posts"), api("/api/library")]); crumb(["Takip"]);
  paint(`<div class="row"><div><h1>Tak<span class="serif">ip</span></h1><p class="lead">YouTube sayıları 6 saatte bir otomatik gelir; TikTok ve Instagram'ı elle gir. Sonuçlar fikir üretimine geri beslenir.</p></div><span class="sp"></span><button class="btn sm" data-act="refreshYT">↻ YouTube'u yenile</button></div>
  <div class="kpis mt16"><div class="kpi"><div class="l">Toplam izlenme</div><div class="v">${num(summary.total_views)}</div></div>${["youtube", "tiktok", "instagram"].map((k) => { const b = summary.by_platform[k]; return `<div class="kpi"><div class="l">${plat(k)}</div><div class="v">${b ? num(b.views) : "—"}</div><div class="tiny faint">${b ? b.posts + " paylaşım · en iyi " + num(b.best) : "henüz yok"}</div></div>`; }).join("")}</div>
  <h2>Paylaşım ekle</h2><div class="card"><div class="grid" style="grid-template-columns:1fr 2fr auto"><select id="pv">${lib.map((v) => `<option value="${esc(v.folder)}">${esc(v.folder)}</option>`).join("")}<option value="">(videosuz)</option></select><input id="pu" type="url" placeholder="YouTube / TikTok / Instagram linki"><button class="btn accent" data-act="addPost">Ekle</button></div></div>
  <h2>Paylaşımlar</h2>${posts.length ? `<div class="card pad0" style="overflow-x:auto"><table><thead><tr><th>Video</th><th>Kanal</th><th>Platform</th><th class="num">İzlenme</th><th class="num">Beğeni</th><th class="num">Yorum</th><th>Trend</th><th></th></tr></thead><tbody>
  ${posts.map((x) => { const l = x.latest || {}; const c = chan(x.channel_id || x.prod_channel); return `<tr><td><b>${esc(x.prod_title || x.title || x.out_name || "—")}</b><div class="tiny faint"><a href="${esc(x.url)}" target="_blank" rel="noopener">link</a> · ${dt(x.posted_at)}</div></td><td>${c ? `<span class="badge"><i class="dot" style="background:${esc(c.color)}"></i>${esc(c.name)}</span>` : ""}</td><td>${plat(x.platform)}</td><td class="num">${num(l.views)}</td><td class="num">${num(l.likes)}</td><td class="num">${num(l.comments)}</td>
    <td>${spark(x.history)}<div class="tiny faint">${l.source ? (l.source === "manual" ? "manuel" : "API") + " · " + ago(l.at) : "veri yok"}</div></td>
    <td><details><summary class="tiny muted">sayı gir</summary><div class="grid" style="gap:4px;margin-top:6px;min-width:150px"><input id="sv${x.post_id}" type="number" placeholder="izlenme"><input id="sl${x.post_id}" type="number" placeholder="beğeni"><input id="sc${x.post_id}" type="number" placeholder="yorum"><input id="ss${x.post_id}" type="number" placeholder="paylaşım"><button class="btn sm" data-act="addStats" data-id="${x.post_id}">Kaydet</button><button class="btn sm ghost danger" data-act="delPost" data-id="${x.post_id}">Sil</button></div></details></td></tr>`; }).join("")}</tbody></table></div>` : `<div class="empty">Henüz paylaşım eklenmedi.</div>`}
  <h2>Formata göre</h2>${Object.keys(summary.by_format).length ? `<div class="card pad0"><table><thead><tr><th>Format</th><th class="num">Paylaşım</th><th class="num">Toplam</th><th class="num">En iyi</th></tr></thead><tbody>${Object.entries(summary.by_format).map(([k, b]) => `<tr><td>${esc(fmtName(k))}</td><td class="num">${b.posts}</td><td class="num">${num(b.views)}</td><td class="num">${num(b.best)}</td></tr>`).join("")}</tbody></table></div>` : '<div class="empty small">Veri geldikçe burada görünür.</div>'}`);
};
ACT.addPost = async () => { await post("/api/posts", { url: $("#pu").value, out_name: $("#pv").value }); toast("Eklendi"); route(); };
ACT.addStats = async (el) => { const id = el.dataset.id; await post(`/api/posts/${id}/stats`, { views: $("#sv" + id).value, likes: $("#sl" + id).value, comments: $("#sc" + id).value, shares: $("#ss" + id).value }); toast("Kaydedildi"); route(); };
ACT.delPost = async (el) => { if (!confirm("Bu paylaşım ve sayıları silinsin mi?")) return; await post(`/api/posts/${el.dataset.id}/delete`); route(); };
ACT.refreshYT = async () => { await post("/api/posts/refresh"); toast("YouTube sayıları çekiliyor…"); setTimeout(route, 5000); };

// ================= Videolar / Referanslar / Yerler =================
ROUTES["#/videolar"] = async () => {
  const lib = await api("/api/library"); crumb(["Videolar"]);
  paint(`<h1>Video<span class="serif">lar</span></h1><p class="lead">Bitmiş videolar (out/). Kanal bilgisi videonun üretim sayfasında.</p>
  ${lib.length ? `<div class="gal mt16">${lib.map((v) => `<div class="it"><img loading="lazy" src="/thumb/out/${encodeURI(v.id)}" data-act="open" data-src="/media/out/${encodeURI(v.id)}" alt="">
    <div class="small mt8" style="font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.folder)}</div><div class="tiny faint">${sec(v.duration)} · ${(v.size / 1e6).toFixed(0)} MB</div>
    <div class="row mt8" style="gap:4px">${v.posts.map((p) => `<a class="badge" href="${esc(p.url)}" target="_blank" rel="noopener">${plat(p.platform)}</a>`).join("")}</div>
    <div class="row mt8" style="gap:6px"><a class="btn sm" href="/media/out/${encodeURI(v.id)}?dl=1">${ICON.download}</a>${v.copy ? `<button class="btn sm" data-act="copy" data-text="${esc(v.copy)}">${ICON.copy}</button>` : ""}${v.prod_id ? `<a class="btn sm" href="#/p/${v.prod_id}">Detay</a>` : ""}<button class="btn sm ghost danger" data-act="delVideo" data-f="${esc(v.folder)}">${ICON.trash}</button></div></div>`).join("")}</div>` : '<div class="empty mt16">Henüz bitmiş video yok</div>'}`);
};
ACT.delVideo = async (el) => { if (!confirm("“" + el.dataset.f + "” diskten silinsin mi?")) return; const r = await post("/api/library/delete", { folder: el.dataset.f }); toast("Silindi · " + r.freed_mb + " MB"); route(); };
// ---------------- technique catalog: every technique with a demo clip; pin into the composer or let Opus choose ----------------
const KIND_TAG = { topic: "konu", talk: "konuşma", footage: "çekim", series: "seri" };
function catCard(t, pins) {
  const on = pins.includes(t.id), bible = t.bible ? Object.entries(t.bible).map(([k, v]) => `<b>${esc(k)}:</b> ${esc(v)}`).join("<br>") : "";
  const media = t.demo ? `<video src="${esc(t.demo)}" muted loop playsinline preload="none" data-auto style="width:100%;aspect-ratio:9/16;object-fit:cover;border-radius:10px;background:#000;display:block" data-act="open" data-src="${esc(t.demo)}"></video>`
    : `<div style="aspect-ratio:9/16;border-radius:10px;background:var(--surface2);display:flex;flex-direction:column;justify-content:center;gap:10px;padding:14px;overflow:hidden" class="tiny muted"><div style="font-size:26px">${t.can_demo ? "🎬" : t.style ? "🎞" : { story: "📖", sound: "🔊", voice: "🎙", captions: "💬", edit: "✂️" }[t.area] || "✨"}</div><div>${t.can_demo ? "Örnek klip henüz üretilmedi." : t.style ? "Film stili: Opus her videoda bu kitaba göre yeniden tasarlar." : ""}</div><div style="display:-webkit-box;-webkit-line-clamp:9;-webkit-box-orient:vertical;overflow:hidden">${esc(t.what)}</div></div>`;
  return `<div class="card catcard" style="padding:10px;${on ? "border-color:var(--ch);box-shadow:0 0 0 2px var(--ch)" : ""}" data-id="${esc(t.id)}">
    ${media}<div class="mt8" style="font-weight:680">${esc(t.tr)}</div>
    <div class="tiny faint">${esc(t.area_tr)}${t.shape ? " · hikâye şekli (videoda tek)" : ""}${t.style ? " · film stili (videoda tek)" : ""} · ${t.kinds.map((k) => KIND_TAG[k] || k).join(", ")}</div>
    ${t.eta ? `<div class="tiny mt8" title="${t.eta.measured ? "Bu makinede ölçülen hıza göre" : "Henüz ölçüm yok: kaba tahmin (örnek klipleri üretince ölçülür)"}">⏱ 30 sn video: önizleme ${esc(t.eta.preview)} · final <b>${esc(t.eta.final)}</b>${t.eta.blur > 1 ? ` <span class="faint">(bulanıklık ×${t.eta.blur})</span>` : ""}${t.eta.weight > 1.15 ? ` <span class="faint">(ağır kare ×${t.eta.weight})</span>` : ""}${t.eta.measured ? "" : ' <span class="faint">· kaba</span>'}</div>` : ""}
    <details class="mt8"><summary class="small muted" style="cursor:pointer">Ne yapar?</summary><div class="small mt8">${esc(t.what)}</div>${bible ? `<div class="tiny muted mt8">${bible}</div>` : ""}</details>
    <button class="btn sm block mt8 ${on ? "accent" : ""}" data-act="pinTech" data-id="${esc(t.id)}">${on ? "📌 Sabitlendi" : "Bunu kullan"}</button></div>`;
}
ROUTES["#/katalog"] = async () => {
  crumb(["Teknik kataloğu"]);
  const { items, missing } = await api("/api/catalog");
  const pins = S.comp.att.pins || [], area = S.catArea || "all", kind = S.catKind || "topic";
  const areas = [...new Map(items.map((t) => [t.area, t.area_tr])).entries()];
  const list = items.filter((t) => (area === "all" || t.area === area) && (kind === "all" || t.kinds.includes(kind)));
  const busy = S.jobs.some((j) => j.kind === "catalog_demos" && (j.status === "running" || j.status === "queued"));
  const html = `<div class="row"><div><h1>Teknik <span class="serif">kataloğu</span></h1><p class="lead">Stüdyonun yapabildiği her şey, kısa örnek kliplerle. İstediklerini <b>Bunu kullan</b> ile sabitle: planlayıcı (Opus) onları mutlaka kullanır. Hiçbirini seçmezsen Opus konuya göre kendisi seçer ve her seçimin nedenini plan kartında yazar.</p></div></div>
    <div class="card mt16 row" style="gap:10px;align-items:center">
      <b id="pinCount">📌 ${pins.length} sabit teknik</b><span class="tiny muted" id="pinNames">${pins.length ? esc(pins.map((id) => (items.find((t) => t.id === id) || {}).tr || id).join(" · ")) : "seçilmedi: Opus seçsin"}</span><span class="sp"></span>
      ${seg("pinMode", [["add", "✨ Opus ekleyebilir"], ["only", "🔒 Sadece bunlar"]], S.comp.att.pin_mode || "add", "pinModeSet")}
      ${pins.length ? `<button class="btn sm ghost" data-act="pinsClear">Temizle</button>` : ""}<a class="btn sm accent" href="#/">Stüdyoya dön ve yaz →</a></div>
    <div class="row mt16" style="gap:8px">${seg("catKind", [["topic", "✍️ Konu"], ["talk", "🎙 Konuşma"], ["footage", "🎞 Çekim"], ["all", "Hepsi"]], kind, "catKind")}
      <span class="sp"></span>${missing ? `<button class="btn sm" data-act="catDemos" ${busy ? "disabled" : ""}>${busy ? '<span class="spin"></span> klipler üretiliyor' : `🎬 ${missing} örnek klibi üret (ücretsiz)`}</button>` : ""}</div>
    <div class="chips mt8"><span class="chip ${area === "all" ? "on" : ""}" data-act="catArea" data-v="all">Hepsi</span>${areas.map(([a, tr]) => `<span class="chip ${area === a ? "on" : ""}" data-act="catArea" data-v="${esc(a)}">${esc(tr)}</span>`).join("")}</div>
    <div class="grid mt16 catgrid" style="grid-template-columns:repeat(auto-fill,minmax(min(190px,44vw),1fr))">${list.map((t) => catCard(t, pins)).join("") || '<div class="empty">Bu filtrede teknik yok</div>'}</div>`;
  if (paint(html, JSON.stringify([items.map((t) => t.demo), pins, area, kind, busy, S.comp.att.pin_mode]))) wireAutoplay();
  return { poll: busy ? 8000 : 0 };
};
// demo clips play only while on screen (muted, looping): a page of videos stays light on a phone
function wireAutoplay() {
  if (!("IntersectionObserver" in window)) return;
  const io = new IntersectionObserver((es) => es.forEach((e) => { const v = e.target; if (e.isIntersecting) { v.preload = "auto"; v.play().catch(() => {}); } else v.pause(); }), { threshold: 0.5 });
  $$("video[data-auto]").forEach((v) => io.observe(v));
}
function savePins() { const a = S.comp.att; store.set("pins", a.pins || []); store.set("pinMode", a.pin_mode || "add"); if (!(a.pins || []).length) { delete a.pins; delete a.pin_mode; } S.sig = null; }
ACT.pinTech = (el) => {
  const a = S.comp.att, id = el.dataset.id; a.pins = a.pins || []; a.pin_mode = a.pin_mode || "add";
  a.pins = a.pins.includes(id) ? a.pins.filter((x) => x !== id) : [...a.pins, id].slice(-12);
  savePins();
  const on = (a.pins || []).includes(id), card = el.closest(".catcard");   // update in place: the clips keep playing
  el.classList.toggle("accent", on); el.textContent = on ? "📌 Sabitlendi" : "Bunu kullan";
  if (card) card.style.cssText = "padding:10px;" + (on ? "border-color:var(--ch);box-shadow:0 0 0 2px var(--ch)" : "");
  toast(on ? "Sabitlendi: planlayıcı bunu kullanacak" : "Çıkarıldı");
  const n = $("#pinCount"), names = $("#pinNames"), cards = $$(".catcard");
  if (n) n.textContent = `📌 ${(a.pins || []).length} sabit teknik`;
  if (names) names.textContent = (a.pins || []).length ? (a.pins || []).map((x) => ((cards.find((c) => c.dataset.id === x) || {}).querySelector?.("div.mt8") || {}).textContent || x).join(" · ") : "seçilmedi: Opus seçsin";
};
ACT.pinsClear = () => { S.comp.att.pins = []; savePins(); route({ poll: true }); };
ACT.pinMode = () => { S.comp.att.pin_mode = S.comp.att.pin_mode === "only" ? "add" : "only"; savePins(); route({ poll: true }); };
ACT.pinModeSet = (el) => { if (!(S.comp.att.pins || []).length) return toast("Önce en az bir teknik sabitle", 1); S.comp.att.pin_mode = el.dataset.v; savePins(); route({ poll: true }); };
ACT.catArea = (el) => { S.catArea = el.dataset.v; S.sig = null; route({ poll: true }); };
ACT.catKind = (el) => { S.catKind = el.dataset.v; S.sig = null; route({ poll: true }); };
ACT.catDemos = async () => { await post("/api/catalog/demos", {}); toast("Örnek klipler üretiliyor (birkaç dakika, kredi harcamaz)"); setTimeout(() => route({ poll: true }), 1500); };
ROUTES["#/referanslar"] = async () => {
  const { refs: lib, themes } = await api("/api/refs"); crumb(["Referanslar"]);
  const pick = q("pick");
  if (pick && S.pickFor !== pick) { S.pickFor = pick; try { S.pickRefs = (await api("/api/production/" + pick)).data.refs || []; } catch (e) { S.pickRefs = []; } }
  const by = {}; lib.forEach((r) => (by[r.theme || "diğer"] = by[r.theme || "diğer"] || []).push(r));
  const card = (r) => { const x = r.recipe || {}; const on = pick && (S.pickRefs || []).includes(r.ref_id);
    return `<div class="card" style="padding:10px;${on ? "border-color:var(--ch)" : ""}"><div class="row nowrap" style="align-items:flex-start">
      <img src="/thumb/ref?id=${encodeURIComponent(r.ref_id)}" data-act="open" data-src="/media/ref?id=${encodeURIComponent(r.ref_id)}" data-photo="${r.kind === "photo" ? 1 : 0}" style="width:86px;height:150px;object-fit:cover;border-radius:10px;cursor:pointer;flex:none" loading="lazy" alt="">
      <div style="min-width:0;flex:1"><div style="font-weight:680">${esc(x.title || r.title || "analiz bekliyor…")}</div>
      <div class="tiny faint">${r.kind === "photo" ? "📷 fotoğraf" : `${sec(r.duration)} · ${r.shot_stats?.shots || "?"} çekim · ort. ${r.shot_stats?.avg_shot_s || "?"} sn${r.bpm ? " · " + Math.round(r.bpm) + " BPM" : ""}`}</div>
      <div class="small muted mt8">${esc(x.summary || "")}</div>
      ${(x.unsupported || []).length ? `<div class="tiny warn mt8">Henüz yapamadığımız: ${esc(x.unsupported.join(", "))}</div>` : ""}
      <div class="row mt8" style="gap:6px"><select data-change="refTheme" data-id="${esc(r.ref_id)}" style="width:auto;padding:5px 30px 5px 9px">${r.theme ? "" : '<option value="">tema?</option>'}${themes.map((t) => `<option value="${t}" ${t === r.theme ? "selected" : ""}>${THEME_TR[t] || t}</option>`).join("")}</select>
      ${pick ? `<button class="btn sm ${on ? "accent" : ""}" data-act="pickRef" data-id="${esc(r.ref_id)}">${on ? "✓ Seçili" : "Seç"}</button>` : ""}<button class="btn sm ghost danger" data-act="delRef" data-id="${esc(r.ref_id)}">${ICON.trash}</button></div></div></div></div>`; };
  paint(`<div class="row"><div><h1>Referans<span class="serif">lar</span></h1><p class="lead">Beğendiğin Reels/TikTok'ların ekran kaydı: kesme ritmi, BPM ve kurgu reçetesi çıkarılır; art director tat olarak kullanır.</p></div><span class="sp"></span><button class="btn sm" data-act="scanRefs">↻ Klasörü tara</button></div>
    ${pick ? `<div class="note warn mt16"><b>#${esc(pick)} için referans seç</b> (en fazla 3)<div class="row mt8"><button class="btn sm accent" data-act="saveRefs" data-id="${esc(pick)}">Kaydet ve videoya dön</button><a class="btn sm ghost" href="#/p/${esc(pick)}">Vazgeç</a></div></div>` : ""}
    <div class="card mt16"><h3>Referans ekle</h3><div class="row"><input type="file" id="rf" accept="video/*,image/*" style="flex:1;min-width:200px"><select id="rt" style="width:auto">${themes.map((t) => `<option value="${t}">${THEME_TR[t] || t}</option>`).join("")}</select><button class="btn accent" data-act="uploadRef">Yükle</button></div><div id="up" class="tiny faint mt8"></div></div>
    ${Object.keys(by).length ? Object.entries(by).map(([t, rs]) => `<h2>${esc(THEME_TR[t] || t)} <span class="faint">${rs.length}</span></h2><div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(330px,1fr))">${rs.map(card).join("")}</div>`).join("") : '<div class="empty mt16">Henüz referans yok</div>'}`);
  return { poll: lib.some((r) => !r.recipe) ? 8000 : 0 };
};
ACT.pickRef = (el) => { const a = S.pickRefs || []; S.pickRefs = a.includes(el.dataset.id) ? a.filter((x) => x !== el.dataset.id) : [...a, el.dataset.id].slice(-3); S.sig = null; route({ poll: true }); };
ACT.saveRefs = async (el) => { await pact(el.dataset.id, "set_refs", { ref_ids: S.pickRefs }); toast("Referanslar kaydedildi"); location.hash = "#/p/" + el.dataset.id; };
ACT.refTheme = async (el) => { await post("/api/refs/theme", { ref_id: el.dataset.id, theme: el.value }); toast("Tema kaydedildi"); };
ACT.scanRefs = async () => { await post("/api/refs/scan"); toast("Referanslar taranıyor"); setTimeout(route, 3000); };
ACT.delRef = async (el) => { if (!confirm("Bu referans silinsin mi?")) return; const r = await post("/api/refs/delete", { ref_id: el.dataset.id }); toast("Silindi · " + r.freed_mb + " MB"); route(); };
ACT.uploadRef = async () => { const f = $("#rf").files[0]; if (!f) return toast("Önce bir dosya seç", 1); await upload("/api/refs/upload", f, { "X-Theme": encodeURIComponent($("#rt").value) }, (x) => ($("#up").textContent = "Yükleniyor… %" + Math.round(x * 100))); toast("Yüklendi, analiz başladı"); route(); };
ROUTES["#/yerler"] = async () => {
  const [places, o] = await Promise.all([api("/api/places"), api("/api/overview")]); crumb(["Yerler & çekimler"]);
  paint(`<h1>Yerler & <span class="serif">çekimler</span></h1><p class="lead">Klipler GPS'e göre yerlere ayrılır. Doğru adlar fikirlerin kalitesini artırır.</p>
    <div class="card mt16"><h3>Yeni çekim ekle (iCloud paylaşımlı albüm)</h3><div class="row"><input id="ilink" type="url" placeholder="https://photos.icloud.com/shared/album/…" style="flex:1;min-width:220px"><button class="btn accent" data-act="ingest">İndir ve analiz et</button></div>
      <div class="tiny faint mt8">${o.clips.total} klip (${o.clips.videos} video) · ${o.clips.described} açıklandı</div>
      ${o.albums.length ? `<div class="row mt8">${o.albums.map((a) => `<button class="btn sm" data-act="ingest" data-link="${esc(a.link)}">↻ ${esc(a.title)} <span class="faint">${ago(a.last_sync)}</span></button>`).join("")}</div>` : ""}</div>
    <div class="card mt16"><h3>Çekimlerde ara</h3><div class="row nowrap"><input type="search" id="clipq" data-keep="clipq" placeholder="ör. gün batımında göl, yürüyen insanlar, karlı zirve…"><button class="btn" data-act="clipSearch">${ICON.search}Ara</button></div><div id="clipres" class="strip mt12"></div></div>
    <div class="grid mt16" style="grid-template-columns:repeat(auto-fill,minmax(340px,1fr))">${places.map((p) => `<div class="card row nowrap"><img src="/thumb/clip/${encodeURIComponent(p.sample)}?t=1" style="width:44px;height:76px;object-fit:cover;border-radius:9px;flex:none" alt=""><div style="flex:1;min-width:0"><input type="text" id="pl${p.place_id}" value="${esc(p.name)}"><div class="tiny faint mt8">${esc(p.day)} · ${p.n} klip (${p.v || 0} video)</div></div><button class="btn sm" data-act="renamePlace" data-id="${p.place_id}">Kaydet</button></div>`).join("")}</div>`);
};
ACT.ingest = async (el) => { const link = el.dataset.link || $("#ilink").value.trim(); const r = await post("/api/ingest", { link }); toast("Albüm işi başladı (#" + r.job_id + ")"); };
ACT.clipSearch = async () => {
  const r = await api("/api/clips/search?q=" + encodeURIComponent($("#clipq").value)), res = r.results;
  const hint = r.backend === "hash" ? `<div class="tiny faint">Çevrimdışı arama: klip açıklamaları İngilizce olduğu için İngilizce kelimelerle ara. Türkçe ↔ İngilizce anlamsal arama için VM'de <code>fastembed</code> kur.</div>` : "";
  $("#clipres").innerHTML = (res.length ? "" : hint) + res.map((c) => `<div class="shot"><img loading="lazy" src="/thumb/clip/${encodeURIComponent(c.clip_id)}?t=1" alt=""><div class="m"><b>${esc(c.place || "")}</b> · ${Math.round(c.score * 100)}%<br>${esc((c.description || "").slice(0, 90))}</div></div>`).join("") || '<div class="tiny faint">Eşleşen çekim yok</div>';
};
ACT.renamePlace = async (el) => { await post(`/api/places/${el.dataset.id}/rename`, { name: $("#pl" + el.dataset.id).value }); toast("Kaydedildi"); };

// ================= Ses / Bütçe / Hesaplar / Sinyaller =================
ROUTES["#/ses"] = async () => {
  const p = await api("/api/eleven"); const a = p.avatar || {}; crumb(["Ses & avatar"]);
  paint(`<h1>Ses & <span class="serif">avatar</span></h1>
  <h2>Seslerin</h2><div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(300px,1fr))">${(p.voices || []).map((v) => `<div class="card"><div class="row"><b>🎙 ${esc(v.name)}</b><span class="sp"></span>${Object.entries(p.defaults || {}).filter(([, id]) => id === v.voice_id).map(([l]) => `<span class="badge ok">varsayılan ${esc(l.toUpperCase())}</span>`).join("")}</div>
    <div class="tiny faint">${esc(v.note || "")} · ${esc(v.voice_id)}</div>${v.preview_url ? `<audio controls preload="none" src="${esc(v.preview_url)}" style="width:100%;margin-top:8px"></audio>` : ""}
    ${["tr", "en"].includes(v.language) ? `<button class="btn sm mt8" data-act="setDefaultVoice" data-lang="${esc(v.language)}" data-id="${esc(v.voice_id)}">${esc(v.language.toUpperCase())} için varsayılan yap</button>` : ""}
    ${v.category === "custom" ? `<button class="btn sm mt8" data-act="removeVoice" data-id="${esc(v.voice_id)}">Sil</button>` : ""}</div>`).join("") || '<div class="empty">Ses yok</div>'}</div>
  <h2>Ses ekle</h2><div class="card"><div class="small muted">ElevenLabs'te sesi aç → <b>ID</b>'yi kopyala (Voices → sesin menüsü → Copy voice ID). Ses bağlı hesapta kontrol edilir (kredi harcanmaz), sonra listeye eklenir.</div>
    <div class="row mt12" style="flex-wrap:wrap;gap:8px">
      <label class="field"><span>Dil</span><select id="nvLang" data-change="newVoiceLang"><option value="">— dil seç —</option>${(p.languages || []).map(([c, n]) => `<option value="${esc(c)}">${esc(n)} (${esc(c)})</option>`).join("")}</select></label>
      <label class="field" id="nvIdWrap" hidden><span>Ses ID'si</span><input id="nvId" placeholder="ör. JBFqnCBsd6RMkjVDRZzb" autocomplete="off" spellcheck="false"></label>
      <label class="field" id="nvNameWrap" hidden><span>İsim (isteğe bağlı)</span><input id="nvName" placeholder="ör. Anlatıcı Defne"></label>
    </div><button class="btn accent mt12" id="nvAdd" data-act="addVoice" hidden>Sesi ekle</button></div>
  <h2>Avatar</h2><div class="card"><div class="small">${a.node_id ? `<span class="ok">✓ Avatar bulundu</span> · düğüm ${esc(a.node_id)}` : `<span class="warn">Avatar henüz akışta yok.</span>`} ${a.checked_at ? `<span class="faint tiny">(${ago(a.checked_at)})</span>` : ""}</div>
    <div class="row mt12"><a class="btn" href="${esc(a.flow_url || "#")}" target="_blank" rel="noopener">ElevenLabs'te aç ↗</a><button class="btn accent" data-act="avatarCheck">Kontrol et</button></div></div>
  <h2>Müzik</h2><div class="card small">ElevenLabs Music · ölçülen fiyat <b>~${p.music_rate ? Math.round(p.music_rate) : 47} kredi/sn</b> · bu ay ${num(p.spent)} / ${num(p.cap)} kredi</div>`);
};
ACT.newVoiceLang = (el) => { for (const k of ["nvIdWrap", "nvNameWrap", "nvAdd"]) document.getElementById(k).hidden = !el.value; if (el.value) document.getElementById("nvId").focus(); };
ACT.addVoice = async () => {
  const body = { language: document.getElementById("nvLang").value, voice_id: document.getElementById("nvId").value.trim(), name: document.getElementById("nvName").value.trim() };
  await post("/api/eleven/voices/add", body); toast("Ses kontrol ediliyor (≈30 sn); işler listesinde görünür"); setTimeout(route, 35000);
};
ACT.removeVoice = async (el) => { if (!confirm("Bu ses listeden silinsin mi?")) return; await post("/api/eleven/voices/remove", { voice_id: el.dataset.id }); toast("Silindi"); route(); };
ACT.setDefaultVoice = async (el) => { await post("/api/eleven/default", { lang: el.dataset.lang, voice_id: el.dataset.id }); toast("Kaydedildi"); route(); };
ACT.avatarCheck = async () => { await post("/api/eleven/avatar_check"); toast("Avatar kontrol ediliyor (≈1 dk)"); };
ROUTES["#/butce"] = async () => {
  const [b, u] = await Promise.all([api("/api/budget"), api("/api/claude_usage").catch(() => null)]); crumb(["Bütçe"]);
  const kinds = Object.entries(b.by_kind).sort((x, y) => y[1] - x[1]), mx = Math.max(1, ...kinds.map((k) => k[1]));
  const KT = { tts: "Ses (TTS)", music: "Müzik", sfx: "Efekt", image: "Görsel / çizim", video: "AI video" };
  paint(`<h1>Bütç<span class="serif">e</span></h1>
  <div class="kpis mt16"><div class="kpi"><div class="l">ElevenLabs bu ay</div><div class="v">${num(b.spent)}</div><div class="bar mt8"><i style="width:${Math.min(100, (b.spent / b.cap) * 100)}%"></i></div><div class="tiny faint mt8">tavan ${num(b.cap)} · kalan ${num(b.cap - b.spent)}</div></div>
    ${u ? [["Son 5 saat", "5h"], ["Bugün", "today"], ["7 gün", "7d"]].map(([l, k]) => `<div class="kpi"><div class="l">Claude · ${l}</div><div class="v">${usd(u.totals[k])}</div>${u.pct_per_usd ? `<div class="tiny faint">≈ %${Math.round(u.totals[k] * u.pct_per_usd)} limit</div>` : ""}</div>`).join("") : ""}</div>
  <div class="note info mt12 small">Kural kodda kilitli: onaylanmış kredi olmadan, tahmin onayı %15'ten fazla aşarsa ya da aylık tavan aşılacaksa üretim çağrısı hiç başlamaz.</div>
  <div class="split mt16"><div>
    <h2>Türe göre (bu ay)</h2><div class="card col" style="gap:10px">${kinds.map(([k, v]) => `<div><div class="row small"><span>${KT[k] || esc(k)}</span><span class="sp"></span><b class="mono">${num(v)}</b></div><div class="bar mt8"><i style="width:${(v / mx) * 100}%"></i></div></div>`).join("") || '<div class="muted small">Bu ay harcama yok</div>'}</div>
    ${u ? `<h2>Claude · bugün adıma göre</h2><div class="card col" style="gap:10px">${u.by_step.map(([k, v]) => `<div><div class="row small"><span>${esc(k)}</span><span class="sp"></span><b class="mono">${usd(v)}</b></div><div class="bar mt8"><i style="width:${(v / Math.max(0.01, ...u.by_step.map((x) => x[1]))) * 100}%"></i></div></div>`).join("") || '<div class="muted small">Bugün çağrı yok</div>'}</div>
    ${u.by_prod.length ? `<h2>Videoya göre (7 gün)</h2><div class="card pad0"><table><tbody>${u.by_prod.map(([id, n, v]) => `<tr><td><a href="#/p/${id}">${esc(n)}</a></td><td class="num">${usd(v)}</td></tr>`).join("")}</tbody></table></div>` : ""}` : ""}
    <h2>Hareketler</h2><div class="card pad0" style="overflow-x:auto"><table><thead><tr><th>Tarih</th><th>Tür</th><th>Not</th><th class="num">Kredi</th></tr></thead><tbody>${b.ledger.map((r) => `<tr><td class="tiny">${dt(r.at)}</td><td>${KT[r.kind] || esc(r.kind)}<div class="tiny faint">${esc(r.model)}</div></td><td class="small muted">${esc(r.note || "")}</td><td class="num">${num(Math.round(r.credits))}</td></tr>`).join("")}</tbody></table></div>
  </div><div>
    <h2>Ölçülen fiyatlar</h2><div class="card pad0"><table><thead><tr><th>Model</th><th class="num">Fiyat</th><th>Birim</th></tr></thead><tbody>${Object.entries(b.rates).map(([k, r]) => `<tr><td>${esc(k)}${r.note ? `<div class="tiny faint">${esc(r.note)}</div>` : ""}</td><td class="num">${(Math.round(r.rate * 100) / 100).toLocaleString("tr-TR")}</td><td class="tiny">kredi/${esc(r.unit)}</td></tr>`).join("")}</tbody></table></div>
    ${u ? `<h2>Son AI çağrıları</h2><div class="card pad0" style="overflow-x:auto"><table><tbody>${u.recent.slice(0, 20).map((r) => `<tr><td class="tiny">${dt(r.at)}</td><td class="small">${esc(r.step)}${r.ok ? "" : ' <span class="bad tiny">hata</span>'}<div class="tiny faint">${esc(r.model)}</div></td><td class="num">${r.cost == null ? "—" : usd(r.cost)}</td></tr>`).join("")}</tbody></table></div>` : ""}
  </div></div>`);
};
ROUTES["#/hesaplar"] = async () => {
  S.me = await api("/api/me"); const m = S.me; crumb(["Hesaplar"]);
  const cl = m.claude.connected ? `<div class="small">✅ Bağlı · ${esc(m.claude.how)}${m.claude.at ? " · " + esc(m.claude.at) : ""}</div>` : `<div class="small">❌ Bağlı değil.</div>`;
  const lc = m.llm_settings || { provider: "claude", models: {} }, provider = lc.provider || "claude";
  const agentModels = (m.llm_agents || []).map((a) => {
    const selected = (lc.models || {})[a.id] || (lc.models || {}).default || "";
    const defaultModel = (m.llm_default_models[provider] || {})[a.id] || (provider === "codex" ? "gpt-6-luna" : "opus");
    return `<label class="field"><span>${esc(a.name)}</span><select data-agent-model="${esc(a.id)}"><option value="">${esc(defaultModel)} · varsayılan</option>${(m.llm_models[provider] || []).map((x) => `<option value="${esc(x.id)}" ${selected === x.id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></label>`;
  }).join("");
  const acc = m.eleven.map((a) => { const b = a.balance || {}; const can = a.mine || m.role === "owner";
    return `<div class="card"><div class="row"><b>💳 ${esc(a.name)}</b><span class="sp"></span><span class="badge">${a.type === "connector" ? "connector" : "API " + esc(a.key_tail || "")}</span>${a.id === m.default_eleven ? '<span class="badge ok">varsayılan</span>' : ""}</div>
    ${a.error ? `<div class="note err mt8 small">${esc(a.error)}</div>` : `<div class="small mt8">${b.left == null ? "bakiye okunmuyor" : num(b.left) + " kredi kaldı"} · ${a.voices} ses</div>`}
    ${can ? `<label class="chk mt8"><input type="checkbox" ${a.shared ? "checked" : ""} data-change="accShared" data-id="${esc(a.id)}"> Diğer kullanıcılar kullanabilsin</label>
    <div class="row nowrap mt8"><input type="number" min="0" placeholder="aylık kişi başı sınır" value="${a.member_month_cap ?? ""}" id="cap_${esc(a.id)}"><button class="btn sm" data-act="accCap" data-id="${esc(a.id)}">Kaydet</button></div>
    ${a.type === "apikey" ? `<div class="row nowrap mt8"><input type="password" placeholder="yeni API anahtarı" id="key_${esc(a.id)}"><button class="btn sm" data-act="accKey" data-id="${esc(a.id)}">Değiştir</button></div><button class="btn sm ghost danger mt8" data-act="accDel" data-id="${esc(a.id)}">Sil</button>` : ""}` : ""}</div>`; }).join("");
  paint(`<div class="row"><h1>Hesap<span class="serif">lar</span></h1><span class="sp"></span>${m.login ? `<button class="btn sm ghost" data-act="logout">Çıkış</button>` : ""}</div>
  <div class="small muted mt8">Giriş yapan: <b>${esc(m.name)}</b> (${m.role === "owner" ? "sahip" : "üye"})</div>
  <div class="card mt16"><h3>⚙️ CLI ve model seçenekleri</h3><p class="small muted">Agent’ların hangi CLI ve modeli kullanacağını seç. Kaydettikten sonra başlayan işlerde uygulanır.</p>
    <label class="field mt12"><span>CLI</span><select id="llm_provider" data-change="llmProvider"><option value="claude" ${provider === "claude" ? "selected" : ""}>Claude Code</option><option value="codex" ${provider === "codex" ? "selected" : ""}>OpenAI Codex CLI</option></select></label>
    <div class="small muted mt8" id="llm_provider_note">${provider === "codex" ? "Varsayılan model tüm agent’larda GPT-6-Luna. Codex, sunucuda kurulu ve oturum açmış CLI hesabını kullanır. ElevenLabs de Codex connector’ı üzerinden çalışır." : "Varsayılanlar mevcut Claude agent modelleridir (opus/sonnet gibi); değiştirmediğin seçimler korunur."}</div>
    <h3 class="mt16">Agent modelleri</h3><div class="grid mt8" style="grid-template-columns:repeat(auto-fill,minmax(220px,1fr))">${agentModels}</div>
    <button class="btn accent sm mt12" data-act="llmSave">Kaydet</button></div>
  <div class="card mt16"><h3>🔌 ElevenLabs · Codex connector</h3>
    <div class="small">${m.codex_elevenlabs?.connected ? "✅ Codex CLI’ye bağlı" : "❌ Codex CLI’ye bağlı değil"}</div>
    <p class="small muted mt8">Codex seçildiğinde ses, müzik ve görsel üretimi bu bağlantıdan yapılır. Bağlan’a basınca ElevenLabs girişine yönlendirilirsin.</p>
    ${m.role === "owner" ? `<button class="btn accent sm mt8" data-act="codexElevenConnect" ${m.codex_elevenlabs?.connected ? "disabled" : ""}>${m.codex_elevenlabs?.connected ? "Bağlandı" : "ElevenLabs’i Codex’e bağla"}</button>` : '<div class="tiny muted">Bu bağlantıyı hesap sahibi yönetir.</div>'}
  </div>
  <div class="card mt16"><h3>🤖 Claude hesabı</h3>${cl}${m.role === "owner" ? "" : `<div id="clflow" class="mt12"><button class="btn sm accent" data-act="claudeStart" data-mode="login">🔗 Tam giriş ile bağla</button> <button class="btn sm" data-act="claudeStart" data-mode="token">🔑 Anahtar ile bağla</button></div>`}</div>
  <h2>ElevenLabs hesapları</h2><div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(300px,1fr))">${acc}</div>
  <div class="card mt16"><h3>＋ ElevenLabs API anahtarı ekle</h3><input type="text" id="ak_name" placeholder="hesap adı (isteğe bağlı)"><input type="password" id="ak_key" placeholder="API anahtarı" class="mt8"><button class="btn accent sm mt8" data-act="accAdd">Ekle ve sesleri oku</button>
    ${m.role === "owner" ? "" : `<button class="btn sm mt8" ${m.claude.connectors ? "" : "disabled"} data-act="accConn">🔌 Connector'ımı bağla</button>`}</div>
  ${m.users ? `<h2>Kullanıcılar</h2>${m.users.map((x) => `<div class="small">👤 ${esc(x.name)} <span class="faint">(${esc(x.id)}, ${x.role === "owner" ? "sahip" : "üye"})</span> · Claude ${x.claude.connected ? "✅" : "❌"}</div>`).join("")}` : ""}`);
};
ACT.llmProvider = (el) => {
  const provider = el.value, options = (S.me.llm_models || {})[provider] || [];
  for (const select of $$('[data-agent-model]')) {
    const prior = select.value;
    const def = ((S.me.llm_default_models || {})[provider] || {})[select.dataset.agentModel] || (provider === "codex" ? "gpt-6-luna" : "opus");
    select.innerHTML = `<option value="">${esc(def)} · varsayılan</option>` + options.map((x) => `<option value="${esc(x.id)}">${esc(x.name)}</option>`).join("");
    if (options.some((x) => x.id === prior)) select.value = prior;
  }
  $("#llm_provider_note").textContent = provider === "codex"
    ? "Varsayılan model tüm agent’larda GPT-6-Luna. Codex, sunucuda kurulu ve oturum açmış CLI hesabını kullanır. ElevenLabs de Codex connector’ı üzerinden çalışır."
    : "Varsayılanlar mevcut Claude agent modelleridir (opus/sonnet gibi); değiştirmediğin seçimler korunur.";
};
ACT.llmSave = async () => {
  const models = Object.fromEntries($$('[data-agent-model]').filter((x) => x.value).map((x) => [x.dataset.agentModel, x.value]));
  await post("/api/llm/settings", { provider: $("#llm_provider").value, models });
  toast("CLI ve agent modelleri kaydedildi"); route();
};
ACT.codexElevenConnect = async () => {
  const r = await post("/api/codex/elevenlabs/start", {});
  if (r.connected) { toast("Codex ElevenLabs zaten bağlı"); return route(); }
  if (!r.url) throw new Error("ElevenLabs giriş bağlantısı alınamadı");
  location.href = r.url;
};
ACT.logout = async () => { await post("/api/logout"); location.href = "/login"; };
ACT.accShared = async (el) => { await post(`/api/eleven/accounts/${el.dataset.id}/update`, { shared: el.checked }); toast("Kaydedildi"); };
ACT.accCap = async (el) => { await post(`/api/eleven/accounts/${el.dataset.id}/update`, { member_month_cap: $("#cap_" + el.dataset.id).value }); toast("Kaydedildi"); route(); };
ACT.accKey = async (el) => { await post(`/api/eleven/accounts/${el.dataset.id}/update`, { key: $("#key_" + el.dataset.id).value }); toast("Anahtar değişti"); route(); };
ACT.accDel = async (el) => { if (!confirm("Bu hesap silinsin mi?")) return; await post(`/api/eleven/accounts/${el.dataset.id}/delete`); route(); };
ACT.accAdd = async () => { await post("/api/eleven/accounts/add", { name: $("#ak_name").value, key: $("#ak_key").value }); toast("Hesap eklendi"); route(); };
ACT.accConn = async () => { await post("/api/eleven/accounts/add_connector"); toast("Connector eklendi, sesler okunuyor"); route(); };
ACT.claudeStart = async (el) => { const r = await post("/api/claude/start", { mode: el.dataset.mode }); $("#clflow").innerHTML = `<div class="small">1) Bu linki aç, giriş yap ve izin ver:</div><a class="btn sm mt8" href="${esc(r.url)}" target="_blank" rel="noopener">Claude'da giriş yap ↗</a><div class="small mt12">2) Verilen kodu yapıştır:</div><div class="row nowrap mt8"><input type="text" id="clcode" placeholder="kod"><button class="btn accent sm" data-act="claudeFinish">Bağla</button></div>`; };
ACT.claudeFinish = async () => { await post("/api/claude/finish", { code: $("#clcode").value }); toast("Claude bağlandı"); route(); };
ROUTES["#/sinyal"] = async () => {
  const prof = q("p") || "travel"; const s = await api("/api/signals?profile=" + prof); const r = s.runs[0]; crumb(["Sinyaller"]);
  paint(`<div class="row"><div><h1>Sinyal<span class="serif">ler</span></h1><p class="lead">YouTube Radar (küçük kanalda patlayan videolar) ve Google Trends: fikir üretimine giden veri.</p></div><span class="sp"></span>
    <a class="chip ${prof === "travel" ? "on" : ""}" href="#/sinyal?p=travel" style="text-decoration:none">Seyahat</a><a class="chip ${prof === "psychology" ? "on" : ""}" href="#/sinyal?p=psychology" style="text-decoration:none">Psikoloji</a></div>
  <div class="row mt16"><span class="small muted">Son çalışma ${r ? dt(r.ts) + " · " + esc(r.status) : "—"}</span><span class="sp"></span><button class="btn sm" data-act="runRadar" data-p="${esc(prof)}">Radar'ı çalıştır (~950 kota)</button></div>
  <div class="grid mt16" style="grid-template-columns:repeat(auto-fill,minmax(340px,1fr))">${s.radar.map((c) => `<a class="card hover row nowrap" href="${esc(c.url)}" target="_blank" rel="noopener" style="text-decoration:none"><img src="${esc(c.thumbnail || "")}" style="width:64px;height:64px;object-fit:cover;border-radius:10px;flex:none" loading="lazy" alt="">
    <div style="min-width:0;flex:1"><div class="small" style="font-weight:650">${esc(c.title)}</div><div class="tiny faint">${esc(c.channel_title || "")} · ${sec(c.duration_s)} · ${(c.age_h / 24).toFixed(0)} gün</div>
    <div class="row mt8" style="gap:6px"><span class="badge">skor ${esc(c.viral_score)}</span><span class="badge">${num(c.views)} izlenme</span>${c.icahn ? `<span class="badge warn">Icahn ✓ ${esc(c.views_per_sub)}×</span>` : ""}</div></div></a>`).join("") || '<div class="empty">Veri yok</div>'}</div>
  <div class="row mt24"><h2 style="margin:0">Google Trends</h2><span class="sp"></span><button class="btn sm" data-act="runTrends">Yenile</button></div>
  <div class="chips mt12">${s.trends.map((t) => `<span class="chip">${esc(t.geo)} · ${esc(t.title)} <span class="faint">${esc(t.traffic || "")}</span></span>`).join("")}</div>`);
};
ACT.runRadar = async (el) => { if (!confirm("YouTube kotasından ~950 birim kullanılacak. Devam?")) return; await post("/api/radar", { profile: el.dataset.p }); toast("Radar başladı"); };
ACT.runTrends = async () => { await post("/api/trends"); toast("Trendler çekiliyor"); setTimeout(route, 6000); };

// ================= boot =================
async function jobsTick() { try { S.jobs = await api("/api/jobs"); const run = S.jobs.filter((j) => j.status === "running" || j.status === "queued"); const el = $(".jobs-ind"); if (el) { el.classList.toggle("on", !!run.length); el.innerHTML = run.length ? `<span class="spin"></span>${run.length} iş sürüyor` : "işler boşta"; } } catch (e) {} }
(async function boot() {
  paintChannel();
  try {
    const [chs, fm, st, me] = await Promise.all([api("/api/channels"), api("/api/formats"), api("/api/styles").catch(() => []), api("/api/me").catch(() => null)]);
    S.channels = chs; S.formats = fm; S.styles = st; S.me = me;
    if (!chan(S.ch) && chs[0]) setChannel(chs[0].id); else paintChannel();
  } catch (e) { $("#app").innerHTML = `<div class="note err">Stüdyo açılamadı: ${esc(e.message)}</div>`; return; }
  route();
  setInterval(jobsTick, 9000);
  setInterval(async () => { try { S.channels = await api("/api/channels"); } catch (e) {} }, 60000);
})();
