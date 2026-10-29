#!/usr/bin/env bash
# Content Factory setup on a fresh Linux machine (no root needed for the app itself).
# Safe to run again: it only adds what is missing.
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$ROOT"
say() { printf '\n== %s\n' "$*"; }
warn() { printf '!! %s\n' "$*" >&2; }

say "Checking tools"
command -v python3 >/dev/null || { warn "python3 is required (3.10+)"; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || { warn "python 3.10+ is required"; exit 1; }
command -v node >/dev/null || { warn "node 18+ is required (motion design renderer)"; exit 1; }
command -v npm >/dev/null || { warn "npm is required"; exit 1; }
if ! command -v ffmpeg >/dev/null && [ ! -x "$HOME/opt/bin/ffmpeg" ]; then
  warn "ffmpeg not found: install it (apt install ffmpeg) or put a static build in ~/opt/bin, or set CF_FFMPEG in config.env"
fi
if ! command -v claude >/dev/null && [ ! -x "$HOME/.local/bin/claude" ]; then
  warn "Claude Code CLI not found: install it (https://code.claude.com) and run 'claude' once to log in"
fi
if ! command -v codex >/dev/null && [ ! -x "$HOME/.local/bin/codex" ]; then
  warn "Codex CLI not found: install it and sign in before selecting Codex in Studio > Hesaplar"
fi
command -v tailscale >/dev/null || warn "tailscale not found: set CF_HOST=127.0.0.1 in config.env to use the Studio on this computer only"

say "Python environment (.venv)"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv 2>/dev/null || {
    command -v uv >/dev/null || { warn "python3-venv missing and no uv: apt install python3-venv, or install uv"; exit 1; }
    uv venv .venv
  }
fi
if [ -x .venv/bin/pip ]; then
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
else
  uv pip install -q --python .venv/bin/python -r requirements.txt
fi

# subject matte model (rembg u2netp, ~5 MB) fetched now so the first render doesn't wait for the download
.venv/bin/python -c 'from rembg import new_session; new_session("u2netp")' >/dev/null 2>&1 \
  && echo "   rembg u2netp model ready" || warn "rembg model not ready: frame break / vertigo / text behind subject fall back"

say "Node packages + headless Chromium (motion/)"
(cd motion && npm ci --silent && npx --yes playwright install chromium)
echo "   If Chromium fails to start later, run once with root: (cd motion && sudo npx playwright install-deps chromium)"

say "Folders and config"
mkdir -p data raw out work assets
[ -f config.env ] || { cp config.env.example config.env; echo "   created config.env (edit CF_HOST etc.)"; }
[ -f .env ] || { cp .env.example .env; echo "   created .env (add YOUTUBE_API_KEY for the Viral Radar)"; }
.venv/bin/python -c 'import sys; sys.path.insert(0, "."); from factory.store import connect; connect().close()'
echo "   database: data/factory.db"

say "Tests"
.venv/bin/python -m pytest -q tests || warn "some tests failed (see above)"

cat <<'EOF'

== Next steps
1. Create the first Studio user (becomes the owner and turns the login on):
     .venv/bin/python bin/users.py add <id> "<Name>" owner
2. Start everything:            bin/start-factory.sh
   Keep it up after reboots:    crontab -e  and add
     @reboot     <repo>/bin/start-factory.sh
     */5 * * * * <repo>/bin/start-factory.sh
3. Open http://<CF_HOST or tailscale ip>:8501 and log in.
4. Claude or Codex: sign in to the selected CLI on this machine; choose the provider and each agent's model in Studio > Hesaplar.
   ElevenLabs: Studio > Hesaplar > add an ElevenLabs API key (or use the claude.ai connector of the owner login).
See README.md and RUNBOOK.md for the full guide.
EOF
