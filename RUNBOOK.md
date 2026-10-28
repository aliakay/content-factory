# Content Factory — runbook

The user's short-form video studio on this VM. I act as their **social-media expert, content creator and
video editor**: I propose ideas, get approval, edit/render, QA, and hand over videos + captions.
On-screen text is **English**, market is **global**, channel is travel-first (TikTok + YouTube Shorts + Reels).

## Studio (main panel since 2026-10-26)
http://100.98.58.82:8501 — `studio/server.py` + `studio/index.html` (stdlib, Turkish UI, tailnet-only, POSTs need
`X-Studio: 1`). Kept up by `bin/start-factory.sh` (cron), which also runs the old Streamlit panel on **:8503**
(clips, Reference Lab, brand kit). Log: `data/studio.log`. index.html is read per request; restart the server
(find the PID with `ps`, never `pkill -f`) after Python changes.
Pages: Pano (waiting-for-you list, jobs, iCloud ingest) · Üret (format + places + brief → ideas) · Üretim hattı ·
production detail (storyboard, edits, decisions) · Takip (posts + stats) · Videolar (out/) · Akışlar (formats) ·
Sinyaller (radar travel/psychology, trends) · Bütçe (ElevenLabs ledger + rates) · Yerler (rename GPS places).

**Production flow** (`factory/productions.py`, table `productions`; formats in `factory/formats.py`):
idea → (voice: estimate shown, user approves → `eleven.tts(..., approved=)` + faster-whisper alignment) → preview
(cinecut `--preview`, veryfast) → approve → final render to `out/<name>/` + QA (technical + Sonnet visual) → ready →
publish link → published. `data` is the source of truth; `timeline()` compiles it to a cinecut spec (shots cut on
spoken-line starts, short clips pass time to neighbours, lint warnings). Revisions: Claude edits `data` from the
user's note (`p_revise`); manual edits via the page. Unverified claims block the final render unless forced.
Jobs: `p_ideas`, `p_voice`, `p_preview`, `p_render`, `p_revise`, `p_verify`, `yt_stats` (see factory/jobs.py).
**Credit guard:** `credits.guard()` refuses any ElevenLabs generation without an approved amount, above approval
+15 %, or over the monthly cap — keep passing `approved=` from a real user approval.
**Tracking** (`factory/tracking.py`, tables `posts`, `post_stats`): YouTube stats via the API key (server refreshes
every 6 h); TikTok/Instagram numbers are typed in (source=manual). Own results feed the idea prompt (`own_results`).
101–103 were imported as ready productions; 102/103 voice timings re-aligned from their mp3s.

## Reference-styled ("CapCut-like") edits (2026-10-26)
**2026-10-27: art director role.** The user wants Claude to art-direct footage videos (research -> brief -> own choice of design, edit and effects), not to copy references or just join clips with text. The factory does it itself: `factory/artdirector.py` (research incl. Chromium `motion/browse.mjs`, brief, effects, self-check, growing skill library `data/art/`); details in `ART_PLAYBOOK.md`.
The user wants edits that follow reference reels, not only the calm cut. **Reference library**: Studio → Referanslar
(upload from the phone, or files dropped in `~/tiktok/referance videolar - gezi vlog manzara motivasyon /` or
`refs/`). Job `ref_lib` (`refs.scan_library` + `refs.describe_recipes`): cuts, shot stats, BPM, a 2 fps frame grid
(`work/refgrids/`) and a Sonnet-written **recipe** in our editor's vocabulary (frame, grade, pace, transitions, layer
types, music feel) plus an `unsupported` list = the roadmap of effects we can't render yet.
Attach 1-3 refs at generation (Üret) or later on a production (set_refs → Claude re-edits in that style). A production
with `data.look` is **styled** (`factory/styled.py`): shots get whole `beats` at `look.bpm` (or the real beats of a
generated music take), a `title_card`, per-shot `layer`s and an `outro`; it compiles to **`bin/stylecut.py`**:
frame full/letterbox/scope, grades natural/film/golden/moody/vivid/mono + grain/vignette, push-ins, enter/exit
cut/flash/dip/whip/glitch, text layers from `motion/templates/overlay.html` (title_serif, title_bold, scramble,
editorial, words, quote, pin, hook, caption) rendered to ProRes alpha by `motion/render.mjs`, music + ambience + voice
mix. Demos: `specs/style/demo_a_como_euro_summer.json`, `demo_b_bavaria_motivation.json` (out/). Fonts (OFL) in fonts/.
Render cost on this 4-CPU VM: ~2 min overlay + ~2-4 min encode for a 20 s video.
**Music**: every production has a Müzik card (ElevenLabs Music v2.5 ≈ 47 credits/s, estimate + user approval, job
`p_music` → `factory/beats.py` beats → re-preview on the beats). Video-to-Music exists but its price is unmeasured.
**Voices/avatar**: `data/eleven_profile.json` (own voices: EN clone vhP2LOWrrIsWMq4m2vP6, TR pL1bBpEC0b6gDqEfoyV1;
avatar flow xLvSOpWpKFvR2Y43D4JB where the user places their avatar via the Avatar Picker; job `avatar_check`).
**Canvas**: every production has `data.aspect` "9:16" (default) or "16:9" (formats.ASPECTS); chosen in Üret or on the
production page (finished videos get a copy in the other canvas instead of being changed). Both renderers cover-crop
the footage; on 16:9 stylecut's "letterbox" becomes the 2.39:1 band. Idea/revision prompts get `canvas_note()`.
Python packages: no pip on this VM — use `~/.local/bin/uv pip install --python .venv/bin/python <pkg>` (librosa
installed this way).

