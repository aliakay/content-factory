"""Render engines (plan Phase 1): one registry and one contract for every renderer in bin/.

Every engine is a module in bin/ with `main(spec_path, preview=False) -> (mp4 path, seconds)` and reads its canvas from
`spec["aspect"]`. A compiled spec names its engine in `spec["engine"]`; old specs without it are recognised by shape.

After the engine, `finish()` runs the shared post-pass that no engine has to know about: the channel's brand layer
(logo watermark in a corner, optional end card with the logo). It reads `spec["brand"]` (filled by productions from the
production's channel) and rewrites the mp4 in place, so previews show exactly what the final video will look like.
"""
import importlib, json, os, shutil, subprocess, sys

from .config import FFMPEG, FFPROBE, ROOT

ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
# engine -> (module in bin/, folder under specs/ for final specs, what it is)
ENGINES = {
    "cine": ("cinecut", "cine", "sakin kurgu: tutulan çekimler, sert kesme, sade yazı"),
    "style": ("stylecut", "style", "referans stili: beat kesme, kadraj, renk, efekt ve yazı katmanları"),
    "explainer": ("explainer", "explainer", "kodla çizilen motion grafik (Pillow) + kinetik altyazı"),
    "html": ("htmlmotion", "explainer", "Opus'un HTML/GSAP ile tasarladığı sahneler (Chromium)"),
    "talk": ("talkcut", "talk", "konuşma videosu kurgusu: kesme, yüz takipli kadraj, punch-in, kodla B-roll, altyazı"),
}
CORNERS = ("tl", "tr", "bl", "br")


def engine_of(spec):
    """The engine a spec is for: explicit `engine`, else recognised by its shape (specs written before Phase 1)."""
    e = spec.get("engine")
    if e in ENGINES:
        return e
    if "segments" in spec:
        return "talk"
    if "scenes" in spec:
        return "explainer"
    if "frame" in spec:
        return "style"
    return "cine"


def canvas(spec):
    return ASPECTS.get(spec.get("aspect", "9:16"), ASPECTS["9:16"])


def module(engine):
    if os.path.join(ROOT, "bin") not in sys.path:
        sys.path.insert(0, os.path.join(ROOT, "bin"))
    return importlib.import_module(ENGINES[engine][0])


def spec_dir(spec):
    return ENGINES[engine_of(spec)][1]


def render(spec_path, preview=False):
    """Run the spec's engine, then the shared post-pass. Returns (mp4 path, real duration in seconds)."""
    spec = json.load(open(spec_path))
    dst, total = module(engine_of(spec)).main(spec_path, preview=preview)
    dst, total = finish(dst, spec, total, preview)
    if not preview:
        master(dst)
    return dst, total


# ---------- shared post-pass: audio mastering ----------
TARGET_LUFS, TARGET_TP = -14.0, -1.5   # TikTok / Shorts / Reels / YouTube all normalise around -14 LUFS


def loudness(path):
    """(integrated LUFS, true peak dBFS) of a file's audio, or (None, None) without audio."""
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    import re
    m = re.search(r"Integrated loudness:\s+I:\s+([-\d.]+) LUFS.*?True peak:\s+Peak:\s+([-\d.]+) dBFS", r.stderr, re.S)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def master(dst):
    """Final-only mastering: when the mix is off target (|I - -14| > 1 LU or true peak above -1 dBFS) the audio is
    re-mastered and the video stream copied. With pedalboard + pyloudnorm installed: a gentle glue compressor, a
    limiter and exact loudness gain; otherwise ffmpeg two-pass loudnorm (linear) + a true-peak limiter."""
    lufs, tp = loudness(dst)
    if lufs is None or (abs(lufs - TARGET_LUFS) <= 1.0 and tp <= -1.0):
        return {"lufs": lufs, "tp": tp, "changed": False}
    tmp = dst + ".master.mp4"
    try:
        _master_pedalboard(dst, tmp)
        how = "pedalboard"
    except Exception:
        _master_ffmpeg(dst, tmp, lufs, tp)
        how = "ffmpeg"
    if os.path.exists(tmp) and os.path.getsize(tmp) > 1000:
        os.replace(tmp, dst)
    after = loudness(dst)
    print(f"master ({how}): {lufs} LUFS / {tp} dBTP -> {after[0]} / {after[1]}", flush=True)
    return {"lufs": after[0], "tp": after[1], "changed": True, "how": how}


