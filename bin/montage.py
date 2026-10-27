#!/usr/bin/env python3
"""Build a steady 1080x1920 base clip from the best parts of raw videos and photos.

Usage: montage.py montage.json   -> writes work/<name>_montage.mp4 (feed it to render.py as input)
                                     and work/<name>_montage.json (shot start times, for text timing)

Spec:
  name     base name
  raw      default raw source (relative to ~/tiktok); any shot can override it with its own "raw"
  xfade    default transition seconds between shots (default 0.5)
  shots    list of
    {"video": [start, end], "speed": 0.85, "stabilize": true, "raw": "raw/X.MOV"}
      speed 0.5 on 60 fps footage gives smooth slow motion
    {"still": t_seconds, "dur": 3.2, "zoom": [z0, z1], "x": [x0, x1], "y": [y0, y1], "raw": "raw/X.MOV"}
    {"photo": "raw/X.JPG", "dur": 1.2, "zoom": ..., "x": ..., "y": ...}
      x / y: 0 = left/top edge, 0.5 = centre, 1 = right/bottom edge (Ken Burns move)
  per shot (optional):
    "trans": xfade transition INTO this shot (fade, slideleft, smoothleft, fadewhite, zoomin, ...)
    "xd":    that transition's length in seconds
    "punch": quick zoom-in pulse at the start of the shot, e.g. 0.1 (energetic edits)
    "creep": slow zoom across a video shot, +0.03 = in by 3 %, -0.03 = out (subtle motion, alternate signs)
    {"card": "#F2F0ED", "dur": 2.0}: plain colour scene for fact / list cards
Audio: each video shot keeps its own ambient sound; stills and photos are silent.
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from factory.config import ROOT, FFMPEG  # noqa: E402
ENC = ["-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p", "-an"]
AUD = ["-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le"]


def run(args):
    subprocess.run([FFMPEG, "-v", "error", "-y", *args], check=True)


def atempo(speed):
    chain = []
    while speed < 0.5:
        chain.append("atempo=0.5")
        speed /= 0.5
    chain.append(f"atempo={speed}")
    return ",".join(chain)


def motion_vf(punch=0.0, creep=0.0, dur=1.0):
    """Camera motion on a video shot: a punch-in pulse at the start (eases back over 0.3 s) times a slow creep
    (+ = zoom in over the shot, - = start zoomed and ease out). Computed at 2x size so the even-pixel rounding
    of the scaler is invisible after the downscale."""
    if not punch and not creep:
        return ""
    z = "1"
    if punch:
        z += f"*(1+{punch}*pow(max(0\\,1-t/0.3)\\,2))"
    if creep > 0:
        z += f"*(1+{creep}*t/{dur:.3f})"
    elif creep < 0:
        z += f"*(1+{-creep}*(1-t/{dur:.3f}))"
    return (f",scale=2160:3840:flags=bicubic,scale=w='trunc(2160*{z}/2)*2':h=-2:eval=frame:flags=bicubic,"
            "crop=2160:3840,scale=1080:1920:flags=bicubic")


def video_shot(raw, shot, out, tmp):
    s, e = shot["video"]
    speed = shot.get("speed", 1.0)
    base = ["-ss", str(s), "-t", str(e - s), "-i", raw]
    vf = "scale=1080:1920:flags=bicubic"
    if shot.get("stabilize"):
        trf = tmp + ".trf"
        run([*base, "-vf", f"{vf},vidstabdetect=shakiness=6:accuracy=15:result={trf}", "-f", "null", "-"])
        vf += f",vidstabtransform=input={trf}:smoothing=20:zoom=4:optzoom=0,unsharp=5:5:0.5"
    dur = (e - s) / speed
    run([*base, "-vf", f"{vf},setpts=PTS/{speed}{motion_vf(shot.get('punch', 0), shot.get('creep', 0), dur)}", *ENC, out])
    run([*base, "-vn", "-af", f"{atempo(speed)},apad", "-t", f"{dur:.3f}", *AUD, tmp + ".wav"])
    return dur


def card_shot(shot, out, tmp):
    """Clean off-white (or any colour) full-screen scene with a little paper grain, for fact/list cards."""
    dur = shot.get("dur", 2.0)
    col = shot.get("card", "#F2F0ED").replace("#", "0x")
    run(["-f", "lavfi", "-t", f"{dur:.3f}", "-i", f"color=c={col}:s=1080x1920:r=30",
         "-vf", "noise=alls=3:allf=t,vignette=PI/7", *ENC, out])
    run(["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo", *AUD, tmp + ".wav"])
    return dur


def still_shot(raw, shot, out, tmp):
    if "photo" in shot:
        img = os.path.join(ROOT, shot["photo"])
    else:
        img = tmp + ".png"
        run(["-i", raw, "-ss", str(shot["still"]), "-frames:v", "1", img])
    dur = shot.get("dur", 3.2)
    n = round(dur * 30)
    z0, z1 = shot.get("zoom", [1.0, 1.1])
    x0, x1 = shot.get("x", [0.5, 0.5])
    y0, y1 = shot.get("y", [0.5, 0.5])
    p = f"(on/{max(n - 1, 1)})"
    zoom = f"{z0}+({z1}-{z0})*{p}"
    if shot.get("punch"):
        zoom = f"({zoom})*(1+{shot['punch']}*pow(max(0\\,1-on/9)\\,2))"
    # upscale first so zoompan's integer crop positions become sub-pixel at output size (no jitter);
    # cover-crop to 9:16 so photos of any aspect fill the frame
    vf = (f"scale=4320:7680:force_original_aspect_ratio=increase:flags=bicubic,crop=4320:7680,"
          f"zoompan=z='{zoom}':"
          f"x='(iw-iw/zoom)*({x0}+({x1}-{x0})*{p})':y='(ih-ih/zoom)*({y0}+({y1}-{y0})*{p})':"
          f"d={n}:s=1080x1920:fps=30")
    run(["-i", img, "-vf", vf, "-frames:v", str(n), *ENC, out])
    run(["-f", "lavfi", "-t", f"{n / 30:.3f}", "-i", "anullsrc=r=48000:cl=stereo", *AUD, tmp + ".wav"])
    return n / 30


def main(spec_path):
    spec = json.load(open(spec_path))
    name = spec["name"]
    default_xd = spec.get("xfade", 0.5)
    tmpdir = os.path.join(ROOT, "work", "montage", name)
    os.makedirs(tmpdir, exist_ok=True)

    shots = spec["shots"]
    files, durs = [], []
    for i, shot in enumerate(shots):
        raw = os.path.join(ROOT, shot.get("raw", spec.get("raw", "")))
        out, tmp = os.path.join(tmpdir, f"shot{i}.mp4"), os.path.join(tmpdir, f"shot{i}")
        if "card" in shot:
            durs.append(card_shot(shot, out, tmp))
        else:
            durs.append((video_shot if "video" in shot else still_shot)(raw, shot, out, tmp))
        files.append(out)

    n = len(files)
    xds = [0.0] + [shots[i].get("xd", default_xd) for i in range(1, n)]
    inputs, chain, last, offset = [], [], "[0:v]", 0.0
    for f in files:
        inputs += ["-i", f]
    for i in range(n):
        inputs += ["-i", os.path.join(tmpdir, f"shot{i}.wav")]
    starts = [0.0]
    for i in range(1, n):
        offset += durs[i - 1] - xds[i]
        starts.append(offset)
        trans = shots[i].get("trans", "fade")
        chain.append(f"{last}[{i}:v]xfade=transition={trans}:duration={xds[i]}:offset={offset:.3f}[x{i}]")
        last = f"[x{i}]"
    if not chain:
        chain.append("[0:v]null[x0]")
        last = "[x0]"
    total = starts[-1] + durs[-1]
    # audio: each shot's sound, cut where the next shot's transition starts
    apads = ""
    for i in range(n):
        keep = durs[i] - (xds[i + 1] if i < n - 1 else 0)
        chain.append(f"[{n + i}:a]atrim=0:{keep:.3f},asetpts=PTS-STARTPTS[a{i}]")
        apads += f"[a{i}]"
    chain.append(f"{apads}concat=n={n}:v=0:a=1[aout]")

    dst = os.path.join(ROOT, "work", f"{name}_montage.mp4")
    run([*inputs, "-filter_complex", ";".join(chain), "-map", last, "-map", "[aout]",
         "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", dst])
    json.dump({"total": total, "starts": starts, "durs": durs},
              open(os.path.join(ROOT, "work", f"{name}_montage.json"), "w"), indent=1)
    print(f"{dst}  ({total:.2f}s)  shot starts: {[round(s, 2) for s in starts]}")


if __name__ == "__main__":
    main(sys.argv[1])