## Faceless explainer short — topic mode (built 2026-10-27)
Format `explainer_short` (Studio → Üret → "Konu anlatımı (çekimsiz)"): the user gives a **topic**, nothing else. ~30 s,
9:16, no footage. Code: `factory/explainer.py` (research/script/scene plan, word alignment, scene compiler) +
`bin/explainer.py` (Pillow frames → ffmpeg, ~25 s render for 27 s at 30 fps; `--preview` = 540x960 @15 fps ~12 s;
`python bin/explainer.py <spec.json> --still 1.5 9.0` writes test PNGs to work/explainer/<name>/).
Flow (production `data.kind == "explainer"`; the shared Studio steps run it unchanged):
1. **Üret**: job `p_ideas` → `explainer.generate`: headless Claude with WebSearch/WebFetch researches the topic
   (primary source first, 2+ independent), returns `facts` (claim + source URL), the script (75-85 words, one sentence =
   one `voice.lines` entry), 4-6 scenes (`lines:[first,last]`, ≤3 elements, trigger words) and post copy.
   `claims` = the facts, so the normal **Doğrula** step re-checks them; unverified claims block the final render.
2. **Ses**: same credit guard (estimate shown, approval needed; ~1.15 credits/char eleven_v4, ≈550 credits for 85 words,
   voice "Ali" unless changed). `make_voice` also stores per-word times (`voice_take.words`, faster-whisper matched to
   the script) — Scribe is not needed.
3. **Preview/render**: `explainer.compile_spec` turns scenes + word times into `specs/explainer/<name>.json`
   (elements pop at their trigger word's start; scenes cut on sentence starts; first hook element is already visible at
   frame 0 for the cover). Elements: label, title, hero (per-letter stagger), text, stat_card, counter, bars, checks,
   strike, price, cta (pulse ring), source line; kinetic captions (≤3 words/≤16 chars, one teal active word).
   Layout/tokens follow the spec: header pill y≈200, visual area 300-1250, source y≈1262, captions y≈1600.
4. QA: shared `qa.review` (+ `explainer.QA_NOTES` so the critic knows the layout is intentional), then publish tracking.
Revisions (`p_revise`) re-run Claude on the current data; the line count must stay equal to the scenes' ranges when
editing the script by hand (otherwise ask Claude via "değişiklik iste"). Optional music card works (mixed at -22 dB).
**Not built yet:** automatic trend scan + scored pitches (0a-0c; the user gives the topic by hand today), avatar PiP (6b;
needs the avatar flow + a price check), 16:9 canvas for this format.

### Explainer: language, backgrounds, looks (2026-10-27, later)
- **Language follows the voice** (`data.lang` from `eleven_profile.json` voice language): a Turkish voice → Turkish script, on-screen
  text, header, caption; Turkish whisper model for alignment; Turkish upper-casing in the renderer. Changing the voice to
  another language queues a free `p_revise` rewrite. **Restart the Studio (find the PID with `ps`) after Python changes** — a
  stale server showed a fixed bug.
- **Backgrounds** (`scene.bg`): `clip` = a library clip (muted, looped, cover-cropped) or `image` = open-licence photo from
  Wikimedia Commons via `factory/stock.py` (CC0 / PD / CC BY / CC BY-SA only, cached in `assets/stock/` + `data/stock_cache.json`).
  Credit lines go into `data.credits` and the post notes; the storyboard shows each scene's picture + author/licence/link
  (`/media/stock/<file>`). Darkened (tech) or washed with cream (paper), slow push-in.
