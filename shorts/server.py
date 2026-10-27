#!/usr/bin/env python3
"""Shorts panel: lists the finished videos in ~/tiktok/out with a preview, a download link and
the caption + hashtags from caption.txt ready to copy. No dependencies.

Listens only on this machine's Tailscale address and refuses clients outside the tailnet, so it is
closed to the internet.

Usage: python3 server.py [--out <repo>/out] [--port 8095] [--host <tailscale ip>]
"""
import argparse
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.realpath(__file__))
CACHE = os.path.join(HERE, "cache")
sys.path.insert(0, os.path.dirname(HERE))
from factory import config  # noqa: E402  (stdlib only: paths/host shared with the Studio)
FFMPEG, FFPROBE = config.FFMPEG, config.FFPROBE
TAILNET = [ipaddress.ip_network(n) for n in ("100.64.0.0/10", "fd7a:115c:a1e0::/48", "127.0.0.0/8", "::1/128")]
SETTLE = 5            # seconds an mp4 must be untouched before it counts as finished

probe_cache = {}      # path -> ((mtime_ns, size), duration or None)
thumb_lock = threading.Lock()


def tailscale_ip():
    try:
        return subprocess.check_output(["tailscale", "ip", "-4"], text=True, timeout=10).split()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


def probe_duration(path, st):
    key = (st.st_mtime_ns, st.st_size)
    hit = probe_cache.get(path)
    if hit and hit[0] == key:
        return hit[1]
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=20)
        duration = float(r.stdout.strip()) if r.returncode == 0 else None
    except (ValueError, subprocess.SubprocessError):
        duration = None          # half-written mp4 (no moov atom yet)
    probe_cache[path] = (key, duration)
    return duration


def parse_caption(text):
    """caption.txt as written by render.py: SERIES, CAPTION/HASHTAGS blocks, LOCATION, MUSIC, optional NOTES."""
    info = {"series": "", "caption": "", "hashtags": "", "location": "", "music": "", "notes": "", "raw": text.strip()}
    block = None
    body = {"caption": [], "hashtags": [], "notes": []}
    for line in text.splitlines():
        head = line.strip()
        if head in ("CAPTION", "HASHTAGS", "NOTES"):
            block = head.lower()
        elif re.match(r"(SERIES|LOCATION|MUSIC):", head):
            key, value = head.split(":", 1)
            info[key.lower()] = value.strip()
            block = None
        elif block:
            body[block].append(line)
    info["caption"] = "\n".join(body["caption"]).strip()
    info["hashtags"] = " ".join(" ".join(body["hashtags"]).split())
    info["notes"] = "\n".join(body["notes"]).strip()
    return info


def copy_text(info):
    if not info:
        return ""
    text = "\n\n".join(part for part in (info["caption"], info["hashtags"]) if part)
    return text or info["raw"]


def list_videos(out_dir):
    videos = []
    now = time.time()
    if not os.path.isdir(out_dir):
        return videos
    for entry in os.scandir(out_dir):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            folder, files = entry.name, [f for f in os.scandir(entry.path)]
        elif entry.is_file():
            folder, files = "", [entry]
        else:
            continue
        files = [f for f in files if f.is_file() and f.name.lower().endswith(".mp4") and not f.name.startswith(".")]
        if not files:
            continue
        info = None
        cap_path = os.path.join(entry.path, "caption.txt") if folder else None
        if cap_path and os.path.isfile(cap_path):
            with open(cap_path, encoding="utf-8", errors="replace") as f:
                info = parse_caption(f.read())
        for f in files:
            st = f.stat()
            duration = probe_duration(f.path, st)
            videos.append({
                "id": f"{folder}/{f.name}" if folder else f.name,
                "file": f.name,
                "mtime": st.st_mtime,
                "size": st.st_size,
                "duration": duration,
                "ready": duration is not None and now - st.st_mtime > SETTLE,
                "post": info,
                "copy": copy_text(info),
            })
    videos.sort(key=lambda v: v["mtime"], reverse=True)
    return videos


