#!/usr/bin/env python3
"""Reference-style edit ("CapCut-like"): beat cuts, a cinematic frame, a film look and designed text layers.

Made after the creator shared reference reels (gezi / vlog / manzara / motivasyon): letterboxed 16:9 footage on
black, teal-orange or golden grades with grain, cuts on the music, serif title cards, kinetic words, location pins.
bin/cinecut.py stays the calm, text-light cut; this one is for videos that follow a reference.

Usage: stylecut.py spec.json [--preview]   -> out/<name>/<name>.mp4 + caption.txt (preview: work/preview/<name>.mp4)

Spec:
  name
  aspect    "9:16" (default, 1080x1920) | "16:9" (1920x1080); on 16:9 "letterbox" uses the 2.39:1 band
  frame     "full" (9:16) | "letterbox" (16:9 band in the middle, black above and below) | "scope" (2.39:1 band)
  look      {"grade": "natural|film|golden|moody|vivid|mono", "grain": 0..1, "vignette": 0..1}
  shots     [{"video": "raw/X.MOV", "in": 2.0, "out": 4.0, "speed": 1.0, "push": 0.04, "focus": [0.5, 0.5],
              "enter": "cut|flash|dip"}, {"photo": "raw/X.JPG", "dur": 1.2, "push": 0.05, ...}]
              push = slow zoom-in over the shot (0 = locked); enter = how this shot starts (flash = 3-frame white,
              dip = 6-frame fade from black, whip = motion smear, glitch = block mosaic, tiles = rectangular patches of this
              shot open over the previous one with a faint grid, like the Dolomites reference); "exit": "whip|glitch"
              smears/blocks the end of the shot so the pair reads as one transition
              "enter": "mask" + "mask": {"shape": "circle|iris|band|split|strips|bars|luma|custom", "dur": 0.6,
              "angle": 30, "center": [0.5, 0.5], "n": 5, "soft": 0.04, "line": true, "expr": "<custom field>"}: the new
              shot opens through an animated shape (see MASKS); "luma" opens through the previous frame's brightness
              "ramp": {"in": 0.35, "out": 0.35, "x": 5}  speed ramp: the first/last seconds run x times faster (with
              motion blur), the rest at "speed"; "leak": true = warm light leak washing over the first 0.7 s
  layers    text/graphic layers drawn by motion/templates/overlay.html (see that file for the types)
  music     {"file": "assets/eleven/x.mp3", "start": 0.0, "db": -4, "fade_out": 1.5}   optional
  ambient_db  level of the clips' own sound (default -6 with music, -2 without)
  voice     {"file": "...", "start": 0.3}  optional; ducks music and ambience
  post      {series, caption, hashtags, location, music, notes} -> caption.txt
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from factory.config import ROOT, FFMPEG  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "bin"))
sys.path.insert(0, ROOT)
from render import write_caption  # noqa: E402

FPS = 30
ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
BAND_RATIO = {"letterbox": 16 / 9, "scope": 2.39}

# looks are built from plain ffmpeg filters so they render the same everywhere
GRADES = {
    "natural": "eq=contrast=1.04:saturation=1.06",
    "film": ("curves=all='0/0.03 0.25/0.20 0.75/0.80 1/0.96',"
             "colorbalance=rs=-0.05:bs=0.07:rm=0.02:bm=-0.02:rh=0.07:gh=0.02:bh=-0.07,eq=saturation=0.92:contrast=1.06"),
    "golden": ("colortemperature=temperature=4800:mix=0.5,curves=all='0/0 0.25/0.21 0.5/0.5 0.8/0.84 1/0.98',"
               "eq=saturation=1.2:contrast=1.12:gamma=0.95"),
    "moody": ("curves=all='0/0.06 0.3/0.24 0.7/0.70 1/0.92',colorbalance=bs=0.05:bm=0.03:gh=-0.02,"
              "eq=saturation=0.78:contrast=1.08:brightness=-0.02"),
    "vivid": "eq=saturation=1.28:contrast=1.07,unsharp=5:5:0.4",
    "mono": "hue=s=0,curves=all='0/0.04 1/0.95',eq=contrast=1.12",
}


def run(args):
    subprocess.run([FFMPEG, "-v", "error", "-y", *args], check=True)


def geometry(frame, W=1080, H=1920):
    """(width, height) of the moving picture and its y offset on the canvas. A band only makes sense when it is
    flatter than the canvas: on a 16:9 canvas "letterbox" becomes the 2.39:1 scope band."""
    ratio = BAND_RATIO.get(frame)
    if ratio and W / H >= 16 / 9 - 0.01 and frame == "letterbox":
        ratio = 2.39
    if ratio:
        h = int(round(W / ratio / 2) * 2)
        if h < H:
            return W, h, (H - h) // 2
    return W, H, 0


def zoom_expr(push, dur):
    return f"1+{push}*(t/{max(dur, 0.01):.3f})"


TILE_DUR = 0.45


def tiles_pass(base, prev_frame, out, size, enc):
    """Block-reveal transition: for the first TILE_DUR s random rectangles of the new shot replace the previous
    shot's last frame (uneven tile order, faint grid on top), the rest of the shot is untouched.
    The per-pixel blend only runs on that short head, the tail is passed through."""
    pw, ph, _ = geometry("full", *size)
    tw, th = max(64, pw // 7), max(64, ph // 12)
    thr = f"mod(floor(X/{tw})*37+floor(Y/{th})*91+floor(X/{tw})*floor(Y/{th})*5,17)/17"
    h = TILE_DUR + 0.05
    fc = (f"[0:v]split[a][b];[a]trim=0:{h},setpts=PTS-STARTPTS[head];[b]trim=start={h},setpts=PTS-STARTPTS[tail];"
          f"[1:v]scale={pw}:{ph}:force_original_aspect_ratio=increase,crop={pw}:{ph},setsar=1,fps={FPS},"
          f"trim=0:{h},setpts=PTS-STARTPTS[prev];"
          f"[head][prev]blend=all_expr='if(lt({thr},min(1,T/{TILE_DUR})),A,B)',"
          f"drawgrid=width={tw}:height={th}:thickness=1:color=white@0.16[hv];[hv][tail]concat=n=2:v=1:a=0[v]")
    run(["-i", base, "-loop", "1", "-t", f"{h:.2f}", "-i", prev_frame, "-filter_complex", fc, "-map", "[v]", "-an",
         "-c:v", "libx264", "-preset", enc[0], "-crf", enc[1], "-pix_fmt", "yuv420p", out])


# Mask transitions: every shape is a "field" F(X, Y) in 0..1; the new shot shows where F < P (P = eased progress), with
# a soft edge. Fields use ffmpeg expression syntax (X, Y, W, H, PI, hypot, abs, floor, mod, cos, sin ...). The art
# director may also send its own field as "custom" (checked by safe_expr), and keeps the good ones as learned skills.
MASKS = {
    "circle": "hypot(X-W*{cx},Y-H*{cy})/hypot(W,H)/0.75",
    "iris": "max(abs(X-W*{cx})/W,abs(Y-H*{cy})/H)*2",
    "band": "((X-W/2)*cos({a})+(Y-H/2)*sin({a}))/(W*abs(cos({a}))+H*abs(sin({a})))+0.5",
    "split": "abs((X-W/2)*cos({a})+(Y-H/2)*sin({a}))/(W*abs(cos({a}))+H*abs(sin({a})))*2",
    "strips": "if(mod(floor((Y+X*tan({a}))/(H/{n})),2),X/W,1-X/W)*0.65+mod(floor((Y+X*tan({a}))/(H/{n})),{n})/{n}*0.35",
    "bars": "if(mod(floor(X/(W/{n})),2),Y/H,1-Y/H)*0.7+floor(X/(W/{n}))/{n}*0.3",
}
SAFE_EXPR = set("XYWHPIhypotabsfloormodcossintanminmaxifltgtexpsqrtclippow0123456789.+-*/(),_ ")


def safe_expr(e):
    import re
    if not e or len(e) > 400 or set(e) - SAFE_EXPR:
        return None
    words = set(re.findall(r"[A-Za-z_]+", e))
    return e if words <= {"X", "Y", "W", "H", "PI", "hypot", "abs", "floor", "mod", "cos", "sin", "tan", "min", "max",
                          "if", "lt", "gt", "exp", "sqrt", "clip", "pow"} else None


def mask_field(m):
    shape = m.get("shape", "circle")
    if shape == "custom":
        f = safe_expr(m.get("expr", ""))
        return f or MASKS["circle"].format(cx=0.5, cy=0.5)
    cx, cy = (m.get("center") or [0.5, 0.5])[:2]
    a = float(m.get("angle", 30)) * 3.14159265 / 180
    return MASKS.get(shape, MASKS["circle"]).format(cx=cx, cy=cy, a=f"{a:.4f}", n=int(m.get("n", 5)))


def head_split(h):
    return (f"[0:v]split[a][b];[a]trim=0:{h},setpts=PTS-STARTPTS[head];"
            f"[b]trim=start={h},setpts=PTS-STARTPTS[tail];")


def mask_pass(base, prev_frame, out, pic, enc, m):
    """The new shot opens over the previous shot's last frame through an animated shape (or its brightness).
    pic = (width, height) of the moving picture (the band on letterboxed frames)."""
    pw, ph = pic
    d = max(0.25, min(float(m.get("dur", 0.6)), 1.5))
    soft = max(0.005, min(float(m.get("soft", 0.04)), 0.3))
    h = d + 0.05
    P = f"(1-pow(1-min(T/{d},1),3))"
    fc = (head_split(h) +
          f"[1:v]scale={pw}:{ph}:force_original_aspect_ratio=increase,crop={pw}:{ph},setsar=1,fps={FPS},"
          f"trim=0:{h},setpts=PTS-STARTPTS,format=gbrp,split[prev][pl];[head]format=gbrp[new];")
    if m.get("shape") == "luma":   # bright parts of the old frame give way first (sky before land)
        fc += f"[pl]format=gray,geq=lum='clip(({P}*(1+{soft})-lum(X,Y)/255)/{soft},0,1)*255',format=gbrp[m];"
        F = None
    else:
        F = mask_field(m)
        fc += (f"[pl]nullsink;color=black:s={pw}x{ph}:r={FPS}:d={h},format=gray,"
               f"geq=lum='clip(({P}*(1+{soft})-({F}))/{soft},0,1)*255',format=gbrp[m];")
    fc += "[prev][new][m]maskedmerge[mm];"
    if m.get("line") and F:        # thin white editorial line riding the mask edge
        lw = 0.0035
        fc += (f"color=white:s={pw}x{ph}:r={FPS}:d={h},format=gbrp[wh];"
               f"color=black:s={pw}x{ph}:r={FPS}:d={h},format=gray,"
               f"geq=lum='lt(abs(({F})-{P}*(1+{soft})+{soft}/2),{lw})*lt(T,{d * 0.97})*230',format=gbrp[lm];"
               "[mm][wh][lm]maskedmerge[mm2];")
        last = "[mm2]"
    else:
        last = "[mm]"
    fc += f"{last}format=yuv420p[hv];[hv][tail]concat=n=2:v=1:a=0[v]"
    run(["-i", base, "-loop", "1", "-t", f"{h:.2f}", "-i", prev_frame, "-filter_complex", fc, "-map", "[v]", "-an",
         "-c:v", "libx264", "-preset", enc[0], "-crf", enc[1], "-pix_fmt", "yuv420p", out])


def leak_pass(base, out, pic, enc, d=0.7):
    """Warm light leak that sweeps across the frame at the start of the shot (procedural, screen-blended)."""
    pw, ph = pic
    h = d + 0.05
    I = (f"exp(-(pow(X-W*(-0.25+1.5*T/{d}),2)/(2*pow(W*0.42,2))+pow(Y-H*0.35,2)/(2*pow(H*0.45,2))))"
         f"*sin(PI*min(T/{d},1))")
    fc = (head_split(h) +
          f"color=black:s={pw}x{ph}:r={FPS}:d={h},format=gbrp,geq=r='255*{I}':g='140*{I}':b='55*{I}'[lk];"
          "[head]format=gbrp[hd];[hd][lk]blend=all_mode=screen,format=yuv420p[hv];[hv][tail]concat=n=2:v=1:a=0[v]")
    run(["-i", base, "-filter_complex", fc, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", enc[0], "-crf", enc[1],
         "-pix_fmt", "yuv420p", out])


def probe_duration(path):
    r = subprocess.run([FFMPEG.replace("ffmpeg", "ffprobe"), "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def ramp_setup(s, dur):
    """(source in, source out, setpts expr, blur windows) for a speed-ramped shot: the first `in` and last `out`
    output seconds run x times faster than the base speed. The source range grows to feed the fast parts."""
    r = s.get("ramp") or {}
    sp = s.get("speed", 1.0)
    x = max(2.0, min(float(r.get("x", 5)), 10.0))
    ri = max(0.0, min(float(r.get("in", 0) or 0), dur * 0.4))
    ro = max(0.0, min(float(r.get("out", 0) or 0), dur * 0.4))
    need = (dur - ri - ro) * sp + x * sp * (ri + ro)
    a = s["in"]
    full = probe_duration(os.path.join(ROOT, s["video"])) or (s["out"] + need)
    if a + need > full:
        a = max(0.0, full - need)
    need = min(need, full - a)
    ui, uo = x * sp * ri, need - x * sp * ro
    u = "((PTS-STARTPTS)*TB)"
    expr = (f"if(lt({u},{ui:.4f}),{u}/{x * sp:.4f},if(gt({u},{uo:.4f}),{dur - ro:.4f}+({u}-{uo:.4f})/{x * sp:.4f},"
            f"{ri:.4f}+({u}-{ui:.4f})/{sp:.4f}))")
    return a, a + need, expr, ri, ro


def shot(s, out, wav, frame, enc, size=(1080, 1920), prev=None):
    pw, ph, _ = geometry(frame, *size)
    push = float(s.get("push", 0.0))
    fx, fy = s.get("focus", [0.5, 0.5])
    if "video" in s:
        a, b, speed = s["in"], s["out"], s.get("speed", 1.0)
        dur = (b - a) / speed
        if s.get("ramp"):
            a, b, expr, ri, ro = ramp_setup(s, dur)
            blur = "+".join(x for x in (f"lt(t,{ri:.3f})" if ri else "", f"gt(t,{dur - ro:.3f})" if ro else "") if x)
            pre = f"setpts='({expr})/TB',fps={FPS}," + (f"tmix=frames=3:enable='{blur}',dblur=angle=0:radius=18:enable='{blur}'," if blur else "")
        else:
            pre = f"setpts=PTS/{speed},fps={FPS},"
        src = ["-ss", str(a), "-t", str(b - a), "-i", os.path.join(ROOT, s["video"])]
    else:
        dur = s.get("dur", 1.5)
        src = ["-loop", "1", "-t", f"{dur:.3f}", "-i", os.path.join(ROOT, s["photo"])]
        pre = f"fps={FPS},"
    # cover-crop to the picture size at 2x, then a slow centred push towards the focus point, then down to size
    z = zoom_expr(push, dur)
    vf = (pre + f"scale={pw * 2}:{ph * 2}:force_original_aspect_ratio=increase:flags=lanczos,"
          f"crop={pw * 2}:{ph * 2},"
          f"scale=w='iw*({z})':h='ih*({z})':eval=frame:flags=bicubic,"
          f"crop={pw * 2}:{ph * 2}:x='(iw-{pw * 2})*{fx}':y='(ih-{ph * 2})*{fy}',"
          f"scale={pw}:{ph}:flags=lanczos,setsar=1")
    enter, exit_ = s.get("enter", "cut"), s.get("exit", "cut")
    if enter == "flash":
        vf += ",fade=t=in:st=0:d=0.1:color=white"
    elif enter == "dip":
        vf += ",fade=t=in:st=0:d=0.2:color=black"
    elif enter == "whip":  # horizontal motion smear over the first frames, the other half of a whip pan
        vf += ",avgblur=sizeX=90:sizeY=1:enable='lt(t,0.07)',avgblur=sizeX=35:sizeY=1:enable='between(t,0.07,0.13)'"
    elif enter == "glitch":  # block mosaic + colour split for a few frames, like a tile reveal
        vf += (",pixelize=width=72:height=72:enable='lt(t,0.07)',pixelize=width=24:height=24:enable='between(t,0.07,0.13)',"
               "rgbashift=rh=-14:bh=14:enable='lt(t,0.13)'")
    if exit_ == "whip":
        vf += f",avgblur=sizeX=35:sizeY=1:enable='between(t,{dur - 0.13:.3f},{dur - 0.07:.3f})',avgblur=sizeX=90:sizeY=1:enable='gt(t,{dur - 0.07:.3f})'"
    elif exit_ == "glitch":
        vf += f",pixelize=width=40:height=40:enable='gt(t,{dur - 0.07:.3f})'"
    use_tiles = enter == "tiles" and prev and dur > TILE_DUR + 0.2
    use_mask = enter == "mask" and prev and dur > 0.6
    use_leak = bool(s.get("leak")) and dur > 0.9
    target = out + ".base.mp4" if (use_tiles or use_mask or use_leak) else out
    run([*src, "-vf", vf, "-frames:v", str(round(dur * FPS)), "-an", "-c:v", "libx264", "-preset", enc[0],
         "-crf", enc[1], "-pix_fmt", "yuv420p", target])
    if use_tiles:
        pf = out + ".prev.png"
        run(["-sseof", "-0.1", "-i", prev, "-frames:v", "1", "-update", "1", pf])
        tiles_pass(target, pf, out if not use_leak else out + ".t.mp4", size, enc)
        os.remove(target)
        target = out + ".t.mp4" if use_leak else out
    elif use_mask:
        pf = out + ".prev.png"
        run(["-sseof", "-0.1", "-i", prev, "-frames:v", "1", "-update", "1", pf])
        mask_pass(target, pf, out if not use_leak else out + ".m.mp4", (pw, ph), enc, s.get("mask") or {})
        os.remove(target)
        target = out + ".m.mp4" if use_leak else out
    if use_leak:
        leak_pass(target, out, (pw, ph), enc)
        os.remove(target)
    if "video" in s:
        run(["-ss", str(s["in"]), "-t", f"{dur:.3f}", "-i", os.path.join(ROOT, s["video"]), "-vn",
             "-af", f"apad,atrim=0:{dur:.3f}", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", wav])
    else:
        run(["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo", "-c:a", "pcm_s16le", wav])
    return round(dur * FPS) / FPS


def overlay(spec, total, tmp, size=(1080, 1920)):
    """Render the text layers to a transparent ProRes clip (None if there are none)."""
    layers = spec.get("layers") or []
    if not layers:
        return None
    pw, ph, y = geometry(spec.get("frame", "full"), *size)
    data = {"w": size[0], "h": size[1], "band": {"top": y, "h": ph} if ph < size[1] else None, "layers": layers}
    jpath = os.path.join(tmp, "layers.json")
    json.dump(data, open(jpath, "w"), ensure_ascii=False)
    out = os.path.join(tmp, "layers.mov")
    page = os.path.join(ROOT, "motion", "templates", "overlay.html") + "#spec=" + os.path.relpath(jpath, ROOT)
    subprocess.run(["node", os.path.join(ROOT, "motion", "render.mjs"), page, out, f"{total:.3f}", str(FPS),
                    str(size[0]), str(size[1])],
                   check=True, cwd=os.path.join(ROOT, "motion"))
    return out


def main(spec_path, preview=False):
    spec = json.load(open(spec_path))
    name = spec["name"]
    tmp = os.path.join(ROOT, "work", "stylecut", name)
    os.makedirs(tmp, exist_ok=True)
    frame = spec.get("frame", "full")
    size = ASPECTS.get(spec.get("aspect", "9:16"), ASPECTS["9:16"])
    W, H = size
    enc = ("veryfast", "20") if preview else ("medium", "15")

    vids, wavs, durs = [], [], []
    for i, s in enumerate(spec["shots"]):
        v, a = os.path.join(tmp, f"s{i}.mp4"), os.path.join(tmp, f"s{i}.wav")
        durs.append(shot(s, v, a, frame, enc, size, vids[-1] if vids else None))
        vids.append(v)
        wavs.append(a)
    total = sum(durs)
    ov = overlay(spec, total, tmp, size)

    look = spec.get("look", {})
    grade = GRADES.get(look.get("grade", "natural"), GRADES["natural"])
    pw, ph, y = geometry(frame, W, H)
    n = len(vids)
    inputs = []
    for f in vids + wavs:
        inputs += ["-i", f]
    chain = ["".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0,{grade}"
             + (f",vignette=angle={0.2 + 0.5 * float(look['vignette']):.2f}" if look.get("vignette") else "")
             + (f",noise=alls={round(4 + 14 * float(look['grain']))}:allf=t" if look.get("grain") else "")
             + (f",pad={W}:{H}:0:{y}:black" if ph < H else "") + ",format=yuv420p[base]"]
    k = 2 * n
    if ov:
        inputs += ["-i", ov]
        chain.append(f"[base][{k}:v]overlay=0:0:format=auto,format=yuv420p[v]")
        k += 1
    else:
        chain.append("[base]null[v]")
    music, voice = spec.get("music"), spec.get("voice")
    amb_db = spec.get("ambient_db", -6 if music else -2)
    chain.append("".join(f"[{n + i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1,volume={amb_db}dB[amb]")
    mix = ["[amb]"]
    if music:
        inputs += ["-ss", str(music.get("start", 0)), "-i", os.path.join(ROOT, music["file"])]
        fo = music.get("fade_out", 1.5)
        chain.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={music.get('db', -4)}dB,"
                     f"apad,atrim=0:{total:.3f},afade=t=out:st={max(0, total - fo):.3f}:d={fo}[mus]")
        mix.append("[mus]")
        k += 1
    if voice:
        inputs += ["-i", os.path.join(ROOT, voice["file"])]
        ms = int(voice.get("start", 0) * 1000)
        chain.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms},apad,"
                     f"atrim=0:{total:.3f},asplit[vo][key]")
        chain.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0[bed]")
        chain.append("[bed][key]sidechaincompress=threshold=0.02:ratio=8:attack=30:release=400[duck]")
        mix = ["[duck]", "[vo]"]
        k += 1
    chain.append("".join(mix) + (f"amix=inputs={len(mix)}:normalize=0," if len(mix) > 1 else "anull,")
                 + f"loudnorm=I=-14:TP=-1.5:LRA=11,atrim=0:{total:.3f}[a]")

    out_dir = os.path.join(ROOT, "work", "preview") if preview else os.path.join(ROOT, "out", name)
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, f"{name}.mp4")
    run([*inputs, "-filter_complex", ";".join(chain), "-map", "[v]", "-map", "[a]", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "veryfast" if preview else "slow", "-crf", "24" if preview else "17",
         "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", dst])
    if spec.get("post") and not preview:
        write_caption(os.path.join(out_dir, "caption.txt"), spec["post"])
    starts = [round(sum(durs[:i]), 2) for i in range(n)]
    print(f"{dst}  ({total:.2f}s)  shot starts: {starts}")
    return dst, total


if __name__ == "__main__":
    main(sys.argv[1], preview="--preview" in sys.argv)
