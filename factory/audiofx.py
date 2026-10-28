"""Sound engineering shared by every engine: the voice chain, silence tightening, music ducking with a carve, music
automation (cut / back on story events), music drop alignment and the sound-effect bus.

Distilled from the workflows the creator shared (talking-head ad, explainer reel, 30 s product ad, stickman horror
story) and turned into one reusable kit instead of per-video tricks:
  - voice: 80 Hz high-pass, light FFT denoise, mud cut, presence lift, de-ess, gentle compression, limiter;
    "natural, never processed" (all moves are small)
  - only REAL silences are shortened: a gap between two words is cut only where the audio is quiet, with padding
    around both words, so word endings are never chopped (cutting one long take blindly chops word tails)
  - music sits under the voice: a static dip around 2.6 kHz (where speech intelligibility lives) plus a sidechain
    duck keyed by the voice ("voiceover carve")
  - music automation: windows where the music is cut out (the power dies) and comes back (the knock)
  - drop alignment: find the drop of a track and start it so the drop lands on the key line
  - sound effects never mask a word: cues that land on speech are pulled down or nudged into the nearest gap
Everything is plain ffmpeg filters + numpy, so it renders the same on every machine.
"""
import os, subprocess

import numpy as np

from .config import FFMPEG

SR = 48000
CARVE_HZ = 2600

# voice chains: small moves only. "clean" = TTS / studio mic, "room" = phone / camera mic in a room
VOICE_CHAINS = {
    "clean": ("highpass=f=80,equalizer=f=280:t=q:w=1.1:g=-1.5,equalizer=f=3600:t=q:w=0.9:g=1.5,deesser=i=0.35,"
              "acompressor=threshold=-20dB:ratio=2.5:attack=10:release=140:makeup=2dB,alimiter=limit=0.89:level=false"),
    "room": ("highpass=f=80,afftdn=nr=10:nf=-40:tn=1,equalizer=f=250:t=q:w=1.0:g=-2.5,equalizer=f=3400:t=q:w=0.9:g=2,"
             "deesser=i=0.45,acompressor=threshold=-22dB:ratio=3:attack=8:release=120:makeup=3dB,"
             "alimiter=limit=0.89:level=false"),
}


def voice_chain(preset="clean"):
    """ffmpeg filter string for the voice (unknown preset -> clean)."""
    return VOICE_CHAINS.get(preset, VOICE_CHAINS["clean"])


def tempo_pitch(tempo=1.0, semitones=0.0, sr=SR):
    """Filter for a tempo change (atempo, pitch kept) and/or a pitch shift (tempo kept). Empty string = no change.
    e.g. tempo 1.05 = 5 % tighter read; semitones -1 = a deeper, ad-style voice."""
    tempo = max(0.8, min(float(tempo or 1.0), 1.25))
    semitones = max(-4.0, min(float(semitones or 0.0), 4.0))
    parts = []
    if abs(semitones) > 0.01:
        r = 2 ** (semitones / 12)
        parts += [f"asetrate={round(sr * r)}", f"aresample={sr}"]
        tempo /= r                      # asetrate changed the speed too; atempo gives it back
    if abs(tempo - 1) > 0.001:
        parts.append(f"atempo={tempo:.4f}")
    return ",".join(parts)


def run(args):
    subprocess.run([FFMPEG, "-v", "error", "-y", *args], check=True)


def decode(path, sr=16000):
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def process_voice(src, dst, tempo=1.0, semitones=0.0, chain=None):
    """Voice post: tempo / pitch, then the chain (None = no chain). Writes a 48 kHz mono WAV."""
    af = ",".join(x for x in (tempo_pitch(tempo, semitones), voice_chain(chain) if chain else "") if x) or "anull"
    run(["-i", src, "-af", af, "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", dst])
    return dst


# ---------- real silences ----------
def rms_db(y, sr, a, b):
    seg = y[max(0, int(a * sr)):max(int(a * sr) + 1, int(b * sr))]
    return 20 * np.log10(np.sqrt(np.mean(seg.astype(np.float64) ** 2)) + 1e-9) if len(seg) else -120.0


def speech_level(y, sr, words):
    """Median loudness of the spoken words (dB), the reference the silence threshold is relative to."""
    lv = [rms_db(y, sr, s, e) for _, s, e in words[:400] if e - s > 0.05]
    return float(np.median(lv)) if lv else -20.0