def _master_ffmpeg(src, dst, lufs, tp):
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", src, "-vn", "-af",
                        f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    st = r.stderr[r.stderr.rfind("{"):r.stderr.rfind("}") + 1]
    try:
        m = json.loads(st)
        af = (f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
              f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    except (ValueError, KeyError):
        af = f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=11"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", src, "-map", "0:v", "-map", "0:a", "-c:v", "copy",
                    "-af", af + ",alimiter=limit=0.84:level=false", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-movflags", "+faststart", dst], check=True)


def _master_pedalboard(src, dst):
    import numpy as np
    import pedalboard
    import pyloudnorm
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", src, "-vn", "-f", "f32le", "-ac", "2", "-ar", "48000", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T.copy()
    board = pedalboard.Pedalboard([pedalboard.HighpassFilter(30), pedalboard.Compressor(threshold_db=-18, ratio=2.5, attack_ms=15,
                                                                                         release_ms=180)])
    y = board(x, 48000)
    meter = pyloudnorm.Meter(48000)
    y = pyloudnorm.normalize.loudness(y.T, meter.integrated_loudness(y.T), TARGET_LUFS).T
    y = pedalboard.Pedalboard([pedalboard.Limiter(threshold_db=TARGET_TP - 0.5, release_ms=80)])(y.astype(np.float32), 48000)
    wav = dst + ".wav"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "f32le", "-ac", "2", "-ar", "48000", "-i", "-", wav],
                   input=np.clip(y.T, -1, 1).astype(np.float32).tobytes(), check=True)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", src, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", dst], check=True)
    os.remove(wav)


# ---------- shared post-pass: the channel's brand layer ----------
def brand_of(spec):
    """Normalised brand settings from a spec, or None when there is nothing to draw (no logo file)."""
    b = spec.get("brand") or {}
    logo = b.get("logo")
    path = os.path.join(ROOT, logo) if logo and not os.path.isabs(logo) else logo
    if not path or not os.path.isfile(path):
        return None
    wm = b.get("watermark") or {}
    outro = b.get("outro") or {}
    return {"logo": path, "name": str(b.get("name") or ""), "handle": str(b.get("handle") or ""),
            "accent": b.get("accent") or "#FFD93D",
            "watermark": {"on": wm.get("on", True), "corner": wm.get("corner") if wm.get("corner") in CORNERS else "tl",
                          "size": max(0.04, min(float(wm.get("size") or 0.11), 0.25)),
                          "opacity": max(0.2, min(float(wm.get("opacity") or 0.85), 1.0))},
            "outro": {"on": bool(outro.get("on")), "seconds": max(1.0, min(float(outro.get("seconds") or 1.8), 4.0)),
                      "text": str(outro.get("text") or "")}}


def watermark_box(size, corner, frac):
    """(x, y, logo width) for a corner watermark. Margins keep it out of the TikTok / Shorts UI on a phone canvas:
    below the top tabs, above the caption block, away from the right-hand button column."""
    w, h = size
    lw = int(round(w * frac / 2) * 2)
    if h > w:   # 9:16: top tabs end ~y 170, bottom UI starts ~y 1500, right buttons are ~150 px wide
        mx, top, bottom, right = int(w * 0.055), int(h * 0.105), int(h * 0.80), int(w * 0.16)
    else:
        mx, top, bottom, right = int(w * 0.03), int(h * 0.05), int(h * 0.93), int(w * 0.03)
    x = mx if corner in ("tl", "bl") else w - right - lw
    y = top if corner in ("tl", "tr") else bottom - lw
    return x, y, lw


def probe(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                        "-of", "json", path], capture_output=True, text=True)
    try:
        info = json.loads(r.stdout)
    except ValueError:
        return None, False, (0, 0)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
    return float(info.get("format", {}).get("duration") or 0), audio, (v.get("width", 0), v.get("height", 0))


