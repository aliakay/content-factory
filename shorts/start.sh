#!/bin/sh
# Starts only the Shorts panel if it is not already running (old cron entry; bin/start-factory.sh now starts it too).
# server.py binds to CF_HOST / the Tailscale IP only, so it retries here until tailscale is up after a reboot.
cd "$(dirname "$0")"
pgrep -f "shorts(-panel)?/server.py" >/dev/null || nohup python3 "$PWD/server.py" >>server.log 2>&1 &
