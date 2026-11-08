"""FFmpeg tool family (t506): typed operations that each measure -> process -> verify.

Every operation declares a JSON schema for its arguments, reads its inputs with ffprobe first (duration, size, frame
rate, audio), builds one ffmpeg command from what it measured, and checks the output against what it promised
(duration, size, frame rate, streams, loudness, file size). A failed check is reported, not hidden:

    r = fftools.run("trim", ["in.mp4"], "out.mp4", {"start": 2, "end": 7.5})
    r["ok"], r["checks"]          # [{"what": "duration", "want": 5.5, "got": 5.5, "ok": True}, ...]

Groups: time (trim, cut, keep, concat, crossfade, speed, speed_ramp, loop, reverse, freeze, fade), frame (fit, crop,
autocrop, resize, rotate, flip, fps), fix (stabilize, denoise, deinterlace, sharpen, color, lut, vignette), overlay
(watermark, text, censor, delogo, pip, multicam, chroma, subtitles), audio (loudnorm, denoise_audio, silence_cut,
volume, mute, replace_audio, music_bed, extract_audio, sync, channels), output (transcode, compress, frame) and
measure-only (probe, scenes, silences, loudness, black, freezes, sync_offset, crop_detect).

Free and local: nothing here spends credits. Platform delivery templates and the safe-area check build on this in
factory/delivery.py.
"""
import json, math, os, re, subprocess, tempfile, time

import jsonschema

from .config import FFMPEG, FFPROBE, ROOT

OPS = {}
GROUPS = ("time", "frame", "fix", "overlay", "audio", "output", "measure")
DUR_TOL = 0.12
FONT = os.path.join(ROOT, "fonts", "Poppins-Bold.ttf")


class FFError(RuntimeError):
    pass


BAD_SOURCES = frozenset({"hls", "m3u8", "m3u", "pls", "applehttp", "concat", "ffconcat", "dash", "mpd", "mpegdash",
                         "rtsp", "rtp", "sdp", "tee", "image2pipe_playlist", "libmodplug"})


def check_source(path):
    """Refuse an input that is a playlist/protocol rather than a file (SSRF and local traversal through ffmpeg)."""
    s = str(path or "")
    if s.startswith(("http://", "https://", "rtsp://", "rtmp://", "tcp://", "udp://")):
        raise ValueError(f"uzak akış reddedildi: kaynağı indirip dosya olarak ver ({s[:80]})")
    ext = os.path.splitext(s)[1].lower().lstrip(".")
    if ext in BAD_SOURCES:
        raise ValueError(f"'{ext}' bir oynatma listesi/kapsayıcı biçimi; dosya olarak indir")
    return s


def op(name, group, summary, schema=None, inputs=1, ext="mp4", measure=False):
    """Register fn(ins, a, tmp) -> {"argv": [...], "expect": {...}} (or {"data": ...} for a measure op).
    `ins` are measured inputs (dicts with "path"), `a` the validated arguments with defaults, `tmp` a scratch dir."""
    assert group in GROUPS, group
    sch = schema or {"type": "object", "properties": {}}
    sch.setdefault("additionalProperties", False)

    def wrap(fn):
        OPS[name] = {"name": name, "group": group, "summary": summary, "schema": sch, "inputs": inputs,
                     "ext": ext, "measure": measure, "fn": fn}
        return fn
    return wrap


def describe():
    return [{k: v for k, v in o.items() if k != "fn"} for o in OPS.values()]


# ---------------------------------------------------------------- measure

def _rate(s):
    try:
        a, b = (s or "0/1").split("/")
        return round(float(a) / float(b), 3) if float(b) else 0.0
    except ValueError:
        return 0.0


def measure(path):
    """What a media file is: {path, duration, size, video, width, height, fps, vcodec, pix_fmt, audio, sr, channels}."""
    if not os.path.exists(path):
        raise FFError(f"missing file: {path}")
    r = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                       capture_output=True, text=True)
    if r.returncode:
        raise FFError(f"ffprobe cannot read {os.path.basename(path)}: {r.stderr.strip()[-200:]}")
    j = json.loads(r.stdout or "{}")
    fmt = j.get("format") or {}
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"
              and not (s.get("disposition") or {}).get("attached_pic")), None)
    a = next((s for s in j.get("streams", []) if s.get("codec_type") == "audio"), None)
    m = {"path": path, "duration": round(float(fmt.get("duration") or 0), 3), "size": int(fmt.get("size") or 0),
         "video": bool(v), "audio": bool(a)}
    if v:
        w, h = int(v.get("width") or 0), int(v.get("height") or 0)
        rot = 0
        for sd in v.get("side_data_list") or []:
            if "rotation" in sd:
                rot = int(sd["rotation"])
        rot = rot or int((v.get("tags") or {}).get("rotate") or 0)
        if abs(rot) % 180 == 90:
            w, h = h, w
        m.update(width=w, height=h, fps=_rate(v.get("avg_frame_rate")) or _rate(v.get("r_frame_rate")),
                 vcodec=v.get("codec_name"), pix_fmt=v.get("pix_fmt"), frames=int(v.get("nb_frames") or 0),
                 vduration=round(float(v.get("duration") or 0), 3))
        if not m["duration"]:
            m["duration"] = round(float(v.get("duration") or 0), 3)
    if a:
        m.update(sr=int(a.get("sample_rate") or 0), channels=int(a.get("channels") or 0), acodec=a.get("codec_name"))
    return m


def _ff(argv, what="ffmpeg"):
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-y"] + [str(x) for x in argv], capture_output=True,
                       text=True)
    if r.returncode:
        raise FFError(f"{what} failed: {r.stderr.strip()[-400:]}")
    return r.stderr


def lufs(path):
    """Integrated loudness, loudness range and true peak of a file's audio (EBU R128)."""
    err = _ff(["-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"], "loudness")
    m = re.search(r"Integrated loudness:\s+I:\s+([-\d.]+) LUFS.*?LRA:\s+([-\d.]+) LU.*?Peak:\s+([-\d.]+) dBFS", err, re.S)
    return {"lufs": float(m.group(1)), "lra": float(m.group(2)), "true_peak": float(m.group(3))} if m else {}


# ---------------------------------------------------------------- shared pieces

def _vid(fps=None):
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


AUD = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
COPY_V = ["-c:v", "copy"]


