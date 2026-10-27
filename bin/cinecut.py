#!/usr/bin/env python3
"""Calm, cinematic cut: held shots joined by hard cuts, the clips' own sound, plain static captions, optional voiceover.

Made after the user rejected the montage.py/render.py look (sliding titles, punch zooms, crossfades, short random shots).
Nothing here moves on screen except the footage itself.

Usage: cinecut.py spec.json [--preview]   -> out/<name>/<name>.mp4 + caption.txt (preview: work/preview/<name>.mp4)

Spec:
  name
  aspect  "9:16" (default, 1080x1920) | "16:9" (1920x1080); footage is cover-cropped to it
  shots   list of
    {"video": "raw/X.MOV", "in": 2.0, "out": 6.5, "speed": 0.5}
      speed < 1 on 60 fps footage = smooth slow motion; the shot's sound stays at normal speed
    {"photo": "raw/X.JPG", "dur": 3.0, "drift": 0.02, "focus": [0.5, 0.5]}
      drift = barely visible push-in over the whole shot (0 = locked off); focus = point the push heads to
  text    [{"start": 0.2, "end": 2.8, "text": "one plain line"}]   lower third, 150 ms fade, no motion
  voice   {"file": "assets/eleven/x.mp3", "start": 0.4}            ambient sound is ducked under it
  bed     {"video": "raw/X.MOV", "in": 0, "at": 9.0, "loop": true, "db": -14}  ambience under photos from `at` on
  music   {"file": "assets/eleven/x.mp3", "db": -6}  generated track under everything (voice still ducks it)
  ambient_db  level of the clips' own sound (default -3)
  post    {series, caption, hashtags, location, music, notes} -> caption.txt
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from factory.config import ROOT, FFMPEG  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "bin"))
from render import write_caption  # noqa: E402

FPS = 30
# one gentle look for every shot: a touch of contrast and warmth, never a filter "style"
GRADE = "eq=contrast=1.04:saturation=1.06:gamma=0.98,colortemperature=temperature=6200:mix=0.25"
ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}


def style_line(w, h):
    """Plain lower-third line: 64 px with the lower third at ~31 % on vertical, 56 px near the bottom on horizontal."""
    size, margin_v, margin_lr = (64, 600, 90) if h > w else (56, 130, 200)
    return (f"Style: Line,Poppins Medium,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H50000000,0,0,0,0,100,100,0.5,0,1,"
            f"1.6,3,2,{margin_lr},{margin_lr},{margin_v},1")


def run(args):
    subprocess.run([FFMPEG, "-v", "error", "-y", *args], check=True)


def video_shot(shot, out, wav, grade, enc=("medium", "14"), size=(1080, 1920)):
    s, e = shot["in"], shot["out"]
    speed = shot.get("speed", 1.0)
    dur = (e - s) / speed
    src = os.path.join(ROOT, shot["video"])
    w, h = size  # cover-crop: vertical footage on a 16:9 canvas keeps its middle band
    vf = (f"setpts=PTS/{speed},fps={FPS},scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
          f"crop={w}:{h}" + (f",{grade}" if grade else ""))
    run(["-ss", str(s), "-t", str(e - s), "-i", src, "-vf", vf, "-an", "-c:v", "libx264", "-preset", enc[0],
         "-crf", enc[1], "-pix_fmt", "yuv420p", out])
    # natural-speed sound from the same moment, so slow motion still sounds like the place
    run(["-ss", str(s), "-t", f"{dur:.3f}", "-i", src, "-vn", "-af", f"apad,atrim=0:{dur:.3f}",
         "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", wav])
    return dur


def photo_shot(shot, out, wav, grade, enc=("medium", "14"), size=(1080, 1920)):
    dur = shot.get("dur", 3.0)
    n = round(dur * FPS)
    drift = shot.get("drift", 0.0)
    fx, fy = shot.get("focus", [0.5, 0.5])
    p = f"(on/{max(n - 1, 1)})"
    zoom = f"1+{drift}*{p}"
    w, h = size
    vf = (f"scale={4 * w}:{4 * h}:force_original_aspect_ratio=increase:flags=lanczos,crop={4 * w}:{4 * h},"
          f"zoompan=z='{zoom}':x='(iw-iw/zoom)*{fx}':y='(ih-ih/zoom)*{fy}':d={n}:s={w}x{h}:fps={FPS}"
          + (f",{grade}" if grade else ""))
    run(["-i", os.path.join(ROOT, shot["photo"]), "-vf", vf, "-frames:v", str(n), "-c:v", "libx264",
         "-preset", enc[0], "-crf", enc[1], "-pix_fmt", "yuv420p", out])
    run(["-f", "lavfi", "-t", f"{n / FPS:.3f}", "-i", "anullsrc=r=48000:cl=stereo", "-c:a", "pcm_s16le", wav])
    return n / FPS


def ass_time(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def build_ass(lines, path, size=(1080, 1920)):
    out = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {size[0]}", f"PlayResY: {size[1]}", "WrapStyle: 0", "",
           "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
           "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
           "MarginL, MarginR, MarginV, Encoding", style_line(*size), "", "[Events]",
           "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for ln in lines:
        out.append(f"Dialogue: 0,{ass_time(ln['start'])},{ass_time(ln['end'])},Line,,0,0,0,,"
                   f"{{\\fad(150,150)}}{ln['text']}")
    open(path, "w").write("\n".join(out) + "\n")


def main(spec_path, preview=False):
    spec = json.load(open(spec_path))
    name = spec["name"]
    tmp = os.path.join(ROOT, "work", "cinecut", name)
    os.makedirs(tmp, exist_ok=True)
    grade = GRADE if spec.get("grade", True) else ""
    size = ASPECTS.get(spec.get("aspect", "9:16"), ASPECTS["9:16"])

    vids, wavs, durs = [], [], []
    enc = ("veryfast", "20") if preview else ("medium", "14")  # previews are for judging the cut, not the pixels
    for i, shot in enumerate(spec["shots"]):
        v, a = os.path.join(tmp, f"s{i}.mp4"), os.path.join(tmp, f"s{i}.wav")
        durs.append((video_shot if "video" in shot else photo_shot)(shot, v, a, grade, enc, size))
        vids.append(v)
        wavs.append(a)
    total = sum(durs)

    ass = os.path.join(tmp, f"{name}.ass")
    build_ass(spec.get("text", []), ass, size)

    n = len(vids)
    inputs = []
    for f in vids + wavs:
        inputs += ["-i", f]
    chain = [f"[{i}:v]setsar=1[v{i}]" for i in range(n)]
    chain += ["".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,ass={ass}:fontsdir={ROOT}/fonts[v]",
             "".join(f"[{n + i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1,volume={spec.get('ambient_db', -3)}dB[amb]"]
    mix, k = "[amb]", 2 * n
    if spec.get("bed"):
        bed = spec["bed"]
        at = bed.get("at", 0.0)
        loop = ["-stream_loop", "-1"] if bed.get("loop") else []
        inputs += [*loop, "-ss", str(bed.get("in", 0)), "-t", f"{total - at:.3f}", "-i", os.path.join(ROOT, bed["video"])]
        ms = int(at * 1000)
        chain.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={bed.get('db', -14)}dB,"
                     f"afade=t=in:d=0.8,adelay={ms}|{ms},apad,atrim=0:{total:.3f}[bed]")
        chain.append("[amb][bed]amix=inputs=2:normalize=0[amb2]")
        mix, k = "[amb2]", k + 1
    if spec.get("music"):  # a generated track under the clips' own sound (which drops a little to make room)
        mu = spec["music"]
        inputs += ["-i", os.path.join(ROOT, mu["file"])]
        fo = mu.get("fade_out", 2.0)
        chain.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={mu.get('db', -6)}dB,apad,"
                     f"atrim=0:{total:.3f},afade=t=in:d=0.6,afade=t=out:st={max(0, total - fo):.3f}:d={fo}[mus]")
        chain.append(f"{mix}[mus]amix=inputs=2:normalize=0[mixm]")
        mix, k = "[mixm]", k + 1
    if spec.get("voice"):
        vo = spec["voice"]
        inputs += ["-i", os.path.join(ROOT, vo["file"])]
        ms = int(vo.get("start", 0) * 1000)
        chain.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms},"
                     f"volume={vo.get('gain_db', 0)}dB,apad,atrim=0:{total:.3f},asplit[vo][key]")
        chain.append(f"{mix}[key]sidechaincompress=threshold=0.02:ratio=10:attack=30:release=500[duck]")
        chain.append("[duck][vo]amix=inputs=2:normalize=0[mix]")
        mix = "[mix]"
    chain.append(f"{mix}loudnorm=I=-14:TP=-1.5:LRA=11,atrim=0:{total:.3f}[a]")

    out_dir = os.path.join(ROOT, "work", "preview") if preview else os.path.join(ROOT, "out", name)
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, f"{name}.mp4")
    run([*inputs, "-filter_complex", ";".join(chain), "-map", "[v]", "-map", "[a]", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "slow" if not preview else "veryfast", "-crf", "17" if not preview else "24", "-profile:v", "high",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", dst])
    if spec.get("post") and not preview:
        write_caption(os.path.join(out_dir, "caption.txt"), spec["post"])
    starts = [round(sum(durs[:i]), 2) for i in range(n)]
    print(f"{dst}  ({total:.2f}s)  shot starts: {starts}")
    return dst, total


if __name__ == "__main__":
    main(sys.argv[1], preview="--preview" in sys.argv)
