/* v2 production lines in the Studio (factory/hat, studio/hat_api.py).
   Pages: #/uret (the 14 lines, start one), #/uretimler (every v2 production), #/u/<project> (one production as a flow:
   stages left to right, the selected stage's output, and at a gate one decision: continue, feedback, or go back).
   Every word on these pages comes from TX in the user's interface language (S.me.ui_lang). */
(() => {
const LANGS = { tr: "Türkçe", en: "English" };
const L = () => ((S.me && S.me.ui_lang) || "tr");
const TX = {
  tr: {
    nav_make: "Üret", nav_prods: "Üretimler", nav_fstyles: "Film stilleri", fs_lead: "Kütüphanedeki 12 stil ve senin kendi stillerin. Bir stili değiştirerek ya da boş sayfadan kendi stilini yap; onaylanınca öneri kapılarında seçilebilir.", fs_lib: "Kütüphane", fs_own: "Senin stillerin", fs_new: "Kendi stilini yap", fs_name: "Stilin adı", fs_base: "Nereden başlayalım?", fs_blank: "Boş sayfa", fs_create: "Başla", fs_change: "Bunu değiştir", fs_st_start: "Başlangıç", fs_st_plan: "Plan", fs_st_brand: "Marka", fs_st_sample: "Örnek kare", fs_st_approve: "Onay", fs_next: "İleri", fs_prev: "Geri", fs_save: "Kaydet", fs_skip: "Atla", fs_draw: "Örnek kareyi çiz", fs_drawing: "Çiziliyor (yaklaşık 1 dk)…", fs_redraw: "Yeniden çiz", fs_approve: "Onayla, kütüphaneye ekle", fs_draft: "taslak", fs_sampled: "kare hazır", fs_approved: "onaylı", fs_stale: "Değişiklikten sonra örnek kareyi yeniden çiz.", fs_need: "Yanıtlanmamış: {0}", fs_logo_up: "Logo yükle", fs_logo_ok: "Logo yüklü", fs_delete: "Sil", fs_del_q: "Bu stil silinsin mi?", fs_saved: "Kaydedildi", fs_in_lib: "Bu stil kütüphanede; öneri kapılarında seçilebilir.", fs_no_cost: "Kredi harcanmaz: kare stüdyonun kendi motoruyla çizilir.", fs_based: "Temel: {0}", lang: "Arayüz dili",
    make_title: "Ne üretelim?", make_lead: "Bir üretim hattı seç. Her hat videoyu aynı sırayla, adım adım üretir ve her kapıda senin kararını bekler.",
    status_ready: "Hazır", status_partial: "Kısmen hazır", status_planned: "Yakında",
    makes: "Ne üretir", good: "İyi olduğu", not: "Uygun değil", needs: "Ne ister", cost: "Maliyet", duration: "Tipik süre",
    stages: "Aşamalar", gate: "kapı", sec: "sn",
    start_with: "Bu hatla başla", not_ready: "Bu hat henüz hazır değil; aşamaları yazıldıkça açılacak.",
    brief: "Ne anlatsın?", brief_ph: "Konu, haber linki ya da istediğin açı. Örn: Avrupa'da doğal gaz 100 avroyu aştı; nedenleri ve faturalara etkisi.",
    title: "Başlık (isteğe bağlı)", video_lang: "Video dili", aspect: "Kadraj", channel: "Kanal", none: "Seçme",
    create: "Başlat", cancel: "Vazgeç", started: "Başladı: ilk aşama çalışıyor",
    prods_title: "Üretimler", prods_lead: "Yeni hatlardaki videolar. Kartı açınca akışı ve senden beklenen kararı görürsün.",
    prods_empty: "Henüz yeni hatta bir üretim yok.", new_prod: "Yeni üretim",
    state_busy: "Çalışıyor", state_gate: "Kararını bekliyor", state_failed: "Hata", state_done: "Bitti", state_run: "Sırada", state_archived: "Arşiv", series: "Seri", episode: "Bölüm", no_series: "Kitabı ve karakterleri hazır bir serin yok.", to_series: "Seriler sayfasına git",  video_file: "Videon (MP4/MOV, en fazla 600 MB)", need_video: "Önce videonu seç", media_file: "Video ya da ses dosyan (MP4/MOV/MP3/M4A/WAV)", page_url: "Sayfa adresi", page_url_hint: "Herkese açık, giriş istemeyen bir sayfa. Tarayıcı adımları kendisi oynatır.", source_lang: "Videonun şimdiki dili (video dili = dublaj dili)", portrait_file: "Sunucu portresi (isteğe bağlı, JPG/PNG)", portrait_hint: "Önden, omuzdan yukarı, ağız kapalı, iyi ışıkta. Yüklemezsen sunucu üretilir.", uploading: "Yükleniyor", style: "Kurgu tarzı", cut_word: "kesildi", fmt_cinematic_calm: "Sakin sinematik", fmt_story_vo: "Hikâye (kendi sesin)", fmt_unreal_places: "Gerçek gibi durmayan yerler", fmt_travel_facts: "Gezi bilgileri (kaynaklı)", fmt_long_compilation: "Uzun derleme (1 dk+)",  shots: "plan", warnings: "Uyarılar", gen_shot: "üretilecek", own_shot: "kendi görüntün", gen_clips: "Üretilen klipler", archived_note: "Eski sistemden arşivlendi; üzerinde iş yapılmaz.",
    state_planned: "Bu hatta sıradaki aşama henüz yok",
    st_pending: "Bekliyor", st_running: "Çalışıyor", st_awaiting_approval: "Kararını bekliyor", st_approved: "Onaylandı",
    st_done: "Bitti", st_failed: "Hata", st_stale: "Yeniden yapılacak",
    back_list: "Üretimler", continue: "Devam et", feedback: "Geri bildirim", fb_ph: "Neyi değiştirelim? Somut yaz: \"hook daha sert olsun\", \"3. sahnede rakam yanlış\"…",
    redo: "Bu aşamayı yeniden yap", start_stage: "Bu aşamayı başlat", approved_ok_start: "Aşama başladı", revisions: "Revizyon {0}/3", go_back: "Bu aşamaya geri dön",
    back_warn: "Sonraki aşamalar yeniden yapılacak olarak işaretlenir; yaptıkları silinmez.", retry: "Tekrar dene",
    decision: "Karar", waiting_prev: "Önceki aşamalar bitince başlar.", not_built: "Bu aşama bu hatta henüz yazılmadı.",
    working: "Çalışıyor…", live: "Canlı akış", spent: "Harcanan", credits: "kredi", note_sent: "Not gönderildi, aşama yeniden çalışıyor",
    approved_ok: "Onaylandı, sıradaki aşama başladı", back_ok: "Aşama yeniden açıldı",
    review: "Denetim", verdict_pass: "Denetimden geçti", verdict_fix: "Açık kritik bulgu var", verdict_unknown: "Denetim alınamadı",
    sev_critical: "Kritik", sev_suggestion: "Öneri", sev_nitpick: "Ayrıntı", rounds: "{0} tur",
    insight: "Ana fikir", misconception: "Yaygın yanlış", data: "Veriler", sources: "Kaynaklar", angles: "Açılar",
    concepts: "Üç yaklaşım", chosen: "Seçilen", look: "Görünüm", music: "Müzik", yes: "Var", no: "Yok", total: "Toplam",
    style_lib: "Film stili", style_pick: "Bu stili kullan", style_now: "Seçili stil", style_avoid: "Kaçın",
    style_type: "Yazı", style_motion: "Hareket", style_sound: "Ses", style_set: "Stil seçildi", render_time: "Render süresi", preview_t: "önizleme", final_t: "final", structure: "Yapı", key_frame: "Ana kare",
    script: "Senaryo", claims: "İddialar", verified: "doğrulandı", unverified: "doğrulanmadı", caption: "Paylaşım metni",
    words: "kelime", lines_n: "satır",
    scenes: "Sahneler", concept: "Görsel fikir", palette: "Renkler", no_stills: "Henüz kare yok.", line_range: "satır {0}–{1}",
    preview: "Önizleme", voice: "Ses", final: "Final video", qa: "Kalite kontrolü", covers: "Kapak adayları", download: "İndir",
    no_problems: "Teknik sorun bulunmadı.", hashtags: "Etiketler", notes: "Notlar", copy: "Kopyala",
    summary: "Özet", output_none: "Bu aşamanın çıktısı henüz yok.", error: "Hata",
    ev_created: "Üretim açıldı", ev_stage_start: "{0} başladı", ev_stage_finish: "{0} bitti", ev_stage_fail: "{0} hata verdi",
    ev_agent_start: "Ajan çalışıyor ({0})", ev_agent_end: "Ajan teslim etti", ev_review: "Denetçi baktı ({0})",
    ev_review_fix: "Denetçi düzeltme istedi", ev_tool: "Araç: {0}", ev_approve: "{0} onaylandı", ev_feedback: "{0} için not",
    ev_reopen: "{0} yeniden açıldı", ev_queued: "{0} sıraya alındı", ev_tool_error: "Araç hatası: {0}",
  },
  en: {
    nav_make: "Make", nav_prods: "Productions", nav_fstyles: "Film styles", fs_lead: "The library's 12 styles and your own. Make your own by changing a style or from a blank page; once approved it can be picked at proposal gates.", fs_lib: "Library", fs_own: "Your styles", fs_new: "Make your own style", fs_name: "Style name", fs_base: "Where to start?", fs_blank: "Blank page", fs_create: "Start", fs_change: "Change this", fs_st_start: "Start", fs_st_plan: "Plan", fs_st_brand: "Brand", fs_st_sample: "Sample frame", fs_st_approve: "Approve", fs_next: "Next", fs_prev: "Back", fs_save: "Save", fs_skip: "Skip", fs_draw: "Draw the sample frame", fs_drawing: "Drawing (about 1 min)…", fs_redraw: "Draw again", fs_approve: "Approve, add to the library", fs_draft: "draft", fs_sampled: "frame ready", fs_approved: "approved", fs_stale: "Draw the sample frame again after a change.", fs_need: "Unanswered: {0}", fs_logo_up: "Upload logo", fs_logo_ok: "Logo uploaded", fs_delete: "Delete", fs_del_q: "Delete this style?", fs_saved: "Saved", fs_in_lib: "This style is in the library; proposal gates can pick it.", fs_no_cost: "No credits: the frame is drawn by the studio's own engine.", fs_based: "Based on: {0}", lang: "Interface language",
    make_title: "What shall we make?", make_lead: "Pick a production line. Each line makes the video step by step in the same order and waits for your decision at every gate.",
    status_ready: "Ready", status_partial: "Partly built", status_planned: "Coming soon",
    makes: "What it makes", good: "Good for", not: "Not for", needs: "What it needs", cost: "Cost", duration: "Typical length",
    stages: "Stages", gate: "gate", sec: "s",
    start_with: "Start with this line", not_ready: "This line is not ready yet; it opens as its stages are written.",
    brief: "What should it say?", brief_ph: "A topic, a news link or the angle you want. E.g.: European gas crossed 100 euros; why, and what it means for bills.",
    title: "Title (optional)", video_lang: "Video language", aspect: "Aspect", channel: "Channel", none: "None",
    create: "Start", cancel: "Cancel", started: "Started: the first stage is running",
    prods_title: "Productions", prods_lead: "Videos on the new lines. Open one to see its flow and the decision waiting for you.",
    prods_empty: "No production on the new lines yet.", new_prod: "New production",
    state_busy: "Working", state_gate: "Waiting for you", state_failed: "Error", state_done: "Done", state_run: "Up next", state_archived: "Archive", series: "Series", episode: "Episode", no_series: "You have no series with its book and characters ready.", to_series: "Go to Series",  video_file: "Your video (MP4/MOV, up to 600 MB)", need_video: "Pick your video first", media_file: "Your video or audio file (MP4/MOV/MP3/M4A/WAV)", page_url: "Page address", page_url_hint: "A public page with no login. The browser plays the steps itself.", source_lang: "The video's current language (video language = dub language)", portrait_file: "Presenter portrait (optional, JPG/PNG)", portrait_hint: "Front-facing, head and shoulders, mouth closed, good light. Without one a presenter is generated.", uploading: "Uploading", style: "Edit style", cut_word: "cut", fmt_cinematic_calm: "Cinematic calm", fmt_story_vo: "Story (your own voice)", fmt_unreal_places: "Places that look unreal", fmt_travel_facts: "Travel facts (sourced)", fmt_long_compilation: "Long compilation (1 min+)",  shots: "shots", warnings: "Warnings", gen_shot: "generated", own_shot: "your footage", gen_clips: "Generated clips", archived_note: "Archived from the old system; no work is done on it.",
    state_planned: "The next stage is not built on this line yet",
    st_pending: "Waiting", st_running: "Working", st_awaiting_approval: "Waiting for you", st_approved: "Approved",
    st_done: "Done", st_failed: "Error", st_stale: "To redo",
    back_list: "Productions", continue: "Continue", feedback: "Feedback", fb_ph: "What should change? Be specific: \"a harder hook\", \"the figure in scene 3 is wrong\"…",
    redo: "Redo this stage", start_stage: "Start this stage", approved_ok_start: "Stage started", revisions: "Revision {0}/3", go_back: "Go back to this stage",
    back_warn: "Later stages are marked to redo; their work is kept.", retry: "Try again",
    decision: "Decision", waiting_prev: "Starts when the earlier stages are done.", not_built: "This stage is not written on this line yet.",
    working: "Working…", live: "Live feed", spent: "Spent", credits: "credits", note_sent: "Note sent; the stage runs again",
    approved_ok: "Approved; the next stage started", back_ok: "Stage reopened",
    review: "Review", verdict_pass: "Passed review", verdict_fix: "Open critical findings", verdict_unknown: "No review",
    sev_critical: "Critical", sev_suggestion: "Suggestion", sev_nitpick: "Nitpick", rounds: "{0} rounds",
    insight: "Insight", misconception: "Common misconception", data: "Data points", sources: "Sources", angles: "Angles",
    concepts: "Three approaches", chosen: "Chosen", look: "Look", music: "Music", yes: "Yes", no: "No", total: "Total",
    style_lib: "Film style", style_pick: "Use this style", style_now: "Chosen style", style_avoid: "Avoid",
    style_type: "Type", style_motion: "Motion", style_sound: "Sound", style_set: "Style chosen", render_time: "Render time", preview_t: "preview", final_t: "final", structure: "Structure", key_frame: "Key frame",
    script: "Script", claims: "Claims", verified: "verified", unverified: "not verified", caption: "Post caption",
    words: "words", lines_n: "lines",
    scenes: "Scenes", concept: "Visual idea", palette: "Colours", no_stills: "No frames yet.", line_range: "lines {0}–{1}",
    preview: "Preview", voice: "Voice", final: "Final video", qa: "Quality check", covers: "Cover candidates", download: "Download",
    no_problems: "No technical problems found.", hashtags: "Hashtags", notes: "Notes", copy: "Copy",
    summary: "Summary", output_none: "This stage has no output yet.", error: "Error",
    ev_created: "Production opened", ev_stage_start: "{0} started", ev_stage_finish: "{0} finished", ev_stage_fail: "{0} failed",
    ev_agent_start: "Agent working ({0})", ev_agent_end: "Agent submitted", ev_review: "Reviewer checked ({0})",
    ev_review_fix: "Reviewer asked for fixes", ev_tool: "Tool: {0}", ev_approve: "{0} approved", ev_feedback: "Note on {0}",
    ev_reopen: "{0} reopened", ev_queued: "{0} queued", ev_tool_error: "Tool error: {0}",
  },
};
const t = (k, ...a) => { let s = (TX[L()] || TX.tr)[k] ?? TX.tr[k] ?? k; a.forEach((v, i) => { s = s.replace("{" + i + "}", v); }); return s; };
const STATUS_ICON = { pending: "○", running: "", awaiting_approval: "⏸", approved: "✓", done: "✓", failed: "!", stale: "↻" };
const HS = { lines: null, open: null, sel: {}, fsQ: {} };

// ---------------- shell: nav entries and the language switch ----------------
NAV.unshift(["#/uret", "wand", ""], ["#/uretimler", "film", ""], ["#/film-stilleri", "palette", ""]);
// One way in: the planner home and the old board send you to the productions list (t206); their pages stay reachable
// from old links until go-live removes them.
for (const old of ["#/", "#/hat"]) ROUTES[old] = () => { location.replace("#/uretimler"); return { poll: 0 }; };
// The old shell (app.js) is written in Turkish. In EN the visible chrome is translated here, after it renders,
// so app.js stays untouched. Page bodies of the old pages are not covered (tracker follow-up).
const SHELL_EN = {
  "Üretim": "Produce", "Kütüphane": "Library", "Sistem": "System", "Kanallar": "Channels",
  "Stüdyo": "Studio", "Üretim panosu": "Production board", "Teknik kataloğu": "Technique catalogue", "Seriler": "Series",
  "Keşif": "Discover", "Takip": "Tracking", "Videolar": "Videos", "Stiller": "Styles", "Referanslar": "References",
  "Yerler & çekimler": "Places & shoots", "Ses & avatar": "Voice & avatar", "Bütçe": "Budget", "Sinyaller": "Signals",
  "Hesaplar": "Accounts", "Ayarlar": "Settings", "Üretimler": "Productions", "Üret": "Make", "Pano": "Board", "Menü": "Menu", "Ara ya da git…": "Search or go to…", "işler boşta": "no jobs running",
  "Tema": "Theme", "Yeni kanal": "New channel", "Kanal yok": "No channel", "🌙 Koyu tema": "🌙 Dark theme", "☀️ Açık tema": "☀️ Light theme",
};
const SHELL_RE = [[/^(\d+) iş sürüyor$/, "$1 jobs running"], [/^çekimli\b/, "footage"], [/^çekimsiz\b/, "topic only"], [/^karışık\b/, "mixed"]];
const trText = (x) => { const k = x.trim(); if (!k) return x; let v = SHELL_EN[k]; for (const [re, to] of SHELL_RE) if (v == null && re.test(k)) v = k.replace(re, to); return v == null ? x : x.replace(k, v); };
function translateShell() {
  if (L() === "tr") return;
  for (const sel of ["#rail", "#side", "#top", "#mtop", "#tabbar", "#drawerPanel"]) {
    const root = $(sel); if (!root) continue;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) { const v = trText(n.nodeValue); if (v !== n.nodeValue) n.nodeValue = v; }
    root.querySelectorAll("[data-tip],[title]").forEach((e) => { for (const a of ["data-tip", "title"]) if (e.hasAttribute(a)) e.setAttribute(a, trText(e.getAttribute(a))); });
  }
}
const _renderShell = renderShell;
renderShell = function () {
  NAV[0][2] = t("nav_make"); NAV[1][2] = t("nav_prods"); NAV[2][2] = t("nav_fstyles");
  document.documentElement.lang = L();   // text-transform: uppercase needs the right language (tr: i→İ, en: i→I)
  _renderShell();
  translateShell();
  const top = $("#top");
  if (top && !top.querySelector(".langsw")) {
    top.insertAdjacentHTML("beforeend", `<div class="seg langsw" title="${esc(t("lang"))}">${Object.keys(LANGS).map((k) =>
      `<button class="${L() === k ? "on" : ""}" data-act="hatLang" data-v="${k}">${k.toUpperCase()}</button>`).join("")}</div>`);
  }
};
const _jobsTick = jobsTick;
jobsTick = async function () { await _jobsTick(); const el = $(".jobs-ind"); if (el && L() !== "tr") el.childNodes.forEach((n) => { if (n.nodeType === 3) n.nodeValue = trText(n.nodeValue); }); };
const _dt = dt;
dt = function (iso) { return L() === "tr" ? _dt(iso) : (iso ? new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : ""); };
ACT.hatLang = async (el) => {
  const r = await post("/api/hat/lang", { lang: el.dataset.v });
  if (S.me) S.me.ui_lang = r.ui_lang;
  HS.lines = null; S.sig = null; route();
};

// ---------------- #/uret: the lines ----------------
function lineCard(l) {
  const st = { ready: "ok", partial: "warn", planned: "" }[l.status];
  return `<article class="hl-card ${l.status}" data-line="${esc(l.id)}">
    <div class="row"><h3>${esc(l.name)}</h3><span class="sp"></span><span class="badge hl-st ${st}">${esc(t("status_" + l.status))}</span></div>
    <p class="hl-tag">${esc(l.tagline)}</p>
    <details><summary class="small muted">${esc(t("makes"))} · ${esc(t("stages"))}</summary>
      <p class="small">${esc(l.makes)}</p>
      <div class="hl-kv small"><b>${esc(t("good"))}</b><ul>${l.good_for.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
        <b>${esc(t("not"))}</b><ul>${l.not_for.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
        <b>${esc(t("needs"))}</b><div>${esc(l.needs)}</div>
        <b>${esc(t("duration"))}</b><div>${l.duration ? `${l.duration[0]}–${l.duration[1]} ${esc(t("sec"))}` : "—"}</div>
        <b>${esc(t("cost"))}</b><div>${esc(l.cost)}</div></div>
      <ol class="hl-stages">${l.stages.map((s) => `<li>${esc(s.name)}${s.gate ? ` <span class="tiny faint">🔒 ${esc(t("gate"))}</span>` : ""}</li>`).join("")}</ol>
    </details>
    ${l.status === "ready" ? `<button class="btn accent block mt12" data-act="hatOpen" data-id="${esc(l.id)}">${esc(t("start_with"))}</button>`
      : `<div class="tiny faint mt12">${esc(t("not_ready"))}</div>`}
    ${HS.open === l.id ? startForm(l) : ""}
  </article>`;
}
function startForm(l) {
  const vl = L();
  return `<div class="hl-form mt12">
    <label class="field"><span>${esc(t("brief"))}</span><textarea id="hlBrief" data-keep="hl-brief" placeholder="${esc(t("brief_ph"))}"></textarea></label>
    <label class="field mt8"><span>${esc(t("title"))}</span><input id="hlTitle" data-keep="hl-title" maxlength="80"></label>
    <div class="row mt8" style="gap:12px;align-items:flex-end">
      <label class="field"><span>${esc(t("video_lang"))}</span><select id="hlVlang">${Object.entries(LANGS).map(([k, v]) => `<option value="${k}" ${k === vl ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      <label class="field"><span>${esc(t("aspect"))}</span><select id="hlAspect"><option>9:16</option><option>16:9</option></select></label>
      <label class="field"><span>${esc(t("channel"))}</span><select id="hlChan"><option value="">${esc(t("none"))}</option>${S.channels.map((c) => `<option value="${esc(c.id)}" ${c.id === S.ch ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
    </div>
    ${(l.inputs || []).includes("url") ? `<label class="field mt8"><span>${esc(t("page_url"))}</span><input type="url" id="hlUrl" placeholder="https://"></label><div class="tiny faint">${esc(t("page_url_hint"))}</div>` : ""}
    ${(l.inputs || []).includes("source_lang") ? `<label class="field mt8"><span>${esc(t("source_lang"))}</span><select id="hlSrcLang"><option value="tr">Türkçe</option><option value="en">English</option></select></label>` : ""}
    ${(l.inputs || []).includes("portrait") ? `<label class="field mt8"><span>${esc(t("portrait_file"))}</span><input type="file" id="hlPortrait" accept="image/jpeg,image/png,image/webp"></label><div class="tiny faint">${esc(t("portrait_hint"))}</div>` : ""}
    ${(l.inputs || []).includes("video") ? `<label class="field mt8"><span>${esc(t((l.inputs || []).includes("audio") ? "media_file" : "video_file"))}</span><input type="file" id="hlVideo" accept="video/mp4,video/quicktime,.mov,.m4v${(l.inputs || []).includes("audio") ? ",audio/*,.mp3,.m4a,.wav" : ""}"></label><div id="hlProg" class="tiny faint"></div>` : ""}
    ${(l.inputs || []).includes("series") ? ((HS.series || []).length ? `<div class="row mt8" style="gap:12px;align-items:flex-end">
      <label class="field"><span>${esc(t("series"))}</span><select id="hlSeries">${HS.series.map((x) => `<option value="${x.id}" data-next="${Math.min(x.made + 1, x.episodes)}">${esc(x.title)} (${x.made}/${x.episodes})</option>`).join("")}</select></label>
      <label class="field"><span>${esc(t("episode"))}</span><input id="hlEp" type="number" min="1" value="${Math.min(HS.series[0].made + 1, HS.series[0].episodes)}" style="width:90px"></label></div>`
      : `<div class="note mt8 small">${esc(t("no_series"))} <a href="#/seriler">${esc(t("to_series"))}</a></div>`) : ""}
    ${l.id === "travel_vlog" ? `<label class="field mt8"><span>${esc(t("style"))}</span><select id="hlFormat">${["cinematic_calm", "story_vo", "unreal_places", "travel_facts", "long_compilation"].map((f) => `<option value="${f}">${esc(t("fmt_" + f))}</option>`).join("")}</select></label>` : ""}
    <div class="row mt12"><button class="btn accent" data-act="hatCreate" data-id="${esc(l.id)}">${esc(t("create"))}</button>
      <button class="btn ghost" data-act="hatClose">${esc(t("cancel"))}</button></div>
  </div>`;
}
ROUTES["#/uret"] = async () => {
  crumb([t("nav_make")]);
  HS.lines = HS.lines || await api("/api/hat/lines");
  if (HS.open === "series_episode") HS.series = await api("/api/hat/series");
  paint(`<h1>${esc(t("make_title"))}</h1><p class="lead">${esc(t("make_lead"))}</p>
    <div class="hl-grid mt16">${HS.lines.map(lineCard).join("")}</div>`, JSON.stringify([L(), HS.open]));
  return {};
};
ACT.hatOpen = (el) => { HS.open = el.dataset.id; S.sig = null; route({ poll: true }); setTimeout(() => $("#hlBrief") && $("#hlBrief").focus(), 60); };
ACT.hatClose = () => { HS.open = null; S.sig = null; route({ poll: true }); };
ACT.hatCreate = async (el) => {
  el.disabled = true;
  try {
    let source = null;
    if ($("#hlVideo")) {          // a line that edits the creator's own video: upload it first (kept as is in raw/talk/)
      const f = $("#hlVideo").files[0];
      if (!f) { toast(t("need_video"), 1); return; }
      source = (await upload("/api/refs/upload", f, { "X-Talk": "1" }, (k) => ($("#hlProg").textContent = t("uploading") + " %" + Math.round(k * 100)))).file;
    }
    let portrait = null;
    if ($("#hlPortrait") && $("#hlPortrait").files[0]) {     // optional: without one the line generates a presenter
      portrait = (await upload("/api/refs/upload", $("#hlPortrait").files[0], { "X-Avatar": "1" }, () => {})).file;
    }
    const r = await post("/api/hat/projects", { portrait, url: $("#hlUrl") ? $("#hlUrl").value.trim() : null, source_lang: $("#hlSrcLang") ? $("#hlSrcLang").value : null, line: el.dataset.id, brief: $("#hlBrief").value, title: $("#hlTitle").value,
      video_lang: $("#hlVlang").value, aspect: $("#hlAspect").value, channel: $("#hlChan").value || null, source,
      format: $("#hlFormat") ? $("#hlFormat").value : null,
      series: $("#hlSeries") ? $("#hlSeries").value : null, episode: $("#hlEp") ? $("#hlEp").value : null });
    HS.open = null; S.drafts = {}; toast(t("started"));
    location.hash = "#/u/" + r.id;
  } finally { el.disabled = false; }
};

// ---------------- #/uretimler: the list ----------------
const stateBadge = (state) => `<span class="badge hl-state s-${esc(state)}">${state === "busy" ? '<span class="spin"></span>' : ""}${esc(t("state_" + state))}</span>`;
ROUTES["#/uretimler"] = async () => {
  crumb([t("nav_prods")]);
  const ps = await api("/api/hat/projects");
  paint(`<div class="row"><div><h1>${esc(t("prods_title"))}</h1><p class="lead">${esc(t("prods_lead"))}</p></div><span class="sp"></span>
      <a class="btn accent" href="#/uret">${ICON.plus}${esc(t("new_prod"))}</a></div>
    <div class="hl-list mt16">${ps.map((p) => `<a class="hl-row" href="#/u/${esc(p.id)}">
        <span class="mono tiny faint">${esc(p.id.slice(0, 3))}</span>
        <span class="hl-row-t"><b>${esc(p.title)}</b><span class="tiny muted">${esc(p.line_name)} · ${esc((p.video_lang || "").toUpperCase())} · ${esc(p.aspect || "")}</span></span>
        <span class="small muted">${esc(p.stage_name || "")}</span>${stateBadge(p.state)}</a>`).join("") || `<div class="empty">${esc(t("prods_empty"))}</div>`}</div>`,
    JSON.stringify([L(), ps.map((p) => [p.id, p.state, p.stage])]));
  return { poll: ps.some((p) => p.state === "busy") ? 5000 : 0 };
};

// ---------------- #/u/<id>: one production as a flow ----------------
function flowRail(f, sel) {
  return `<ol class="hl-flow">${f.stages.map((s, i) => `<li class="hl-node st-${esc(s.status)} ${s.id === sel ? "sel" : ""}" data-act="hatSel" data-id="${esc(s.id)}">
      <span class="ic">${s.status === "running" ? '<span class="spin"></span>' : STATUS_ICON[s.status] || ""}</span>
      <span class="nm">${esc(s.name)}${s.gate ? ' <span class="lock" aria-hidden="true">🔒</span>' : ""}</span>
      <span class="tiny faint">${esc(t("st_" + s.status))}</span></li>${i < f.stages.length - 1 ? '<li class="hl-link" aria-hidden="true"></li>' : ""}`).join("")}</ol>`;
}
const link = (u) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(String(u).replace(/^https?:\/\/(www\.)?/, "").slice(0, 60))}</a>`;
function outResearch(o) {
  return `${o.insight ? `<div class="hl-big">${esc(o.insight)}</div>` : ""}
    ${o.misconception ? `<div class="note mt12"><b>${esc(t("misconception"))}:</b> ${esc(o.misconception)}</div>` : ""}
    ${(o.data_points || []).length ? `<h3 class="mt16">${esc(t("data"))}</h3><ul class="hl-ul">${o.data_points.map((x) => `<li>${esc(x.claim)}${x.value ? ` <span class="muted">— ${esc(x.value)}</span>` : ""}${x.source && /^https?:/.test(x.source) ? ` <span class="tiny">${link(x.source)}</span>` : ""}</li>`).join("")}</ul>` : ""}
    ${(o.angles || []).length ? `<h3 class="mt16">${esc(t("angles"))}</h3><ul class="hl-ul">${o.angles.map((x) => `<li><b>${esc(x.title)}</b> <span class="muted small">${esc(x.grounded_in || "")}</span></li>`).join("")}</ul>` : ""}
    ${(o.sources || []).length ? `<h3 class="mt16">${esc(t("sources"))}</h3><ol class="hl-ul small">${o.sources.map((x) => `<li>${esc(x.title || "")} ${link(x.url)}</li>`).join("")}</ol>` : ""}`;
}
function outProposal(o) {
  const c = o.cost || {};
  return `<h3>${esc(t("concepts"))}</h3><div class="hl-concepts">${(o.concepts || []).map((x) => `<div class="hl-concept ${x.id === o.chosen ? "on" : ""}">
      ${x.id === o.chosen ? `<span class="badge ok">${esc(t("chosen"))}</span>` : ""}<h4>${esc(x.title)}</h4>
      <div class="hl-hook">“${esc(x.hook)}”</div><div class="small mt8"><b>${esc(t("structure"))}:</b> ${esc(x.structure)}</div>
      <div class="small mt8"><b>${esc(t("look"))}:</b> ${esc(x.look)}</div>${x.key_frame ? `<div class="small mt8 muted"><b>${esc(t("key_frame"))}:</b> ${esc(x.key_frame)}</div>` : ""}</div>`).join("")}</div>
    <div class="kv mt16"><div>${esc(t("duration"))}</div><div>${esc(o.seconds)} ${esc(t("sec"))}</div><div>${esc(t("look"))}</div><div>${esc(o.look || "")}</div>
      <div>${esc(t("music"))}</div><div>${(o.music || {}).use ? esc(t("yes")) + " · " + esc((o.music || {}).prompt || "") : esc(t("no"))}</div>
      ${o.render_time ? `<div>${esc(t("render_time"))}</div><div>${esc(t("preview_t"))} ~${Math.round((o.render_time.preview_s || 0) / 60)} dk · ${esc(t("final_t"))} ~${Math.round((o.render_time.final_s || 0) / 60)} dk</div>` : ""}</div>
    <div class="costs mt12">${(c.lines || []).map((l) => `<div class="ln"><span class="muted">${esc(l.label || l.kind)}</span><b>~${num(l.credits)} ${esc(t("credits"))}</b></div>`).join("")}
      <div class="ln"><span>${esc(t("total"))}</span><b>~${num(c.credits)} ${esc(t("credits"))}</b></div></div>`;
}
function outScript(o) {
  const n = (o.lines || []).join(" ").split(/\s+/).filter(Boolean).length;
  return `<div class="tiny muted">${o.lines.length} ${esc(t("lines_n"))} · ${n} ${esc(t("words"))}</div>
    <ol class="hl-script">${(o.lines || []).map((l) => `<li>${esc(l)}</li>`).join("")}</ol>
    ${(o.claims || []).length ? `<h3 class="mt16">${esc(t("claims"))}</h3><ul class="hl-ul small">${o.claims.map((c) => `<li><span class="${c.verified ? "ok" : "bad"}">${c.verified ? "✓" : "✕"}</span> ${esc(c.text)}${c.source && /^https?:/.test(c.source) ? ` ${link(c.source)}` : ""}</li>`).join("")}</ul>` : ""}
    ${o.caption ? `<div class="mt12 small"><b>${esc(t("caption"))}:</b> ${esc(o.caption)}</div>` : ""}`;
}
function outScenes(o, s) {
  const pal = o.palette || {};
  return `${o.concept ? `<div class="hl-big small">${esc(o.concept)}</div>` : ""}
    <div class="hl-swatch mt8">${Object.entries(pal).map(([k, v]) => `<span title="${esc(k)}" style="background:${esc(v)}"></span>`).join("")}</div>
    ${(s.stills || []).length ? `<div class="hl-stills mt12">${s.stills.map((u, i) => `<figure><img loading="lazy" src="${esc(u)}" data-act="hatZoom" data-src="${esc(u)}" alt="">
      <figcaption class="tiny muted">${esc(((o.scenes || [])[i] || {}).id || "")} · ${esc(t("line_range", ...(((o.scenes || [])[i] || {}).lines || [0, 0]).map((x) => x + 1)))}</figcaption></figure>`).join("")}</div>`
      : `<div class="tiny faint mt12">${esc(t("no_stills"))}</div>`}`;
}
function player(u, wide) { return u ? `<div class="player ${wide ? "wide" : ""}"><video src="${esc(u)}" controls playsinline preload="metadata"></video></div>` : ""; }
function outAssets(o, s, f) {
  return `${player(o.preview_url, f.project.aspect === "16:9")}
    <div class="kv mt12"><div>${esc(t("voice"))}</div><div>${o.voice ? `${esc(o.voice.duration)} ${esc(t("sec"))} · ${num(o.voice.credits)} ${esc(t("credits"))}` : "—"}</div>
      <div>${esc(t("music"))}</div><div>${o.music ? esc(o.music.prompt || t("yes")) : esc(t("no"))}</div></div>`;
}
function outRender(o, s, f) {
  const tq = ((o.qa || {}).technical) || {};
  return `${player(o.final_url, f.project.aspect === "16:9")}
    ${o.final_url ? `<div class="row mt8"><a class="btn sm" href="${esc(o.final_url)}?dl=1">${ICON.download}${esc(t("download"))}</a></div>` : ""}
    <h3 class="mt16">${esc(t("qa"))}</h3><div class="small">${(tq.problems || []).length ? `<ul class="hl-ul">${tq.problems.map((p) => `<li class="warn">${esc(p)}</li>`).join("")}</ul>` : esc(t("no_problems"))}
      <div class="tiny muted mt8">${esc(tq.duration ?? "")} ${esc(t("sec"))} · ${esc(tq.lufs ?? "—")} LUFS · ${esc(tq.true_peak_db ?? "—")} dBTP</div></div>
    ${(o.cover_urls || []).length ? `<h3 class="mt16">${esc(t("covers"))}</h3><div class="hl-stills">${o.cover_urls.map((u) => `<figure><img src="${esc(u)}" alt=""></figure>`).join("")}</div>` : ""}`;
}
function outPublish(o, s, f) {
  const text = [o.caption, (o.hashtags || []).join(" ")].filter(Boolean).join("\n\n");
  const fin = (f.stages.find((x) => x.id === "compose") || {}).output || {};
  return `${player(fin.final_url, f.project.aspect === "16:9")}
    <div class="hl-big mt12">${esc(o.caption || "")}</div><div class="mt8">${(o.hashtags || []).map((h) => `<span class="chip">${esc(h)}</span>`).join(" ")}</div>
    <div class="row mt12"><button class="btn sm" data-act="copy" data-text="${esc(text)}">${ICON.copy}${esc(t("copy"))}</button>
      ${fin.final_url ? `<a class="btn sm" href="${esc(fin.final_url)}?dl=1">${ICON.download}${esc(t("download"))}</a>` : ""}</div>
    ${o.notes ? `<h3 class="mt16">${esc(t("notes"))}</h3><div class="small" style="white-space:pre-wrap">${esc(o.notes)}</div>` : ""}`;
}
function outCut(o) {
  return `${o.hook ? `<div class="hl-big">“${esc(o.hook)}”</div>` : ""}
    <div class="tiny muted mt8">${esc(o.raw_s)} → ${esc(o.kept_s)} ${esc(t("sec"))}</div>
    <ol class="hl-ul small mt8">${(o.phrases || []).map((x) => `<li class="${x.kept ? "" : "faint"}" style="${x.kept ? "" : "text-decoration:line-through"}">
      ${x.kept ? `<span class="badge ok">${esc(x.pos)}</span>` : `<span class="badge">${esc(t("cut_word"))}</span>`} ${esc(x.text)}
      ${(x.flags || []).length ? `<span class="tiny warn">${esc(x.flags.join(", "))}</span>` : ""}</li>`).join("")}</ol>
    ${(o.broll || []).length ? `<h3 class="mt16">B-roll</h3><ul class="hl-ul small">${o.broll.map((b) => `<li>${esc(b.kind)} · ${esc(b.text || "")}</li>`).join("")}</ul>` : ""}`;
}
function outPlates(o) {
  return `${o.concept ? `<div class="hl-big small">${esc(o.concept)}</div>` : ""}
    <div class="hl-stills mt12">${(o.plate_urls || []).map((u) => `<figure><img loading="lazy" src="${esc(u)}" data-act="hatZoom" data-src="${esc(u)}" alt=""></figure>`).join("")}</div>`;
}
function outCutPlan(o, s, f) {
  return `${player(o.preview_url, f.project.aspect === "16:9")}
    ${o.concept ? `<div class="hl-big small mt12">${esc(o.concept)}</div>` : ""}
    <div class="tiny muted mt8">${(o.shots || []).length} ${esc(t("shots"))} · ${esc(o.duration ?? "")} ${esc(t("sec"))}</div>
    <ol class="hl-ul small mt8">${(o.shots || []).map((x) => `<li><span class="mono tiny">${esc(x.clip || "")} ${esc(x.in ?? "")}–${esc(x.out ?? "")}</span>
      ${x.text ? ` <b>“${esc(x.text)}”</b>` : ""} <span class="muted">${esc(x.shows || "")}</span></li>`).join("")}</ol>
    ${(o.warnings || []).length ? `<h3 class="mt16">${esc(t("warnings"))}</h3><ul class="hl-ul small">${o.warnings.map((w) => `<li class="warn">${esc(w)}</li>`).join("")}</ul>` : ""}`;
}
function outShotList(o) {
  const c = o.cost || {};
  return `<div class="tiny muted">${(o.shots || []).length} ${esc(t("shots"))} · ${esc(o.seconds ?? "")} ${esc(t("sec"))}</div>
    <ol class="hl-ul small mt8">${(o.shots || []).map((x) => `<li>${x.kind === "gen"
      ? `<span class="badge warn">${esc(t("gen_shot"))} · ${esc(x.seconds)} ${esc(t("sec"))}</span> ${esc(x.frame || "")} <span class="muted">→ ${esc(x.prompt || "")}</span>`
      : `<span class="badge">${esc(t("own_shot"))}</span> <span class="mono tiny">${esc(x.clip_id || "")} ${esc(x.in ?? "")}–${esc(x.out ?? "")}</span> <span class="muted">${esc(x.shows || "")}</span>`}
      ${x.text ? ` <b>“${esc(x.text)}”</b>` : ""}</li>`).join("")}</ol>
    ${(c.lines || []).length ? `<div class="costs mt12">${c.lines.map((l) => `<div class="ln"><span class="muted">${esc(l.label)}</span><b>${l.credits == null ? "?" : "~" + num(l.credits)} ${esc(t("credits"))}</b></div>`).join("")}
      <div class="ln"><span>${esc(t("total"))}</span><b>~${num(c.credits)} ${esc(t("credits"))}</b></div></div>` : ""}`;
}
function styleCard(c) {
  return `<div class="hl-style on">${c.preview ? `<img src="${esc(c.preview)}" alt="">` : ""}<div><h4>${esc(t("style_now"))}: ${esc(c.name)}</h4>
      <div class="small">${esc(c.look)}</div><div class="hl-pal mt8">${(c.palette || []).map((h) => `<i style="background:${esc(h)}"></i>`).join("")}</div>
      <div class="tiny mt8"><b>${esc(t("style_type"))}:</b> ${esc(c.type)}</div><div class="tiny"><b>${esc(t("style_motion"))}:</b> ${esc(c.motion)}</div>
      <div class="tiny"><b>${esc(t("style_sound"))}:</b> ${esc(c.sound)}</div><div class="tiny muted"><b>${esc(t("style_avoid"))}:</b> ${esc(c.avoid)}</div></div></div>`;
}
function styleLib(s) {
  const now = (s.style || {}).id;
  const gate = s.status === "awaiting_approval";
  return `<h3 class="mt16">${esc(t("style_lib"))}</h3>${s.style ? styleCard(s.style) : ""}
    <div class="hl-styles mt12">${(HS.styles || []).map((c) => `<div class="hl-style-t ${c.id === now ? "on" : ""}" title="${esc(c.look)}">
      ${c.preview ? `<img src="${esc(c.preview)}" alt="">` : ""}<div class="tiny"><b>${esc(c.name)}</b></div>
      ${gate && c.id !== now ? `<button class="btn sm block mt8" data-act="hatStyle" data-style="${esc(c.id)}" data-stage="${esc(s.id)}">${esc(t("style_pick"))}</button>` : ""}</div>`).join("")}</div>`;
}
const OUT = { research: outResearch, proposal: outProposal, script: outScript, scene_plan: outScenes, assets: outAssets,
  render: outRender, publish: outPublish, cut_plan: outCutPlan, cut: outCut, plates: outPlates, shot_list: outShotList };
function outputHtml(s, f) {
  const o = s.output;
  if (!o) return `<div class="tiny faint">${esc(s.status === "pending" ? t("waiting_prev") : t("output_none"))}</div>`;
  const fn = OUT[s.artifact];
  if (fn && s.style_pick) return fn(o, s, f) + styleLib(s);
  return fn ? fn(o, s, f) : `<pre class="log">${esc(JSON.stringify(o, null, 1).slice(0, 4000))}</pre>`;
}
function reviewHtml(r) {
  if (!r) return "";
  const v = r.verdict === "pass" ? "ok" : r.verdict === "fix" ? "bad" : "";
  return `<div class="card"><h3>${esc(t("review"))} <span class="badge ${v}">${esc(t("verdict_" + (r.verdict || "unknown")))}</span>
      ${r.rounds ? `<span class="tiny faint">${esc(t("rounds", r.rounds))}</span>` : ""}</h3>
    ${r.summary ? `<div class="small">${esc(r.summary)}</div>` : ""}
    ${(r.findings || []).map((x) => `<div class="hl-find sev-${esc(x.severity)} mt8"><span class="badge">${esc(t("sev_" + x.severity))}</span>
      <div class="small"><b>${esc(x.item || "")}</b> ${esc(x.problem || "")}</div>${x.fix ? `<div class="tiny muted">→ ${esc(x.fix)}</div>` : ""}</div>`).join("")}
    ${r.error ? `<div class="tiny faint">${esc(r.error)}</div>` : ""}</div>`;
}
function decisionHtml(s, f) {
  const id = esc(s.id);
  if (f.state === "archived") return `<div class="card hl-dec"><h3>${esc(t("state_archived"))}</h3><div class="small muted">${esc(t("archived_note"))}</div></div>`;
  if (s.status === "running") return `<div class="card hl-dec"><h3><span class="spin"></span> ${esc(t("working"))}</h3><div class="small muted">${esc(s.says)}</div></div>`;
  if (s.status === "awaiting_approval") return `<div class="card hl-dec gate"><h3>🔒 ${esc(t("decision"))}</h3>
      ${s.summary ? `<div class="small">${esc(s.summary)}</div>` : ""}${s.gate_says ? `<div class="tiny muted mt8">${esc(s.gate_says)}</div>` : ""}
      <button class="btn accent block mt12" data-act="hatAct" data-a="approve" data-stage="${id}">${ICON.check}${esc(t("continue"))}</button>
      <label class="field mt16"><span>${esc(t("feedback"))} · <span class="faint">${esc(t("revisions", s.revisions || 0))}</span></span>
        <textarea id="hlNote" data-keep="hl-note-${id}" placeholder="${esc(t("fb_ph"))}"></textarea></label>
      <button class="btn block mt8" data-act="hatAct" data-a="feedback" data-stage="${id}" ${(s.revisions || 0) >= 3 ? "disabled" : ""}>${esc(t("redo"))}</button></div>`;
  if (s.status === "failed") return `<div class="card hl-dec bad"><h3>${esc(t("error"))}</h3><pre class="log">${esc(s.error || "")}</pre>
      <button class="btn accent block mt12" data-act="hatAct" data-a="retry" data-stage="${id}">${esc(t("retry"))}</button>
      <textarea id="hlNote" class="mt12" data-keep="hl-note-${id}" placeholder="${esc(t("fb_ph"))}"></textarea>
      <button class="btn block mt8" data-act="hatAct" data-a="feedback" data-stage="${id}">${esc(t("redo"))}</button></div>`;
  if (s.status === "approved" || s.status === "done") {
    const busy = f.stages.some((x) => x.status === "running");
    return `<div class="card hl-dec"><h3>${esc(t("st_" + s.status))}</h3>${s.summary ? `<div class="small">${esc(s.summary)}</div>` : ""}
      ${busy ? "" : `<button class="btn ghost block mt12" data-act="hatAct" data-a="back" data-stage="${id}">${ICON.back}${esc(t("go_back"))}</button><div class="tiny faint mt8">${esc(t("back_warn"))}</div>`}</div>`;
  }
  if (f.state === "run" && f.current === s.id && s.run !== "planned") return `<div class="card hl-dec"><button class="btn accent block" data-act="hatAct" data-a="advance" data-stage="${id}">${esc(t("start_stage"))}</button></div>`;
  return `<div class="card hl-dec"><div class="small muted">${esc(s.run === "planned" ? t("not_built") : t("waiting_prev"))}</div></div>`;
}
function eventText(e, f) {
  const nm = (sid) => ((f.stages.find((x) => x.id === sid) || {}).name || sid || "");
  const k = "ev_" + e.kind;
  if (!(k in TX.tr)) return "";
  if (e.kind === "tool" || e.kind === "tool_error") return t(k, e.tool || "");
  if (e.kind === "agent_start" || e.kind === "review") return t(k, e.model || "");
  return t(k, nm(e.stage));
}
function eventsHtml(f) {
  const rows = f.events.slice().reverse().map((e) => [e, eventText(e, f)]).filter(([, x]) => x).slice(0, 18);
  return `<div class="card"><h3>${esc(t("live"))}</h3><div class="hl-ev">${rows.map(([e, x]) => `<div><time>${esc(dt(e.at))}</time><span>${esc(x)}${e.seconds != null && e.kind !== "tool" ? ` <span class="faint">${e.seconds}s</span>` : ""}</span></div>`).join("")}</div>
    <div class="tiny muted mt8">${esc(t("spent"))}: ${num(f.spent.credits)} ${esc(t("credits"))} · $${(f.spent.usd || 0).toFixed(2)}</div></div>`;
}
async function viewProject(pid) {
  const f = await api("/api/hat/project/" + encodeURIComponent(pid));
  if (f.stages.some((x) => x.style_pick) && (!HS.styles || HS.styles_lang !== L())) {
    HS.styles = await api("/api/hat/styles"); HS.styles_lang = L();
  }
  const p = f.project;
  crumb([t("nav_prods"), p.title]);
  const sel = HS.sel[pid] && f.stages.some((x) => x.id === HS.sel[pid]) ? HS.sel[pid] : (f.current || f.stages[f.stages.length - 1].id);
  const s = f.stages.find((x) => x.id === sel);
  const html = `<div class="row"><a class="btn ghost sm" href="#/uretimler">${ICON.back}${esc(t("back_list"))}</a><span class="sp"></span>
      <span class="badge">${esc(f.line.name)}</span><span class="badge">${esc((p.video_lang || "").toUpperCase())}</span><span class="badge">${esc(p.aspect || "")}</span>${stateBadge(f.state)}</div>
    <h1 class="mt12">${esc(p.title)}</h1>${p.brief ? `<div class="lead hl-brief">${esc(p.brief)}</div>` : ""}
    ${flowRail(f, sel)}
    <div class="split mt16"><div class="col" style="gap:14px"><div class="card"><div class="row"><h2 style="margin:0">${esc(s.name)}</h2><span class="sp"></span>
        <span class="badge hl-sb st-${esc(s.status)}">${esc(t("st_" + s.status))}</span></div><div class="small muted mt8">${esc(s.says)}</div>
        ${s.note ? `<div class="note mt12 small"><b>${esc(t("feedback"))}:</b> ${esc(s.note)}</div>` : ""}<div class="mt16">${outputHtml(s, f)}</div></div></div>
      <div class="col sticky" style="gap:14px">${decisionHtml(s, f)}${reviewHtml(s.review)}${eventsHtml(f)}</div></div>`;
  const busy = f.state === "busy" || f.stages.some((x) => x.status === "running");
  paint(html, JSON.stringify([L(), sel, f.state, f.current, f.stages.map((x) => [x.status, x.revisions]), f.events.length]));
  return { poll: busy ? 4000 : 0 };
}
ROUTE_RX.push([/^#\/u\/([\w-]+)/, viewProject]);
// ---------------- film styles: the library and the creator's own (factory/filmstyles.py, factory/ownstyles.py) ----------------
async function viewStyles() {
  crumb([t("nav_fstyles")]);
  const [lib, own] = await Promise.all([api("/api/hat/styles"), api("/api/hat/ownstyles")]);
  const mine = own.filter((x) => x.status !== "approved");
  const tile = (c) => `<div class="hl-style-t">${c.preview ? `<img src="${esc(c.preview)}" alt="" data-act="open" data-src="${esc(c.preview)}" data-photo="1">` : ""}
      <div class="tiny"><b>${esc(c.name)}</b></div><div class="tiny muted">${esc(c.look)}</div><div class="hl-pal mt8">${(c.palette || []).map((h) => `<i style="background:${esc(h)}"></i>`).join("")}</div>
      <button class="btn sm block mt8" data-act="fsBase" data-id="${esc(c.id)}">${esc(t("fs_change"))}</button></div>`;
  const ownTile = (s) => `<a class="hl-style-t" href="#/film-stilleri/${esc(s.id)}">${s.sample ? `<img src="${esc(s.sample)}" alt="">` : `<div class="hl-pal">${(s.palette || []).map((h) => `<i style="background:${esc(h)}"></i>`).join("")}</div>`}
      <div class="tiny"><b>${esc(s.name)}</b></div><span class="badge ${s.status === "approved" ? "ok" : "warn"}">${esc(t("fs_" + s.status))}</span></a>`;
  paint(`<h1>${esc(t("nav_fstyles"))}</h1><p class="lead">${esc(t("fs_lead"))}</p>
    <div class="card mt16"><h3>${esc(t("fs_new"))}</h3><div class="row">
      <label class="field" style="flex:1;min-width:200px"><span>${esc(t("fs_name"))}</span><input id="fsName" data-keep="fs-name" type="text" maxlength="40"></label>
      <label class="field" style="flex:1;min-width:200px"><span>${esc(t("fs_base"))}</span><select id="fsBase"><option value="blank">${esc(t("fs_blank"))}</option>
        ${lib.map((c) => `<option value="${esc(c.id)}" ${HS.fsBase === c.id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label></div>
      <button class="btn accent mt12" data-act="fsCreate">${esc(t("fs_create"))}</button><div class="tiny faint mt8">${esc(t("fs_no_cost"))}</div></div>
    ${mine.length ? `<h2>${esc(t("fs_own"))}</h2><div class="hl-styles">${mine.map(ownTile).join("")}</div>` : ""}
    <h2>${esc(t("fs_lib"))}</h2><div class="hl-styles wide">${lib.map((c) => c.id.startsWith("own_") ? ownTile(own.find((x) => x.id === c.id) || c) : tile(c)).join("")}</div>`,
    JSON.stringify([L(), lib.length, own.map((x) => [x.id, x.status, x.sample])]));
  return { poll: 0 };
}
function fsQuestion(st, q) {
  const v = q.value;
  if (q.kind === "text") return `<textarea id="fsVal" rows="3">${esc(v || "")}</textarea>`;
  if (q.kind === "colors") return `<input id="fsVal" type="text" value="${esc((v || []).join(", "))}" placeholder="#f4eee2, #0078bf, #ff48b0">
      <div class="hl-pal mt8">${(v || []).map((h) => `<i style="background:${esc(h)}"></i>`).join("")}</div>`;
  if (q.kind === "font") return `<select id="fsVal">${st.fonts.map((f) => `<option ${f === v ? "selected" : ""} style="font-family:'${esc(f)}'">${esc(f)}</option>`).join("")}</select>
      <div class="mt8" style="font:400 34px '${esc(v)}'">Aa Ğğ Şş İı 123</div>`;
  if (q.kind === "texture") return `<div class="chips">${st.textures.map((x) => `<span class="chip ${x.id === v ? "on" : ""}" data-act="fsPick" data-v="${esc(x.id)}">${esc(x.name)}</span>`).join("")}</div>`;
  if (q.kind === "logo") return `<label class="drop">${esc(st.logo ? t("fs_logo_ok") : t("fs_logo_up"))}<input type="file" id="fsLogo" accept="image/png,image/jpeg,image/webp" style="display:none"></label>`;
  return `<textarea id="fsVal" rows="4" placeholder="Mira: kısa kızıl saç, sarı yağmurluk">${esc((v || []).map((c) => c.name + ": " + c.look).join("\n"))}</textarea>`;
}
async function viewOwnStyle(sid) {
  const st = await api("/api/hat/ownstyle/" + encodeURIComponent(sid));
  crumb([t("nav_fstyles"), st.name]);
  const qs = st.questions.filter((q) => q.step === "plan" || q.step === "brand");
  const at = Math.min(HS.fsQ[sid] ?? Math.max(0, qs.findIndex((q) => st.missing.includes(q.id))), qs.length);
  const step = at < qs.length ? qs[at].step : (st.status === "draft" ? "sample" : "approve");
  const base = (st.bases.find((b) => b.id === st.base) || {}).name || t("fs_blank");
  const rail = `<div class="chips mt12">${st.steps.map((s, i) => `<span class="chip ${s === step ? "on" : ""}">${st.steps.indexOf(step) > i ? "✓" : i + 1} · ${esc(t("fs_st_" + s))}</span>`).join("")}</div>`;
  let body;
  if (at < qs.length) {
    const q = qs[at];
    body = `<div class="card"><div class="tiny muted">${at + 1} / ${qs.length}</div><h3>${esc(q.q)}</h3>${fsQuestion(st, q)}
      <div class="row mt12">${at ? `<button class="btn ghost" data-act="fsGo" data-to="${at - 1}">${esc(t("fs_prev"))}</button>` : ""}<span class="sp"></span>
        ${q.optional ? `<button class="btn ghost" data-act="fsGo" data-to="${at + 1}">${esc(t("fs_skip"))}</button>` : ""}
        ${q.kind === "logo" || q.kind === "texture" ? `<button class="btn accent" data-act="fsGo" data-to="${at + 1}">${esc(t("fs_next"))}</button>`
          : `<button class="btn accent" data-act="fsAnswer" data-q="${esc(q.id)}" data-to="${at + 1}">${esc(t("fs_next"))}</button>`}</div></div>`;
  } else {
    const busy = HS.fsBusy === sid && st.status === "draft";
    body = `<div class="card"><h3>${esc(t("fs_st_sample"))}</h3>
      ${st.sample ? `<img class="hl-sample" src="${esc(st.sample)}" alt="">` : ""}
      ${st.missing.length ? `<div class="small bad">${esc(t("fs_need", st.missing.join(", ")))}</div>` : ""}
      ${st.sample && st.status === "draft" ? `<div class="tiny muted mt8">${esc(t("fs_stale"))}</div>` : ""}
      ${st.status === "approved" ? `<div class="small mt8">${esc(t("fs_in_lib"))}</div>` : ""}
      <div class="row mt12"><button class="btn ghost" data-act="fsGo" data-to="0">${esc(t("fs_prev"))}</button><span class="sp"></span>
        ${busy ? `<span class="small"><span class="spin"></span> ${esc(t("fs_drawing"))}</span>` : st.missing.length ? "" : `<button class="btn ${st.status === "draft" ? "accent" : ""}" data-act="fsSample">${esc(st.sample ? t("fs_redraw") : t("fs_draw"))}</button>`}
        ${st.status === "sampled" ? `<button class="btn accent" data-act="fsApprove">${ICON.check}${esc(t("fs_approve"))}</button>` : ""}</div>
      <div class="tiny faint mt8">${esc(t("fs_no_cost"))}</div></div>`;
  }
  paint(`<div class="row"><a class="btn ghost sm" href="#/film-stilleri">${ICON.back}${esc(t("nav_fstyles"))}</a><span class="sp"></span>
      <span class="badge ${st.status === "approved" ? "ok" : "warn"}">${esc(t("fs_" + st.status))}</span>
      <button class="btn sm ghost danger" data-act="fsDelete">${ICON.trash}${esc(t("fs_delete"))}</button></div>
    <h1 class="mt12">${esc(st.name)}</h1><div class="small muted">${esc(t("fs_based", base))}</div>${rail}
    <div class="split mt16"><div class="col">${body}</div><div class="col sticky"><div class="card"><div class="hl-pal">${st.palette.map((h) => `<i style="background:${esc(h)}"></i>`).join("")}</div>
      ${st.questions.filter((q) => q.kind === "text" && q.value).map((q) => `<div class="tiny mt8"><b>${esc(q.q.split(/[?:.]/)[0])}:</b> ${esc(q.value)}</div>`).join("")}</div></div></div>`,
    JSON.stringify([L(), at, st.status, st.sample, st.updated, HS.fsBusy]));
  return { poll: HS.fsBusy === sid && st.status === "draft" ? 4000 : 0 };
}
ROUTE_RX.push([/^#\/film-stilleri\/(own_[\w]+)/, viewOwnStyle]);
ROUTES["#/film-stilleri"] = viewStyles;
const fsId = () => location.hash.split("/")[2];
const fsPost = (b) => post("/api/hat/ownstyle/" + encodeURIComponent(fsId()), b);
const fsRedraw = () => { S.sig = null; route({ poll: true }); };
ACT.fsBase = (el) => { HS.fsBase = el.dataset.id; const s = $("#fsBase"); if (s) s.value = el.dataset.id; const n = $("#fsName"); if (n) { n.focus(); n.scrollIntoView({ block: "center" }); } };
ACT.fsCreate = async () => {
  const st = await post("/api/hat/ownstyles", { name: ($("#fsName") || {}).value || "", base: ($("#fsBase") || {}).value || "blank" });
  S.drafts = {}; location.hash = "#/film-stilleri/" + st.id;
};
ACT.fsGo = (el) => { HS.fsQ[fsId()] = +el.dataset.to; fsRedraw(); };
ACT.fsAnswer = async (el) => {
  await fsPost({ action: "answer", q: el.dataset.q, value: ($("#fsVal") || {}).value || "" });
  HS.fsQ[fsId()] = +el.dataset.to; fsRedraw();
};
ACT.fsPick = async (el) => { await fsPost({ action: "answer", q: "texture", value: el.dataset.v }); fsRedraw(); };
ACT.fsSample = async () => { await fsPost({ action: "sample" }); HS.fsBusy = fsId(); toast(t("fs_drawing")); fsRedraw(); };
ACT.fsApprove = async () => { await fsPost({ action: "approve" }); HS.fsBusy = null; toast(t("fs_saved")); fsRedraw(); };
ACT.fsDelete = async () => { if (!confirm(t("fs_del_q"))) return; await fsPost({ action: "delete" }); location.hash = "#/film-stilleri"; };
document.addEventListener("change", async (e) => {
  if (e.target.id !== "fsLogo" || !e.target.files[0]) return;
  const r = await upload("/api/refs/upload", e.target.files[0], { "X-Logo": "1" }, () => {});
  await fsPost({ action: "answer", q: "logo", value: r.file }); toast(t("fs_logo_ok")); fsRedraw();
});

ACT.hatSel = (el) => { const pid = location.hash.split("/")[2]; HS.sel[pid] = el.dataset.id; S.sig = null; route({ poll: true }); };
ACT.hatZoom = (el) => openVideo(el.dataset.src, true);
ACT.hatStyle = async (el) => {
  const pid = location.hash.split("/")[2];
  el.disabled = true;
  try {
    await post("/api/hat/project/" + encodeURIComponent(pid), { action: "feedback", stage: el.dataset.stage, note: "style: " + el.dataset.style });
    toast(t("style_set")); S.sig = null; route({ poll: true });
  } finally { el.disabled = false; }
};
ACT.hatAct = async (el) => {
  const pid = location.hash.split("/")[2], a = el.dataset.a, stage = el.dataset.stage;
  const note = ($("#hlNote") || {}).value || "";
  el.disabled = true;
  try {
    await post("/api/hat/project/" + encodeURIComponent(pid), { action: a, stage, note });
    toast(t({ approve: "approved_ok", feedback: "note_sent", back: "back_ok", retry: "working", advance: "approved_ok_start" }[a]));
    if (a !== "back") delete HS.sel[pid];
    S.drafts = {}; S.sig = null; route({ poll: true });
  } finally { el.disabled = false; }
};
})();
