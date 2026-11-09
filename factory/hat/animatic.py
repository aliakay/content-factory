"""The animatic: the whole film at draft timing, in a minute and at no credit, before the voice is paid for.

An explainer spends most of its money on narration and music, and most of its taste decisions are made before either
exists. This stage draws the scene plan with the script's draft timing (factory/hat/explainer.draft_timing, or the
beats' holds for a music-led piece), renders it at 15 fps and half size with no post effects, and puts a free click
track on it: a tick where each line starts, a lower one where each scene starts. The creator sees and hears the cut,
the pace and the scene changes before a single credit is spent.

It also measures the render itself (factory/qa.py: energy, frozen_time) and reports only what an animatic can prove:
a scene too short to register, a scene that outstays its one idea, words that cannot be said in the time a scene
gives them, a film that sits still, an opening that does not move, a script line no scene shows. Every flag is a
number against a threshold, never a taste judgement, and the numbers are in the artifact for the human to overrule.

A note at the gate is not a re-render. It is the creator saying the film is wrong, and this is the first stage that
can tell *which* earlier stage is wrong: `route()` sends it to the scene plan (what is on screen) or the script
(what is said and how long it takes), and factory/hat/project.revise() moves the line back there. The work is then
fixed at its cause instead of redrawn on top of a plan that was already wrong.
"""
import array, json, math, os, wave

from ..config import ROOT
from . import explainer as X
from . import project as P

PREVIEW_FPS = 15
CLICK = {"line": (1500.0, 0.34), "scene": (820.0, 0.46)}   # (Hz, gain): a bright tick per line, a duller one per scene
CLICK_MS = 26
CLICK_DB = -18                       # the click track sits well under where the voice will be
SHORT_SCENE, LONG_SCENE = 1.2, 10.0  # seconds: under this a cut cannot register, over it one idea is stretched
FAST, SLOW = 1.4, 0.55               # how far a scene's words/second may stray from the language's speaking rate
STILL_SHARE, LONG_HOLD = 0.35, 1.2   # an animatic above these plays like a slideshow
HOOK_S = 3.0                         # the first line must be sayable in under this
DURATION_TOLERANCE = 0.20

SCENE_WORDS = ("sahne", "sahneyi", "sahnesi", "kesme", "kesim", "kesit", "gecis", "cekim", "plan",
               "scene", "shot", "cut", "transition")
SCRIPT_WORDS = ("kelime", "metin", "satir", "cumle", "soz", "sure", "uzun", "kisa", "zaman", "ritim", "tempo",
                "anlatim", "seslendirme", "word", "line", "text", "length", "timing", "pace", "voice")
_FOLD = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ç": "c", "Ç": "c",
                       "ö": "o", "Ö": "o", "ü": "u", "Ü": "u", "â": "a", "î": "i", "û": "u",
                       "\u0307": ""})    # "İ".lower() is "i" + a combining dot: strip it, or "METİN" never folds
TIMING = {"draft": {"tr": "taslak", "en": "draft"}, "beats": {"tr": "vuruş", "en": "beats"},
          "voice": {"tr": "gerçek ses", "en": "real voice"}}


def _ui_lang():
    try:
        from .. import accounts
        return accounts.ui_lang()
    except Exception:
        return "tr"


def _text(lang, tr, en):
    return tr if lang == "tr" else en


# ---------------------------------------------------------------- which stage a note belongs to

def _fold(text):
    return str(text or "").lower().translate(_FOLD)


def route(note):
    """The earlier stage a note at the animatic gate belongs to: `scene_plan` when the note is about what is on
    screen (a scene, a cut, a transition, a shot), else `script` when it is about the words and their timing.

    The stage word that appears first wins, because that is the subject of the sentence ("sahne 3'ün metni uzun"
    is a scene problem). A note naming neither goes to the script: an animatic exists to test whether the words fit
    the time, so a note that says nothing more specific is a note about the words."""
    text = _fold(note)
    best = None
    for stage, words in (("scene_plan", SCENE_WORDS), ("script", SCRIPT_WORDS)):
        for w in words:
            i = text.find(w)
            if i >= 0 and (best is None or i < best[0]):
                best = (i, stage)
    return best[1] if best else "script"


