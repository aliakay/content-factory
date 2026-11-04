"""Platform delivery (t506): one finished video -> a file made for each platform, checked against that platform.

PLATFORMS holds each platform's delivery template: frame size, frame-rate ceiling, longest allowed video, upload size
limit, loudness target, and where its own interface (tabs, buttons, caption, player controls) covers the picture.
`deliver_one` fits the video into the frame (a blurred copy behind it when the shape differs), caps the frame rate,
brings the sound to the loudness target, encodes H.264 + AAC and then verifies the result with factory.fftools. A
video longer than the platform allows is refused for that platform, never silently cut.

`safe_area` says what sits under the platform's interface:
  - the HTML engine's scene texts, measured exactly from the page (the layout lint boxes) and mapped into the
    delivered frame;
  - for other videos an estimate: edge density (text, faces, detail) inside each interface zone on sampled frames;
plus a preview picture of frames with the zones drawn over them, so the creator sees it.

The zone rectangles are approximations of the apps' current layouts, kept in one table to adjust when they change.
"""
import glob, json, os, shutil, time

from . import fftools as F
from .hat import project as P

# zones: [x0, y0, x1, y1] as fractions of the frame
PLATFORMS = {
    "tiktok": {"name": "TikTok", "size": (1080, 1920), "max_fps": 60, "max_s": 600, "max_mb": 4096, "lufs": -14,
               "zones": {"top": [0, 0, 1, 0.0885], "right": [0.861, 0.25, 1, 0.86], "bottom": [0, 0.78, 1, 1]}},
    "reels": {"name": "Instagram Reels", "size": (1080, 1920), "max_fps": 60, "max_s": 180, "max_mb": 4096, "lufs": -14,
              "zones": {"top": [0, 0, 1, 0.07], "right": [0.86, 0.5, 1, 0.88], "bottom": [0, 0.82, 1, 1]}},
    "shorts": {"name": "YouTube Shorts", "size": (1080, 1920), "max_fps": 60, "max_s": 180, "max_mb": 4096, "lufs": -14,
               "zones": {"top": [0, 0, 1, 0.08], "right": [0.84, 0.42, 1, 0.88], "bottom": [0, 0.83, 1, 1]}},
    "youtube": {"name": "YouTube", "size": (1920, 1080), "max_fps": 60, "max_s": 43200, "max_mb": 131072, "lufs": -14,
                "zones": {"title": [0, 0, 0.7, 0.11], "controls": [0, 0.87, 1, 1]}},
    "x": {"name": "X", "size": (1920, 1080), "max_fps": 60, "max_s": 140, "max_mb": 512, "lufs": -14,
          "zones": {"controls": [0, 0.88, 1, 1]}},
    "linkedin": {"name": "LinkedIn", "size": (1080, 1920), "max_fps": 60, "max_s": 600, "max_mb": 5120, "lufs": -14,
                 "zones": {"controls": [0, 0.88, 1, 1]}},
}
ZONE_NAMES = {
    "top": {"tr": "üst sekmeler", "en": "top tabs"},
    "right": {"tr": "sağdaki düğmeler", "en": "buttons on the right"},
    "bottom": {"tr": "alttaki açıklama ve kullanıcı adı", "en": "caption and username at the bottom"},
    "title": {"tr": "başlık şeridi", "en": "title bar"},
    "controls": {"tr": "oynatıcı düğmeleri", "en": "player controls"},
}
# share of strong-edge pixels in a zone that reads as text or fine detail under the interface; calibrated on rendered
# text (~0.10 for three caption lines) and real finals (flat graphics ~0.0-0.04). Natural texture (leaves, rock) also
# crosses it, which is why it is shown as an estimate of "dense detail", not as text.
EDGE_BUSY = 0.07
EDGE_CUT = 90


class DeliveryError(ValueError):
    pass