- **Looks** (`data.look_pack`, chips in Üret and on the production page, `set_look` action, render-only so no Claude call):
  `tech` (dark navy/teal) and `paper` = Vox register distilled from github.com/Cele-san/vox-style-animation and
  github.com/charlie947/motion-graphics-skills (both MIT; read online, nothing installed): cream paper `#f2ecdf`, ink `#161513`,
  ONE yellow `#ffd200` highlighter swipe per scene, red `#e5483f` = old world / negation, cobalt `#2f5fe8` = new capability;
  hard offset shadows, cards crooked ±0.4-0.8°, slap-in 1.15→1 on power3.out (no bounce), paper grain, halftone dots stepping at
  12 fps, nothing glows, sheet-wipe as the only transition (0.4 s, in-out so the seam is covered). Rules kept for BOTH looks: facts first
  (every number in `facts`), question/hook visible in 3 s, one frame per scene QA, no invented numbers, motion explains never decorates.
  `claudemotion` (npm, paid third-party plan + browser login) was NOT installed: unrelated to this renderer.

## Daily discovery — Keşif (built 2026-10-27, plan Phase 2)
`factory/discover.py`: free feeds (HN via hnrss, Ars/BBC/ScienceDaily/Nature RSS, Google News RSS queries, Wikipedia top
pageviews as a boost) -> token-overlap dedupe into candidates (48 h window, `exclude` topics dropped; single-source kept only
for science or with a Wikipedia signal) -> ONE headless Claude call (no web, ~$0.08) scores + writes idea cards with accuracy
`flags` -> tables `disc_runs`, `disc_cards`. Studio -> Keşif lists the cards; "Bunu üret" queues `p_ideas` for
`explainer_short` with the card as the topic brief (research + script follow, voice credits still need approval); "Geç" skips.
**Tags (2026-10-28):** every category has a `region`: **Global** (ai, tech, science, finance, world, papers; cards in
English) or **Türkiye** (`tr_gundem`, `tr_spor`, `tr_tech`; cards in Turkish, `topic` brief stays English). Türkiye feeds:
Google News TR topic pages (NATION/SPORTS/TECHNOLOGY, many publishers = cross-coverage), AA, TRT Haber, BBC Türkçe, DW
Türkçe, Euronews TR, Hürriyet, Webtekno, ShiftDelete, DonanımHaber, Chip; signals: tr.wikipedia top views + Google Trends
TR RSS (`signals.trend_term`). Turkish keyword exclude list in `REGIONS["tr"]["exclude"]` (crime, tragedy, elections, gossip).
Dead/empty when tested: NTV RSS, NTVSpor, Fanatik, Fotomaç (stale), Hürriyet Daily News. One run (one Sonnet call,
~$0.08-0.14) per region in a scan; `disc_runs.scope` = "global" / "tr:tr_spor" ...; Keşif shows the newest run per
category, with Tümü / Global / Türkiye tabs ("Şimdi tara" scans the selected tag).
Cron, one job per topic (UTC): tr_gundem 05:40 · global 07:30 · tr_spor 08:10 + 20:30 (match nights) · tr_tech 10:20 (`data/discover_cron.log`).
Manual: `python -m factory.discover [--region global|tr] [--only tr_spor,tr_tech]` or Keşif -> Şimdi tara (job kind `discover`).
Niches/quotas: `discover.NICHES`. Not built: embeddings dedupe, papers sub-pipeline (EurekAlert RSS URLs 404), finance/sports APIs,
push/email delivery, style system (plan Phases 4-6), engine refactor (Phase 1).

## Custom looks from reference images — Stiller (built 2026-10-27, plan Phase 4 Level 1)
`factory/styles.py`: Üret → Görünüm → "＋ Referans görselinden stil" (PNG/JPG/WEBP upload, optional note) → job `style_extract`:
median-cut palette + Claude vision assigns roles (bg, text, muted, accent, hot, hero, paper|lit) → WCAG contrast nudge →
`data/styles/<id>/style.json` (+ private copies of the refs). Look id `custom:<id>`; `compile_spec` embeds the theme in the spec
(`spec.theme`), `bin/explainer.py` registers it. Works wherever `look_pack` is chosen (Üret, production page `set_look`).
Limits: tokens only (colours + paper/lit flavour); layout, typography, motion, the yellow highlighter swipe (still hardcoded
YELLOW) and video refs (keyframes) are not extracted yet; no still-approval gate.