def _revise(pid, note, d=None):
    target = route(note)
    lang = _ui_lang()
    what = {"scene_plan": {"tr": "sahne planına", "en": "scene plan"},
            "script": {"tr": "senaryoya", "en": "script"}}[target][lang]
    summary = _text(lang,
                    f"Not {what} geri gönderildi; o aşama bu notla yeniden çalışacak, sonra sıra yeniden buraya gelecek.",
                    f"The note went back to the {what}; that stage runs again with it and the line comes back here.")
    return {"revise": {"stage": target, "note": note}, "summary": summary,
            "review": {"verdict": "fix", "summary": summary}}


# ---------------------------------------------------------------- the render

def _click_track(path, sp):
    """A free temp click track on the video's own timeline: a tick where each line starts and a lower one where each
    scene starts, so the pace and the cuts can be judged by ear without paying for a voice or music."""
    sr, total = 48000, float(sp["duration"])
    n = int(round(total * sr)) + 1
    buf = array.array("h", bytes(4 * n))                      # stereo, silent
    vs = float(sp.get("voice_start", 0))
    marks = [(float(lt["start"]) + vs, "line") for lt in sp.get("line_times") or []]
    marks += [(float(sc["start"]), "scene") for sc in sp.get("scenes") or [] if float(sc["start"]) >= 0.2]
    for t, kind in marks:
        freq, gain = CLICK[kind]
        i0, m = int(round(t * sr)), int(sr * CLICK_MS / 1000)
        for k in range(m):
            j = i0 + k
            if 0 <= j < n:
                v = buf[2 * j] + int(32767 * gain * (1.0 - k / m) ** 3 * math.sin(2 * math.pi * freq * k / sr))
                buf[2 * j] = buf[2 * j + 1] = max(-32768, min(32767, v))   # two marks may overlap
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(buf.tobytes())
    return path


def _capture(pid, sp, plan, d=None):
    """Draw the plan at draft timing: half size, 15 fps, no post effects, no paid sound. The click track is mixed on
    afterwards, so the render itself is a plain silent preview."""
    work = P.path(pid, "work", "animatic", d=d)
    os.makedirs(work, exist_ok=True)
    b = os.path.join(work, "bundle.json")
    with open(b, "w", encoding="utf-8") as f:
        json.dump(X._htmlmotion().make_bundle(sp, X.design(plan)), f, ensure_ascii=False)
    silent = os.path.join(work, "silent.mp4")
    X._htmlmotion().render_bundle(b, sp, work, silent, preview=True)
    dst = P.path(pid, "renders", "animatic.mp4", d=d)
    from .. import audiofx
    audiofx.mix(silent, dst, sp["duration"], extra_audio={"file": _click_track(os.path.join(work, "clicks.wav"), sp),
                                                          "db": CLICK_DB})
    return dst


def _motion(path):
    """What the render itself proves about motion (factory/qa.py). A measurement that fails is not a failed animatic:
    the flags that need it are left out and the artifact says so."""
    from .. import qa
    out = {"still_share": None, "longest_hold_s": None, "cuts_per_10s": None, "frozen_s": None, "holds": []}
    try:
        e = qa.energy(path)
        out.update({k: e.get(k) for k in ("still_share", "longest_hold_s", "cuts_per_10s", "holds")})
    except Exception as exc:
        out["error"] = str(exc)[:200]
    try:
        out["frozen_s"] = qa.frozen_time(path).get("frozen_s")
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- what the animatic can prove

def scene_rows(sp, script):
    """Per scene: when it is on screen, how many words it shows and how fast that is. The speed is measured over the
    scene's *spoken* span (its lines' own timing), not its on-screen padding, so the lead-in and the tail of the film
    do not make the first and last scenes look slow. A beat held too short for its text still shows up as fast."""
    lines = script.get("lines") or []
    lt = sp.get("line_times") or []
    rate = X.WPS.get(sp.get("lang"), 2.5)
    rows = []
    for sc in sp.get("scenes") or []:
        a, b = (sc.get("lines") or [0, 0])[:2]
        words = len(" ".join(lines[i] for i in range(a, b + 1) if 0 <= i < len(lines)).split())
        secs = round(float(sc["end"]) - float(sc["start"]), 2)
        spoken = round(float(lt[min(b, len(lt) - 1)]["end"]) - float(lt[min(a, len(lt) - 1)]["start"]), 2) if lt else 0.0
        wps = round(words / spoken, 2) if spoken > 0 else 0.0
        flags = []
        if secs < SHORT_SCENE:
            flags.append("short")
        elif secs > LONG_SCENE:
            flags.append("long")
        if words and spoken > 0 and wps > rate * FAST:
            flags.append("fast")
        elif words and secs >= 2.0 and spoken > 0 and wps < rate * SLOW:
            flags.append("slow")
        rows.append({"id": sc["id"], "start": sc["start"], "end": sc["end"], "seconds": secs, "spoken": spoken,
                     "lines": [a, b], "words": words, "wps": wps, "flags": flags})
    return rows