def _fit_vf(src, W, H):
    """Filter graph bringing the picture to W x H: a plain scale when the shape matches, else the picture fitted on a
    blurred, darkened copy of itself."""
    if abs(src["width"] / src["height"] - W / H) < 0.01:
        return f"[0:v]scale={W}:{H}:flags=lanczos,setsar=1[v]"
    return (f"[0:v]split[b][f];[b]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:2,"
            f"eq=brightness=-0.08[bg];[f]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]")


def _fit_map(src, W, H):
    """(scale, dx, dy) taking a point of the source frame to the delivered frame when it was fitted."""
    s = min(W / src["width"], H / src["height"])
    return s, (W - src["width"] * s) / 2, (H - src["height"] * s) / 2


def deliver_one(src, platform, dst):
    """Encode `src` for one platform and verify it. Returns {platform, ok, refused, file, checks, output, seconds}."""
    pl = PLATFORMS[platform]
    m = F.measure(src)
    if not m["video"]:
        raise DeliveryError("the file has no picture")
    if m["duration"] > pl["max_s"]:
        return {"platform": platform, "ok": False, "file": None, "checks": [],
                "refused": f"{m['duration']:.0f} s > {pl['max_s']} s"}
    W, H = pl["size"]
    fps = min(m["fps"] or 30, pl["max_fps"])
    graph = _fit_vf(m, W, H)
    graph += f";[v]fps={fps},format=yuv420p[vo]"
    t0 = time.time()
    argv = ["-i", src]
    if m["audio"]:
        base = f"loudnorm=I={pl['lufs']}:TP=-1:LRA=11"
        err = F._ff(["-i", src, "-vn", "-af", base + ":print_format=json", "-f", "null", "-"], "loudness")
        j = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
        if float(j["input_i"]) > -70:     # a real sound, not digital silence
            graph += (f";[0:a]{base}:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA="
                      f"{j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true,"
                      f"aresample=48000,aformat=channel_layouts=stereo[ao]")
            amap, loud = "[ao]", True
        else:
            graph += ";[0:a]aresample=48000,aformat=channel_layouts=stereo[ao]"
            amap, loud = "[ao]", False
    else:       # platforms treat a video with no audio track oddly: give it a silent one
        argv += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        amap, loud = "1:a", False
    kbps = 12000 if W * H <= 1920 * 1080 else 30000
    argv += ["-filter_complex", graph, "-map", "[vo]", "-map", amap, "-t", f"{m['duration']:.3f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high", "-level:v", "4.2",
             "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    F._ff(argv + [dst], f"deliver {platform}")
    out = F.measure(dst)
    expect = {"duration": m["duration"], "width": W, "height": H, "fps": fps, "video": True, "audio": True,
              "vcodec": "h264", "max_bytes": pl["max_mb"] * 1024 * 1024}
    if loud:
        expect["lufs"] = pl["lufs"]
    checks = F.verify(out, expect, 0.12)
    checks.append({"what": "pix_fmt", "want": "yuv420p", "got": out.get("pix_fmt"), "ok": out.get("pix_fmt") == "yuv420p"})
    return {"platform": platform, "ok": all(c["ok"] for c in checks), "refused": None, "file": dst, "checks": checks,
            "output": out, "seconds": round(time.time() - t0, 1)}


# ---------------------------------------------------------------- safe area

def _inside(box, zone, W, H):
    """Share of the box (pixels) under the zone (fractions)."""
    zx0, zy0, zx1, zy1 = zone[0] * W, zone[1] * H, zone[2] * W, zone[3] * H
    ix = max(0.0, min(box["x"] + box["w"], zx1) - max(box["x"], zx0))
    iy = max(0.0, min(box["y"] + box["h"], zy1) - max(box["y"], zy0))
    return ix * iy / max(1.0, box["w"] * box["h"])


def text_findings(lint, platform, src_size, fit=None):
    """Scene texts (the layout lint's boxes, source-frame pixels) under the platform's interface zones."""
    pl = PLATFORMS[platform]
    W, H = pl["size"]
    s, dx, dy = fit or _fit_map({"width": src_size[0], "height": src_size[1]}, W, H)
    out, seen = [], set()
    for t, shot in sorted(lint.items(), key=lambda kv: float(kv[0])):
        for b in shot.get("boxes") or []:
            if not (b.get("text") or "").strip():
                continue
            bb = {"x": b["x"] * s + dx, "y": b["y"] * s + dy, "w": b["w"] * s, "h": b["h"] * s}
            for zn, z in pl["zones"].items():
                share = _inside(bb, z, W, H)
                key = (b.get("text"), zn)
                if share >= 0.15 and key not in seen:
                    seen.add(key)
                    out.append({"zone": zn, "t": round(float(t), 2), "scene": b.get("scene"), "text": b["text"][:80],
                                "share": round(share, 2), "how": "text"})
    return out


def _edges(img):
    from PIL import ImageFilter
    g = img.convert("L").resize((216, int(216 * img.height / img.width)))
    return g.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > EDGE_CUT else 0)