## Opus motion design — "✨ Otomatik" look (built 2026-10-27, replaces the palette-only art direction)
Üret → Görünüm → Otomatik (`look_pack == "auto"`): at the first preview `factory/motiondesign.py` has Opus (WebSearch/WebFetch: no logins,
no gallery scraping, nothing downloaded; refs are inspiration only) research references and then WRITE every scene itself as
HTML/CSS/GSAP (block format `@@META/@@SCENE/@@HTML/@@CSS/@@JS`, not JSON), plus `stock` requests for open-licence Wikimedia photos
(`{{img:ID}}`). Loop: free Chromium stills of every scene -> Opus Reads them + JS errors and fixes (1 round since 2026-10-27; a 2nd round cost ~$0.7–0.85 and found nothing new) -> `data/auto/<prod>/design.json`;
`data.motion` holds concept, refs, shots, cost; `look_pack` becomes `html`. Render: `bin/htmlmotion.py` (spec.engine "html") builds
`work/auto/<name>/bundle.json` (design + scene/word/line timings) and `motion/render.mjs` captures `motion/templates/explainer_shell.html`
(CSP blocks network; one paused GSAP master timeline; scene JS gets `tl, root, T, gsap, $`; `T.at("word")` = spoken time; shell draws the
kinetic captions) at 30 fps (preview 15 fps @ 0.5 scale), then ffmpeg mixes voice/music. Studio production page shows concept, stills,
refs and "Yeniden tasarla (not yaz)" (`redesign` action). A script revision drops the design and redesigns (look back to auto).
First real test (Berlin script, draft timing): ~$2 of Opus, build + preview ~12 min; produced a ballot + vote bars + a 153-seat hemicycle.
Limits: one design per video (no side-by-side candidates), final render is slower than the Pillow engine (~4-6 min), design quality varies
(the design now runs right after the script, in the p_ideas job / `p_design`, so the stills are visible BEFORE voice approval; the first preview only retries it if it failed). Old Pillow looks
(tech/paper/custom styles) still work and are cheaper. `factory/artdirect.py` (palette-only directions) is unused now.

## When the user sends an iCloud shared-album link
1. Check the panels are up (`curl -s -o /dev/null -w '%{http_code}' http://100.98.58.82:8501/`, same for `:8095`);
   start the factory with `bin/start-factory.sh` if needed.
2. Ingest (downloads originals, photos as JPEG, skips files already in raw/; screenshots are excluded for privacy):
   `cd ~/tiktok && .venv/bin/python -c "from factory.store import connect; from factory import jobs; jobs.do_ingest(connect(), '<link>')"`
   (or queue it from the panel: Inbox → paste link). This also runs analyze (GPS place groups, steady segments,
   contact sheets) and Claude descriptions of every clip.
3. Look at what arrived (places, dates, clip descriptions in the Clips tab / `data/factory.db` table `clips`) and the
   signals: `python -m radar.cli report travel` and `report psychology` (YouTube Radar), Google Trends (panel).
4. **Propose ideas as their social-media expert** (in chat and/or Ideas tab → Generate ideas with a brief). Prefer the
   formats the data supports (see "What works" below). Each idea: theme, hook + pattern, cover, beats with
   animations, shot list on real clips, music/pacing, caption + hashtags, claims to verify, content fit.
5. Approval stops: idea → (if ElevenLabs is needed) script + **credit estimate** → preview frames
   (`jobs.do_preview`) → render (`jobs.do_render`, which also runs SFX + QA with the Gauntlet ledger).
6. Hand over: videos land in `out/<NNN_name>/` with `caption.txt`; the user downloads them in the Studio
   (production page or Videolar) or the Shorts Paneli (:8095). Termius SFTP is the fallback.
   Prefer the Studio flow for new videos (Üret → ideas → approvals); steps 2–5 above are the manual equivalents.

