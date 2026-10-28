# Content Factory

A self-hosted studio that turns travel footage or a topic into finished 9:16 short videos (TikTok, YouTube Shorts,
Reels): ideas → script → design → voice → preview → render → QA → publish tracking. Everything is driven from a
phone-friendly web page, the **Studio**.

Claude does the thinking through the local **Claude Code CLI** (`claude -p`, on the logged-in subscription; no API
key). ElevenLabs makes the voice, music and effects. ffmpeg, Pillow and headless Chromium render the video.

Detailed operating guide: [RUNBOOK.md](RUNBOOK.md). Art rules for the designers: [ART_PLAYBOOK.md](ART_PLAYBOOK.md).

## How it is built

Everything starts in one composer: write what you want (and attach places, reference videos, a series, links or a raw
video of yourself talking); the planner (`factory/planner.py`) acts as producer **and art director**: it reads the
studio's technique catalogue (`factory/capabilities.py`), writes an art direction with a benchmark (what to learn /
what not to take), proposes three different treatments and combines the techniques that serve this idea (story
shapes, film styles, code-drawn characters, rebuilt UI, sound design, voice post, caption styles, talking-head
editing). The plan card is editable (treatments, technique chips, direction) and only your approval starts work. Kinds: own footage, a topic explainer (tech / paper / auto / illustrated / custom
looks), a new story series, or the next episode of a series. Videos live inside **channels** (logo, colour, language,
niche, defaults, discovery categories); the logo is burned in by the shared post-pass.

```
studio/server.py + index.html   Studio web app (stdlib HTTP server)                         :8501
studio/app.js + app.css         the single-page UI (channel rail, composer, boards, series, styles; no build step)
shorts/server.py                Shorts panel: finished videos, download, caption copy       :8095
factory/app.py                  old Streamlit panel: clips, Reference Lab, brand kit        :8503

factory/                        the pipeline (Python package)
  planner.py      the composer's planner / art director: request + attachments -> direction + techniques -> jobs
  capabilities.py the technique catalogue every stage reads (writer notes, designer notes, data switches) + film styles
  talk.py         talking-head editor: transcript, filler / retake / false-start cuts, face reframe, punch-ins, B-roll
  audiofx.py      sound engineering: voice chain, real-silence tightening, carve + duck, music cut/back, drop alignment
  soundqa.py      the ears: measures a finished mix (loudness arc, clicks, tail, low end, density, masking) + a sheet
  layoutlint.py   design checks on HTML scenes: safe zones, overlaps, contrast, tiny text, readcheck, motion lint
  sheets.py       review sheets (scene start/middle, strips across cuts, phone width)
  channels.py     channels (identity, niche, defaults, brand layer); every production/post belongs to one
  engines.py      render engine registry + shared post-pass (logo watermark, end card, audio mastering)
  series.py       story series: bible + mini book -> character sheets -> episodes
  illustrate.py   illustrated look: per-scene AI illustrations on one ElevenLabs flow, animated by Opus
  discover.py     daily discovery (news + papers: arXiv, bioRxiv/medRxiv, PubMed, OpenAlex), embedding dedupe
  embed.py        text embeddings (fastembed if installed, offline fallback) for dedupe and clip search
  fxdetect.py     measured effect material per clip (horizons, motion, occlusions) for match cuts / object wipes
  motionref.py    how a reference really moves: full-frame-rate sheets, subject bob / sway / squash in % + period, colours
  catalog.py      the technique catalog page (Studio → Teknik kataloğu): every technique + an engine-drawn demo clip
  matte.py        subject mattes for text-behind-subject (rembg if installed)
  thumbs.py       cover / thumbnail candidates per finished video
  jobs.py         job queue: the Studio writes a row, each job runs as its own process
  productions.py  one video's way through the factory (stages, preview, render, QA)
  explainer.py    topic-first "faceless explainer" format (research, script, scenes)
  motiondesign.py Claude designs each scene as HTML/GSAP, checks its own stills
  artdirector.py  Claude art-directs footage videos (research, brief, edit decisions)
  llm.py          headless Claude calls; every call is logged in llm_usage (Studio > Bütçe)
  eleven*.py      ElevenLabs (claude.ai connector or API key), credit estimates + monthly cap
  accounts.py     Studio users; members can bring their own Claude + ElevenLabs accounts
  config.py       machine-specific settings (paths, host, ports) from config.env
bin/            renderers (cinecut, stylecut, explainer, htmlmotion, talkcut), iCloud fetch, user admin, start script
motion/         node + Playwright: HTML → video frames (render.mjs --blur=N: real sub-frame motion blur), research
                screenshots; templates/fxlib.js = the FX + 3D recipe library the motion designer uses (story kit,
                stickman rig + illustrated FX.character with a live face, the ALIVE kit: gaze, blinks, moving holds,
                flowing poses, idle loops by subject; the KINETIC kit: type on the beat, cut runs, zoom through a
                letter, never-parked pictures; UI/phone kit, transitions, 3D sets, sound cues);
                templates/talk_overlay.html = captions / hook / B-roll of talking-head edits
data/film_styles.json  the film-style bibles (riso, ink wash, cut paper, blueprint, newsreel, swiss, cel, HUD, ...)
radar/          Viral Radar: YouTube reference videos, scored daily (cron)
tests/          pytest
```

