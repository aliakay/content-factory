"""Talking-head edit: the creator's own raw video of them talking to camera -> a tight vertical short, cut, reframed,
captioned, sound-designed and mastered. The source file is never modified; everything is written to work/ and out/.

Pipeline (production data.kind == "talk"; the shared Studio steps run it: idea -> preview -> final render + QA):
  analyze   faster-whisper word timings (fillers kept on purpose), phrases split at pauses, every filler word, false
            start and repeated take flagged; a face track (OpenCV when installed, else centre); accent colours from the
            footage itself
  decide    Claude, as editor: which phrases stay and in what order (strongest line first as the hook), hook text,
            punch-ins on key moments, 4-6 motion-graphics B-roll cutaways, keyword colours, music brief, post copy.
            Without Claude a deterministic rough cut (no fillers, no retakes, real silences tightened) still works.
  compile   kept word runs -> frame-aligned segments (audio and picture cut on the same frame grid, so sync never
            drifts), a face-centred 9:16 crop per segment, instant punch-ins at the key word, captions in output time,
            sound cues (impact on the hook, whoosh on punch-ins, swish into B-roll, pops on highlights; kept off words)
  render    bin/talkcut.py (engine "talk"): ffmpeg pieces + an HTML overlay (captions with highlight boxes, hook, B-roll)
            + voice chain + ducked music + effects; mastering by the shared post-pass
The techniques are in factory/capabilities.py (edit.*); the planner can combine them with the rest of the studio.
"""
import difflib, json, os, re, subprocess

from . import llm
from .config import FFMPEG, FFPROBE, ROOT

DATA = os.path.join(ROOT, "data", "talk")
RAW = os.path.join(ROOT, "raw", "talk")
VIDEO_EXT = (".mp4", ".mov", ".m4v")
FILLERS = {"en": {"um", "uh", "uhm", "umm", "erm", "er", "ah", "ahh", "hmm", "hm", "mm", "mhm", "uh-huh"},
           "tr": {"ıı", "ııı", "ıh", "ee", "eee", "eh", "hmm", "ım", "ıım", "şey", "aa"}}
LEADS = {"en": {"so", "and", "okay", "ok", "well", "like", "now", "but"},   # discourse words a restart often begins with
         "tr": {"yani", "şey", "hani", "ve", "ama", "tamam", "evet", "şimdi"}}
FILLER_PROMPT = {"en": "Umm, uh, so, I mean, like, you know, uh, okay.", "tr": "Iıı, eee, şey, yani, hani, ıım, tamam."}
GAP_SPLIT = 0.45      # a pause this long ends a phrase
MAX_GAP = 0.30        # inside a kept run, a real pause longer than this is cut (jump cut)
PRE, POST = 0.06, 0.10   # breathing room around a kept run (never past the midpoint to the next word)


def norm(w):
    return re.sub(r"[^\w']", "", str(w).replace("İ", "i").lower())