def gaps(words, y, sr, min_gap=0.32, keep=0.16, pad=0.05, below=26.0):
    """Cuttable stretches between words: [(start, end)] in file seconds. A gap qualifies only when it is longer than
    `min_gap`, and only its inside (`pad` away from both words) is checked: it must sit `below` dB under the speech
    level. `keep` seconds of each gap stay, split around the middle, so the rhythm still breathes."""
    ref = speech_level(y, sr, words) - below
    out = []
    for (_, _, e0), (_, s1, _) in zip(words, words[1:]):
        g = s1 - e0
        if g <= max(min_gap, keep + 2 * pad):
            continue
        a, b = e0 + pad, s1 - pad
        # the quiet must hold across the whole inside, in 40 ms windows (a breath or a click keeps the gap)
        wins = np.arange(a, b, 0.04)
        if len(wins) and all(rms_db(y, sr, t, min(b, t + 0.04)) <= ref for t in wins):
            mid = (e0 + s1) / 2
            ca, cb = max(a, mid - (g - keep) / 2), min(b, mid + (g - keep) / 2)
            if cb - ca > 0.04:
                out.append((round(ca, 3), round(cb, 3)))
    return out


def keep_ranges(cuts, total):
    """Complement of the cut list inside [0, total]."""
    out, t = [], 0.0
    for a, b in sorted(cuts):
        if a > t:
            out.append((t, a))
        t = max(t, b)
    if t < total:
        out.append((t, total))
    return [(round(a, 3), round(b, 3)) for a, b in out if b - a > 0.01]


def remap(t, ranges):
    """A time in the original file -> the time after the cut (times inside a cut snap to its edge)."""
    acc = 0.0
    for a, b in ranges:
        if t < a:
            return round(acc, 3)
        if t <= b:
            return round(acc + t - a, 3)
        acc += b - a
    return round(acc, 3)


def concat_audio(src, ranges, dst, fade=0.008):
    """Keep only `ranges` of `src` (seconds), joined with tiny fades so the joins never click."""
    chain = []
    for i, (a, b) in enumerate(ranges):
        d = b - a
        f = min(fade, d / 3)
        chain.append(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d={f:.3f},"
                     f"afade=t=out:st={max(0, d - f):.3f}:d={f:.3f}[a{i}]")
    chain.append("".join(f"[a{i}]" for i in range(len(ranges))) + f"concat=n={len(ranges)}:v=0:a=1[out]")
    run(["-i", src, "-filter_complex", ";".join(chain), "-map", "[out]", "-ac", "1", "-ar", str(SR),
         "-c:a", "pcm_s16le", dst])
    return dst


def tighten(src, dst, words, max_gap=0.32, keep=0.16):
    """Shorten only the real silences of a voice file. -> (dst, ranges kept, words remapped to the new file)."""
    y = decode(src)
    total = len(y) / 16000
    cuts = gaps(words, y, 16000, min_gap=max_gap, keep=keep)
    ranges = keep_ranges(cuts, total)
    if not cuts:
        run(["-i", src, "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", dst])
        return dst, [(0.0, round(total, 3))], [list(w) for w in words]
    concat_audio(src, ranges, dst)
    return dst, ranges, [[w, remap(s, ranges), remap(e, ranges)] for w, s, e in words]


# ---------- music ----------
def drop_time(path, lo=2.0):
    """Where a track 'drops': the biggest jump from a quieter stretch into a louder one (RMS, 0.1 s windows, two
    seconds either side), at least `lo` s in and 3 s before the end. None for tracks shorter than ~8 s."""
    y = decode(path, 22050)
    sr, hop = 22050, 2205
    n = len(y) // hop
    if n < 80:
        return None
    env = np.array([np.sqrt(np.mean(y[i * hop:(i + 1) * hop].astype(np.float64) ** 2)) for i in range(n)])
    db = 20 * np.log10(env + 1e-6)
    k = 20
    best, at = -1e9, None
    for i in range(max(k, int(lo * 10)), n - max(k, 30)):
        jump = db[i:i + k].mean() - db[i - k:i].mean()
        if jump > best:
            best, at = jump, i
    if at is None or best < 3.0:      # no real drop (flat track): nothing to align
        return None
    # the drop itself: the strongest single-window rise around the found boundary
    seg = np.diff(db[max(0, at - 5):at + 6])
    return round((max(0, at - 5) + int(np.argmax(seg)) + 1) * hop / sr, 2)


