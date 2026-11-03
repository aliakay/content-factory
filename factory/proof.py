"""Proof-film mode (t503): in a news or data video every number has a source, and the source shows.

A project created with `proof: true` on a line that researches (explainer, animation) keeps a ledger of sourced
figures: the research `data_points` that name a source, plus the script `claims` marked verified with an http source.
At each gate this module reads the stage's output and finds every number in it, written in digits ("1.250", "%42",
"3,4 milyar", "2.5bn") or in words ("kırk iki", "yüzde on beş", "three point four billion"):

  script      every number in a script line matches a sourced figure
  scene_plan  every number on screen matches a sourced figure AND is said in the script; the scene names its
              sources in `sources: [{url, label}]` and each label is written visibly in that scene
  publish     every number in the caption matches a sourced figure

A shown number matches a figure when the figure rounds to it ("1,2 milyon" matches 1 234 000). A plain year
(1800-2100) matches when that year appears anywhere in the research. `check` returns a report the gate shows;
`guard` refuses the approval while anything is unmatched, so an unsourced number cannot pass a gate.
"""
import html as H, re, urllib.parse

from .hat import manifest, project as P

STAGES = ("script", "scene_plan", "publish")      # artifacts a proof check reads

# ---------------------------------------------------------------- numbers in text

SCALE = {"bin": 1e3, "milyon": 1e6, "milyar": 1e9, "trilyon": 1e12,
         "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12,
         "mn": 1e6, "bn": 1e9, "mlr": 1e9, "tn": 1e12}