def flags_of(pid, sp, rows, motion, script, d=None):
    """The animatic's findings, each a number against a threshold, in the creator's interface language."""
    lang, out = _ui_lang(), []

    def add(level, code, scene, tr, en):
        out.append({"level": level, "code": code, "scene": scene, "message": _text(lang, tr, en)})

    rate = X.WPS.get(sp.get("lang"), 2.5)
    for r in rows:
        if "short" in r["flags"]:
            add("warn", "scene_short", r["id"],
                f"'{r['id']}' {r['seconds']} sn: algılanamayacak kadar kısa. Süresini uzat ya da bir sonraki sahneyle birleştir.",
                f"'{r['id']}' is {r['seconds']} s: too short to register. Give it more time or merge it with the next scene.")
        if "long" in r["flags"]:
            add("info", "scene_long", r["id"],
                f"'{r['id']}' {r['seconds']} sn: tek bir fikir için uzun. İçine bir kesme ya da ikinci bir hareket koy.",
                f"'{r['id']}' is {r['seconds']} s: long for one idea. Cut inside it or add a second movement.")
        if "fast" in r["flags"]:
            add("warn", "text_fast", r["id"],
                f"'{r['id']}' {r['words']} kelimeyi {r['spoken']} sn'de gösteriyor ({r['wps']}/sn); seslendirme "
                f"{rate}/sn ile okunur. Metni kısalt ya da sahneyi uzat.",
                f"'{r['id']}' shows {r['words']} words in {r['spoken']} s ({r['wps']}/s); the voice reads at {rate}/s. "
                f"Shorten the text or give the scene more time.")
        if "slow" in r["flags"]:
            add("info", "dead_air", r["id"],
                f"'{r['id']}' {r['seconds']} sn sürüyor ama yalnız {r['words']} kelime var ({r['wps']}/sn); sahne "
                f"boşlukta bekliyor. İçine bir hareket ya da metin ekle, süresini kısalt.",
                f"'{r['id']}' runs {r['seconds']} s for {r['words']} words ({r['wps']}/s); the scene waits in dead air. "
                f"Give it more to say or make it shorter.")
    covered = {i for r in rows for i in range(r["lines"][0], r["lines"][1] + 1)}
    for i in range(len(script.get("lines") or [])):
        if i not in covered:
            add("warn", "line_uncovered", None,
                f"{i + 1}. satırı hiçbir sahne göstermiyor; sahneler senaryonun tamamını kapsamalı.",
                f"No scene shows line {i + 1}; the scenes must cover the whole script.")
    lt = sp.get("line_times") or []
    if lt and float(lt[0]["end"]) - float(lt[0]["start"]) > HOOK_S:
        secs = round(float(lt[0]["end"]) - float(lt[0]["start"]), 1)
        add("warn", "hook_slow", None,
            f"İlk satır {secs} sn sürüyor; kanca {HOOK_S:.0f} sn altında inmelidir.",
            f"The first line takes {secs} s; the hook must land under {HOOK_S:.0f} s.")
    holds = [h for h in (motion.get("holds") or []) if isinstance(h, (list, tuple)) and len(h) == 2]
    opening = [h for h in holds if float(h[0]) < 2.0 and float(h[1]) >= 1.0]
    if opening:
        add("warn", "hook_still", None,
            f"İlk 2 saniyede görüntü {opening[0][1]} sn duruyor; açılış hemen kımıldamalı.",
            f"The picture holds still for {opening[0][1]} s inside the first 2; the opening must move at once.")
    if motion.get("still_share") is not None and float(motion["still_share"]) > STILL_SHARE:
        add("warn", "slideshow", None,
            f"Filmin %{round(float(motion['still_share']) * 100)}'i hareketsiz; slayt gibi oynuyor.",
            f"{round(float(motion['still_share']) * 100)}% of the film is still; it plays like a slideshow.")
    elif motion.get("longest_hold_s") and float(motion["longest_hold_s"]) > LONG_HOLD:
        add("warn", "long_hold", None,
            f"En uzun duruş {motion['longest_hold_s']} sn; hareket {LONG_HOLD} sn'den uzun durmamalı.",
            f"The longest hold is {motion['longest_hold_s']} s; motion should not stop for more than {LONG_HOLD} s.")
    planned = (P.read_artifact(pid, "proposal", d) or {}).get("seconds")
    if planned:
        diff = abs(float(sp["duration"]) - float(planned)) / float(planned)
        if diff > DURATION_TOLERANCE:
            add("info", "duration_off", None,
                f"Film {sp['duration']:.1f} sn, onaylanan öneri {float(planned):.1f} sn: fark %{round(diff * 100)}.",
                f"The film is {sp['duration']:.1f} s, the approved proposal {float(planned):.1f} s: {round(diff * 100)}% apart.")
    from .. import beats
    bpm, offset = X._music_bpm(pid, d)
    if bpm:
        starts = [r["start"] for r in rows][1:]
        fit = beats.grid_fit(starts, beats.grid(bpm, float(sp["duration"]) + 1, offset))
        if fit["share"] < 0.6:
            add("warn", "off_beat", None,
                f"Kesmelerin yalnız %{round(fit['share'] * 100)}'i {bpm:.0f} BPM'lik vuruşta; müzikli film vuruş "
                f"ızgarasına kesilmeli.",
                f"Only {round(fit['share'] * 100)}% of the cuts sit on the {bpm:.0f} BPM beat; a music-led film cuts on "
                f"the grid.")
    return out