def outro_card(frame_png, brand, size, out_png):
    """End card: the video's last frame, blurred and darkened, the logo in the middle and the channel name/handle."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    w, h = size
    try:
        bg = Image.open(frame_png).convert("RGB").resize((w, h))
    except OSError:
        bg = Image.new("RGB", (w, h), (12, 14, 20))
    bg = bg.filter(ImageFilter.GaussianBlur(max(8, w // 40)))
    bg = Image.blend(bg, Image.new("RGB", (w, h), (8, 9, 12)), 0.55)
    logo = Image.open(brand["logo"]).convert("RGBA")
    lw = int(min(w, h) * 0.30)
    logo = logo.resize((lw, max(1, int(logo.height * lw / logo.width))), Image.LANCZOS)
    cy = int(h * 0.44)
    bg.paste(logo, ((w - logo.width) // 2, cy - logo.height // 2), logo)
    d = ImageDraw.Draw(bg)
    font_path = os.path.join(ROOT, "fonts", "InterTight[wght].ttf")
    y = cy + logo.height // 2 + int(h * 0.03)
    for text, sz, wght, fill in ((brand["outro"]["text"] or brand["name"], int(min(w, h) * 0.06), 800, (245, 247, 250)),
                                 (brand["handle"], int(min(w, h) * 0.04), 600, brand["accent"])):
        if not text:
            continue
        try:
            f = ImageFont.truetype(font_path, sz)
            f.set_variation_by_axes([wght])
        except (OSError, AttributeError):
            f = ImageFont.load_default()
        tw = d.textlength(text, font=f)
        d.text(((w - tw) / 2, y), text, font=f, fill=fill)
        y += int(sz * 1.45)
    bg.save(out_png)
    return out_png


def finish(dst, spec, total, preview=False):
    """Apply the brand layer to a rendered mp4 in place. Without a logo the file is returned untouched."""
    brand = brand_of(spec)
    if not brand or not (brand["watermark"]["on"] or brand["outro"]["on"]):
        return dst, total
    dur, has_audio, size = probe(dst)
    if not dur or not size[0]:
        return dst, total
    tmp = dst + ".brand"
    os.makedirs(tmp, exist_ok=True)
    w, h = size
    inputs, chain, last = ["-i", dst], [], "[0:v]"
    k = 1
    if brand["watermark"]["on"]:
        x, y, lw = watermark_box(size, brand["watermark"]["corner"], brand["watermark"]["size"])
        inputs += ["-loop", "1", "-i", brand["logo"]]
        chain.append(f"[{k}:v]scale={lw}:-1,format=rgba,colorchannelmixer=aa={brand['watermark']['opacity']:.2f}[lg]")
        chain.append(f"{last}[lg]overlay={x}:{y}:shortest=1:format=auto[wm]")
        last, k = "[wm]", k + 1
    out_total = dur
    if brand["outro"]["on"]:
        sec = brand["outro"]["seconds"]
        frame = os.path.join(tmp, "last.png")
        subprocess.run([FFMPEG, "-v", "error", "-y", "-sseof", "-0.1", "-i", dst, "-frames:v", "1", "-update", "1", frame],
                       capture_output=True)
        card = outro_card(frame, brand, (w, h), os.path.join(tmp, "outro.png"))
        inputs += ["-loop", "1", "-t", f"{sec:.2f}", "-i", card]
        chain.append(f"{last}fps=30,format=yuv420p,setsar=1[main]")
        chain.append(f"[{k}:v]fps=30,format=yuv420p,setsar=1,fade=t=in:d=0.25[oc]")
        k += 1
        if has_audio:
            inputs += ["-f", "lavfi", "-t", f"{sec:.2f}", "-i", "anullsrc=r=48000:cl=stereo"]
            chain.append("[0:a]aformat=sample_rates=48000:channel_layouts=stereo[a0]")
            chain.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo[a1]")
            chain.append("[main][a0][oc][a1]concat=n=2:v=1:a=1[v][a]")
            k += 1
        else:
            chain.append("[main][oc]concat=n=2:v=1:a=0[v]")
        out_total = dur + sec
    else:
        chain.append(f"{last}format=yuv420p[v]")
    out = os.path.join(tmp, "branded.mp4")
    cmd = [FFMPEG, "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chain), "-map", "[v]"]
    if has_audio:
        cmd += ["-map", "[a]"] if brand["outro"]["on"] else ["-map", "0:a", "-c:a", "copy"]
        if brand["outro"]["on"]:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast" if preview else "medium", "-crf", "24" if preview else "17",
            "-pix_fmt", "yuv420p", "-t", f"{out_total:.3f}", "-movflags", "+faststart", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode or not os.path.exists(out):
        print("brand pass failed (video kept without it):", (r.stderr or "")[-300:], flush=True)
        shutil.rmtree(tmp, ignore_errors=True)
        return dst, total
    os.replace(out, dst)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"brand: {'logo ' + brand['watermark']['corner'] if brand['watermark']['on'] else ''}"
          f"{' + end card' if brand['outro']['on'] else ''} -> {dst} ({out_total:.2f}s)", flush=True)
    return dst, round(out_total, 3)
