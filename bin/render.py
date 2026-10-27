#!/usr/bin/env python3
"""Render a 9:16 TikTok edit from a JSON spec.

Usage: render.py spec.json

Spec fields:
  name    video name, e.g. 004_garmisch_proverb_german -> out/<name>/<name>.mp4 (+ caption.txt)
  input   raw video path (relative to ~/tiktok)
  post    optional {series, caption, hashtags, location, music} written to out/<name>/caption.txt
  speed   playback speed, e.g. 0.8 (default 1.0)
  zoom    total slow zoom over the clip, e.g. 0.07 (default 0.05)
  segments           optional [[start, end], ...] raw-clip seconds to keep, joined in order
  start / duration   simple single trim (used when segments is absent)
  audio_volume       original audio level (default 0.5)
  events  list of {start, end, style, text, marginv?}  (times are output-timeline seconds)

Styles: Label, Hook, Original, Translation, Fact, FactBig, Vlog
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from factory.config import ROOT, FFMPEG, FFPROBE  # noqa: E402

STYLES = """\
Style: Label,Poppins Medium,46,&H00C8E6FF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,6,0,1,2,2,8,90,90,330,1
Style: Hook,Poppins,100,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3.5,4,8,40,120,430,1
Style: Original,Poppins Medium,62,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,-1,0,0,100,100,0,0,1,2.5,3,8,90,90,410,1
Style: Translation,Poppins,76,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,4,8,90,90,600,1
Style: Fact,Poppins,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,4,4,8,40,120,440,1
Style: FactBig,Poppins,96,&H0000E1FF,&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,4,5,8,40,120,440,1
Style: Vlog,Poppins,60,&H00FFFFFF,&H00FFFFFF,&H70000000,&H70000000,-1,0,0,0,100,100,0,0,3,16,0,2,90,90,640,1
Style: Draw,Poppins,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: Pin,Poppins,56,&H00101010,&H00FFFFFF,&H0000E1FF,&H00000000,-1,0,0,0,100,100,3,0,3,14,0,7,0,0,0,1
Style: PinSub,Poppins,40,&H00FFFFFF,&H00FFFFFF,&H50101010,&H00000000,-1,0,0,0,100,100,2,0,3,10,0,7,0,0,0,1
Style: Stamp,Poppins,170,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,4,0,1,6,6,5,0,0,0,1
Style: Counter,Poppins,140,&H0000E1FF,&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,5,5,5,0,0,0,1
Style: Title,Poppins Medium,50,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,8,0,1,2.5,3,8,0,0,0,1
Style: TitleBig,Poppins,112,&H0000E1FF,&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,2,0,1,4,5,8,0,0,0,1
Style: Card,Poppins Medium,46,&H00FFFFFF,&H00FFFFFF,&H90000000,&H00000000,0,0,0,0,100,100,0,0,3,22,0,5,70,70,0,1
Style: CardText,Poppins,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: CardCite,Poppins Medium,70,&H00F0F0F0,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,0,0,5,0,0,0,1
Style: ChapterNum,Instrument Serif,230,&H003DD9FF,&H00FFFFFF,&H00000000,&H00000000,0,-1,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: MapLabel,Poppins,38,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,2,0,1,3,0,4,0,0,0,1
"""


def brand_accent():
    """Accent colour from the style lock (data/brand.json) as ASS &HAABBGGRR."""
    try:
        h = json.load(open(os.path.join(ROOT, "data", "brand.json"))).get("accent_hex", "#FFD93D").lstrip("#")
        return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()
    except (OSError, ValueError):
        return "&H003DD9FF"


def ts(t):
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def build_ass(events):
    out = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        STYLES.replace("&H003DD9FF", brand_accent()), "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for e in events:
        fade = e.get("fade", "{\\fad(300,300)}")
        out.append(f"Dialogue: {e.get('layer', 0)},{ts(e['start'])},{ts(e['end'])},{e['style']},,0,0,"
                   f"{e.get('marginv', 0)},,"
                   f"{fade}{e['text']}")
    return "\n".join(out) + "\n"


def write_caption(path, post):
    lines = [f"SERIES: {post.get('series', '')}", "", "CAPTION", post.get("caption", ""), "",
             "HASHTAGS", post.get("hashtags", ""), "", f"LOCATION: {post.get('location', '')}",
             f"MUSIC: {post.get('music', '')}"]
    if post.get("notes"):
        lines += ["", "NOTES", post["notes"]]
    open(path, "w").write("\n".join(lines) + "\n")


def main(spec_path):
    spec = json.load(open(spec_path))
    src = os.path.join(ROOT, spec["input"])
    name = spec["name"]
    out_dir = os.path.join(ROOT, "out", name)
    dst = os.path.join(out_dir, f"{name}.mp4")
    preview = spec.get("preview", False)  # fast low-res draft for style frames; never written to out/
    if preview:
        out_dir = os.path.join(ROOT, "work", "preview")
        dst = os.path.join(out_dir, f"{name}.mp4")
    speed = spec.get("speed", 1.0)
    zoom = spec.get("zoom", 0.05)
    vol = spec.get("audio_volume", 0.5)

    # segments: list of [start, end] in raw-clip seconds, joined in order (the best moments only)
    segments = spec.get("segments")
    if not segments:
        full = float(subprocess.check_output(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src]).decode())
        start = spec.get("start", 0.0)
        segments = [[start, start + spec.get("duration", full - start)]]
    raw_dur = sum(e - s for s, e in segments)
    dur = raw_dur / speed

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(ROOT, "work", "ass"), exist_ok=True)
    ass_path = os.path.join(ROOT, "work", "ass", f"{name}.ass")
    open(ass_path, "w").write(build_ass(spec.get("events", [])))
    if "post" in spec and not preview:
        write_caption(os.path.join(out_dir, "caption.txt"), spec["post"])

    parts, pads = [], ""
    for i, (s, e) in enumerate(segments):
        parts.append(f"[0:v]trim={s}:{e},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim={s}:{e},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d=0.08,afade=t=out:st={e - s - 0.08:.2f}:d=0.08[a{i}]")
        pads += f"[v{i}][a{i}]"
    parts.append(f"{pads}concat=n={len(segments)}:v=1:a=1[vc][ac]")

    atempo = f"atempo={speed}," if speed != 1.0 else ""
    parts.append(
        f"[vc]setpts=PTS/{speed},"
        f"scale=w='trunc(1080*(1+{zoom}*t/{dur:.2f})/2)*2':h=-2:eval=frame:flags=bicubic,crop=1080:1920,"
        "eq=contrast=1.06:saturation=1.18:gamma=0.98,"
        "colorbalance=rs=0.03:bs=-0.03:rh=0.03:bh=-0.02,vignette=PI/6[base]")
    # motion-graphics layers (transparent ProRes from motion/render.mjs), each placed at its start time
    overlays = spec.get("overlays", [])
    sfx_base = 2 + len(overlays)
    cur = "[base]"
    for k, ov in enumerate(overlays):
        s0 = float(ov.get("start", 0))
        parts.append(f"[{2 + k}:v]setpts=PTS-STARTPTS+{s0}/TB,format=yuva420p[ov{k}]")
        parts.append(f"{cur}[ov{k}]overlay=0:0:eof_action=pass:format=auto[ob{k}]")
        cur = f"[ob{k}]"
    parts.append(f"{cur}[1:v]overlay=0:0,ass={ass_path}:fontsdir={ROOT}/fonts[v]")
    sfx = spec.get("sfx", [])  # [{file, start (s), gain_db}] synthesised effects mixed under the ambience
    parts.append(f"[ac]{atempo}volume={vol},afade=t=out:st={max(dur - 1, 0):.2f}:d=1"
                 + ("[amain]" if sfx else "[a]"))
    sfx_inputs = []
    if sfx:
        for k, fx in enumerate(sfx):
            sfx_inputs += ["-i", fx["file"]]
            ms = int(round(fx["start"] * 1000))
            parts.append(f"[{sfx_base + k}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms},"
                         f"volume={fx['gain_db']}dB[fx{k}]")
        mix = "".join(f"[fx{k}]" for k in range(len(sfx)))
        norm = f",loudnorm=I={spec['loudness']}:TP=-1.5:LRA=11" if spec.get("loudness") else ""
        parts.append(f"[amain]{mix}amix=inputs={len(sfx) + 1}:duration=first:normalize=0,alimiter=limit=0.89{norm}[a]")

    ov_inputs = [x for ov in overlays for x in ("-i", os.path.join(ROOT, ov["file"]))]
    cmd = [FFMPEG, "-v", "error", "-y", "-i", src, "-i", f"{ROOT}/assets/top_gradient.png", *ov_inputs, *sfx_inputs,
           "-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]", "-map_metadata", "-1",
           "-r", "30", "-c:v", "libx264", "-preset", "ultrafast" if preview else "slow", "-crf", "28" if preview else "18",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", dst]
    subprocess.run(cmd, check=True)
    print(f"{dst}  ({dur:.1f}s)")


if __name__ == "__main__":
    main(sys.argv[1])