### Data

All state is local:

| Where | What |
|---|---|
| `data/factory.db` (SQLite) | clips, places, ideas, productions, jobs, ElevenLabs ledger, Claude usage, posts + stats, discovery cards |
| `data/radar.db` (SQLite) | radar videos and daily metric snapshots |
| `data/users.json`, `data/eleven_accounts.json` | logins, members' Claude tokens, ElevenLabs API keys (mode 600, **never in git**) |
| `raw/`, `work/`, `out/`, `assets/eleven/` | footage, intermediate renders, finished videos, generated audio |

None of these are in git. Back them up separately (e.g. a nightly copy of `data/*.db` and `data/*.json`).

## Setup on a new machine

Requirements: Linux, Python 3.10+, Node 18+, ffmpeg, the Claude Code CLI (logged in), optionally Tailscale.

```bash
git clone https://github.com/aliakay/content-factory.git
cd content-factory
./install.sh                     # venv + Python packages, node packages + Chromium, config files, tests
```

Then:

1. **Config.** Edit `config.env` (created by the installer):
   - `CF_HOST`: empty = your Tailscale IP (recommended; the panels refuse anyone outside your tailnet),
     `127.0.0.1` = this computer only.
   - Tool paths only if ffmpeg/claude are not on PATH.
   - `.env`: `YOUTUBE_API_KEY` for the Viral Radar and YouTube stats (optional).
2. **Claude.** Run `claude` once and log in. The owner's factory steps run on this login and use its 5-hour limit.
3. **First user.** `.venv/bin/python bin/users.py add <id> "<Name>" owner` prints a password. The first user turns
   the login on. Members are added the same way with `member`. They connect their own Claude subscription
   (`claude setup-token`) and ElevenLabs key in the Studio, so their jobs spend from their own accounts.
4. **ElevenLabs.** Studio → Hesaplar: add an ElevenLabs API key. The owner can also use the claude.ai ElevenLabs
   connector of the logged-in Claude account.
5. **Start.** Run `bin/start-factory.sh` and open `http://<host>:8501`. To keep it running, add it to cron:
   ```
   @reboot     /path/to/content-factory/bin/start-factory.sh
   */5 * * * * /path/to/content-factory/bin/start-factory.sh
   17 6 * * *  cd /path/to/content-factory && .venv/bin/python -m radar.cli run && .venv/bin/python -m radar.cli snapshot
   30 7 * * *  cd /path/to/content-factory && .venv/bin/python -m factory.discover
   ```

A new install starts empty: no footage, productions or history. Those live in the other machine's `data/` and media
folders.

## Costs

- **Claude:** creative steps (script, motion design, art direction, revise, style) run on Opus. Checks, research
  helpers and tool calls run on Sonnet. Studio → Bütçe → "Claude kullanımı" shows the list-price equivalent per step
  and per video.
- **ElevenLabs:** every generation needs an approved credit estimate. A hard monthly cap is enforced in code
  (`factory/credits.py`).

### Optional packages (install on the VM with uv when wanted)

```bash
~/.local/bin/uv pip install --python .venv/bin/python fastembed        # multilingual semantic dedupe + clip search
~/.local/bin/uv pip install --python .venv/bin/python pedalboard pyloudnorm   # mastering chain (else ffmpeg loudnorm)
~/.local/bin/uv pip install --python .venv/bin/python opencv-python-headless   # face tracking for talking-head reframes
```
Without them the factory falls back (hashed-trigram vectors, ffmpeg loudnorm, centred crop). `rembg[cpu]` (subject
mattes for text behind subject, frame break and vertigo) is in requirements.txt; on a VM installed before it, add it with
`~/.local/bin/uv pip install --python .venv/bin/python "rembg[cpu]"`.

## Tests

```bash
.venv/bin/python -m pytest -q tests
```