def thumbnail(path, st):
    key = hashlib.sha1(f"{path}:{st.st_mtime_ns}:{st.st_size}".encode()).hexdigest()
    dst = os.path.join(CACHE, key + ".jpg")
    with thumb_lock:
        if os.path.exists(dst):
            return dst
        os.makedirs(CACHE, exist_ok=True)
        tmp = os.path.join(CACHE, key + ".tmp.jpg")
        for seek in ("1.5", "0"):        # 1.5 s in shows the hook text; short clips fall back to frame 0
            subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", seek, "-i", path, "-frames:v", "1",
                            "-vf", "scale=360:-2", "-q:v", "4", tmp], capture_output=True, timeout=60)
            if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                os.replace(tmp, dst)
                return dst
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ShortsPanel"

    def do_GET(self):
        self.route(head=False)

    def do_HEAD(self):
        self.route(head=True)

    def route(self, head):
        if not self.allowed():
            return self.send_bytes(403, b"Forbidden\n", "text/plain; charset=utf-8", head)
        url = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(url.path)
        query = urllib.parse.parse_qs(url.query)
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self.send_bytes(200, f.read(), "text/html; charset=utf-8", head)
        if path == "/api/videos":
            body = json.dumps(list_videos(self.server.out_dir), ensure_ascii=False).encode()
            return self.send_bytes(200, body, "application/json; charset=utf-8", head)
        if path.startswith("/media/") or path.startswith("/thumb/"):
            video = self.resolve(path.split("/", 2)[2])
            if not video:
                return self.send_bytes(404, b"Not found\n", "text/plain; charset=utf-8", head)
            if path.startswith("/media/"):
                return self.send_file(video, "video/mp4", head, download="dl" in query)
            thumb = thumbnail(video, os.stat(video))
            if not thumb:
                return self.send_bytes(404, b"No preview\n", "text/plain; charset=utf-8", head)
            return self.send_file(thumb, "image/jpeg", head, cache="private, max-age=604800")
        self.send_bytes(404, b"Not found\n", "text/plain; charset=utf-8", head)

    def allowed(self):
        ip = ipaddress.ip_address(self.client_address[0])
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if not any(ip in net for net in TAILNET):
            return False
        # DNS-rebinding guard: only IP literals and tailnet (MagicDNS) names.
        host = (self.headers.get("Host") or "").strip().lower()
        host = host[1:].split("]")[0] if host.startswith("[") else host.rsplit(":", 1)[0]
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return "." not in host or host.rstrip(".").endswith(".ts.net") or host == "localhost"

    def resolve(self, rel):
        """Map a video id ("<folder>/<file>.mp4") to a real file inside the out directory."""
        if not rel.lower().endswith(".mp4"):
            return None
        full = os.path.realpath(os.path.join(self.server.out_dir, rel))
        if not full.startswith(self.server.out_dir + os.sep) or not os.path.isfile(full):
            return None
        return full

    def send_bytes(self, status, body, ctype, head):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def send_file(self, path, ctype, head, download=False, cache="private, max-age=3600"):
        size = os.path.getsize(path)
        start, end, status = 0, size - 1, 200
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", (self.headers.get("Range") or "").strip())
        if m and (m[1] or m[2]):
            if m[1]:
                start = int(m[1])
                end = min(int(m[2]), size - 1) if m[2] else size - 1
            else:
                start = max(size - int(m[2]), 0)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", cache)
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download:
            name = os.path.basename(path)
            plain = name.encode("ascii", "replace").decode().replace('"', "")
            self.send_header("Content-Disposition",
                             f"attachment; filename=\"{plain}\"; filename*=UTF-8''{urllib.parse.quote(name)}")
        self.end_headers()
        if head:
            return
        try:
            with open(path, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = f.read(min(1 << 16, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True     # Safari drops range requests it no longer needs

    def log_request(self, code="-", size="-"):
        if isinstance(code, int) and code >= 400:
            super().log_request(code, size)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(config.ROOT, "out"))
    ap.add_argument("--host", help="address to listen on (default: CF_HOST, else this machine's Tailscale IPv4)")
    ap.add_argument("--port", type=int, default=config.SHORTS_PORT)
    args = ap.parse_args()
    host = args.host or config.HOST or tailscale_ip()
    if not host:
        sys.exit("Tailscale IP not found (is tailscale up?); refusing to listen on a public address. "
                 "For local use set CF_HOST=127.0.0.1 in config.env.")
    server = ThreadingHTTPServer((host, args.port), Handler)
    server.daemon_threads = True
    server.out_dir = os.path.realpath(args.out)
    print(f"{time.strftime('%F %T')} Shorts panel on http://{host}:{args.port} serving {server.out_dir}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