def busy_findings(video, platform, samples=8):
    """Estimate for videos without measured texts: interface zones holding dense detail on sampled frames."""
    from PIL import Image
    pl = PLATFORMS[platform]
    m = F.measure(video)
    hits = {z: [] for z in pl["zones"]}
    tmp = os.path.join(os.path.dirname(os.path.abspath(video)), ".safe-frames")
    os.makedirs(tmp, exist_ok=True)
    try:
        for i in range(samples):
            t = m["duration"] * (i + 0.5) / samples
            f = os.path.join(tmp, f"{i}.png")
            F._ff(["-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf", "scale=432:-2", f], "frame")
            e = _edges(Image.open(f))
            for zn, z in pl["zones"].items():
                # 2 px in from the frame edge: the edge filter marks the picture's own border
                box = (max(2, int(z[0] * e.width)), max(2, int(z[1] * e.height)), min(e.width - 2, int(z[2] * e.width)),
                       min(e.height - 2, int(z[3] * e.height)))
                crop = e.crop(box)
                dens = sum(crop.histogram()[255:]) / max(1, crop.width * crop.height)
                if dens >= EDGE_BUSY:
                    hits[zn].append(round(t, 2))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return [{"zone": zn, "t": ts[0], "times": ts, "share": round(len(ts) / samples, 2), "how": "busy"}
            for zn, ts in hits.items() if len(ts) >= max(2, samples // 4)]


def preview(video, platform, dst, frames=3, lang="tr"):
    """Frames of the delivered video side by side with the platform's interface zones drawn over them."""
    from PIL import Image, ImageDraw, ImageFont
    pl = PLATFORMS[platform]
    m = F.measure(video)
    tiles = []
    tmp = dst + ".d"
    os.makedirs(tmp, exist_ok=True)
    try:
        for i in range(frames):
            t = m["duration"] * (i + 0.5) / frames
            f = os.path.join(tmp, f"{i}.png")
            F._ff(["-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf", "scale=360:-2", f], "frame")
            im = Image.open(f).convert("RGBA")
            ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            try:
                font = ImageFont.truetype(F.FONT, 13)
            except OSError:
                font = ImageFont.load_default()
            for zn, z in pl["zones"].items():
                r = (z[0] * im.width, z[1] * im.height, z[2] * im.width - 1, z[3] * im.height - 1)
                d.rectangle(r, fill=(255, 40, 60, 70), outline=(255, 60, 80, 230), width=2)
                label = ZONE_NAMES[zn][lang]
                tw = d.textlength(label, font=font)
                # a narrow zone (the right-hand buttons): the name goes beside it, inside the picture
                x = r[0] + 5 if tw + 10 <= r[2] - r[0] else max(4, r[0] - tw - 6)
                d.text((x, r[1] + 4), label, font=font, fill=(255, 255, 255, 255), stroke_width=2,
                       stroke_fill=(0, 0, 0, 200))
            tiles.append(Image.alpha_composite(im, ov).convert("RGB"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    gap = 12
    sheet = Image.new("RGB", (sum(t.width for t in tiles) + gap * (len(tiles) + 1), tiles[0].height + 2 * gap), (24, 24, 28))
    x = gap
    for t in tiles:
        sheet.paste(t, (x, gap))
        x += t.width + gap
    sheet.save(dst)
    return dst


def _lint_boxes(pid, d=None):
    """The HTML engine's text boxes at each scene's settled moment of the final: ({t: shot}, (W, H)) or (None, None)."""
    from . import export
    if not export.html_engine(pid, d):
        return None, None
    from .hat import explainer
    plan = P.read_artifact(pid, "scene_plan", d)
    sp = explainer._render_spec(pid, plan, d, True)
    hm = explainer._htmlmotion()
    work = P.path(pid, "work", "deliver-lint", d=d)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    b = os.path.join(work, "bundle.json")
    json.dump(hm.make_bundle(sp, explainer.design(plan)), open(b, "w", encoding="utf-8"), ensure_ascii=False)
    times = [round(s["start"] + (s["end"] - s["start"]) * 0.7, 2) for s in export.scenes(pid, d)] or [1.0]
    _, _, lp = hm.shots(b, times, os.path.join(work, "shots"), lint=True)
    lint = json.load(open(lp)) if lp and os.path.exists(lp) else {}
    size = (1920, 1080) if (P.load(pid, d).get("aspect") or "9:16") == "16:9" else (1080, 1920)
    return lint, size


# ---------------------------------------------------------------- the job

def build(pid, platforms, d=None, log=print, lang=None):
    """Deliver the project's final to each platform: renders/deliver-<stamp>/<platform>.mp4 + <platform>-safe.png +
    .deliver.json. Returns the meta dict."""
    from . import export
    platforms = [p for p in platforms if p in PLATFORMS]
    if not platforms:
        raise DeliveryError("no platform chosen")
    video = export.final(pid, d)
    if not video:
        raise DeliveryError("no final video yet")
    if not lang:
        from .accounts import ui_lang
        lang = ui_lang()
    out = P.path(pid, "renders", f"deliver-{time.strftime('%Y%m%d-%H%M%S')}", d=d)
    os.makedirs(out, exist_ok=True)
    lint, size = None, None
    try:
        log("measuring scene texts")
        lint, size = _lint_boxes(pid, d)
    except Exception as e:          # the estimate below still runs
        log(f"text boxes unavailable: {type(e).__name__}: {e}")
    results = []
    for pl in platforms:
        log(f"encoding for {PLATFORMS[pl]['name']}")
        r = deliver_one(video, pl, os.path.join(out, f"{pl}.mp4"))
        if r["file"]:
            log(f"safe area on {PLATFORMS[pl]['name']}")
            r["findings"] = text_findings(lint, pl, size) if lint else busy_findings(r["file"], pl)
            r["measured"] = "text" if lint else "estimate"
            r["preview"] = os.path.basename(preview(r["file"], pl, os.path.join(out, f"{pl}-safe.png"), lang=lang))
            r["file"] = os.path.basename(r["file"])
            r["size"] = os.path.getsize(os.path.join(out, r["file"]))
        r.pop("output", None)
        results.append(r)
    meta = {"at": P.now(), "platforms": platforms, "results": results}
    json.dump(meta, open(os.path.join(out, ".deliver.json"), "w", encoding="utf-8"), ensure_ascii=False)
    P.event(pid, "deliver", d=d, folder=os.path.basename(out), platforms=platforms,
            ok=[r["platform"] for r in results if r["ok"] and not r.get("findings")])
    return meta | {"folder": out}


def deliveries(pid, d=None):
    """Past deliveries, newest first."""
    out = []
    for f in sorted(glob.glob(P.path(pid, "renders", "deliver-*", ".deliver.json", d=d)), reverse=True):
        out.append(json.load(open(f, encoding="utf-8")) | {"folder": os.path.dirname(f)})
    return out
