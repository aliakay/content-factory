#!/usr/bin/env bash
# Keep the Content Factory up (cron: @reboot + every 5 min; safe to call repeatedly):
#   Studio (studio/server.py)             :8501  — main panel
#   Shorts panel (shorts/server.py)       :8095  — finished videos: play, download, copy caption
#   old Streamlit panel (factory/app.py)  :8503  — clips, Reference Lab, brand kit
# Host and ports come from config.env (CF_HOST, CF_*_PORT); default host = this machine's Tailscale IP.
ROOT="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$ROOT" || exit 1
if [ -f config.env ]; then set -a; . ./config.env; set +a; fi
HOST="${CF_HOST:-$(tailscale ip -4 2>/dev/null | head -1)}"
if [ -z "$HOST" ]; then echo "start-factory: no CF_HOST and no Tailscale IP; set CF_HOST in config.env" >&2; exit 1; fi
PY="$ROOT/.venv/bin/python"
mkdir -p data
up() { curl -s -m 3 -o /dev/null "http://$HOST:$1/"; }
# setsid (own session, survives the calling shell) is Linux-only; macOS has none on PATH, so fall back to nohup alone
detach() { if command -v setsid >/dev/null; then setsid nohup "$@"; else nohup "$@"; fi; }
if ! up "${CF_STUDIO_PORT:-8501}"; then
  detach "$PY" studio/server.py --host "$HOST" --port "${CF_STUDIO_PORT:-8501}" \
    >> data/studio.log 2>&1 < /dev/null &
fi
if ! up "${CF_SHORTS_PORT:-8095}"; then
  detach "$PY" shorts/server.py --host "$HOST" --port "${CF_SHORTS_PORT:-8095}" \
    >> data/shorts.log 2>&1 < /dev/null &
fi
if [ "${CF_STREAMLIT:-1}" = "1" ] && ! up "${CF_STREAMLIT_PORT:-8503}"; then
  detach "$ROOT/.venv/bin/streamlit" run factory/app.py --server.address "$HOST" \
    --server.port "${CF_STREAMLIT_PORT:-8503}" --server.headless true --browser.gatherUsageStats false \
    >> data/streamlit.log 2>&1 < /dev/null &
fi