# ---------- analysis ----------
def probe(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:stream_side_data=rotation:format=duration", "-of", "json", path],
                       capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    st = (d.get("streams") or [{}])[0]
    w, h = st.get("width", 1080), st.get("height", 1920)
    rot = next((sd.get("rotation") for sd in st.get("side_data_list", []) if "rotation" in sd), 0)
    if rot in (90, -90, 270, -270):
        w, h = h, w
    num, den = (st.get("r_frame_rate") or "30/1").split("/")
    return {"w": w, "h": h, "fps": round(float(num) / float(den or 1), 3),
            "duration": float((d.get("format") or {}).get("duration") or 0)}


def transcribe(path, lang="en"):
    """[[word, start, end, prob]] with fillers kept (the initial prompt is full of them, so whisper writes them down);
    words whisper invents inside a final silence are dropped."""
    from faster_whisper import WhisperModel
    from .audiofx import decode
    audio = decode(path)
    model = WhisperModel("small.en" if lang == "en" else "small", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(audio, language=lang, word_timestamps=True, initial_prompt=FILLER_PROMPT.get(lang, ""),
                               vad_filter=False, condition_on_previous_text=False)
    words = []
    for w in (w for s in segs for w in (s.words or [])):
        if words and not w.word.startswith(" ") and not norm(w.word) in FILLERS.get(lang, set()):
            words[-1] = [words[-1][0] + w.word, words[-1][1], float(w.end), min(words[-1][3], float(w.probability))]
        else:
            words.append([w.word.strip(), float(w.start), float(w.end), float(w.probability)])
    return drop_tail_hallucination(words, audio)


def drop_tail_hallucination(words, audio, sr=16000):
    """Whisper invents 'Thank you.' over a silent tail: drop words that start where the audio is silent."""
    import numpy as np
    out = []
    for w in words:
        a, b = int(w[1] * sr), int(max(w[2], w[1] + 0.05) * sr)
        seg = audio[a:b]
        lv = 20 * np.log10(np.sqrt(np.mean(seg.astype(np.float64) ** 2)) + 1e-9) if len(seg) else -120
        if lv > -45 or w[1] < len(audio) / sr - 1.5:
            out.append(w)
    return out


def phrases(words, lang="en"):
    """Words -> phrases split at pauses / sentence ends, each flagged: fillers (word indexes), retake (an earlier take of
    the phrase that follows), false_start (a short broken-off phrase whose words restart in the next one)."""
    fill = FILLERS.get(lang, set())
    out, cur = [], []
    for i, w in enumerate(words):
        if cur and (w[1] - words[cur[-1]][2] >= GAP_SPLIT or re.search(r"[.!?]$", words[cur[-1]][0])):
            out.append(cur)
            cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    res = []
    for k, idx in enumerate(out):
        toks = [norm(words[i][0]) for i in idx]
        res.append({"id": k, "a": idx[0], "b": idx[-1], "start": round(words[idx[0]][1], 3),
                    "end": round(words[idx[-1]][2], 3), "text": " ".join(words[i][0] for i in idx),
                    "fillers": [i for i in idx if norm(words[i][0]) in fill], "flags": [], "_t": [t for t in toks if t not in fill]})
    lead = LEADS.get(lang, set())
    strip = lambda t: t[next((i for i, x in enumerate(t) if x not in lead), len(t)):]  # noqa: E731
    for k, ph in enumerate(res):
        mine = strip(ph["_t"])
        for nxt in res[k + 1:k + 3]:
            other = strip(nxt["_t"])
            same = difflib.SequenceMatcher(None, mine, other[:len(mine)]).ratio() if mine else 0
            if len(mine) >= 3 and (other[:3] == mine[:3] or same >= 0.75) and not re.search(r"[.!?]$", ph["text"]) \
                    or len(mine) >= 4 and same >= 0.85:
                ph["flags"].append("retake")       # the speaker said it again: keep the later take
                break
            if mine and len(mine) <= 4 and other and other[0] == mine[0] and \
                    difflib.SequenceMatcher(None, mine, other[:len(mine)]).ratio() >= 0.5 and \
                    not re.search(r"[.!?]$", ph["text"]):
                ph["flags"].append("false_start")
                break
        if not mine:
            ph["flags"].append("filler_only")
    for ph in res:
        ph.pop("_t")
        ph["repeats"] = stutters(words, ph, fill)
    return res


def stutters(words, ph, fill=()):
    """Word indexes of an immediate restart inside a phrase ("the big idea the big idea is ..."): the first take of a
    2-5 word sequence that is repeated right away is dropped."""
    idx = [i for i in range(ph["a"], ph["b"] + 1) if norm(words[i][0]) not in fill]
    toks = [norm(words[i][0]).rstrip(".") for i in idx]
    drop, k = [], 0
    while k < len(toks):
        hit = 0
        for n in range(5, 1, -1):
            if k + 2 * n <= len(toks) and toks[k:k + n] == toks[k + n:k + 2 * n]:
                hit = n
                break
        if hit:
            drop += idx[k:k + hit]
            k += hit
        else:
            k += 1
    return drop


def faces(path, dur, fps=2.0):
    """[(t, cx, cy, size)] face centres as fractions of the frame, OpenCV Haar cascade (optional package). [] without
    OpenCV: the crop stays centred."""
    try:
        import cv2
    except ImportError:
        return []
    import numpy as np
    det = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
    w = 360
    r = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-vf", f"fps={fps},scale={w}:-2,format=gray", "-f", "rawvideo", "-"],
                       capture_output=True)
    info = probe(path)
    h = int(round(info["h"] * w / info["w"] / 2) * 2)
    n = len(r.stdout) // (w * h)
    out = []
    for i in range(n):
        g = np.frombuffer(r.stdout[i * w * h:(i + 1) * w * h], np.uint8).reshape(h, w)
        fs = det.detectMultiScale(g, 1.15, 5, minSize=(w // 12, w // 12))
        if len(fs):
            x, y, fw, fh = max(fs, key=lambda f: f[2] * f[3])
            out.append((round(i / fps, 2), round((x + fw / 2) / w, 3), round((y + fh / 2) / h, 3), round(fw / w, 3)))
    return out


def footage_accent(path, dur):
    """Accent colours taken from the footage itself: the most saturated mid-bright colour of a few frames."""
    from PIL import Image
    import colorsys, io
    cols = []
    for t in (dur * 0.2, dur * 0.5, dur * 0.8):
        r = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1", "-vf", "scale=160:-2",
                            "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        if r.stdout:
            im = Image.open(io.BytesIO(r.stdout)).convert("RGB").quantize(8).convert("RGB")
            cols += [c for _, c in im.getcolors(64) or []]
    best, score = (255, 210, 61), -1
    for c in cols:
        h, l, s = colorsys.rgb_to_hls(*(x / 255 for x in c))
        sc = s * (1 - abs(l - 0.55) * 1.6)
        if sc > score:
            best, score = c, sc
    h, l, s = colorsys.rgb_to_hls(*(x / 255 for x in best))
    pop = colorsys.hls_to_rgb(h, 0.62, max(0.75, s))      # lift it so it reads as a caption accent on any footage
    return "#%02x%02x%02x" % tuple(int(x * 255) for x in pop)


def analyze(src, lang="en"):
    """Everything the edit decision needs, cached in data/talk/<stem>.json."""
    os.makedirs(DATA, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src))[0]
    cache = os.path.join(DATA, f"{stem}.json")
    if os.path.exists(cache):
        a = json.load(open(cache))
        if a.get("src") == os.path.relpath(src, ROOT) and a.get("lang") == lang:
            return a
    info = probe(src)
    words = transcribe(src, lang)
    a = {"src": os.path.relpath(src, ROOT), "lang": lang, **info, "words": [[w, round(s, 3), round(e, 3), round(p, 2)]
                                                                           for w, s, e, p in words],
         "phrases": phrases(words, lang), "faces": faces(src, info["duration"]), "accent": footage_accent(src, info["duration"])}
    json.dump(a, open(cache, "w"), ensure_ascii=False)
    return a


# ---------- the edit decision ----------
EDIT_SCHEMA = """{"title": "short working title", "logline": "one sentence", "why": "why this cut works (hypothesis)",
 "hook_text": "<= 6 words, from the strongest line, shown big in the first 1-2 s",
 "hook_options": ["2 alternative hook texts"], "hook_accent": "<one word of hook_text set in the serif accent>",
 "order": [<phrase ids in the order they play; the strongest line first; drop fillers-only, retakes, false starts, weak
            or repeated ideas; the story must still make sense>],
 "trim": {"<phrase id>": [<first word index inside the phrase>, <last word index>]},
 "punch": [{"id": <phrase id>, "word": <word index inside the phrase>, "zoom": 1.1-1.25}],
 "broll": [{"id": <phrase id>, "word": <word index where it starts>, "dur": 1.0-2.0,
            "kind": "kinetic|stat|list|quote|shape", "text": "<= 5 words (stat: the number)", "accent": "<one word>",
            "items": ["<list: 2-3 short items>"], "label": "<stat: what the number is>"}],
 "keywords": {"key": ["4-10 words to colour"], "danger": ["0-6 words for problems / warnings"]},
 "grade": "natural|film|golden|moody|vivid", "music_prompt": "instrumental brief for this cut",
 "post": {"caption": "< 150 chars, ends with a question", "hashtags": "#a #b #c"}}"""


def decide(a, brief="", target=None, recipe=None, feedback="", current=None):
    """Claude edits the transcript. Returns the cleaned edit (falls back to rough_edit when the model fails)."""
    from . import capabilities
    lines = [{"id": p["id"], "t": [p["start"], p["end"]], "text": p["text"], "flags": p["flags"],
              "fillers": [i - p["a"] for i in p["fillers"]]} for p in a["phrases"]]
    lo, hi = (target or [15, 60])
    notes = capabilities.designer_notes({"recipe": recipe}) if recipe else ""
    prompt = f"""You are a senior short-form video editor (TikTok / Reels / Shorts) editing the creator's own talking-head
video. You get the transcript as numbered phrases (word timings measured; "flags" are automatic: retake = an earlier
take of the next phrase, false_start = broken off and restarted, filler_only = only "um/uh"; "fillers" = filler word
indexes inside a phrase, they are removed automatically). Make the strongest possible cut:
- Final length {lo}-{hi} s. Keep only the strongest parts; remove every pause, filler, false start and repeated take;
  the story MUST still make sense. Strongest line first as the hook (a line moved to the front must still read).
- Hook text from the strongest line, big in the first 1-2 s. Punch-ins (1.1-1.25x) on key moments only (3-6).
- 4-6 motion-graphics B-roll cutaways (1-2 s each, ~20 % of the runtime) on the biggest moments, built in code: kinetic
  typography (heavy bold + one serif accent word), a stat with its number, a 2-3 item checklist, a quote, a 3D shape
  with a word; the creator's voice keeps playing under them. NO stock footage. Only numbers the creator said.
- Keywords to colour in the captions (key) and problem words (danger).
{notes}
Creator brief (data): <<<{brief or "none"}>>>
{f"Creator feedback on the current cut (apply it): <<<{feedback}>>>" if feedback else ""}
{f"Current cut (JSON): {json.dumps(current, ensure_ascii=False)}" if current else ""}
Language of the video: {a.get("lang", "en")} (write hook / B-roll / caption texts in it).
Transcript phrases (JSON): {json.dumps(lines, ensure_ascii=False)}
Reply with ONLY JSON in this schema:
{EDIT_SCHEMA}"""
    try:
        data, meta = llm.ask(prompt, tools=(), timeout=900)
        edit = clean_edit(data if isinstance(data, dict) else {}, a)
        edit["cost_usd"] = meta.get("cost_usd")
        if not edit["order"]:
            raise ValueError("empty cut")
        return edit
    except Exception as e:
        edit = rough_edit(a, target)
        edit["fallback"] = type(e).__name__
        return edit


def rough_edit(a, target=None):
    """Deterministic cut: every phrase except retakes, false starts and fillers-only, in order; hook = first phrase."""
    keep = [p for p in a["phrases"] if not set(p["flags"]) & {"retake", "false_start", "filler_only"}]
    hi = (target or [15, 60])[1]
    order, t = [], 0.0
    for p in keep:
        if t + (p["end"] - p["start"]) > hi + 3 and order:
            break
        order.append(p["id"])
        t += p["end"] - p["start"]
    first = next((p for p in a["phrases"] if p["id"] == (order or [0])[0]), None)
    hook = " ".join((first or {}).get("text", "").split()[:6])
    punch = [{"id": pid, "word": 0, "zoom": 1.15} for k, pid in enumerate(order) if k % 4 == 2][:4]
    return {"title": hook[:60] or "talking head", "hook_text": hook, "order": order, "trim": {}, "punch": punch,
            "broll": [], "keywords": {"key": [], "danger": []}, "grade": "film", "post": {}}


def clean_edit(e, a):
    ids = {p["id"]: p for p in a["phrases"]}
    order = []
    for x in e.get("order") or []:
        try:
            x = int(x)
        except (TypeError, ValueError):
            continue
        if x in ids and x not in order:
            order.append(x)
    n_of = lambda pid: ids[pid]["b"] - ids[pid]["a"]  # noqa: E731
    trim = {}
    for k, v in (e.get("trim") or {}).items():
        try:
            pid, (i, j) = int(k), v
            i, j = max(0, int(i)), min(n_of(pid), int(j))
            if pid in ids and i <= j:
                trim[pid] = [i, j]
        except (TypeError, ValueError):
            continue

    def at(x):
        try:
            pid, w = int(x.get("id")), int(x.get("word") or 0)
        except (TypeError, ValueError, AttributeError):
            return None
        return (pid, max(0, min(w, n_of(pid)))) if pid in ids and pid in order else None
    punch = [{"id": p[0], "word": p[1], "zoom": max(1.08, min(float(x.get("zoom") or 1.15), 1.25))}
             for x in e.get("punch") or [] if (p := at(x))][:8]
    broll = []
    for x in e.get("broll") or []:
        p = at(x)
        if not p:
            continue
        kind = x.get("kind") if x.get("kind") in ("kinetic", "stat", "list", "quote", "shape") else "kinetic"
        broll.append({"id": p[0], "word": p[1], "kind": kind, "dur": max(0.8, min(float(x.get("dur") or 1.5), 2.4)),
                      "text": str(x.get("text") or "")[:40], "accent": str(x.get("accent") or "")[:20],
                      "label": str(x.get("label") or "")[:40], "items": [str(i)[:28] for i in x.get("items") or []][:3]})
    kw = e.get("keywords") if isinstance(e.get("keywords"), dict) else {}
    return {"title": str(e.get("title") or "talking head")[:80], "logline": str(e.get("logline") or "")[:240],
            "why": str(e.get("why") or "")[:300], "hook_text": str(e.get("hook_text") or "")[:60],
            "hook_options": [str(h)[:60] for h in e.get("hook_options") or []][:3],
            "hook_accent": str(e.get("hook_accent") or "")[:24], "order": order, "trim": trim, "punch": punch,
            "broll": broll[:6], "keywords": {r: [str(w)[:24] for w in kw.get(r) or []][:12] for r in ("key", "danger")},
            "grade": e.get("grade") if e.get("grade") in ("natural", "film", "golden", "moody", "vivid") else "film",
            "music_prompt": str(e.get("music_prompt") or "")[:400],
            "post": e.get("post") if isinstance(e.get("post"), dict) else {}}


# ---------- compile: edit -> frame-aligned segments ----------
def runs(a, edit):
    """Kept word runs in play order: [(phrase id, [word indexes])], split at fillers and at real pauses > MAX_GAP."""
    words, ids = a["words"], {p["id"]: p for p in a["phrases"]}
    out = []
    for pid in edit["order"]:
        p = ids[pid]
        i0, i1 = edit["trim"].get(pid, [0, p["b"] - p["a"]])
        gone = set(p["fillers"]) | set(p.get("repeats") or [])
        idx = [i for i in range(p["a"] + i0, p["a"] + i1 + 1) if i not in gone]
        cur = []
        for i in idx:
            if cur and (words[i][1] - words[cur[-1]][2] > MAX_GAP or i != cur[-1] + 1 and words[i][1] - words[cur[-1]][2] > 0.12):
                out.append((pid, cur))
                cur = []
            cur.append(i)
        if cur:
            out.append((pid, cur))
    return out


def crop_center(a, t0, t1):
    fs = [f for f in a.get("faces") or [] if t0 - 0.25 <= f[0] <= t1 + 0.25] or a.get("faces") or []
    if not fs:
        return 0.5, 0.42
    xs, ys = sorted(f[1] for f in fs), sorted(f[2] for f in fs)
    return xs[len(xs) // 2], ys[len(ys) // 2]


def segments(a, edit, fps=30):
    """Frame-aligned segments. Every piece's picture is n frames at the output rate and its audio is exactly the same
    n / fps seconds from the same in-point, so lip sync can never drift over many cuts."""
    words = a["words"]
    punch = {(x["id"], x["word"]): x["zoom"] for x in edit["punch"]}
    ids = {p["id"]: p for p in a["phrases"]}
    src_f = a.get("fps") or 30
    segs, spans = [], []
    rs = runs(a, edit)
    for k, (pid, idx) in enumerate(rs):
        prev_end = words[idx[0] - 1][2] if idx[0] > 0 else 0.0
        next_start = words[idx[-1] + 1][1] if idx[-1] + 1 < len(words) else a["duration"]
        s = max(words[idx[0]][1] - PRE, (prev_end + words[idx[0]][1]) / 2, 0.0)
        e = min(words[idx[-1]][2] + POST, (words[idx[-1]][2] + next_start) / 2, a["duration"])
        s = round(s * src_f) / src_f                        # snap the in-point to a source frame
        if e - s < 2 / fps:                                  # outside the source (a bad timing): nothing to cut
            continue
        # split at a punch-in word: the zoom cuts in on that word and holds to the end of the run
        cuts = [(s, 1.0)]
        for i in idx:
            z = punch.get((pid, i - ids[pid]["a"]))
            if z and words[i][1] - s > 0.25:
                cuts.append((round((words[i][1] - 0.03) * src_f) / src_f, z))
            elif z:
                cuts[0] = (cuts[0][0], z)      # the run starts on the punch word: the whole piece is punched in
        for j, (cs, z) in enumerate(cuts):
            ce = cuts[j + 1][0] if j + 1 < len(cuts) else e
            n = max(1, int(round((ce - cs) * fps)))
            cx, cy = crop_center(a, cs, ce)
            segs.append({"in": round(cs, 4), "frames": n, "zoom": z, "cx": cx, "cy": cy, "phrase": pid})
        spans.append((idx, len(segs) - len(cuts), len(segs)))   # this run's words live in these segments
    t, starts = 0.0, []
    for sg in segs:
        starts.append(t)
        t += sg["frames"] / fps
    total = round(t, 3)
    out_words = []          # output times of every kept word
    for idx, k0, k1 in spans:
        for i in idx:
            w = words[i]
            for k in range(k0, k1):
                sg, dur = segs[k], segs[k]["frames"] / fps
                if sg["in"] - 0.001 <= w[1] < sg["in"] + dur or k == k1 - 1:
                    o = starts[k] + max(0.0, w[1] - sg["in"])
                    out_words.append([w[0], round(o, 3), round(min(o + (w[2] - w[1]), starts[k] + dur), 3), i])
                    break
    return segs, out_words, total, starts


def caption_keys(edit):
    from .explainer import _cap_key
    return {_cap_key(w): role for role in ("key", "danger") for ln in edit["keywords"].get(role) or [] for w in str(ln).split()
            if _cap_key(w)}


def compile_spec(con, p, fmt=None, preview=True):
    """Production -> (talkcut spec, total, segment starts, warnings). Deterministic."""
    from . import sfx
    d = p["data"]
    a = json.load(open(os.path.join(ROOT, d["analysis"])))
    edit = d["edit"]
    fps = 60 if d.get("fps60") and not preview else 30
    segs, ow, total, starts = segments(a, edit, fps)
    warn = []
    if not segs:
        raise ValueError("the cut is empty: keep at least one phrase")
    lo, hi = (fmt or {}).get("duration") or [15, 60]
    target = (d.get("recipe") or {}).get("seconds") or [lo, hi]
    if total > target[1] + 3:
        warn.append(f"kurgu {total:.1f} s, hedef en fazla {target[1]} s")
    ids = {x["id"]: x for x in a["phrases"]}
    wi = {w[3]: w for w in ow}

    def out_t(pid, k):
        w = wi.get(ids[pid]["a"] + k)
        return w[1] if w else None
    hook_end = min(2.2, max(1.2, (ow[min(len(ow) - 1, 5)][2] if ow else 2.0)))
    broll = []
    for b in edit["broll"]:
        t0 = out_t(b["id"], b["word"])
        if t0 is None:
            warn.append(f"B-roll kelimesi kurguda yok ({b['text']})")
            continue
        t0 = max(t0, hook_end + 0.2)
        if broll and t0 < broll[-1]["end"] + 0.8:
            continue
        broll.append({**{k: b[k] for k in ("kind", "text", "accent", "label", "items")}, "start": round(t0, 3),
                      "end": round(min(total - 0.3, t0 + b["dur"]), 3)})
    cues = [{"t": 0.08, "kind": "impact", "gain_db": -12}]
    t = 0.0
    for sg in segs:
        if sg["zoom"] > 1.0:
            cues.append({"t": round(t, 3), "kind": "whoosh", "gain_db": -16})
        t += sg["frames"] / fps
    for b in broll:
        cues.append({"t": b["start"], "kind": "swish", "gain_db": -14})
    keys, seen = caption_keys(edit), set()
    from .explainer import _cap_key
    for w in ow:
        k = _cap_key(w[0])
        if keys.get(k) == "key" and k not in seen and len(seen) < 6:
            seen.add(k)
            cues.append({"t": w[1], "kind": "pop", "gain_db": -14})
    cues = sfx.clean_cues(cues, total, "subtle", per10=7)
    spec = {"name": p["name"] or "draft", "engine": "talk", "aspect": d.get("aspect", "9:16"), "fps": fps,
            "source": a["src"], "src_size": [a["w"], a["h"]], "segments": segs, "duration": total,
            "words": [[w, s, e] for w, s, e, _ in ow], "keys": keys, "accent": a.get("accent") or "#ffd93d",
            "hook": {"text": edit.get("hook_text") or "", "accent": edit.get("hook_accent") or "", "end": round(hook_end, 2),
                     "behind": bool(d.get("hook_behind", True))},
            "broll": broll, "cues": cues, "grade": edit.get("grade", "film"), "voice_chain": d.get("voice_chain", "room"),
            "captions": {"energy": (d.get("captions") or {}).get("energy", "talk")},
            "post": dict(edit.get("post") or {}, series="Talking head")}
    if d.get("music_take"):
        spec["music"] = {"file": d["music_take"]["file"], "auto": True, "gap": 12.0}
    spec["text"] = [{"start": b["start"], "end": b["end"], "text": b["text"]} for b in broll] or \
        [{"start": 0.0, "end": hook_end, "text": spec["hook"]["text"]}]
    return spec, total, starts, warn


QA_NOTES = """This is the creator's own talking-head video, edited: fast jump cuts between kept phrases are intended (the
pauses, fillers and retakes were removed on purpose), occasional instant punch-ins (1.1-1.25x) on key words are intended,
full-frame motion-graphics cards (big type, a number, a checklist) that briefly replace the speaker while the voice
continues are intended B-roll, and the captions sit around y 1230 with a coloured box on the active word by design.
Flag real problems: the face cut off or off-centre, captions covering the mouth or eyes, unreadable text, a B-roll card
that contradicts what is said, black or frozen frames, a visible glitch at a cut."""


# ---------- production ----------
def is_talk(d):
    return (d or {}).get("kind") == "talk"


def create(con, src, brief="", channel_id=None, aspect="9:16", recipe=None, lang=None):
    """Analyze the raw video, let Claude cut it, and file it as a production at stage 'idea' (the cut plan to approve)."""
    from . import capabilities, productions
    lang = lang or ("tr" if re.search(r"[çğışöüÇĞİŞÖÜ]", brief or "") else "en")
    a = analyze(src, lang)
    if not a["words"]:
        raise ValueError("videoda konuşma bulunamadı")
    target = (recipe or {}).get("seconds")
    target = [max(8, target - 5), target + 5] if isinstance(target, int) else target
    edit = decide(a, brief, target, recipe)
    stem = os.path.splitext(os.path.basename(src))[0]
    d = {"kind": "talk", "title": edit["title"], "hook": edit["hook_text"], "logline": edit.get("logline", ""),
         "why": edit.get("why", ""), "analysis": os.path.relpath(os.path.join(DATA, f"{stem}.json"), ROOT),
         "source": a["src"], "lang": lang, "aspect": aspect if aspect in ("9:16", "16:9") else "9:16", "edit": edit,
         "shots": [], "claims": [], "post": edit.get("post") or {}, "voice": None}
    if edit.get("music_prompt"):
        d["music"] = {"prompt": edit["music_prompt"]}
    capabilities.apply(recipe or {}, d, "talk")
    return productions.create(con, "talking_head", d, brief, channel_id)


def revise(con, p, feedback):
    from . import productions
    d = p["data"]
    a = json.load(open(os.path.join(ROOT, d["analysis"])))
    keep = {k: v for k, v in d["edit"].items() if k != "cost_usd"}
    edit = decide(a, p.get("brief") or "", (d.get("recipe") or {}).get("seconds"), d.get("recipe"), feedback, keep)
    new = dict(d, edit=edit, title=edit["title"] or d["title"], hook=edit["hook_text"] or d.get("hook"))
    productions.apply_edit(con, p, new, "revizyon", feedback[:200])


def summary(d):
    """What the Studio shows on the cut card: kept / cut transcript, hook, punches, B-roll, sound plan."""
    a = json.load(open(os.path.join(ROOT, d["analysis"])))
    e = d["edit"]
    keep = set(e["order"])
    rows = []
    for ph in a["phrases"]:
        rows.append({"id": ph["id"], "t": [ph["start"], ph["end"]], "text": ph["text"], "kept": ph["id"] in keep,
                     "pos": e["order"].index(ph["id"]) + 1 if ph["id"] in keep else None, "flags": ph["flags"],
                     "fillers": len(ph["fillers"])})
    kept_s = sum(ph["end"] - ph["start"] for ph in a["phrases"] if ph["id"] in keep)
    return {"phrases": rows, "raw_s": round(a["duration"], 1), "kept_s": round(kept_s, 1), "accent": a.get("accent"),
            "faces": len(a.get("faces") or []), "hook": e.get("hook_text"), "hook_options": e.get("hook_options"),
            "punch": e.get("punch"), "broll": e.get("broll"), "keywords": e.get("keywords"), "grade": e.get("grade"),
            "fallback": e.get("fallback")}