def _even(x):
    return max(2, int(x) // 2 * 2)


def _same(m, **over):
    """Expectations for an output that keeps the input's duration, size and streams."""
    e = {"duration": m["duration"], "video": m["video"], "audio": m["audio"]}
    if m["video"]:
        e.update(width=m["width"], height=m["height"])
    return e | over


def _atempo(f):
    out = []
    while f > 2.0:
        out.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        out.append("atempo=0.5")
        f /= 0.5
    out.append(f"atempo={f:.6f}")
    return ",".join(out)


def _between(ranges):
    return "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in ranges)


def _merge(ranges, total):
    rs = sorted((max(0.0, float(a)), min(total, float(b))) for a, b in ranges)
    out = []
    for a, b in rs:
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _norm_inputs(ins, W, H, fps):
    """Filter chains bringing every input to W x H at fps with stereo 48 kHz audio; inputs without audio get a
    silent track from an extra lavfi input. Returns (extra input argv, filter parts, video labels, audio labels)."""
    extra, parts, vl, al = [], [], [], []
    k = len(ins)
    for i, m in enumerate(ins):
        parts.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
                     f"setsar=1,fps={fps},format=yuv420p,settb=AVTB[v{i}]")
        if m["audio"]:
            parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
        else:
            extra += ["-f", "lavfi", "-t", f"{m['duration']:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            parts.append(f"[{k}:a]aformat=channel_layouts=stereo[a{i}]")
            k += 1
        vl.append(f"[v{i}]")
        al.append(f"[a{i}]")
    return extra, parts, vl, al


def _i(ins):
    out = []
    for m in ins:
        out += ["-protocol_whitelist", "file,pipe", "-i", m["path"]]
    return out


def _fc(parts):
    return ["-filter_complex", ";".join(parts)]


def _need_video(m):
    if not m["video"]:
        raise FFError(f"{os.path.basename(m['path'])} has no video")


def _need_audio(m):
    if not m["audio"]:
        raise FFError(f"{os.path.basename(m['path'])} has no audio")


NUM = {"type": "number"}
POS = {"type": "number", "minimum": 0}
CORNER = {"type": "string", "enum": ["tl", "tr", "bl", "br", "center", "top", "bottom"], "default": "br"}
BOX = {"type": "object", "required": ["x", "y", "w", "h"], "additionalProperties": False,
       "properties": {"x": POS, "y": POS, "w": {"type": "number", "minimum": 2}, "h": {"type": "number", "minimum": 2},
                      "start": POS, "end": POS}}
RANGES = {"type": "array", "minItems": 1, "items": {"type": "array", "minItems": 2, "maxItems": 2, "items": POS}}


def _place(corner, margin, w="w", h="h", W="W", H="H"):
    return {"tl": (f"{margin}", f"{margin}"), "tr": (f"{W}-{w}-{margin}", f"{margin}"),
            "bl": (f"{margin}", f"{H}-{h}-{margin}"), "br": (f"{W}-{w}-{margin}", f"{H}-{h}-{margin}"),
            "center": (f"({W}-{w})/2", f"({H}-{h})/2"), "top": (f"({W}-{w})/2", f"{margin}"),
            "bottom": (f"({W}-{w})/2", f"{H}-{h}-{margin}")}[corner]


# ---------------------------------------------------------------- time

@op("trim", "time", "Keep one stretch of the video, frame-accurate.",
    {"type": "object", "required": ["start"], "properties": {"start": POS, "end": POS, "duration": POS}})
def _trim(ins, a, tmp):
    m = ins[0]
    end = a.get("end") if a.get("end") is not None else a["start"] + a.get("duration", m["duration"])
    end = min(end, m["duration"])
    if end <= a["start"]:
        raise FFError("trim: end must be after start")
    d = end - a["start"]
    return {"argv": ["-ss", f"{a['start']:.3f}", "-i", m["path"], "-t", f"{d:.3f}"] + _vid() + AUD,
            "expect": _same(m, duration=round(d, 3))}


@op("cut", "time", "Remove one or more stretches ([[start, end], ...]) and close the gaps.",
    {"type": "object", "required": ["ranges"], "properties": {"ranges": RANGES}})
def _cut(ins, a, tmp):
    m = ins[0]
    rs = _merge(a["ranges"], m["duration"])
    if not rs:
        raise FFError("cut: no range inside the video")
    gone = sum(b - x for x, b in rs)
    if gone >= m["duration"] - 0.1:
        raise FFError("cut: that removes the whole video")
    sel = _between(rs)
    argv = ["-i", m["path"]]
    if m["video"]:
        argv += ["-vf", f"select='not({sel})',setpts=N/FRAME_RATE/TB"]
    if m["audio"]:
        argv += ["-af", f"aselect='not({sel})',asetpts=N/SR/TB"]
    return {"argv": argv + _vid() + AUD, "expect": _same(m, duration=round(m["duration"] - gone, 3)), "tol": 0.15}


@op("keep", "time", "Keep only the given stretches ([[start, end], ...]), joined in order.",
    {"type": "object", "required": ["ranges"], "properties": {"ranges": RANGES}})
def _keep(ins, a, tmp):
    m = ins[0]
    rs = _merge(a["ranges"], m["duration"])
    if not rs:
        raise FFError("keep: no range inside the video")
    sel = _between(rs)
    argv = ["-i", m["path"]]
    if m["video"]:
        argv += ["-vf", f"select='{sel}',setpts=N/FRAME_RATE/TB"]
    if m["audio"]:
        argv += ["-af", f"aselect='{sel}',asetpts=N/SR/TB"]
    return {"argv": argv + _vid() + AUD, "expect": _same(m, duration=round(sum(b - x for x, b in rs), 3)), "tol": 0.15}


@op("concat", "time", "Join clips one after another; every clip is brought to the first one's size and frame rate "
    "(letterboxed if its shape differs); clips without sound get silence.",
    {"type": "object", "properties": {"width": {"type": "integer", "minimum": 16}, "height": {"type": "integer", "minimum": 16},
                                      "fps": {"type": "number", "minimum": 1, "maximum": 120}}}, inputs=(2, 20))
def _concat(ins, a, tmp):
    for m in ins:
        _need_video(m)
    W, H = _even(a.get("width") or ins[0]["width"]), _even(a.get("height") or ins[0]["height"])
    fps = a.get("fps") or ins[0]["fps"] or 30
    extra, parts, vl, al = _norm_inputs(ins, W, H, fps)
    parts.append("".join(v + x for v, x in zip(vl, al)) + f"concat=n={len(ins)}:v=1:a=1[v][a]")
    return {"argv": _i(ins) + extra + _fc(parts) + ["-map", "[v]", "-map", "[a]"] + _vid() + AUD,
            "expect": {"duration": round(sum(m["duration"] for m in ins), 3), "width": W, "height": H, "fps": fps,
                       "video": True, "audio": True}, "tol": 0.1 * len(ins)}


@op("crossfade", "time", "Join two clips with a transition (xfade) and a matching audio crossfade.",
    {"type": "object", "properties": {"duration": {"type": "number", "minimum": 0.1, "maximum": 5, "default": 0.5},
                                      "transition": {"type": "string", "default": "fade", "enum": [
                                          "fade", "fadeblack", "fadewhite", "dissolve", "wipeleft", "wiperight",
                                          "slideleft", "slideright", "slideup", "slidedown", "circleopen",
                                          "circleclose", "radial", "smoothleft", "smoothright", "zoomin"]}}},
    inputs=(2, 2))
def _crossfade(ins, a, tmp):
    for m in ins:
        _need_video(m)
    d = a["duration"]
    if d >= min(m["duration"] for m in ins):
        raise FFError("crossfade: the transition is longer than a clip")
    W, H, fps = _even(ins[0]["width"]), _even(ins[0]["height"]), ins[0]["fps"] or 30
    extra, parts, vl, al = _norm_inputs(ins, W, H, fps)
    off = ins[0]["duration"] - d
    parts += [f"{vl[0]}{vl[1]}xfade=transition={a['transition']}:duration={d}:offset={off:.3f}[v]",
              f"{al[0]}{al[1]}acrossfade=d={d}[a]"]
    return {"argv": _i(ins) + extra + _fc(parts) + ["-map", "[v]", "-map", "[a]"] + _vid() + AUD,
            "expect": {"duration": round(ins[0]["duration"] + ins[1]["duration"] - d, 3), "width": W, "height": H,
                       "video": True, "audio": True}, "tol": 0.15}


@op("speed", "time", "Play faster or slower (0.25-4x); the voice keeps its pitch unless pitch=false.",
    {"type": "object", "required": ["factor"], "properties": {
        "factor": {"type": "number", "minimum": 0.25, "maximum": 4}, "pitch": {"type": "boolean", "default": True}}})
def _speed(ins, a, tmp):
    m, f = ins[0], a["factor"]
    argv = ["-i", m["path"]]
    if m["video"]:
        argv += ["-vf", f"setpts=PTS/{f}"]
    if m["audio"]:
        argv += ["-af", _atempo(f) if a["pitch"] else f"asetrate={m.get('sr') or 48000}*{f},aresample=48000"]
    return {"argv": argv + _vid() + AUD, "expect": _same(m, duration=round(m["duration"] / f, 3)), "tol": 0.15}


@op("speed_ramp", "time", "Different speeds for different stretches ([{start, end, speed}]); the rest plays at 1x.",
    {"type": "object", "required": ["segments"], "properties": {"segments": {"type": "array", "minItems": 1, "items": {
        "type": "object", "required": ["start", "end", "speed"], "additionalProperties": False,
        "properties": {"start": POS, "end": POS, "speed": {"type": "number", "minimum": 0.25, "maximum": 4}}}}}})
def _ramp(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    segs, t = [], 0.0
    for s in sorted(a["segments"], key=lambda s: s["start"]):
        st, en = max(t, s["start"]), min(m["duration"], s["end"])
        if en <= st:
            continue
        if st > t + 0.01:
            segs.append((t, st, 1.0))
        segs.append((st, en, s["speed"]))
        t = en
    if t < m["duration"] - 0.01:
        segs.append((t, m["duration"], 1.0))
    n = len(segs)
    parts = [f"[0:v]split={n}" + "".join(f"[vs{i}]" for i in range(n))]
    if m["audio"]:
        parts.append(f"[0:a]asplit={n}" + "".join(f"[as{i}]" for i in range(n)))
    cat = ""
    for i, (x, y, s) in enumerate(segs):
        parts.append(f"[vs{i}]trim={x:.3f}:{y:.3f},setpts=(PTS-STARTPTS)/{s}[v{i}]")
        if m["audio"]:
            parts.append(f"[as{i}]atrim={x:.3f}:{y:.3f},asetpts=PTS-STARTPTS,{_atempo(s)}[a{i}]")
        cat += f"[v{i}]" + (f"[a{i}]" if m["audio"] else "")
    parts.append(cat + f"concat=n={n}:v=1:a={1 if m['audio'] else 0}[v]" + ("[a]" if m["audio"] else ""))
    maps = ["-map", "[v]"] + (["-map", "[a]"] if m["audio"] else [])
    return {"argv": ["-i", m["path"]] + _fc(parts) + maps + _vid() + (AUD if m["audio"] else ["-an"]),
            "expect": _same(m, duration=round(sum((y - x) / s for x, y, s in segs), 3)), "tol": 0.1 + 0.04 * n}


@op("loop", "time", "Repeat the whole clip a number of times.",
    {"type": "object", "required": ["times"], "properties": {"times": {"type": "integer", "minimum": 2, "maximum": 50}}})
def _loop(ins, a, tmp):
    m = ins[0]
    return {"argv": ["-stream_loop", str(a["times"] - 1), "-i", m["path"]] + _vid() + AUD,
            "expect": _same(m, duration=round(m["duration"] * a["times"], 3)), "tol": 0.06 * a["times"]}


@op("reverse", "time", "Play backwards, sound too (clips up to 60 s: the whole clip is held in memory).")
def _reverse(ins, a, tmp):
    m = ins[0]
    if m["duration"] > 60:
        raise FFError("reverse: clip longer than 60 s; trim it first")
    argv = ["-i", m["path"]] + (["-vf", "reverse"] if m["video"] else []) + (["-af", "areverse"] if m["audio"] else [])
    return {"argv": argv + _vid() + AUD, "expect": _same(m)}


@op("freeze", "time", "Hold the frame at `at` for `seconds` (silence under it), then play on.",
    {"type": "object", "required": ["at", "seconds"], "properties": {"at": POS, "seconds": {"type": "number", "minimum": 0.1, "maximum": 30}}})
def _freeze(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    at, s, fps = min(a["at"], m["duration"] - 0.05), a["seconds"], m["fps"] or 30
    parts = [f"[0:v]split[va][vb]", f"[va]trim=0:{at:.3f},setpts=PTS-STARTPTS[v1]",
             f"[vb]trim=start={at:.3f},setpts=PTS-STARTPTS,split[vc][vd]",
             f"[vc]trim=end_frame=1,loop=loop={max(0, round(s * fps) - 1)}:size=1:start=0,setpts=N/{fps}/TB[vf]",
             f"[vd]setpts=PTS-STARTPTS[v2]"]
    if m["audio"]:
        parts += ["[0:a]aresample=48000,aformat=channel_layouts=stereo,asplit[aa][ab]", f"[aa]atrim=0:{at:.3f},asetpts=PTS-STARTPTS[a1]",
                  f"[ab]atrim=start={at:.3f},asetpts=PTS-STARTPTS[a2]",
                  f"anullsrc=r=48000:cl=stereo,atrim=0:{s:.3f}[a0]", "[v1][a1][vf][a0][v2][a2]concat=n=3:v=1:a=1[v][a]"]
        maps = ["-map", "[v]", "-map", "[a]"]
    else:
        parts.append("[v1][vf][v2]concat=n=3:v=1:a=0[v]")
        maps = ["-map", "[v]"]
    return {"argv": ["-i", m["path"]] + _fc(parts) + maps + _vid() + (AUD if m["audio"] else ["-an"]),
            "expect": _same(m, duration=round(m["duration"] + s, 3)), "tol": 0.15}


@op("fade", "time", "Fade in from / out to black (or white), sound with it.",
    {"type": "object", "properties": {"in": {"type": "number", "minimum": 0, "maximum": 10, "default": 0.5},
                                      "out": {"type": "number", "minimum": 0, "maximum": 10, "default": 0.5},
                                      "color": {"type": "string", "enum": ["black", "white"], "default": "black"}}})
def _fade(ins, a, tmp):
    m = ins[0]
    d, fi, fo = m["duration"], a["in"], a["out"]
    vf, af = [], []
    if fi:
        vf.append(f"fade=t=in:st=0:d={fi}:color={a['color']}")
        af.append(f"afade=t=in:st=0:d={fi}")
    if fo:
        vf.append(f"fade=t=out:st={max(0, d - fo):.3f}:d={fo}:color={a['color']}")
        af.append(f"afade=t=out:st={max(0, d - fo):.3f}:d={fo}")
    argv = ["-i", m["path"]] + (["-vf", ",".join(vf)] if vf and m["video"] else []) + \
           (["-af", ",".join(af)] if af and m["audio"] else [])
    return {"argv": argv + _vid() + AUD, "expect": _same(m)}


# ---------------------------------------------------------------- frame

@op("fit", "frame", "Fit into a frame size or aspect (9:16, 16:9, 1:1, 4:5) without distortion: pad with a colour, "
    "a blurred copy of the video behind it, or crop to fill.",
    {"type": "object", "properties": {"aspect": {"type": "string", "enum": ["9:16", "16:9", "1:1", "4:5"]},
                                      "width": {"type": "integer", "minimum": 16}, "height": {"type": "integer", "minimum": 16},
                                      "mode": {"type": "string", "enum": ["pad", "blur", "crop"], "default": "blur"},
                                      "color": {"type": "string", "default": "black"}}})
def _fit(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    if a.get("width") and a.get("height"):
        W, H = _even(a["width"]), _even(a["height"])
    else:
        W, H = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}[a.get("aspect", "9:16")]
    if a["mode"] == "pad":
        vf = ["-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={a['color']},setsar=1"]
    elif a["mode"] == "crop":
        vf = ["-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"]
    else:
        vf = _fc([f"[0:v]split[b][f]", f"[b]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                  f"boxblur=24:2,eq=brightness=-0.08[bg]", f"[f]scale={W}:{H}:force_original_aspect_ratio=decrease[fg]",
                  "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"]) + ["-map", "[v]", "-map", "0:a?"]
    return {"argv": ["-i", m["path"]] + vf + _vid() + AUD, "expect": _same(m, width=W, height=H)}


@op("crop", "frame", "Crop a region: x, y, w, h in pixels, or an aspect with a horizontal / vertical centre (0-1) to "
    "reframe a wide shot for a tall frame.",
    {"type": "object", "properties": {"x": POS, "y": POS, "w": {"type": "number", "minimum": 16}, "h": {"type": "number", "minimum": 16},
                                      "aspect": {"type": "string", "enum": ["9:16", "16:9", "1:1", "4:5"]},
                                      "cx": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5},
                                      "cy": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5}}})
def _crop(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    W0, H0 = m["width"], m["height"]
    if a.get("aspect"):
        p, q = map(int, a["aspect"].split(":"))
        w, h = (W0, W0 * q / p) if W0 * q / p <= H0 else (H0 * p / q, H0)
        w, h = _even(w), _even(h)
        x = min(max(0, a["cx"] * W0 - w / 2), W0 - w)
        y = min(max(0, a["cy"] * H0 - h / 2), H0 - h)
    elif all(k in a for k in ("x", "y", "w", "h")):
        x, y = a["x"], a["y"]
        w, h = _even(min(a["w"], W0 - x)), _even(min(a["h"], H0 - y))
    else:
        raise FFError("crop: give x, y, w, h or an aspect")
    return {"argv": ["-i", m["path"], "-vf", f"crop={w}:{h}:{int(x)}:{int(y)},setsar=1"] + _vid() + AUD,
            "expect": _same(m, width=w, height=h)}


def _cropdetect(m):
    err = _ff(["-ss", f"{min(1.0, m['duration'] / 4):.2f}", "-i", m["path"], "-t", "8", "-vf", "cropdetect=24:2:0",
               "-an", "-f", "null", "-"], "cropdetect")
    found = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", err)
    if not found:
        return None
    w, h, x, y = map(int, max(set(found), key=found.count))
    return {"w": _even(w), "h": _even(h), "x": x, "y": y}


@op("autocrop", "frame", "Find black bars (letterbox / pillarbox) and crop them away.")
def _autocrop(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    c = _cropdetect(m)
    if not c or (c["w"] >= m["width"] - 4 and c["h"] >= m["height"] - 4):
        c = {"w": _even(m["width"]), "h": _even(m["height"]), "x": 0, "y": 0}
    return {"argv": ["-i", m["path"], "-vf", f"crop={c['w']}:{c['h']}:{c['x']}:{c['y']},setsar=1"] + _vid() + AUD,
            "expect": _same(m, width=c["w"], height=c["h"])}


@op("resize", "frame", "Scale to a width or height, keeping the shape.",
    {"type": "object", "properties": {"width": {"type": "integer", "minimum": 16}, "height": {"type": "integer", "minimum": 16}}})
def _resize(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    if a.get("width"):
        W = _even(a["width"])
        H = _even(round(m["height"] * W / m["width"]))
    elif a.get("height"):
        H = _even(a["height"])
        W = _even(round(m["width"] * H / m["height"]))
    else:
        raise FFError("resize: give width or height")
    return {"argv": ["-i", m["path"], "-vf", f"scale={W}:{H}:flags=lanczos,setsar=1"] + _vid() + AUD,
            "expect": _same(m, width=W, height=H)}


@op("rotate", "frame", "Turn by 90, 180 or 270 degrees clockwise.",
    {"type": "object", "required": ["degrees"], "properties": {"degrees": {"type": "integer", "enum": [90, 180, 270]}}})
def _rotate(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    vf = {90: "transpose=1", 180: "transpose=1,transpose=1", 270: "transpose=2"}[a["degrees"]]
    w, h = (m["height"], m["width"]) if a["degrees"] != 180 else (m["width"], m["height"])
    return {"argv": ["-i", m["path"], "-vf", vf] + _vid() + AUD, "expect": _same(m, width=w, height=h)}


@op("flip", "frame", "Mirror horizontally or vertically.",
    {"type": "object", "properties": {"direction": {"type": "string", "enum": ["h", "v"], "default": "h"}}})
def _flip(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    return {"argv": ["-i", m["path"], "-vf", "hflip" if a["direction"] == "h" else "vflip"] + _vid() + AUD,
            "expect": _same(m)}


@op("fps", "frame", "Change the frame rate: drop/duplicate frames, blend them, or interpolate motion (slow).",
    {"type": "object", "required": ["rate"], "properties": {"rate": {"type": "number", "minimum": 1, "maximum": 120},
                                                            "mode": {"type": "string", "enum": ["drop", "blend", "interpolate"], "default": "drop"}}})
def _fps(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    r = a["rate"]
    vf = {"drop": f"fps={r}", "blend": f"framerate=fps={r}", "interpolate": f"minterpolate=fps={r}:mi_mode=mci"}[a["mode"]]
    return {"argv": ["-i", m["path"], "-vf", vf] + _vid() + AUD, "expect": _same(m, fps=r)}


# ---------------------------------------------------------------- fix

@op("stabilize", "fix", "Steady a shaky handheld shot (two passes: measure the shake, then smooth it; the edges are "
    "zoomed in slightly so no black borders show).",
    {"type": "object", "properties": {"strength": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}}})
def _stabilize(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    trf = os.path.join(tmp, "shake.trf")
    _ff(["-i", m["path"], "-vf", f"vidstabdetect=shakiness={min(10, a['strength'] + 3)}:accuracy=12:result={trf}",
         "-an", "-f", "null", "-"], "stabilize (measure)")
    vf = f"vidstabtransform=input={trf}:smoothing={a['strength'] * 6}:optzoom=1:interpol=bicubic,unsharp=5:5:0.6"
    return {"argv": ["-i", m["path"], "-vf", vf] + _vid() + AUD, "expect": _same(m)}


@op("denoise", "fix", "Clean up grainy low-light video.",
    {"type": "object", "properties": {"strength": {"type": "string", "enum": ["light", "medium", "strong"], "default": "medium"},
                                      "method": {"type": "string", "enum": ["fast", "best"], "default": "fast"}}})
def _denoise(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    if a["method"] == "best":
        vf = f"nlmeans=s={ {'light': 2, 'medium': 3.5, 'strong': 6}[a['strength']] }"
    else:
        vf = "hqdn3d=" + {"light": "2:1.5:3:2.5", "medium": "4:3:6:4.5", "strong": "8:6:12:9"}[a["strength"]]
    return {"argv": ["-i", m["path"], "-vf", vf] + _vid() + AUD, "expect": _same(m)}


@op("deinterlace", "fix", "Remove the comb lines of interlaced footage.")
def _deinterlace(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    return {"argv": ["-i", m["path"], "-vf", "yadif=0:-1:0"] + _vid() + AUD, "expect": _same(m)}


@op("sharpen", "fix", "Sharpen soft footage (0.3 subtle - 2 strong).",
    {"type": "object", "properties": {"amount": {"type": "number", "minimum": 0.1, "maximum": 2.5, "default": 0.8}}})
def _sharpen(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    return {"argv": ["-i", m["path"], "-vf", f"unsharp=5:5:{a['amount']}:5:5:0"] + _vid() + AUD, "expect": _same(m)}


@op("color", "fix", "Colour correction: brightness (-1..1), contrast, saturation, gamma (1 = unchanged) and white "
    "balance as a colour temperature in kelvin (6500 = neutral; lower is warmer).",
    {"type": "object", "properties": {"brightness": {"type": "number", "minimum": -1, "maximum": 1, "default": 0},
                                      "contrast": {"type": "number", "minimum": 0, "maximum": 3, "default": 1},
                                      "saturation": {"type": "number", "minimum": 0, "maximum": 3, "default": 1},
                                      "gamma": {"type": "number", "minimum": 0.1, "maximum": 3, "default": 1},
                                      "temperature": {"type": "number", "minimum": 1000, "maximum": 40000}}})
def _color(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    vf = f"eq=brightness={a['brightness']}:contrast={a['contrast']}:saturation={a['saturation']}:gamma={a['gamma']}"
    if a.get("temperature"):
        vf += f",colortemperature=temperature={int(a['temperature'])}"
    return {"argv": ["-i", m["path"], "-vf", vf] + _vid() + AUD, "expect": _same(m)}


@op("lut", "fix", "Apply a colour look from a .cube LUT file.",
    {"type": "object", "required": ["file"], "properties": {"file": {"type": "string"},
                                                            "mix": {"type": "number", "minimum": 0, "maximum": 1, "default": 1}}})
def _lut(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    if not (os.path.exists(a["file"]) and a["file"].lower().endswith(".cube")):
        raise FFError("lut: needs an existing .cube file")
    f = a["file"].replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    if a["mix"] >= 1:
        argv = ["-vf", f"lut3d=file='{f}'"]
    else:
        argv = _fc([f"[0:v]split[o][l]", f"[l]lut3d=file='{f}'[g]",
                    f"[o][g]blend=all_mode=normal:all_opacity={a['mix']}[v]"]) + ["-map", "[v]", "-map", "0:a?"]
    return {"argv": ["-i", m["path"]] + argv + _vid() + AUD, "expect": _same(m)}


@op("vignette", "fix", "Darken the corners to pull the eye to the centre.",
    {"type": "object", "properties": {"strength": {"type": "number", "minimum": 0.1, "maximum": 1, "default": 0.4}}})
def _vignette(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    return {"argv": ["-i", m["path"], "-vf", f"vignette=angle={math.pi / 2 * a['strength']:.4f}"] + _vid() + AUD,
            "expect": _same(m)}


# ---------------------------------------------------------------- overlay

@op("watermark", "overlay", "Put a logo or watermark image (input 2) in a corner, scaled to a share of the width, "
    "with an opacity.",
    {"type": "object", "properties": {"corner": CORNER, "scale": {"type": "number", "minimum": 0.03, "maximum": 0.6, "default": 0.15},
                                      "opacity": {"type": "number", "minimum": 0.05, "maximum": 1, "default": 0.8},
                                      "margin": {"type": "integer", "minimum": 0, "default": 40}}}, inputs=(2, 2))
def _watermark(ins, a, tmp):
    m, wm = ins
    _need_video(m)
    x, y = _place(a["corner"], a["margin"], "w", "h", "W", "H")
    ww = _even(m["width"] * a["scale"])
    parts = [f"[1:v]scale={ww}:-1,format=rgba,colorchannelmixer=aa={a['opacity']}[wm]",
             f"[0:v][wm]overlay={x}:{y}:eof_action=repeat[v]"]
    return {"argv": ["-i", m["path"], "-loop", "1", "-i", wm["path"]] + _fc(parts) + ["-map", "[v]", "-map", "0:a?", "-t",
            f"{m['duration']:.3f}"] + _vid() + AUD, "expect": _same(m)}


@op("text", "overlay", "Draw a line of text (title, lower third, label) for a stretch of time, optionally on a box.",
    {"type": "object", "required": ["text"], "properties": {
        "text": {"type": "string", "minLength": 1, "maxLength": 300}, "position": CORNER | {"default": "bottom"},
        "size": {"type": "integer", "minimum": 10, "maximum": 300, "default": 64},
        "color": {"type": "string", "default": "white"}, "box": {"type": "boolean", "default": True},
        "margin": {"type": "integer", "minimum": 0, "default": 120}, "start": POS, "end": POS}})
def _text(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    png = _text_png(a["text"], a["size"], a["color"], a["box"], m["width"] - 2 * min(a["margin"], m["width"] // 8),
                    os.path.join(tmp, "text.png"))
    x, y = _place(a["position"], a["margin"])
    en = ""
    if a.get("start") is not None or a.get("end") is not None:
        en = f":enable='between(t,{a.get('start') or 0},{a.get('end') if a.get('end') is not None else m['duration']})'"
    return {"argv": ["-i", m["path"], "-i", png] + _fc([f"[0:v][1:v]overlay={x}:{y}{en}[v]"]) +
            ["-map", "[v]", "-map", "0:a?"] + _vid() + AUD, "expect": _same(m)}


def _text_png(text, size, color, box, max_w, dst):
    """The text as a transparent picture (this ffmpeg build has no drawtext): wrapped to max_w, on a dark box or
    with an outline."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(FONT, size)
    except OSError:
        font = ImageFont.load_default()
    d = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    lines = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split():
            t = f"{cur} {w}".strip()
            if cur and d.textlength(t, font=font) > max_w - 40:
                lines.append(cur)
                cur = w
            else:
                cur = t
        lines.append(cur)
    lh = int(size * 1.25)
    tw = int(max(d.textlength(l, font=font) for l in lines)) + 2
    pad = 18 if box else 4
    img = Image.new("RGBA", (tw + 2 * pad, lh * len(lines) + 2 * pad), (0, 0, 0, 140 if box else 0))
    dr = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        dr.text((pad, pad + i * lh), l, font=font, fill=color,
                **({} if box else {"stroke_width": max(2, size // 20), "stroke_fill": (0, 0, 0, 160)}))
    img.save(dst)
    return dst


@op("censor", "overlay", "Hide regions (faces, plates, screens) with blur, pixelation or a black box; each box has "
    "pixel x, y, w, h and an optional start/end time.",
    {"type": "object", "required": ["boxes"], "properties": {
        "boxes": {"type": "array", "minItems": 1, "maxItems": 12, "items": BOX},
        "mode": {"type": "string", "enum": ["blur", "pixelate", "black"], "default": "blur"}}})
def _censor(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    parts, cur = [], "[0:v]"
    for i, b in enumerate(a["boxes"]):
        x, y = int(min(b["x"], m["width"] - 2)), int(min(b["y"], m["height"] - 2))
        w, h = _even(min(b["w"], m["width"] - x)), _even(min(b["h"], m["height"] - y))
        en = (f":enable='between(t,{b.get('start') or 0},{b['end']})'" if b.get("end") is not None else
              f":enable='gte(t,{b['start']})'" if b.get("start") else "")
        if a["mode"] == "black":
            parts.append(f"{cur}drawbox=x={x}:y={y}:w={w}:h={h}:color=black:t=fill{en}[c{i}]")
        else:
            fx = f"boxblur={max(2, min(w, h) // 8)}:3" if a["mode"] == "blur" else f"pixelize=w={max(4, w // 10)}:h={max(4, h // 10)}"
            parts += [f"{cur}split[s{i}][r{i}]", f"[r{i}]crop={w}:{h}:{x}:{y},{fx}[b{i}]",
                      f"[s{i}][b{i}]overlay={x}:{y}{en}[c{i}]"]
        cur = f"[c{i}]"
    return {"argv": ["-i", m["path"]] + _fc(parts) + ["-map", cur, "-map", "0:a?"] + _vid() + AUD, "expect": _same(m)}


@op("delogo", "overlay", "Remove a small static logo or burned-in mark by interpolating the pixels around it.",
    {"type": "object", "required": ["x", "y", "w", "h"], "properties": {"x": {"type": "integer", "minimum": 1},
                                                                         "y": {"type": "integer", "minimum": 1},
                                                                         "w": {"type": "integer", "minimum": 2},
                                                                         "h": {"type": "integer", "minimum": 2}}})
def _delogo(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    x, y = min(a["x"], m["width"] - 3), min(a["y"], m["height"] - 3)
    w, h = min(a["w"], m["width"] - x - 1), min(a["h"], m["height"] - y - 1)
    return {"argv": ["-i", m["path"], "-vf", f"delogo=x={x}:y={y}:w={w}:h={h}"] + _vid() + AUD, "expect": _same(m)}


@op("pip", "overlay", "Picture in picture: input 2 small in a corner of input 1 (sound from input 1), from `start`.",
    {"type": "object", "properties": {"corner": CORNER | {"default": "tr"},
                                      "scale": {"type": "number", "minimum": 0.1, "maximum": 0.7, "default": 0.33},
                                      "margin": {"type": "integer", "minimum": 0, "default": 40}, "start": POS,
                                      "border": {"type": "integer", "minimum": 0, "maximum": 30, "default": 6}}},
    inputs=(2, 2))
def _pip(ins, a, tmp):
    m, s = ins
    _need_video(m)
    _need_video(s)
    w = _even(m["width"] * a["scale"])
    x, y = _place(a["corner"], a["margin"])
    st = a.get("start") or 0
    parts = [f"[1:v]scale={w}:-2,pad=iw+{2 * a['border']}:ih+{2 * a['border']}:{a['border']}:{a['border']}:white,"
             f"setpts=PTS-STARTPTS+{st}/TB[p]",
             f"[0:v][p]overlay={x}:{y}:eof_action=pass:enable='gte(t,{st})'[v]"]
    return {"argv": _i(ins) + _fc(parts) + ["-map", "[v]", "-map", "0:a?"] + _vid() + AUD, "expect": _same(m)}


@op("multicam", "overlay", "Several camera angles of the same moment: side by side (hstack / vstack / grid), or a cut "
    "between them at given times ([{at, cam}], cam = input number from 0); sound from input `audio`.",
    {"type": "object", "properties": {"layout": {"type": "string", "enum": ["hstack", "vstack", "grid", "switch"], "default": "switch"},
                                      "cuts": {"type": "array", "items": {"type": "object", "required": ["at", "cam"],
                                                                          "additionalProperties": False,
                                                                          "properties": {"at": POS, "cam": {"type": "integer", "minimum": 0}}}},
                                      "audio": {"type": "integer", "minimum": 0, "default": 0}}}, inputs=(2, 4))
def _multicam(ins, a, tmp):
    for m in ins:
        _need_video(m)
    n, d = len(ins), min(m["duration"] for m in ins)
    au = min(a["audio"], n - 1)
    W, H, fps = _even(ins[0]["width"]), _even(ins[0]["height"]), ins[0]["fps"] or 30
    if a["layout"] == "switch":
        cuts = sorted([c for c in a.get("cuts") or [] if c["at"] < d and c["cam"] < n], key=lambda c: c["at"])
        if not cuts or cuts[0]["at"] > 0:
            cuts = [{"at": 0, "cam": 0}] + cuts
        segs = [(c["at"], cuts[i + 1]["at"] if i + 1 < len(cuts) else d, c["cam"]) for i, c in enumerate(cuts)]
        segs = [s for s in segs if s[1] - s[0] > 0.04]
        uses = {}
        for _, _, c in segs:
            uses[c] = uses.get(c, 0) + 1
        parts = []
        for c, k in uses.items():
            parts.append(f"[{c}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
                         f"setsar=1,fps={fps},format=yuv420p,split={k}" + "".join(f"[m{c}_{j}]" for j in range(k)))
        used, cat = {}, ""
        for i, (x, y, c) in enumerate(segs):
            j = used.get(c, 0)
            used[c] = j + 1
            parts.append(f"[m{c}_{j}]trim={x:.3f}:{y:.3f},setpts=PTS-STARTPTS[s{i}]")
            cat += f"[s{i}]"
        parts.append(cat + f"concat=n={len(segs)}:v=1:a=0[v]")
        exp = {"width": W, "height": H}
    else:
        cw, ch = (W // 2 * 2, H // 2 * 2) if a["layout"] != "grid" else (_even(W / 2), _even(H / 2))
        parts = [f"[{i}:v]scale={cw}:{ch}:force_original_aspect_ratio=decrease,pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2,"
                 f"setsar=1,fps={fps},trim=0:{d:.3f},format=yuv420p[c{i}]" for i in range(n)]
        lbl = "".join(f"[c{i}]" for i in range(n))
        if a["layout"] == "hstack":
            parts.append(f"{lbl}hstack=inputs={n}[v]")
            exp = {"width": cw * n, "height": ch}
        elif a["layout"] == "vstack":
            parts.append(f"{lbl}vstack=inputs={n}[v]")
            exp = {"width": cw, "height": ch * n}
        else:
            if n == 3:
                parts.append(f"color=black:s={cw}x{ch}:r={fps}:d={d:.3f},format=yuv420p[c3]")
                lbl += "[c3]"
            parts.append(f"{lbl}xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0[v]")
            exp = {"width": cw * 2, "height": ch * 2}
    maps = ["-map", "[v]"] + (["-map", f"{au}:a"] if ins[au]["audio"] else [])
    return {"argv": _i(ins) + _fc(parts) + maps + ["-t", f"{d:.3f}"] + _vid() + (AUD if ins[au]["audio"] else ["-an"]),
            "expect": exp | {"duration": round(d, 3), "video": True, "audio": ins[au]["audio"]}, "tol": 0.15}


@op("chroma", "overlay", "Key out a green / blue screen (input 1) and put input 2 (image or video) behind it.",
    {"type": "object", "properties": {"color": {"type": "string", "default": "0x00FF00"},
                                      "similarity": {"type": "number", "minimum": 0.01, "maximum": 0.6, "default": 0.15},
                                      "blend": {"type": "number", "minimum": 0, "maximum": 0.5, "default": 0.05}}},
    inputs=(2, 2))
def _chroma(ins, a, tmp):
    m, bg = ins
    _need_video(m)
    W, H = _even(m["width"]), _even(m["height"])
    loop = ["-loop", "1"] if bg["duration"] < 0.2 or not bg.get("fps") else ["-stream_loop", "-1"]
    parts = [f"[1:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[bg]",
             f"[0:v]chromakey={a['color']}:{a['similarity']}:{a['blend']}[fg]", "[bg][fg]overlay=shortest=1[v]"]
    return {"argv": ["-i", m["path"]] + loop + ["-i", bg["path"]] + _fc(parts) + ["-map", "[v]", "-map", "0:a?", "-t",
            f"{m['duration']:.3f}"] + _vid() + AUD, "expect": _same(m)}


@op("subtitles", "overlay", "Burn an .srt file into the picture (font size and distance from the bottom in pixels).",
    {"type": "object", "required": ["file"], "properties": {"file": {"type": "string"},
                                                            "size": {"type": "integer", "minimum": 8, "maximum": 120, "default": 18},
                                                            "margin": {"type": "integer", "minimum": 0, "maximum": 600, "default": 60}}})
def _subtitles(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    if not (os.path.exists(a["file"]) and a["file"].lower().endswith((".srt", ".ass", ".vtt"))):
        raise FFError("subtitles: needs an existing .srt / .ass / .vtt file")
    f = a["file"].replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    fd = os.path.dirname(FONT).replace(":", r"\:")
    style = f"FontName=Poppins,Bold=1,FontSize={a['size']},MarginV={a['margin']},Outline=2,Shadow=0"
    return {"argv": ["-i", m["path"], "-vf", f"subtitles='{f}':fontsdir='{fd}':force_style='{style}'"] + _vid() + AUD,
            "expect": _same(m)}


# ---------------------------------------------------------------- audio

@op("loudnorm", "audio", "Bring the sound to a loudness target (EBU R128, two passes; -14 LUFS suits TikTok / Reels / "
    "Shorts / YouTube) with a true-peak ceiling. The picture is copied untouched.",
    {"type": "object", "properties": {"target": {"type": "number", "minimum": -30, "maximum": -8, "default": -14},
                                      "peak": {"type": "number", "minimum": -6, "maximum": 0, "default": -1}}})
def _loudnorm(ins, a, tmp):
    m = ins[0]
    _need_audio(m)
    base = f"loudnorm=I={a['target']}:TP={a['peak']}:LRA=11"
    err = _ff(["-i", m["path"], "-vn", "-af", base + ":print_format=json", "-f", "null", "-"], "loudnorm (measure)")
    j = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
    af = (f"{base}:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:"
          f"measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true,aresample=48000")
    # loudnorm's look-ahead pads the end a little: keep the input's length
    return {"argv": ["-i", m["path"], "-af", af, "-t", f"{m['duration']:.3f}"] + (COPY_V if m["video"] else []) + AUD,
            "expect": _same(m, lufs=a["target"]), "tol": 0.1}


@op("denoise_audio", "audio", "Reduce background hiss, hum and room noise under a voice.",
    {"type": "object", "properties": {"strength": {"type": "string", "enum": ["light", "medium", "strong"], "default": "medium"}}})
def _denoise_audio(ins, a, tmp):
    m = ins[0]
    _need_audio(m)
    nr = {"light": 8, "medium": 14, "strong": 24}[a["strength"]]
    af = f"highpass=f=70,afftdn=nr={nr}:nf=-40:tn=1"
    return {"argv": ["-i", m["path"], "-af", af] + (COPY_V if m["video"] else []) + AUD, "expect": _same(m)}


def _silences(m, threshold, min_len):
    err = _ff(["-i", m["path"], "-vn", "-af", f"silencedetect=noise={threshold}dB:d={min_len}", "-f", "null", "-"],
              "silencedetect")
    st = [float(x) for x in re.findall(r"silence_start: ([-\d.]+)", err)]
    en = [float(x) for x in re.findall(r"silence_end: ([-\d.]+)", err)]
    out = []
    for i, s in enumerate(st):
        out.append((max(0.0, s), en[i] if i < len(en) else m["duration"]))
    return out


@op("silence_cut", "audio", "Cut the pauses: silences longer than `min_silence` seconds (quieter than `threshold` dB) "
    "are removed, keeping `keep` seconds of each so speech does not sound clipped.",
    {"type": "object", "properties": {"threshold": {"type": "number", "minimum": -70, "maximum": -15, "default": -35},
                                      "min_silence": {"type": "number", "minimum": 0.15, "maximum": 5, "default": 0.5},
                                      "keep": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.15}}})
def _silence_cut(ins, a, tmp):
    m = ins[0]
    _need_audio(m)
    k = a["keep"] / 2
    rs = [(s + k, e - k) for s, e in _silences(m, a["threshold"], a["min_silence"]) if e - s > a["keep"] + 0.05]
    if not rs:
        return {"argv": ["-i", m["path"], "-c", "copy"], "expect": _same(m), "note": "no pauses to cut"}
    r = _cut([m], {"ranges": [list(x) for x in rs]}, tmp)
    r["note"] = f"{len(rs)} pauses cut, {sum(e - s for s, e in rs):.1f} s"
    return r


@op("volume", "audio", "Make the sound louder or quieter by a number of dB (a limiter stops it clipping).",
    {"type": "object", "required": ["db"], "properties": {"db": {"type": "number", "minimum": -40, "maximum": 30}}})
def _volume(ins, a, tmp):
    m = ins[0]
    _need_audio(m)
    return {"argv": ["-i", m["path"], "-af", f"volume={a['db']}dB,alimiter=limit=0.95"] + (COPY_V if m["video"] else []) + AUD,
            "expect": _same(m)}


@op("mute", "audio", "Silence the sound (a silent track stays, so players and platforms treat it like any video).")
def _mute(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    return {"argv": ["-i", m["path"], "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a",
                     "-shortest"] + COPY_V + AUD, "expect": _same(m, audio=True), "tol": 0.1}


@op("replace_audio", "audio", "Put a new sound (input 2) under the video, shifted by `offset` seconds, looped if it is "
    "shorter; the video's length wins.",
    {"type": "object", "properties": {"offset": {"type": "number", "minimum": -600, "maximum": 600, "default": 0},
                                      "loop": {"type": "boolean", "default": False}}}, inputs=(2, 2))
def _replace_audio(ins, a, tmp):
    m, s = ins
    _need_video(m)
    _need_audio(s)
    off = a["offset"]
    af = (f"adelay={int(off * 1000)}:all=1," if off > 0 else f"atrim=start={-off},asetpts=PTS-STARTPTS," if off < 0 else "")
    af += f"apad,atrim=0:{m['duration']:.3f}"
    pre = ["-stream_loop", "-1"] if a["loop"] else []
    return {"argv": ["-i", m["path"]] + pre + ["-i", s["path"], "-filter_complex", f"[1:a]{af}[a]", "-map", "0:v",
                     "-map", "[a]", "-t", f"{m['duration']:.3f}"] + COPY_V + AUD, "expect": _same(m, audio=True)}


@op("music_bed", "audio", "Lay music (input 2) under the video's own sound at `db`, ducked under speech, faded out "
    "at the end, looped if it is short.",
    {"type": "object", "properties": {"db": {"type": "number", "minimum": -40, "maximum": 0, "default": -18},
                                      "duck": {"type": "boolean", "default": True},
                                      "fade_out": {"type": "number", "minimum": 0, "maximum": 10, "default": 1.5}}},
    inputs=(2, 2))
def _music_bed(ins, a, tmp):
    m, s = ins
    _need_audio(s)
    d = m["duration"]
    mus = (f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{d:.3f},volume={a['db']}dB,"
           f"afade=t=out:st={max(0, d - a['fade_out']):.3f}:d={a['fade_out']}")
    if m["audio"]:
        parts = [f"[0:a]aresample=48000,aformat=channel_layouts=stereo,asplit[v1][v2]"]
        if a["duck"]:
            parts += [mus + "[m0]", "[m0][v1]sidechaincompress=threshold=0.04:ratio=8:attack=20:release=420[m]"]
        else:
            parts += [mus + "[m]", "[v1]anullsink"]
        parts.append("[v2][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
    else:
        parts = [mus + "[a]"]
    return {"argv": ["-i", m["path"], "-stream_loop", "-1", "-i", s["path"]] + _fc(parts) +
            (["-map", "0:v"] if m["video"] else []) + ["-map", "[a]", "-t", f"{d:.3f}"] +
            (COPY_V if m["video"] else []) + AUD, "expect": _same(m, audio=True)}


@op("extract_audio", "audio", "Take the sound out as its own file (wav, mp3 or m4a).",
    {"type": "object", "properties": {"format": {"type": "string", "enum": ["wav", "mp3", "m4a"], "default": "wav"}}},
    ext="wav")
def _extract_audio(ins, a, tmp):
    m = ins[0]
    _need_audio(m)
    codec = {"wav": ["-c:a", "pcm_s16le", "-ar", "48000"], "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
             "m4a": AUD}[a["format"]]
    return {"argv": ["-i", m["path"], "-vn"] + codec, "expect": {"duration": m["duration"], "video": False, "audio": True},
            "ext": a["format"]}


@op("sync", "audio", "Shift the sound against the picture by `offset` seconds (positive = sound later), e.g. with the "
    "offset sync_offset measured.",
    {"type": "object", "required": ["offset"], "properties": {"offset": {"type": "number", "minimum": -10, "maximum": 10}}})
def _sync(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    _need_audio(m)
    off = a["offset"]
    af = (f"adelay={int(off * 1000)}:all=1" if off >= 0 else f"atrim=start={-off},asetpts=PTS-STARTPTS")
    return {"argv": ["-i", m["path"], "-af", f"{af},apad,atrim=0:{m['duration']:.3f}", "-t", f"{m['duration']:.3f}"]
            + COPY_V + AUD, "expect": _same(m)}


@op("channels", "audio", "Mono (both ears the same, e.g. a voice recorded on one side) or stereo.",
    {"type": "object", "properties": {"to": {"type": "string", "enum": ["mono", "stereo"], "default": "mono"},
                                      "source": {"type": "string", "enum": ["mix", "left", "right"], "default": "mix"}}})
def _channels(ins, a, tmp):
    m = ins[0]
    _need_audio(m)
    src = {"mix": "0.5*c0+0.5*c1", "left": "c0", "right": "c1"}[a["source"]] if (m.get("channels") or 1) > 1 else "c0"
    af = f"pan=mono|c0={src}" if a["to"] == "mono" else f"pan=stereo|c0={src}|c1={src}"
    return {"argv": ["-i", m["path"], "-af", af] + (COPY_V if m["video"] else []) + AUD,
            "expect": _same(m, channels=1 if a["to"] == "mono" else 2)}


# ---------------------------------------------------------------- output

@op("transcode", "output", "Re-encode to another codec: h264 (mp4, plays everywhere), h265 (smaller), prores (mov, for "
    "editing) or vp9 (webm).",
    {"type": "object", "properties": {"codec": {"type": "string", "enum": ["h264", "h265", "prores", "vp9"], "default": "h264"},
                                      "crf": {"type": "integer", "minimum": 0, "maximum": 51, "default": 20}}})
def _transcode(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    c, crf = a["codec"], a["crf"]
    v = {"h264": ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
         "h265": ["-c:v", "libx265", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-tag:v", "hvc1",
                  "-movflags", "+faststart"],
         "prores": ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"],
         "vp9": ["-c:v", "libvpx-vp9", "-crf", str(crf + 10), "-b:v", "0", "-row-mt", "1"]}[c]
    au = {"prores": ["-c:a", "pcm_s16le", "-ar", "48000"], "vp9": ["-c:a", "libopus", "-b:a", "160k"]}.get(c, AUD)
    return {"argv": ["-i", m["path"]] + v + au, "raw": True, "ext": {"prores": "mov", "vp9": "webm"}.get(c, "mp4"),
            "expect": _same(m, vcodec={"h264": "h264", "h265": "hevc", "prores": "prores", "vp9": "vp9"}[c])}


@op("compress", "output", "Shrink to a target file size in MB (two-pass bitrate), e.g. for a platform's upload limit.",
    {"type": "object", "required": ["target_mb"], "properties": {"target_mb": {"type": "number", "minimum": 0.5, "maximum": 4000},
                                                                 "audio_kbps": {"type": "integer", "minimum": 48, "maximum": 320, "default": 128}}})
def _compress(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    kbps = int((a["target_mb"] * 8 * 1024 * 0.96 / max(0.5, m["duration"])) - (a["audio_kbps"] if m["audio"] else 0))
    if kbps < 80:
        raise FFError(f"compress: {a['target_mb']} MB is too small for {m['duration']:.0f} s of video")
    log = os.path.join(tmp, "pass")
    v = ["-c:v", "libx264", "-preset", "medium", "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.5)}k",
         "-bufsize", f"{kbps * 2}k", "-pix_fmt", "yuv420p", "-passlogfile", log]
    _ff(["-i", m["path"]] + v + ["-pass", "1", "-an", "-f", "mp4", os.devnull], "compress (pass 1)")
    au = ["-c:a", "aac", "-b:a", f"{a['audio_kbps']}k", "-ar", "48000"] if m["audio"] else ["-an"]
    return {"argv": ["-i", m["path"]] + v + ["-pass", "2", "-movflags", "+faststart"] + au, "raw": True,
            "expect": _same(m, max_bytes=int(a["target_mb"] * 1024 * 1024 * 1.02))}


@op("frame", "output", "One frame as a picture (png or jpg) at a time in seconds.",
    {"type": "object", "properties": {"at": {"type": "number", "minimum": 0, "default": 0},
                                      "format": {"type": "string", "enum": ["png", "jpg"], "default": "png"}}}, ext="png")
def _frame(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    at = min(a["at"], max(0, m["duration"] - 0.05))
    return {"argv": ["-ss", f"{at:.3f}", "-i", m["path"], "-frames:v", "1"] + (["-q:v", "2"] if a["format"] == "jpg" else []),
            "raw": True, "ext": a["format"], "expect": {"width": m["width"], "height": m["height"], "image": True}}


# ---------------------------------------------------------------- measure-only

@op("probe", "measure", "What the file is: duration, size, frame rate, codecs, audio.", measure=True)
def _probe(ins, a, tmp):
    return {"data": ins[0]}


@op("scenes", "measure", "Where the shots change (scene cuts) in seconds.",
    {"type": "object", "properties": {"threshold": {"type": "number", "minimum": 1, "maximum": 50, "default": 10}}},
    measure=True)
def _scenes(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    err = _ff(["-i", m["path"], "-vf", f"scale=320:-2,scdet=threshold={a['threshold']}", "-an", "-f", "null", "-"], "scdet")
    cuts = [round(float(t), 3) for t in re.findall(r"lavfi\.scd\.time: ([\d.]+)", err)]
    return {"data": {"cuts": cuts, "count": len(cuts)}}


@op("silences", "measure", "The quiet stretches: [[start, end]] quieter than `threshold` dB for at least `min_silence` s.",
    {"type": "object", "properties": {"threshold": {"type": "number", "minimum": -70, "maximum": -15, "default": -35},
                                      "min_silence": {"type": "number", "minimum": 0.1, "maximum": 10, "default": 0.5}}},
    measure=True)
def _silences_op(ins, a, tmp):
    _need_audio(ins[0])
    s = _silences(ins[0], a["threshold"], a["min_silence"])
    return {"data": {"silences": [[round(x, 3), round(y, 3)] for x, y in s], "total": round(sum(y - x for x, y in s), 3)}}


@op("loudness", "measure", "Integrated loudness (LUFS), loudness range and true peak.", measure=True)
def _loudness(ins, a, tmp):
    _need_audio(ins[0])
    return {"data": lufs(ins[0]["path"])}


@op("black", "measure", "Black stretches [[start, end]] (a black first frame makes a bad cover).", measure=True)
def _black(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    err = _ff(["-i", m["path"], "-vf", "blackdetect=d=0.04:pix_th=0.08", "-an", "-f", "null", "-"], "blackdetect")
    return {"data": {"black": [[float(x), float(y)] for x, y in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)]}}


@op("freezes", "measure", "Stretches where the picture does not move for at least `min` seconds.",
    {"type": "object", "properties": {"min": {"type": "number", "minimum": 0.2, "maximum": 10, "default": 1.0}}},
    measure=True)
def _freezes(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    err = _ff(["-i", m["path"], "-vf", f"freezedetect=n=0.003:d={a['min']}", "-an", "-f", "null", "-"], "freezedetect")
    st = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", err)]
    en = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", err)]
    return {"data": {"freezes": [[s, en[i] if i < len(en) else m["duration"]] for i, s in enumerate(st)]}}


def _pcm(path, sr, seconds):
    import numpy as np
    r = subprocess.run([FFMPEG, "-v", "error", "-nostdin", "-i", path, "-t", str(seconds), "-vn", "-ac", "1", "-ar",
                        str(sr), "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.float32)


@op("sync_offset", "measure", "How far input 2's sound is behind input 1's (seconds; cross-correlation of the two "
    "recordings of the same moment, e.g. a phone and a separate microphone). Feed the result to sync.",
    {"type": "object", "properties": {"max_shift": {"type": "number", "minimum": 0.5, "maximum": 30, "default": 10},
                                      "seconds": {"type": "number", "minimum": 5, "maximum": 300, "default": 60}}},
    inputs=(2, 2), measure=True)
def _sync_offset(ins, a, tmp):
    import numpy as np
    for m in ins:
        _need_audio(m)
    sr = 8000
    x, y = (_pcm(m["path"], sr, a["seconds"]) for m in ins)
    if len(x) < sr or len(y) < sr:
        raise FFError("sync_offset: need at least a second of sound in both")
    x, y = x - x.mean(), y - y.mean()
    n = 1 << int(math.ceil(math.log2(len(x) + len(y))))
    c = np.fft.irfft(np.fft.rfft(y, n) * np.conj(np.fft.rfft(x, n)), n)
    lag = int(a["max_shift"] * sr)
    c = np.concatenate([c[-lag:], c[:lag + 1]])
    k = int(np.argmax(np.abs(c)))
    off = (k - lag) / sr
    conf = float(np.abs(c[k]) / (np.sqrt((x ** 2).sum() * (y ** 2).sum()) + 1e-9))
    # `off` > 0: the same sound arrives later in input 2 -> shift input 2's sound earlier by `off` to line it up
    return {"data": {"offset": round(off, 3), "confidence": round(conf, 3),
                     "sure": conf > 0.2, "fix": {"op": "sync", "on": "input 2", "offset": round(-off, 3)}}}


@op("crop_detect", "measure", "The picture area inside black bars, if any.", measure=True)
def _crop_detect(ins, a, tmp):
    m = ins[0]
    _need_video(m)
    c = _cropdetect(m)
    bars = bool(c) and (c["w"] < m["width"] - 4 or c["h"] < m["height"] - 4)
    return {"data": {"bars": bars, "crop": c if bars else None}}


# ---------------------------------------------------------------- run + verify

def verify(out, expect, tol=DUR_TOL):
    """[{what, want, got, ok}] for an output measurement against the expectations."""
    checks = []

    def chk(what, want, got, ok):
        checks.append({"what": what, "want": want, "got": got, "ok": bool(ok)})

    chk("file", "exists", out.get("size", 0), out.get("size", 0) > 0)
    if expect.get("image"):
        chk("width", expect["width"], out.get("width"), out.get("width") == expect["width"])
        chk("height", expect["height"], out.get("height"), out.get("height") == expect["height"])
        return checks
    for k in ("video", "audio"):
        if k in expect:
            chk(k, expect[k], out.get(k), out.get(k) == expect[k])
    if "duration" in expect:
        tl = max(tol, 2.5 / (out.get("fps") or 30))
        chk("duration", expect["duration"], out.get("duration"), abs((out.get("duration") or 0) - expect["duration"]) <= tl)
        if out.get("vduration"):        # the picture itself, not only the container (a short video under long sound)
            chk("picture", expect["duration"], out["vduration"], abs(out["vduration"] - expect["duration"]) <= tl)
    for k in ("width", "height", "channels", "vcodec"):
        if k in expect and out.get("video" if k != "channels" else "audio"):
            chk(k, expect[k], out.get(k), out.get(k) == expect[k])
    if "fps" in expect and out.get("video"):
        chk("fps", expect["fps"], out.get("fps"), abs((out.get("fps") or 0) - expect["fps"]) <= 0.05)
    if "max_bytes" in expect:
        chk("size", f"<= {expect['max_bytes']}", out.get("size"), out.get("size", 0) <= expect["max_bytes"])
    if "lufs" in expect and out.get("audio"):
        lv = lufs(out["path"]).get("lufs")
        chk("loudness", expect["lufs"], lv, lv is not None and abs(lv - expect["lufs"]) <= 1.0)
    return checks


def _inputs_ok(o, n):
    lo, hi = o["inputs"] if isinstance(o["inputs"], tuple) else (o["inputs"], o["inputs"])
    if not lo <= n <= hi:
        raise FFError(f"{o['name']} takes {lo if lo == hi else f'{lo}-{hi}'} input(s), got {n}")


def run(name, inputs, dst=None, args=None, outdir=None):
    """Measure the inputs, run one operation, measure the output and check it.

    Returns {op, ok, inputs, output, checks, cmd, seconds, note} or, for a measure op, {op, ok, inputs, data}.
    `dst` defaults to <outdir or the first input's folder>/<input name>-<op>.<ext>."""
    if name not in OPS:
        raise FFError(f"unknown operation '{name}'")
    o = OPS[name]
    args = dict(args or {})
    try:
        jsonschema.validate(args, o["schema"])
    except jsonschema.ValidationError as e:
        raise FFError(f"{name}: bad arguments: {e.message}") from None
    for k, v in (o["schema"].get("properties") or {}).items():
        if "default" in v and k not in args:
            args[k] = v["default"]
    inputs = [inputs] if isinstance(inputs, str) else list(inputs)
    _inputs_ok(o, len(inputs))
    ins = [measure(p) for p in inputs]
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="ff-") as tmp:
        plan = o["fn"](ins, args, tmp)
        if o["measure"]:
            return {"op": name, "ok": True, "inputs": ins, "data": plan["data"], "seconds": round(time.time() - t0, 2)}
        ext = plan.get("ext") or o["ext"]
        if not dst:
            base = os.path.splitext(os.path.basename(inputs[0]))[0]
            dst = os.path.join(outdir or os.path.dirname(os.path.abspath(inputs[0])), f"{base}-{name}.{ext}")
        if os.path.abspath(dst) in {os.path.abspath(p) for p in inputs}:
            raise FFError("the output must not overwrite an input")
        os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
        _ff(plan["argv"] + [dst], name)
    out = measure(dst)
    checks = verify(out, plan["expect"], plan.get("tol", DUR_TOL))
    return {"op": name, "ok": all(c["ok"] for c in checks), "inputs": ins, "output": out, "checks": checks,
            "cmd": "ffmpeg " + " ".join(str(x) for x in plan["argv"] + [dst]), "seconds": round(time.time() - t0, 2),
            "note": plan.get("note", "")}


def failed(r):
    """Readable lines for the checks that did not pass."""
    return [f"{c['what']}: wanted {c['want']}, got {c['got']}" for c in r.get("checks", []) if not c["ok"]]