def drop_offset(drop_t, key_t):
    """How to place a track so its drop lands on key_t (seconds in the video): seek into the track when the drop comes
    later than the key line, otherwise delay the track's start. -> {"seek": s, "delay": s}"""
    if drop_t is None or key_t is None:
        return {"seek": 0.0, "delay": 0.0}
    d = round(drop_t - key_t, 3)
    return {"seek": max(0.0, d), "delay": max(0.0, -d)}


def mute_expr(mutes):
    """volume filter that silences the music inside the windows [[a, b], ...] (hard cut: a story event, not a fade)."""
    ws = [(float(a), float(b)) for a, b in mutes or [] if float(b) > float(a)]
    if not ws:
        return ""
    cond = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in ws)
    return f"volume='if({cond},0,1)':eval=frame"


def music_chain(idx, total, db=-18.0, seek=0.0, delay=0.0, mutes=None, carve=True, fade_out=1.5, label="mus"):
    """Filter lines for the music input `idx` (seek / delay / level / carve / automation / fades) -> [label].
    The sidechain duck is added by mix_chain once the voice exists."""
    ms = int(round(delay * 1000))
    parts = [f"[{idx}:a]aformat=sample_rates={SR}:channel_layouts=stereo"]
    if seek > 0:
        parts.append(f"atrim=start={seek:.3f},asetpts=PTS-STARTPTS")
    parts.append(f"volume={db}dB")
    if carve:
        parts.append(f"equalizer=f={CARVE_HZ}:t=q:w=1.4:g=-4")
    if ms:
        parts.append(f"adelay={ms}|{ms}")
    parts += ["apad", f"atrim=0:{total:.3f}", "afade=t=in:d=0.4", f"afade=t=out:st={max(0, total - fade_out):.3f}:d={fade_out}"]
    me = mute_expr(mutes)
    if me:
        parts.append(me)
    return [",".join(parts) + f"[{label}]"]


def duck_lines(music, voice, out="ducked", ratio=8, release=420):
    """Sidechain the music under the voice. `voice` is consumed: the caller splits it first if it is needed again."""
    return [f"[{music}][{voice}]sidechaincompress=threshold=0.025:ratio={ratio}:attack=25:release={release}[{out}]"]


# ---------- sound effects ----------
def no_mask(cues, words, offset=0.0, nudge=0.15, under=4.0):
    """Sound effects never cover a word: a cue that lands on speech moves into a gap when one is within `nudge` s,
    else it plays `under` dB lower (hits and risers that mark the hook stay where they are, just lower).
    `words` = [[w, start, end]] relative to the voice file, which starts at `offset` in the video."""
    spans = [(s + offset, e + offset) for _, s, e in words or []]
    out = []
    for c in cues:
        c = dict(c)
        t = float(c["t"])
        hit = next(((a, b) for a, b in spans if a - 0.02 <= t <= b), None)
        if hit:
            a, b = hit
            to = a - 0.04 if t - a < b - t else b + 0.02
            fixed = c.get("kind") in ("hit", "riser", "impact", "logo_hit", "drone")
            if not fixed and abs(to - t) <= nudge and not any(x - 0.02 <= to <= y for x, y in spans):
                c["t"] = round(max(0.0, to), 3)
            else:
                c["gain_db"] = round(float(c.get("gain_db", -10)) - under, 1)
        out.append(c)
    return out


def sfx_lines(renders, first_idx, total, label="sfx"):
    """(input args, filter lines) for rendered cues [{file, start, gain_db}] -> one [label] stream, or ([], [])."""
    if not renders:
        return [], []
    args, chain = [], []
    for k, r in enumerate(renders):
        args += ["-i", r["file"]]
        ms = int(round(max(0.0, r["start"]) * 1000))
        chain.append(f"[{first_idx + k}:a]aformat=sample_rates={SR}:channel_layouts=stereo,volume={r['gain_db']}dB,"
                     f"adelay={ms}|{ms}[x{k}]")
    chain.append("".join(f"[x{k}]" for k in range(len(renders))) +
                 f"amix=inputs={len(renders)}:normalize=0,apad,atrim=0:{total:.3f}[{label}]")
    return args, chain