def _summary(sp, rows, flags, lang):
    warns = sum(1 for f in flags if f["level"] == "warn")
    timing = TIMING.get(sp.get("timing") or "", {"tr": sp.get("timing") or "", "en": sp.get("timing") or ""})[lang]
    head = _text(lang, f"{sp['duration']:.1f} sn, {len(rows)} sahne, {timing} zamanlama. Kredi harcanmadı.",
                 f"{sp['duration']:.1f} s, {len(rows)} scenes, {timing} timing. No credits spent.")
    tail = _text(lang, f" {warns} uyarı var." if warns else " Ölçülen kontrollerde uyarı yok.",
                 f" {warns} warning(s)." if warns else " No warnings in the measured checks.")
    return head + tail


# ---------------------------------------------------------------- the stage

def run(pid, s, note=None, d=None):
    """`fn(pid, stage, note=None, d=None) -> {artifact, summary, review, cost}` (factory/hat/runner.py calls it)."""
    note = (note or "").strip()
    if note:                                     # the creator says the film is wrong: send the note to its cause
        return _revise(pid, note, d)
    plan = P.read_artifact(pid, "scene_plan", d)
    script = P.read_artifact(pid, "script", d) or {}
    if not plan or not plan.get("scenes"):
        raise P.GateError("no scene plan to draw")
    if not (script.get("lines") or []):
        raise P.GateError("no script lines to time")
    sp = X.spec(pid, plan, d)
    sp["sound"] = {"sfx": False}                 # the click track is the only sound: no scene cues, no paid audio
    path = _capture(pid, sp, plan, d)
    rows = scene_rows(sp, script)
    motion = _motion(path)
    flags = flags_of(pid, sp, rows, motion, script, d)
    lang = _ui_lang()
    summary = _summary(sp, rows, flags, lang)
    art = {"file": os.path.relpath(path, ROOT), "duration": sp["duration"], "fps": PREVIEW_FPS,
           "timing": sp.get("timing"), "scenes": rows, "flags": flags, "motion": motion, "summary": summary}
    from .. import determinism
    art["fingerprint"] = determinism.fingerprint(sp, X.design(plan))
    return {"artifact": art, "summary": summary, "cost": {"credits": 0, "usd": 0.0},
            "review": {"verdict": "fix" if any(f["level"] == "warn" for f in flags) else "pass", "summary": summary}}