WORD_SCALE = ("bin", "milyon", "milyar", "trilyon", "thousand", "million", "billion", "trillion")
UNITS = {"sıfır": 0, "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9,
         "dörd": 4, "on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60, "yetmiş": 70, "seksen": 80,
         "doksan": 90,
         "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
         "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
         "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
HUNDRED = ("yüz", "hundred")
POINT = ("virgül", "nokta", "point")
PERCENT_PRE = ("yüzde", "%")
PERCENT_POST = ("%", "percent", "per cent")
# Turkish words that are also everyday words ("on" = on top, "altı" = under, "yüz" = face, "bin" = get on): they
# count only inside a number run or before a scale word, never with a case ending
AMBIGUOUS = {"on", "altı", "yüz", "bin", "bir", "one", "a"}

DIGITS = re.compile(r"(?<![\w.,])(%\s?)?(\d[\d.,]*\d|\d)(?:'\w+)?(%)?"
                    r"(?:\s?(bin|milyon|milyar|trilyon|thousand|million|billion|trillion|bn|mn|mlr|tn|percent)"
                    r"(?:[a-zçğıöşü]{0,4}|'\w+)(?![\w]))?", re.I)
WORD = re.compile(r"[a-zçğıöşü%]+|\d+|[^\s]", re.I)
SUFFIX = 4      # a case ending on the last number word: "kırk ikide", "milyonluk", "dördü"


def _fold(s):
    return s.replace("İ", "i").replace("I", "ı").lower()


def _digits_value(s, lang):
    """'1.250' -> (1250, 0 decimals); '3,4' -> (3.4, 1) in Turkish. Ambiguous separators follow the language."""
    dot, com = s.count("."), s.count(",")
    if dot and com:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
    elif dot or com:
        sep = "." if dot else ","
        tail = s.rsplit(sep, 1)[1]
        if (dot + com) > 1:
            dec = None
        elif len(tail) == 3:
            dec = "," if lang == "tr" else "."
            dec = sep if sep == dec else None
        else:
            dec = sep
    else:
        dec = None
    if dec:
        whole, frac = s.rsplit(dec, 1)
        whole = re.sub(r"[.,]", "", whole)
        return float(whole + "." + frac), len(frac)
    return float(re.sub(r"[.,]", "", s)), 0


def _tol(value, decimals, scale):
    """Half a step of what the shown number keeps: '1,2 milyon' keeps 0.1 million; '2000' keeps thousands."""
    if decimals:
        return 0.5 * 10 ** -decimals * scale
    v = int(round(value))
    zeros = len(str(v)) - len(str(v).rstrip("0")) if v else 0
    return 0.5 * 10 ** zeros * scale


def _digit_numbers(text, lang):
    out = []
    for m in DIGITS.finditer(text):
        pre, raw, post, word = m.group(1), m.group(2), m.group(3), _fold(m.group(4) or "")
        try:
            v, dec = _digits_value(raw, lang)
        except ValueError:
            continue
        scale = SCALE.get(word, 1) if word and (word in SCALE) else 1
        pct = bool(pre or post) or word in ("percent",)
        if not pre and _fold(text[:m.start()].rstrip()).endswith("yüzde"):     # "yüzde 1,6"
            pct, pre = True, "yüzde "
        shown = (pre or "") + raw + (post or "") + (" " + m.group(4) if scale != 1 else "")
        out.append({"text": shown.strip(), "value": v * scale, "tol": _tol(v, dec, scale), "percent": pct,
                    "year": not dec and scale == 1 and not pct and 1800 <= v <= 2100 and "." not in raw
                    and "," not in raw})
    return out


def _word(tok):
    """A token as a number word: the word itself, or a word plus a short ending (never for everyday words)."""
    if tok in UNITS or tok in HUNDRED or tok in WORD_SCALE:
        return tok, False
    for w in sorted(list(UNITS) + list(HUNDRED) + list(WORD_SCALE), key=len, reverse=True):
        if len(w) >= 3 and w not in AMBIGUOUS and tok.startswith(w) and 0 < len(tok) - len(w) <= SUFFIX:
            return w, True
    return None, False


def _word_numbers(text):
    """Spoken numbers: 'kırk iki', 'yüzde on beş', 'üç virgül dört milyar', 'forty-two', 'two point five million'."""
    raw = [_fold(t) for t in WORD.findall(text.replace("-", " "))]
    toks, ends = [], []
    for t in raw:
        w, suffixed = _word(t)
        toks.append(w or t)
        ends.append(suffixed)
    out, i = [], 0
    while i < len(toks):
        j, pct = i, False
        if toks[j] in PERCENT_PRE and j + 1 < len(toks):
            pct, j = True, j + 1
        total, cur, dec, decimals, used, start = 0.0, 0.0, None, 0, [], j
        while j < len(toks):
            w = toks[j]
            if w in UNITS:
                if dec is not None:
                    dec += str(UNITS[w])
                    decimals += 1
                else:
                    cur += UNITS[w]
            elif w == "buçuk" and used and dec is None:     # "bir buçuk milyon" = 1.5 million
                dec, decimals = "5", 1
            elif w in HUNDRED and dec is None:
                cur = (cur or 1) * 100
            elif w in WORD_SCALE:
                if not used and w == "bin" and not (j + 1 < len(toks) and toks[j + 1] in UNITS):
                    break                      # "bin" alone is also a verb; "bin beş yüz" is a number
                n = (cur if (cur or dec is not None) else 1) + (float("0." + dec) if dec else 0)
                total += n * SCALE[w]
                cur, dec = 0.0, None
                used.append(w)
                j += 1
                if ends[j - 1] or not (j < len(toks) and (toks[j] in UNITS or toks[j] in HUNDRED)):
                    break
                continue
            elif w in POINT and used and dec is None and j + 1 < len(toks) and toks[j + 1] in UNITS:
                dec = ""
            elif w == "and" and used and j + 1 < len(toks) and toks[j + 1] in UNITS:
                pass
            else:
                break
            used.append(w)
            j += 1
            if ends[j - 1]:                    # an ending closes the number
                break
        if not used:
            i += 1
            continue
        value = total + cur + (float("0." + dec) if dec else 0)
        scales = [w for w in used if w in WORD_SCALE]
        scale = SCALE[scales[-1]] if scales and not cur and not dec else 1
        # a lone everyday word ("bir", "on", "altı") is not a figure unless a percent or a scale makes it one
        lone = len(used) == 1 and used[0] in AMBIGUOUS and not pct
        if j < len(toks) and toks[j] in ("percent",) or (j + 1 < len(toks) and toks[j] == "per" and toks[j + 1] == "cent"):
            pct = True
        if not lone and (value >= 10 or pct or scales):
            shown = " ".join(toks[start - (1 if pct and start > i else 0):j])
            out.append({"text": shown, "value": value, "tol": _tol(value / scale, decimals, scale) if decimals
                        else (0.5 * scale if scales else 0.5), "percent": pct, "year": False, "spoken": True})
        i = j if j > i else i + 1
    return out


def numbers(text, lang="tr"):
    """Every number in `text`, each as {text, value, tol, percent, year}."""
    text = str(text or "")
    return _digit_numbers(text, lang) + _word_numbers(DIGITS.sub(" ", text))


def visible_text(html):
    """What a scene shows: its markup without tags, styles, scripts or attributes."""
    s = re.sub(r"(?is)<(style|script)\b.*?</\1>", " ", str(html or ""))
    s = re.sub(r"(?s)<[^>]*>", " ", s)
    return re.sub(r"\s+", " ", H.unescape(s)).strip()


# ---------------------------------------------------------------- the ledger of sourced figures

def _is_url(s):
    return bool(re.match(r"^https?://", str(s or "").strip()))


def ledger(pid, d=None):
    """Sourced figures: [{value, tol, text, source, from}] from research data points and verified script claims."""
    research = P.read_artifact(pid, "research", d, {}) or {}
    script = P.read_artifact(pid, "script", d, {}) or {}
    rows = []
    for dp in research.get("data_points") or []:
        src = str(dp.get("source") or "").strip()
        if not src:
            continue
        for txt in (dp.get("value"), dp.get("claim")):
            for lang in ("tr", "en"):           # research may be in either language: read both conventions
                for n in numbers(txt, lang):
                    rows.append(n | {"source": src, "from": "research", "claim": str(dp.get("claim") or "")[:160]})
    for c in script.get("claims") or []:
        if c.get("verified") and _is_url(c.get("source")):
            for lang in ("tr", "en"):
                for n in numbers(c.get("text"), lang):
                    rows.append(n | {"source": c["source"], "from": "script", "claim": str(c.get("text"))[:160]})
    return rows


def _years(pid, d=None):
    research = P.read_artifact(pid, "research", d, {}) or {}
    blob = " ".join(str(x) for x in [research.get("insight"), research.get("misconception")]
                    + [s.get("title") for s in research.get("sources") or []]
                    + [f"{dp.get('claim')} {dp.get('value')} {dp.get('source')}" for dp in research.get("data_points") or []])
    return {int(y) for y in re.findall(r"(?<!\d)(1[89]\d\d|20\d\d|2100)(?!\d)", blob)}


def _match(n, rows):
    for r in rows:
        if r["percent"] != n["percent"] and (r["percent"] or n["percent"]) and not n.get("spoken"):
            continue
        if abs(r["value"] - n["value"]) <= max(n["tol"], 1e-9):
            return r
    return None


# ---------------------------------------------------------------- the gate check

def supports(line):
    """A line can run in proof mode when it researches its figures before writing."""
    return any(s.get("artifact") == "research" for s in line.get("stages") or [])


def on(pid, d=None):
    p = P.load(pid, d)
    return bool(p.get("proof")) and supports(manifest.get(p["line"]))


def _label_shown(label, shown):
    f = lambda s: re.sub(r"[^0-9a-zçğıöşü]+", " ", _fold(s)).strip()
    return bool(f(label)) and f(label) in f(shown)


def check(pid, sid, d=None, data=None):
    """The proof report for one stage (its stored output, or a draft `data`), or None when proof mode is off or the
    stage holds no checked artifact."""
    if not on(pid, d):
        return None
    p = P.load(pid, d)
    art = manifest.stage(manifest.get(p["line"]), sid)["artifact"]
    if art not in STAGES:
        return None
    lang = p.get("video_lang") or "tr"
    rows, years = ledger(pid, d), _years(pid, d)
    data = data if isinstance(data, dict) else (P.read_artifact(pid, art, d, {}) or {})
    items = []

    def verdict(where, n, extra=None):
        hit = _match(n, rows)
        ok = bool(hit) or (n["year"] and int(n["value"]) in years)
        item = {"where": where, "text": n["text"], "ok": ok,
                "source": hit["source"] if hit else ("research" if ok else None),
                "problem": None if ok else "no_source"}
        if extra and ok:
            prob = extra(n, hit)
            if prob:
                item.update(ok=False, problem=prob)
        items.append(item)

    if art == "script":
        for i, line in enumerate(data.get("lines") or []):
            for n in numbers(line, lang):
                verdict(f"line {i + 1}", n)
    elif art == "publish":
        for n in numbers(data.get("caption"), lang):
            verdict("caption", n)
    else:
        script = P.read_artifact(pid, "script", d, {}) or {}
        said = [n for line in script.get("lines") or [] for n in numbers(line, lang)]
        for sc in data.get("scenes") or []:
            shown = visible_text(sc.get("html"))
            srcs = [s for s in sc.get("sources") or [] if isinstance(s, dict)]
            scan = shown
            for s in srcs:                     # the source line itself ("Kaynak: TÜİK, 2024") is not a figure
                if s.get("label"):
                    scan = re.sub(re.escape(str(s["label"])), " ", scan, flags=re.I)
            urls = {str(s.get("url") or "").strip() for s in srcs}

            def in_scene(n, hit, shown=shown, srcs=srcs, urls=urls):
                if n["year"]:
                    return None
                if not any(abs(m["value"] - n["value"]) <= max(n["tol"], m["tol"], 1e-9) for m in said):
                    return "not_in_script"
                if hit["source"] not in urls and _host(hit["source"]) not in {_host(u) for u in urls}:
                    return "source_not_named"
                label = next((s.get("label") for s in srcs if s.get("url") == hit["source"]
                              or _host(s.get("url")) == _host(hit["source"])), "")
                return None if _label_shown(label or "", shown) else "source_not_shown"
            for n in numbers(scan, lang):
                verdict(f"scene {sc.get('id')}", n, in_scene)
    bad = [x for x in items if not x["ok"]]
    return {"stage": sid, "artifact": art, "ok": not bad, "checked": len(items), "unmatched": len(bad),
            "items": items, "figures": len({r["source"] for r in rows})}


def _host(url):
    h = urllib.parse.urlparse(str(url or "")).netloc.lower()
    return h[4:] if h.startswith("www.") else h


PROBLEM = {
    "no_source": {"tr": "kaynaklı bir rakamla eşleşmiyor", "en": "matches no sourced figure"},
    "not_in_script": {"tr": "ekranda var ama senaryoda söylenmiyor", "en": "is on screen but not said in the script"},
    "source_not_named": {"tr": "sahnenin `sources` listesinde kaynağı yok", "en": "its source is not in the scene's `sources`"},
    "source_not_shown": {"tr": "kaynağın adı sahnede yazmıyor", "en": "the source's name is not shown in the scene"},
}


def problems(report, ui="tr"):
    return [f"{x['where']}: \"{x['text']}\" {PROBLEM[x['problem']][ui]}" for x in report["items"] if not x["ok"]]


def guard(pid, sid, d=None):
    """Refuse an approval while the stage shows a number without its source."""
    r = check(pid, sid, d)
    if r and not r["ok"]:
        ui = P.load(pid, d).get("ui_lang") or "tr"
        head = {"tr": f"Kanıt modu: {r['unmatched']} rakam kaynaksız, kapı geçilemez. Notla düzelttir:",
                "en": f"Proof mode: {r['unmatched']} number(s) lack a source; the gate cannot pass. Fix them with a note:"}[ui]
        raise P.GateError(head + "\n" + "\n".join("- " + x for x in problems(r, ui)[:12]))
    return r


BRIEF = {
    "script": """## Proof mode (binding)
This is a proof film: every number you write in a line must match a figure in `research.data_points` that names a
source, or a claim you add to `claims` with verified: true and its http(s) source. Shown rounding is fine ("1,2
milyon" for 1 234 000); a new or different number is not. Run `proof_check` before you submit; the gate refuses any
unmatched number.""",
    "scene_plan": """## Proof mode (binding)
This is a proof film: every number on screen must be a sourced figure that the script also says. Give every scene
that shows a number `sources: [{url, label}]` (url = the figure's source exactly as in research or the script claims;
label = a short name such as "TÜİK, 2024") and write that label visibly in the scene, e.g. a small "Kaynak: TÜİK,
2024" line. Run `proof_check` before you submit; the gate refuses any unmatched number.""",
    "publish": """## Proof mode (binding)
Every number in the caption must be a sourced figure from the research or the script; run `proof_check`.""",
}


def brief(pid, s, d=None):
    """The proof-mode section of a stage agent's task, or ''."""
    return ("\n" + BRIEF[s["artifact"]] + "\n") if s.get("artifact") in BRIEF and on(pid, d) else ""