def mix(video, out, total, voice=None, music=None, cues=None, words=None, voice_offset=0.0, chain=None,
        extra_audio=None):
    """Put the sound on a (silent or not) video: voice (+chain), music (carve, duck, automation, drop alignment), sound
    effects (no-mask) and an optional extra bed. Video is stream-copied. Loudness is left to the final master.
      voice  {"file", "start"}        music {"file", "db", "seek", "delay", "mutes", "drop_on"}
      cues   [{"t", "kind", "gain_db"}]  (factory/sfx.py kinds)   extra_audio {"file", "db"}"""
    from . import sfx
    args, lines, mixes, i = ["-i", video], [], [], 1
    vo = None
    if voice:
        args += ["-i", voice["file"]]
        ms = int(round(float(voice.get("start", 0)) * 1000))
        ch = voice_chain(chain) + "," if chain else ""
        lines.append(f"[{i}:a]aformat=sample_rates={SR}:channel_layouts=stereo,{ch}adelay={ms}|{ms},apad,"
                     f"atrim=0:{total:.3f}[vo0]")
        vo, i = "vo0", i + 1
    if music:
        args += ["-i", music["file"]]
        if music.get("auto") and voice:     # voice ~10 dB over the music by RMS (before the duck), within sane bounds
            music = dict(music, db=auto_music_db(voice["file"], music["file"], gap=music.get("gap", 10.0)))
        lines += music_chain(i, total, music.get("db", -18), music.get("seek", 0), music.get("delay", 0),
                             music.get("mutes"), music.get("carve", True))
        i += 1
        if vo:
            lines.append(f"[{vo}]asplit=2[vo][vokey]")
            lines += duck_lines("mus", "vokey")
            mixes += ["[vo]", "[ducked]"]
        else:
            mixes.append("[mus]")
    elif vo:
        mixes.append(f"[{vo}]")
    if extra_audio:
        args += ["-i", extra_audio["file"]]
        lines.append(f"[{i}:a]aformat=sample_rates={SR}:channel_layouts=stereo,volume={extra_audio.get('db', -12)}dB,"
                     f"apad,atrim=0:{total:.3f}[bed]")
        mixes.append("[bed]")
        i += 1
    if cues:
        rend = sfx.to_render(no_mask(cues, words, voice_offset) if words else cues)
        a, ln = sfx_lines(rend, i, total)
        args += a
        lines += ln
        if ln:
            mixes.append("[sfx]")
    if not mixes:
        run(["-i", video, "-c", "copy", out])
        return out
    lines.append("".join(mixes) + (f"amix=inputs={len(mixes)}:normalize=0" if len(mixes) > 1 else "anull") +
                 f",atrim=0:{total:.3f},alimiter=limit=0.95:level=false[a]")
    run([*args, "-filter_complex", ";".join(lines), "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
         "-b:a", "192k", "-ar", str(SR), "-t", f"{total:.3f}", "-movflags", "+faststart", out])
    return out


def auto_music_db(voice_file, music_file, gap=10.0):
    """Music gain (dB) that puts the voice `gap` dB over the music by RMS (speech parts only), clamped to -30..-8."""
    v, m = decode(voice_file), decode(music_file)
    sp = v[np.abs(v) > 0.01]
    if not len(sp) or not len(m):
        return -18.0
    rv = 20 * np.log10(np.sqrt(np.mean(sp.astype(np.float64) ** 2)) + 1e-9)
    rm = 20 * np.log10(np.sqrt(np.mean(m.astype(np.float64) ** 2)) + 1e-9)
    return round(float(max(-30.0, min(-8.0, rv - rm - gap))), 1)


def save_placed(name, cues, words=None, voice_offset=0.0):
    """Keep what the mix placed (for the sound QA after the final render)."""
    from .config import ROOT
    import json
    p = os.path.join(ROOT, "work", "sound", f"{name}.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump({"cues": cues, "words": words or [], "voice_offset": voice_offset}, open(p, "w"))
    return p


def place_music(music, key_t):
    """Fill seek/delay of a music spec so its drop lands on key_t (only when the spec asks: music['drop_on'] set)."""
    if not music or key_t is None or not os.path.exists(music["file"]):
        return music
    m = dict(music)
    m.update(drop_offset(m.get("drop_t") if m.get("drop_t") is not None else drop_time(m["file"]), key_t))
    return m