## Shared Studio: users, Claude per user, ElevenLabs accounts (built 2026-10-27)
Login is on (`data/users.json`, mode 600; `bin/users.py add <id> "<Name>" [member]` prints a password, `passwd <id>`).
Owner `ali` runs Claude on the VM's own Claude Code login. A **member** connects their own Claude subscription in Studio →
Hesaplar ("Claude hesabımı bağla": `factory/claudeauth.py` runs `claude setup-token` in a pty, the member opens the link and
pastes the code). Two modes: **"login"** = `claude auth login --claudeai` into `~/.claude-profiles/<id>` (full scopes incl.
user:mcp_servers, so the member's own claude.ai connectors work, e.g. their ElevenLabs connector: Hesaplar → "Connector'ımı
bağla" → job `eleven_voices` reads its voices) or **"token"** = `claude setup-token` (user:inference only, no connectors →
ElevenLabs via API key). Every job carries its user
(`jobs.user`, env `FACTORY_USER`); `llm.ask_text` adds `CLAUDE_CODE_OAUTH_TOKEN` + `CLAUDE_CONFIG_DIR=~/.claude-profiles/<id>`.
**ElevenLabs accounts** (`data/eleven_accounts.json`, `factory/accounts.py`): `ali` = the owner's connector account (runs
the MCP calls as the owner even when a member started the job); others = API keys (`factory/eleven_api.py`: TTS, music,
sfx; voices + balance read live, cached 10 min). Each production has `data.eleven_account` (default: its creator's own);
choose it on the production page; the voice list follows the account. Owner can share an account and set a per-member
monthly cap; the ledger records user + account (`eleven_ledger.user/account`). Avatar/image/video need the connector account.

## Three modes
- **Footage-first** (default with a link): vlogs, itineraries, "places that don't look real", travel facts,
  motivation/daily reminder, famous proverbs, psychology only when the place carries the idea.
- **Topic-first** (no footage): built as the `explainer_short` format, see "Faceless explainer short" above (code-drawn
  motion graphics, no stock/AI visuals).
- **Avatar + cloned voice** (news/explainers, e.g. tech): the user will supply their ElevenLabs voice clone and
  photos/video later; until then use stock ElevenLabs voices. Talking-head models available through the
  connector: HeyGen Avatar 4 (image+audio, 1080p 9:16), OmniHuman 1.5, Creatify Aurora, Veed Fabric,
  MiniMax H3 (5–14.8 s chunks), video lip-sync Sync 3 / Veed. Voice cloning is NOT possible via the connector.
  Always remind the user to switch on TikTok's AI-generated-content label for avatar/cloned-voice videos.

## ElevenLabs rules
- Budget: **≤ 100,000 credits / month** (Pro plan). **Before any generation, tell the user the estimated credits and
  wait for OK.** `factory/credits.py`: `estimate()`, `record()`, `month_spent()`, `check_budget()`; learned rates in
  `data/eleven_rates.json` (measured: eleven_v4 TTS ≈ 1.15 credits/char). Unmeasured models are "unknown" —
  a calibration run (cap 5,000 credits) is still **awaiting the user's approval**.
- Access is via the claude.ai connector through headless Claude (`llm.ask(..., mcp=True)`); the generate tools return
  a flow run → poll `creative_get_flow_run_status` → signed URL (expires ~2 h) → download.
- Catalogue (models, limits): `data/elevenlabs_models.json`, `data/elevenlabs_avatar_models.json`.

## Editing style (user feedback 2026-10-26; later the same day the user asked for reference-driven CapCut-style edits — see above)
- Rejected: sliding/animated titles and labels, scaling hook text, punch zooms, slides, crossfades, short random
  shots, whoosh SFX. Wanted: **cinematic-calm** (held shots, hard cuts, natural sound, 1–2 plain lines) and
  **story** (their own cloned voice "Ali" `vhP2LOWrrIsWMq4m2vP6`, captions = the spoken phrases, cuts on phrases).
- Voiceover: `creative_generate_speech` defaults to 2 takes = double price; use `generations_count: 1` unless more
  takes were approved (eleven_v4 ≈ 1.15 credits/char per take). Word timings: faster-whisper `small.en`.

## What works (data, Oct 2026)
- Travel shorts (`radar.cli run travel`, 398 videos < 60 s): "Places That Don't Look/Feel Real" (small channels
  1–6 M views, 14–32 s, numbered Part series), single-place "This X Looks Unreal", "Travel facts you won't believe",
  day-numbered vlog series. Median ~21 s. A bare place name (e.g. "Zugspitze") gets few views — framing matters.
- Psychology shorts (`radar.cli run psychology`): 6–8 s list cards; many claims online are false → our angle is
  *sourced* facts; generic psychology over travel footage was judged weak.

## Pieces and commands
| What | Where |
|---|---|
| Studio | `studio/`, http://100.98.58.82:8501; old Streamlit `factory/app.py` on :8503; both via `bin/start-factory.sh` |
| Shorts tab | embeds the Shorts Paneli (`shorts/`, :8095, started by `bin/start-factory.sh`; `~/projeler/shorts-panel` is a symlink to it for the old cron line); parses caption.txt fields |
| Jobs | `python -m factory.jobs run <id>`; kinds ingest/analyze/describe/trends/radar/ideas/verify/preview/render/refs |
| Ideas, craft rules | `factory/ideas.py` (CRAFT_RULES distilled from the skills the user shared) |
| **Clean cut (current style)** | `bin/cinecut.py specs/cine/<name>.json [--preview]`: held shots, hard cuts, own sound, plain static captions, optional voiceover (ducks ambience) and ambience bed. Use this by default |
| Montage / render (old look) | `bin/montage.py` (cards, photos, punch, creep, xfades), `bin/render.py` (ASS text, panels, overlays, SFX). The user rejected this look (2026-10-26) — don't use it for new videos |
| Motion graphics | `motion/render.mjs` (headless Chromium, no root; libs in ~/opt/chromelibs), templates in `motion/templates/`, `factory/motion.py` |
| QA | `factory/qa.py` (black frames, loudness, frozen time, settled + transition frames, independent critic, ledger) |
| Style lock / taste | `data/brand.json` (accent #FFD93D, panel, personality, SFX default); playbook rows like/dislike |
| Radar | `radar/` (profiles psychology, travel), cron 06:17 UTC runs psychology; `.env` has YOUTUBE_API_KEY |
| Sources | iCloud: `bin/icloud_fetch.py <link> [--photos]`; main album "Shorts videos raw" (link in memory) |
| Tests | `.venv/bin/python -m pytest -q tests` |

## Known quirks
- Static ffmpeg has no drawtext → all text is ASS (libass) with fonts in `fonts/`.
- faster-whisper + PyAV 19: decode audio with ffmpeg to a float32 array before `transcribe`.
- Headless Claude: use `--disable-slash-commands --strict-mcp-config` (8× cheaper) unless a step needs a connector.
- `pkill -f` on the streamlit command line kills your own shell; find the PID with `ps` instead.

## Claude model routing + usage ledger (2026-10-27)
All factory Claude calls go through `factory/llm.py` (`claude -p` on the owner's subscription = same 5-hour limit as chat).
Default `MODEL = "opus"` is kept only for creative steps: script (`productions.generate`, `explainer.generate`), revise,
motion design (`motiondesign.author`), art direction (`artdirector.direct`), style extraction. **Sonnet**: daily discovery,
footage ideas, fact-check (`ideas.check_claims`), motion-design self-check (1 round), art-direction review, edit plan,
render QA, clip describe, reference profiling/recipes, and every ElevenLabs connector call (`eleven.CLAUDE_MODEL`).
Every call is written to `llm_usage` in factory.db (step = calling `module.function`, job/prod via FACTORY_JOB_ID /
FACTORY_PROD_ID env set in `jobs.py`, cost = CLI `total_cost_usd`). Studio → **Bütçe** shows "Claude kullanımı"
(5 h / today / 7 days, per step, per video, last calls) via `factory/usage.py` + `/api/claude_usage`; older calls are
imported once from `~/.claude/projects/-home-at-ali-tiktok-work` (estimated, marked *). Limit % is not exposed by
Anthropic: write `data/claude_calibration.json` `{"pct_per_usd": X, "at": "<iso>"}` after the creator measures % before/after
one job, and the card shows ≈ % too. `factory/artdirect.py` (old palette-only director, unused) was deleted.
Backup of the pre-change code: `backup-before-model-routing-2026-10-27.tgz`.

## Repo + portability (2026-10-27)
Code lives in the private GitHub repo `aliakay/content-factory` (README.md = setup on a new machine, `install.sh`).
Machine-specific values live in `factory/config.py` (env / `config.env` / defaults: ROOT = repo dir, ffmpeg ~/opt/bin
else PATH, claude ~/.local/bin else PATH, host = CF_HOST else Tailscale IP); node helpers read `motion/config.mjs`.
Secrets (`.env`, `config.env`, `data/users.json`, `data/eleven_accounts.json`), DBs, media and per-production state are
gitignored: back them up separately. Commit and push code changes after each working change.

## Studio 2 — channels, one composer, series (2026-10-27, night)
**UI** (`studio/index.html` shell + `studio/app.js` + `studio/app.css`, served by `/static/`, read per request): channel
rail (logo, colour tints the UI, pending counts), sidebar, ⌘K palette, phone tab bar. Home = one composer: prompt +
attachments (places, refs, series, links) -> job `plan` (`factory/planner.py`, Sonnet; keyword fallback without Claude)
-> editable plan card -> `/api/plan/<id>/start` queues `p_ideas` / `series_bible` / `series_episode`. Formats are presets
now: modes footage / topic / series (`formats.MODES`); `this_looks_unreal` -> `cinematic_calm`, `day_vlog` -> `story_vo`
(ids stay valid), `facts_listicle` is ready.
**Channels** (`factory/channels.py`, table `channels`; `productions/posts/disc_cards.channel_id`): first run files old
productions under "seyahat" (footage) and "bilgi" (explainers). Description + audience go into every idea/script prompt.
Brand layer: logo watermark (corner picker with the TikTok UI zones on a phone mock) + optional end card, burned in by
`engines.finish` for previews and finals; per video switch `data.brand = false`. Logos in `data/channels/<id>/`.
**Engines** (`factory/engines.py`): `spec.engine` = cine | style | explainer | html; `render()` = engine + brand pass +
(final only) mastering to -14 LUFS / -1.5 dBTP. Explainers render 9:16 or 16:9 (Pillow: scaled stage on the wide canvas;
HTML: canvas-aware prompt + shell). A canvas switch on an Opus design queues a redesign.
**Illustrated look** (`look_pack "illustrated"`, `factory/illustrate.py`): script writes `art_style` + per-scene `plate`;
Çizimler card = estimate + approval -> job `p_plates` (`eleven.image`, one flow, same-place plates and series characters
made FROM their nodes) -> Opus animates with `motion/templates/fxlib.js` (camera, boxes, pins, draw-on, 3D). One plate can
be re-rolled (`reroll_plate`, its own approval). Prompts for images are always English.
**Series** (`factory/series.py`, table `series`, page `#/s/<id>`): premise -> bible + mini book (Opus) -> approve ->
character sheets (approval) -> voices per character -> episode n -> production `series_episode` with speakers;
`productions.cast_voice` voices each run with its speaker's voice and joins them before alignment.
**Motion design**: FX library docs, taste numbers, 8 grammars (`data.grammar`, chips on the production page), a @@SPEC
build spec before code, scored self-critique with an anti-slideshow rule.
**Effects**: J/L cuts (`audio.lead/tail`), `enter: match`, `enter: object`, layers `behind: true` (rembg matte);
measured material in `clips.fx` (`factory/fxdetect.py`).
**Discovery**: embedding dedupe (`factory/embed.py`, fastembed or hashed trigrams), history check (21 days), papers
sub-pipeline (arXiv / bioRxiv / medRxiv / PubMed top journals; OpenAlex OA link on picked cards).
**Styles** level 2: type class -> OFL fonts, case, tracking, cards/shadow/grid, entrance/pace/transition, highlight colour;
video refs measured; drafts need approval (3 preview stills) on `#/stiller`.
**QA**: flash windows (photosensitivity), broken frames, slideshow gate for explainers; three cover candidates per final
(`out/<name>/thumb_*.jpg`).

## Studio 3 — techniques instead of formats, art-director planner, talking-head edits, ears (2026-10-28)
The creator wants the planner to know every technique the studio can execute and combine them per idea (no named
genre templates). Distilled (reverse-engineered, never copied) from shared workflows (stickman horror story, explainer
reel, 30 s product ad, talking-head ad) and repos (superpowers brainstorming, lemo-opuscar DIRECTOR/TECHNIQUE + style
bibles, mcp-for-blender scene guides, ClaudeAnimationBase acting, LottieFiles motion-design principles, earshot QA,
HyperFrames captions/sound/review).
- **Catalogue** `factory/capabilities.py`: ~58 techniques in areas story / style / look / sound / voice / captions /
  edit / check. Each carries writer notes, designer notes and data switches (`voice_fx`, `captions`, `sound`,
  `post_fx`, `fps60`); `apply(recipe, d)` pins them, `writer_notes(d)` / `designer_notes(d)` feed explainer.generate,
  motiondesign.author, artdirector.direct and talk.decide. One story shape and one film style per video. Film styles
  live in `data/film_styles.json` (essence / not / render / composition / colour / type / motion / camera /
  transitions / sound / post).
- **Planner** (Opus now): direction, benchmark (learn / avoid), techniques, seconds, three treatments, one question.
  Plan card: pick a treatment, remove / add technique chips (`/api/techniques?kind=`), edit the direction. `start`
  passes `recipe` to `p_ideas` (or `talk_new`). Fallback without Claude still picks techniques from keywords.
- **FX kit** (`motion/templates/fxlib.js`): `FX.sfx/FX.music` cues (collected by `render.mjs --cues`), stickman rig
  (poses, walk, wave, on twos) + `FX.emotions` (19 emotions: anticipation -> take -> settle, emotes, idle per emotion,
  no twins), story kit (hud, rule, choice, flipCard, lightsOut/On, slash, shatter, shake), devices (phone, alert, tap),
  transitions (iris, brushWipe, whip/whipIn, dipCut, colorFlood), `FX.boil`, `FX.set3d` (real-scale blockout, light
  rigs, lens, practicals, dolly). Shell captions: `captions.mode word|chunk`, `pos mid|low`, `energy high|talk|calm`,
  key / danger colour roles.
- **Sound** `factory/audiofx.py` + `factory/sfx.py`: 19 synthesised kinds (knock, buzz, clunk, swish, glass, impact,
  logo_hit, typing, notify, click, heartbeat, drone, alarm, flip + the old 5), sync offsets (clicks lead, impacts land a
  frame after), rotating takes, pitch-climbing runs, density cap (~9 / 10 s), no-mask placement, voice chains
  (clean / room), real-silence tightening, carve at 2.6 kHz + sidechain duck, music cut/back windows, drop alignment,
  auto music level (voice ~10 dB over music). htmlmotion mixes the scenes' own cues and applies film `post_fx`
  (grain / flicker / weave / vignette / mono) in ffmpeg. Voice post on TTS takes: `data.voice_fx`
  {tempo, pitch, tighten, fit} runs before alignment.
- **Checks**: `factory/layoutlint.py` on every design round (safe zone, caption band, overlap, contrast, tiny text;
  readcheck = every text visible long enough; motion lint = linear spatial easing, long staggers, creeping titles,
  dead stretches) -> fed to the Opus self-check together with review sheets (`factory/sheets.py`: scene start/middle,
  strips across every cut, phone width) and P0/P1/P2 notes. `factory/soundqa.py` on every final render
  (`qa.sound`, sound sheet in `work/sound/<name>.png`, shown on the production page).
- **Talking-head edits** (`factory/talk.py`, `bin/talkcut.py`, engine "talk", format `talking_head`, mode "talk"):
  composer "🎙 Konuşma videosu" uploads to `raw/talk/` (X-Talk header), the plan becomes kind "talk", job `talk_new`
  analyses (faster-whisper with fillers kept, phrases, retake / false-start / stutter flags, OpenCV face track if
  installed, accent colour from the footage; cached in `data/talk/<stem>.json`), Claude decides the cut (order, trims,
  hook + options, punch-ins, B-roll, keywords, grade, music brief; deterministic rough cut as fallback) -> stage idea
  shows the kept / cut transcript -> approve -> preview -> final (60 fps with `edit.fps60`). Segments are
  frame-aligned (audio and picture cut on the same grid, no drift); voice chain "room"; hook behind the speaker when
  rembg is installed. Revisions re-run the decision with the note.
- Not built yet: Blender sets (we use Three.js `FX.set3d`; needs Blender on the VM), licensed real-recording SFX
  (all effects are synthesised), lip-sync for code-drawn characters.

## The director's team — research, memory, sketches, critic (2026-10-28)
Planning is no longer one call. `planner.think` -> `factory/director.py` (Python orchestrator; agents share work only
through the plan row, live progress in `plan.progress`, then `plan.team` with time + cost per stage):
1. **memory** (code, `factory/memory.py`): recent recipes from `productions` (techniques, concept, notes, views from
   `posts`), treatments picked / passed over in `plans`, dislikes from `playbook` + rejections -> overused (half of
   the last 6, or a style / shape twice in the last 3), unexplored (spread across areas), picked / passed,
   best / weakest, `novelty()` 0..1 per treatment. Also fed to the motion designer (`memory.designer_note`).
2. **scout** (Sonnet + WebSearch/WebFetch): insight, misconception, sourced facts, prior art + metaphors, clichés, real
   questions, 3 original metaphors (fiction: genre research).
3. **art director** (`planner.draft`, Opus): request + catalogue + research + memory -> direction, benchmark, three
   treatments that differ from each other and from memory.recent (one bold from unexplored), each with a `moment`.
   The creator never has to say how it should look.
4. **sketch artists** (Sonnet x3 in parallel): each writes its treatment's hook frame as a real scene with the FX kit
   -> Chromium stills in `work/plans/<plan>/t<i>/` (+ layout check), served at `/media/plans/`.
5. **critic** (Opus + Read): reads the frames, scores clarity / hook / novelty / feasibility / fit, recommends one,
   writes one fix per treatment. The recommendation is applied; the creator can pick another on the card.
The chosen treatment's frame, concept, palette and fix travel in `recipe.sketch` (designer gets its code as the
approved style frame), the scout's research in `recipe.research` (writer re-verifies every fact). `attachments.quick`
(composer "⚡ hızlı plan") = only memory + art director. A full plan costs ~$1-1.5 of Claude, quick ~$0.3-0.5.
**Reasoning effort** per role: `llm.EFFORT`. Owner's rule (2026-10-28): **nothing above medium** (`llm.MAX_EFFORT` caps the
table, `CF_EFFORT_<MODULE>_<FUNCTION>` / `CF_EFFORT` overrides and `effort=`); connector calls low. Passed as
`claude --effort`; an older CLI without the flag is detected and called without it. Why: prod 17's xhigh motion design
thought ~30 min, cost ~$7 and overflowed one reply.
**Split replies**: calls use `--output-format stream-json --verbose`; `llm._stream` joins every text block after the last
tool call (the CLI's `result` is only the last message, which once dropped prod 17's hook scene). Timeouts are written to
the ledger (estimated cost, ok=0). `motiondesign.build` keeps the raw reply in `data/auto/<prod>/author_raw.txt`.
**Voice alignment** (2026-10-28): `productions.align` derives line times from `explainer.align_words` (one whisper pass,
Turkish-aware `_norm`, temperature 0; a weak match (<80 % of words) is retried without the script prompt). Before, a
drifting whisper run left prod 17 with 0.05 s scenes and sound/picture out of sync.
