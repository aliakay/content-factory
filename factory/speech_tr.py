"""Turkish speech normalisation for the narration: numbers, dates, units, abbreviations and foreign names are rewritten
into how they are SPOKEN before the text goes to the TTS; captions keep the written form. Pure string code, free.

  "II. Mehmed 1452–1481'de %75 ile TBMM'nin 3/4'ünü..." -> "ikinci Mehmed bin dört yüz elli iki ile bin dört yüz seksen
  birde yüzde yetmiş beş ile Türkiye Büyük Millet Meclisi'nin dörtte üçünü..."

Why: ElevenLabs / Gemini read "1.5" as "bir nokta beş", "3/4" as "üç bölü dört", "C++" as "si artı artı", "COBOL" as letters,
and each model does it differently. The reading rules are code, so the same script is voiced the same way every time.

The API is token based, so word timings that come back for the spoken text can be mapped to the original words:

  plan(text, lang, pron) -> Plan(groups=[Group(written=[...], spoken=[...], a, b, kind)], spoken, used)
  spoken(text, lang, pron) -> str                  what the TTS receives (the text itself when nothing changes)
  spoken_lines(lines, lang, pron) -> [str]         the spoken form per script line
  restore_words(timed, plan) -> [[written, s, e]]  spoken-word timings -> original words; one written token that became
                                                   several spoken words (1990'da, C++) spans their whole time range
  voicing(lang, pron)                              context the TTS call (eleven.tts) reads: language + overrides
  for_tts(text)                                    the one place the spoken form is made for a TTS request

Lexicon: data/pronounce_tr.json (built-in, ~175 terms). Precedence: project > series > built-in (`pronunciations` dict on
the hat project / production data / series data). Matching is whole-word, longest match first, case-insensitive; an
ALL-CAPS key (AB, BM, RAM, BASIC, C++) must match its exact case so the Turkish words "ab", "ram", "basic" stay alone.
Suffixes after an apostrophe survive: "NATO'nun" stays, "ABD'ye" -> "Amerika Birleşik Devletleri'ne" (rebuilt by Turkish
vowel harmony), "1990'da" -> "bin dokuz yüz doksanda" (harmony follows how the number is spoken).

Other languages get only the overrides (a light pass): numbers and dates are left to the TTS.
Reading rules and the lexicon idea are ported from AI-Video-Factory (MIT, © Ersin KOÇ): see THIRD_PARTY.md.
"""
import contextlib
import contextvars
import functools
import json
import os
import re
from dataclasses import dataclass, field

LEXICON_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pronounce_tr.json")

ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
SCALES = ["", "bin", "milyon", "milyar", "trilyon", "katrilyon", "kentilyon"]
CURRENCY = {"$": "dolar", "€": "avro", "£": "sterlin", "₺": "lira", "¥": "yen"}
CURRENCY_WORDS = {"TL": "lira", "₺": "lira", "$": "dolar", "€": "avro", "£": "sterlin", "USD": "dolar", "EUR": "avro",
                  "GBP": "sterlin"}
HARD = "fstkçşhp"
VOWELS = "aeıioöuü"
MONTHS = ["ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık"]
LETTER = "[^\\W\\d_]"
AMT = r"\d[\d.,]*"
SCALE_WORD = re.compile(r"^(bin|milyon|milyar|trilyon)(" + LETTER + r"*)$")
# dotted abbreviations and how they are read (any case); the dot is the abbreviation's, not a sentence end
ABBREVIATIONS = {"vb": "ve benzeri", "vs": "vesaire", "yy": "yüzyıl", "ör": "örneğin", "örn": "örneğin", "bkz": "bakınız"}
# titles: capitalised only and always followed by a name ("av." is a hunt, "Av. Ali" a lawyer)
TITLES = {"Dr": "doktor", "Prof": "profesör", "Doç": "doçent", "Av": "avukat"}
# nouns that follow an ordinal even when written with a capital ("21. Yüzyıl")
ORDINAL_NOUNS = ("yüzyıl", "asır", "binyıl", "yıl", "dönem", "bölüm", "sezon", "sınıf", "kat", "nesil", "gün", "hafta",
                 "cadde", "sokak", "ordu", "tümen", "filo", "cumhuriyet")
UNITS = {"km": "kilometre", "m": "metre", "cm": "santimetre", "mm": "milimetre", "kg": "kilogram", "g": "gram",
         "mg": "miligram", "l": "litre", "lt": "litre", "ml": "mililitre", "km/h": "kilometre bölü saat",
         "km/s": "kilometre bölü saat", "m/s": "metre bölü saniye", "°C": "santigrat derece", "°F": "fahrenhayt derece",
         "°": "derece", "m²": "metrekare", "km²": "kilometrekare", "cm²": "santimetrekare", "m³": "metreküp",
         "cm³": "santimetreküp", "ha": "hektar", "KB": "kilobayt", "MB": "megabayt", "GB": "gigabayt", "TB": "terabayt",
         "Hz": "hertz", "kHz": "kilohertz", "MHz": "megahertz", "GHz": "gigahertz", "kW": "kilovat", "MW": "megavat",
         "kWh": "kilovat saat", "mAh": "miliamper saat", "dk": "dakika", "sn": "saniye", "ms": "milisaniye"}
UNIT_ATTACHED = re.compile("^(" + AMT + ")(" + "|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True)) + ")$")
LETTER_NAMES = {"a": "a", "b": "be", "c": "ce", "ç": "çe", "d": "de", "e": "e", "f": "fe", "g": "ge", "ğ": "yumuşak ge",
                "h": "he", "ı": "ı", "i": "i", "j": "je", "k": "ke", "l": "le", "m": "me", "n": "ne", "o": "o", "ö": "ö",
                "p": "pe", "r": "re", "s": "se", "ş": "şe", "t": "te", "u": "u", "ü": "ü", "v": "ve", "y": "ye", "z": "ze",
                "q": "kü", "w": "dabılyu", "x": "iks"}
URL = re.compile(r"(?i)(://|^www\.|@|^[#@]|[\w-]\.(com|org|io|gov|edu|tr|co|me|dev|app|ai|tv)(/|$|\W))")
SENTENCE_END = re.compile(r"[.!?…]['\"”’)\]]*$")


# ---------------------------------------------------------------- numbers
def _under1000(n):
    h, t, o = n // 100, n % 100 // 10, n % 10
    return " ".join(x for x in ("" if h == 0 else "yüz" if h == 1 else f"{ONES[h]} yüz", TENS[t], ONES[o]) if x)


def say_integer(digits):
    """'1453' -> 'bin dört yüz elli üç' (never 'bir bin'); more than 21 digits are read one by one."""
    d = re.sub(r"^0+(?=\d)", "", digits)
    if len(d) > 21:
        return " ".join("sıfır" if c == "0" else ONES[int(c)] for c in d)
    if set(d) == {"0"}:
        return "sıfır"
    groups, end = [], len(d)
    while end > 0:
        groups.insert(0, int(d[max(0, end - 3):end]))
        end -= 3
    out = []
    for i, g in enumerate(groups):
        scale = SCALES[len(groups) - 1 - i]
        if g == 0:
            continue
        out.append("bin" if scale == "bin" and g == 1 else " ".join(x for x in (_under1000(g), scale) if x))
    return " ".join(out)


def _last_vowel(word):
    return next((c for c in reversed(word) if c in VOWELS), "e")


def _v4(v):
    return {"a": "ı", "ı": "ı", "e": "i", "i": "i", "o": "u", "u": "u", "ö": "ü", "ü": "ü"}[v]


def _v2(v):
    return "a" if v in "aıou" else "e"


def ordinal(words):
    """Ordinal of a spoken number: the last word takes -(I)ncI with vowel harmony ('dört' -> 'dördüncü')."""
    *head, last = words.split(" ")
    base = "dörd" if last == "dört" else last
    v = _v4(_last_vowel(base))
    end = f"{base}nc{v}" if base[-1] in VOWELS else f"{base}{v}nc{v}"
    return " ".join([*head, end])


def locative(words):
    """'dört' -> 'dörtte', 'iki' -> 'ikide', 'on' -> 'onda'."""
    return words + ("t" if words[-1] in HARD else "d") + _v2(_last_vowel(words))


def harmonize(stem, suffix):
    """The author's suffix fitted to a new stem: vowels follow harmony, a leading d/t follows the stem's last sound."""
    last, out = _last_vowel(stem), ""
    for i, c in enumerate(suffix):
        if c in "ae":
            last = _v2(last)
        elif c in "ıiuü":
            last = _v4(last)
        else:
            out += ("t" if stem[-1] in HARD else "d") if (i == 0 and c in "dt") else c
            continue
        out += last
    return out


def join_suffix(stem, suffix):
    """stem + suffix as one spoken word group; 'dört' softens before a vowel ('4'ü' -> 'dördü')."""
    h = harmonize(stem, suffix)
    if h and h[0] in VOWELS and stem.endswith("dört"):
        stem = stem[:-1] + "d"
    return stem + h


def attach_suffix(stem, suffix):
    """Suffix for an expanded acronym, rebuilt by Turkish grammar: a compound noun ending in a possessive vowel takes the
    pronoun n ('Devletleri'ne', 'Meclisi'nin'), a consonant-final stem none ('Milletler'e'), y before a vowel."""
    compound = " " in stem.strip() and bool(re.search(r"[ıiuü]$", stem))
    ends_vowel = stem[-1] in VOWELS
    buffer, rest = "", suffix
    if re.match(r"[yn][aeıioöuü]", rest) or rest.startswith("yl"):
        buffer, rest = rest[0], rest[1:]
    lead = ""
    if rest and rest[0] in VOWELS:
        lead = "" if not ends_vowel else ("n" if compound else (buffer or "y"))
    elif re.match(r"[dt]", rest) and compound:
        lead = "n"
    elif re.match(r"l[ae]", rest) and buffer == "y" and ends_vowel:
        lead = "y"
    out = harmonize(stem, lead + rest)
    return "nd" + out[2:] if lead == "n" and out.startswith("nt") else out


def say_decimal(i, f):
    """'1,5' -> 'bir buçuk', '3,14' -> 'üç virgül on dört', '0,05' -> 'sıfır virgül sıfır beş'."""
    if f == "5" and set(i) != {"0"}:
        return f"{say_integer(i)} buçuk"
    zeros = len(f) - len(f.lstrip("0"))
    rest = f[zeros:]
    return " ".join([say_integer(i), "virgül", *["sıfır"] * zeros, *([say_integer(rest)] if rest else [])])


def say_amount(core, version=False, scaled=False):
    """One quantity: integer, Turkish thousands dots and decimal comma, English decimal point, version, minus."""
    if re.match(r"^-\d", core):
        rest = say_amount(core[1:], version, scaled)
        return f"eksi {rest}" if rest else None
    m = re.match(r"^(\d{1,3}(?:\.\d{3})+)(?:,(\d+))?$", core)
    if m:
        i = m.group(1).replace(".", "")
        return say_decimal(i, m.group(2)) if m.group(2) else say_integer(i)
    m = re.match(r"^(\d+),(\d+)$", core)
    if m:
        return say_decimal(m.group(1), m.group(2))
    if re.match(r"^\d+(?:\.\d+)+$", core):
        parts = core.split(".")
        if len(parts) > 2 or (version and not scaled):
            return " nokta ".join(say_integer(p) for p in parts)
        return say_decimal(parts[0], parts[1])
    if re.match(r"^0\d+$", core):
        return " ".join("sıfır" if c == "0" else ONES[int(c)] for c in core)
    if re.match(r"^\d+$", core):
        return say_integer(core)
    return None


ROMAN = [(100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def roman_value(s):
    """Value of a canonical Roman numeral ('II' -> 2); None when it is not one or is a lone L / C (initials)."""
    if not re.match(r"^[IVXLC]+$", s) or s in ("L", "C"):
        return None
    n, rest = 0, s
    for v, r in ROMAN:
        while rest.startswith(r):
            n, rest = n + v, rest[len(r):]
    back, k = "", n
    for v, r in ROMAN:
        while k >= v:
            back, k = back + r, k - v
    return n if back == s else None


# ---------------------------------------------------------------- tokens
def fold(s):
    """Comparison key: lower case with the Turkish dotted / dotless i folded together."""
    return s.replace("İ", "i").replace("I", "i").replace("ı", "i").lower()


def split(token):
    """(lead, core, tail): opening marks, the word itself, and the apostrophe suffix + punctuation after it."""
    lead = re.match(r"^[\"'“‘«(\[]*", token).group(0)
    rest = token[len(lead):]
    m = re.search(r"['’]" + LETTER, rest)
    body = rest[:m.start()] if m and m.start() > 0 else rest
    core = re.sub(r"[.,;:!?…\"'”’»)\]]+$", "", body)
    return lead, core, rest[len(core):]


def fit(stem, tail):
    """stem + the tail's apostrophe suffix harmonised to how the stem is SPOKEN (apostrophe dropped), then punctuation."""
    m = re.match(r"['’](" + LETTER + r"+)(.*)$", tail, re.S)
    return join_suffix(stem, m.group(1)) + m.group(2) if m else stem + tail


def _has_alnum(t):
    return bool(re.search(r"\w", t))


def _upper_initial(w):
    return bool(w) and w[0].isupper()


def _version_context(parts, i, names=()):
    """'Python 3.12' / 'sürüm 2.1' read as versions; 'Bunu 3.5 kat' (a capital only because it starts a sentence) does not.
    `names`: indexes of tokens that are listed terms (product names): a number right after one is a version too."""
    if i == 0:
        return False
    lead, core, tail = parts[i - 1]
    if core.lower() in ("sürüm", "versiyon", "ver", "v") or (i - 1) in names:
        return True
    if not _upper_initial(core) or tail or core.isdigit() or roman_value(core) is not None:
        return False
    return i - 1 > 0 and not SENTENCE_END.search(parts[i - 2][0] + parts[i - 2][1] + parts[i - 2][2])


# ---------------------------------------------------------------- lexicon
@functools.lru_cache(maxsize=4)
def _builtin(lang, mtime):
    if lang != "tr":
        return {}
    try:
        return dict(json.load(open(LEXICON_FILE, encoding="utf-8")).get("terms") or {})
    except (OSError, ValueError):
        return {}


def builtin_terms(lang="tr"):
    try:
        mtime = os.path.getmtime(LEXICON_FILE)
    except OSError:
        mtime = 0
    return dict(_builtin(lang_of(lang), mtime))


def lang_of(lang):
    return (lang or "en").strip().lower().replace("_", "-").split("-")[0] or "en"


def clean_terms(terms):
    """A user dictionary checked: written <= 120 chars, spoken <= 240, both non-empty strings."""
    out = {}
    for k, v in (terms or {}).items():
        k, v = str(k).strip(), " ".join(str(v).split())
        if k and v and len(k) <= 120 and len(v) <= 240 and not k.startswith("__"):
            out[k] = v
    return out


def merge(*layers):
    """Dictionaries from the lowest layer to the highest; a term (same words, any case) is replaced by a higher layer."""
    keys, out = {}, {}
    for layer in layers:
        for k, v in clean_terms(layer).items():
            fk = " ".join(fold(k).split())
            if fk in keys:
                out.pop(keys[fk], None)
            keys[fk] = k
            out[k] = v
    return out


def terms_for(lang="tr", pron=None):
    """The effective dictionary: built-in < overrides (series merged under project by the caller: see overrides())."""
    return merge(builtin_terms(lang), pron or {})


@dataclass
class Key:
    parts: tuple
    written: str
    spoken: str
    exact: bool
    acronym: bool


@functools.lru_cache(maxsize=32)
def _compile(items):
    keys = []
    for written, spoken in items:
        words = written.split()
        if not words:
            continue
        exact = len(words) == 1 and written.isupper()         # AB, RAM, BASIC, C++, 3D: only in this exact case
        keys.append(Key(tuple(words) if exact else tuple(fold(w) for w in words), written, spoken, exact,
                        bool(re.fullmatch(LETTER + "{2,6}", written)) and written.isupper()))
    return sorted(keys, key=lambda k: (-len(k.parts), -len(k.written)))


def compiled(lang, pron):
    return _compile(tuple(sorted(terms_for(lang, pron).items())))


def _match_term(keys, parts, i):
    for k in keys:
        n = len(k.parts)
        if i + n > len(parts):
            continue
        ok = True
        for j, want in enumerate(k.parts):
            lead, core, tail = parts[i + j]
            if (j > 0 and lead) or (j < n - 1 and tail) or not (core == want if k.exact else fold(core) == want):
                ok = False
                break
        if ok:
            return k
    return None


# ---------------------------------------------------------------- plan
@dataclass
class Group:
    written: list
    spoken: list
    a: int = 0                    # character offsets of the written span in the text
    b: int = 0
    kind: str = "plain"           # plain | number | abbr | term | letters

    @property
    def changed(self):
        return self.spoken != self.written


@dataclass
class Plan:
    text: str
    groups: list = field(default_factory=list)
    used: dict = field(default_factory=dict)

    @property
    def spoken(self):
        out, pos = [], 0
        for g in self.groups:
            out.append(self.text[pos:g.a])
            out.append(self.text[g.a:g.b] if not g.changed else " ".join(g.spoken))
            pos = g.b
        out.append(self.text[pos:])
        return "".join(out)

    def tokens(self):
        """Every spoken token in order (what the voice file contains)."""
        return [t for g in self.groups for t in g.spoken]

    def mapping(self):
        """Token-level mapping [(written span, spoken span, kind)] for the groups that changed."""
        return [(" ".join(g.written), " ".join(g.spoken), g.kind) for g in self.groups if g.changed]


def _abbreviation(parts, i):
    lead, core, tail = parts[i]
    if not tail.startswith("."):
        return None
    nxt = parts[i + 1] if i + 1 < len(parts) else None
    word = (nxt[0] + nxt[1])[:1] if nxt else ""
    if core in TITLES:
        return (1, lead + TITLES[core] + tail[1:]) if word.isupper() else None
    said = ABBREVIATIONS.get(fold(core))
    if not said:
        return None
    return 1, lead + said + (tail[1:] if word.islower() else tail)


def _ordinal_noun(word):
    w = fold(word)
    return any(w.startswith(fold(n)) for n in ORDINAL_NOUNS)


def _number(parts, i, names=()):
    """(tokens taken, spoken text) when parts[i...] is a number expression, else None."""
    lead, core, tail = parts[i]
    nxt = parts[i + 1] if i + 1 < len(parts) else None
    prev = parts[i - 1] if i else ("", "", "")
    one = lambda spoken, rest=tail: (1, lead + fit(spoken, rest))      # noqa: E731
    m = re.match(r"^[≈~](\S+)$", core)
    if m:
        inner = _number([*parts[:i], ("", m.group(1), tail), *parts[i + 1:]], i, names)
        return inner and (inner[0], lead + "yaklaşık " + inner[1])
    if core in CURRENCY_WORDS and not lead and i and (re.match("^" + AMT + "$", prev[1]) or SCALE_WORD.match(prev[1])):
        return one(CURRENCY_WORDS[core])             # "1,5 milyon TL", "5 bin $"
    roman = roman_value(core)
    # ordinals: Roman numeral / digits + dot + a word ("II. Mehmed", "19. yüzyıl", "1. Dünya Savaşı", "21. Yüzyıl")
    if nxt and tail.startswith(".") and re.match(LETTER, nxt[0] + nxt[1]):
        if roman is not None:
            return 1, lead + fit(ordinal(say_integer(str(roman))), tail[1:])
        if re.match(r"^[1-9]\d{0,4}$", core) and ((nxt[1][:1].islower() and not nxt[0]) or int(core) <= 20
                                                    or _ordinal_noun(nxt[1])):
            return 1, lead + fit(ordinal(say_integer(core)), tail[1:])
    # a Roman numeral after a name: "Mehmed II'nin", "Louis XIV" (small values only: sizes like XL are not read)
    if roman is not None and 2 <= roman <= 30 and core != "XL" and _upper_initial(prev[1]) and not prev[2] \
            and not tail.startswith(".") and roman_value(prev[1]) is None and len(prev[1]) > 1 and not prev[1].isupper():
        return 1, lead + fit(ordinal(say_integer(str(roman))), tail)
    if re.match(r"^(MÖ|M\.Ö|MS|M\.S)$", core) and nxt and nxt[1][:1].isdigit():
        return 1, lead + ("milattan önce" if "Ö" in core else "milattan sonra") + tail.lstrip(".")
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$", core) or re.match(r"^(\d{4})-(\d{2})-(\d{2})$", core)
    if m:
        a, b, c = (int(x) for x in m.groups())
        d, mo, y = (c, b, a) if a > 31 else (a, b, c)
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return one(f"{say_integer(str(d))} {MONTHS[mo - 1]} {say_integer(str(y))}")
    m = re.match(f"^%({AMT})$", core) or re.match(f"^({AMT})%$", core)
    if m and say_amount(m.group(1)):
        return one("yüzde " + say_amount(m.group(1)))
    m = re.match(r"^([$€£₺¥])(" + AMT + ")$", core) or re.match("^(" + AMT + r")([$€£₺¥])$", core)
    if m:
        symbol, raw = (m.group(2), m.group(1)) if m.group(1)[0].isdigit() else (m.group(1), m.group(2))
        amount, unit = say_amount(raw), CURRENCY[symbol]
        sc = nxt and not tail and SCALE_WORD.match(nxt[1])
        if amount and sc:        # "$1 milyarlık" -> "bir milyar dolarlık": the scale word comes before the unit
            return 2, lead + f"{amount} {sc.group(1)} " + fit(unit, ("'" + sc.group(2) if sc.group(2) else "") + nxt[2])
        if amount:
            return one(f"{amount} {unit}")
    m = re.match("^(" + AMT + ")[x×]$", core)
    if m and say_amount(m.group(1)):
        return one(say_amount(m.group(1)) + " kat")
    m = re.match("^(" + AMT + ")[-–—](" + AMT + ")$", core)
    if m and say_amount(m.group(1)) and say_amount(m.group(2)):
        return one(f"{say_amount(m.group(1))} ile {say_amount(m.group(2))}")
    if re.match("^" + AMT + "$", core) and not tail and i + 2 < len(parts) and parts[i + 1][1] in ("-", "–", "—") \
            and re.match("^" + AMT + "$", parts[i + 2][1]) and say_amount(core) and say_amount(parts[i + 2][1]):
        a, c = parts[i], parts[i + 2]
        return 3, lead + fit(f"{say_amount(core)} ile {say_amount(c[1])}", c[2])
    m = re.match(r"^(\d+)/(\d+)$", core)
    if m and int(m.group(2)) >= 2 and not m.group(2).startswith("0"):
        return one(f"{locative(say_integer(m.group(2)))} {say_integer(m.group(1))}")
    m = re.match(r"^(\d{1,2}):(\d{2})$", core)
    if m and int(m.group(1)) <= 24 and int(m.group(2)) <= 59:
        return one(" ".join(x for x in (say_integer(m.group(1)), "" if m.group(2) == "00" else say_amount(m.group(2))) if x))
    m = re.match(r"^(\d+)-(" + LETTER + "+)$", core)
    if m:
        return one(f"{say_integer(m.group(1))} {m.group(2)}")
    m = UNIT_ATTACHED.match(core)
    if m and say_amount(m.group(1)):
        return one(f"{say_amount(m.group(1))} {UNITS[m.group(2)]}")
    if re.match("^" + AMT + "$", core) and not tail and nxt and not nxt[0]:
        amt = say_amount(core, _version_context(parts, i, names), bool(SCALE_WORD.match(nxt[1])))
        if amt and nxt[1] in UNITS and (len(nxt[1]) > 1 or nxt[1] in "mgl"):
            return 2, lead + amt + " " + fit(UNITS[nxt[1]], nxt[2])
        if amt and nxt[1] in CURRENCY_WORDS:
            return 2, lead + amt + " " + fit(CURRENCY_WORDS[nxt[1]], nxt[2])
        if amt and nxt[1] == "%":
            return 2, lead + "yüzde " + amt + nxt[2]
    amt = say_amount(core, _version_context(parts, i, names), bool(nxt and SCALE_WORD.match(nxt[1])))
    return one(amt) if amt else None


def _compound(keys, parts, i):
    """'GPT-2' -> 'ci pi ti iki' (the listed term, then the number); an unlisted name stays ('Boeing-747' -> 'Boeing yedi
    yüz kırk yedi')."""
    lead, core, tail = parts[i]
    m = re.match(r"^(" + LETTER + r"+)-(\d+)$", core)
    if not m or not say_amount(m.group(2)):
        return None
    k = _match_term(keys, [("", m.group(1), "")], 0)
    return 1, lead + fit(f"{k.spoken if k else m.group(1)} {say_amount(m.group(2))}", tail)


def _letters(parts, i):
    """A vowel-less ALL-CAPS acronym that nobody listed (CHP, KPSS) is spelled by letter names."""
    lead, core, tail = parts[i]
    if not re.match(r"^[A-ZÇĞİÖŞÜ]{2,5}$", core) or re.search(r"[AEIİOÖUÜ]", core) or roman_value(core) is not None:
        return None
    names = [LETTER_NAMES["ı" if c == "I" else "i" if c == "İ" else c.lower()] for c in core]
    return 1, lead + " ".join(names) + tail


def plan(text, lang="tr", pron=None):
    """Group the text's whitespace tokens: unchanged words, numbers, abbreviations, listed terms (longest first)."""
    lang = lang_of(lang)
    toks = [(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", text or "")]
    parts = [split(t[0]) for t in toks]
    keys = compiled(lang, pron)
    out = Plan(text or "")
    names = set()                                  # tokens that were listed terms: "Python 3.12" is a version
    i = 0
    while i < len(toks):
        g = None
        if not URL.search(toks[i][0]):
            k = _match_term(keys, parts, i)
            if k:
                n = len(k.parts)
                first, last = parts[i], parts[i + n - 1]
                tail = last[2]
                if lang == "tr" and k.acronym and " " in k.spoken:       # ABD'ye -> ...Devletleri'ne
                    tail = re.sub(r"^(['’])(" + LETTER + r"+)", lambda m: m.group(1) + attach_suffix(k.spoken, m.group(2)), tail)
                g = Group([t[0] for t in toks[i:i + n]], (first[0] + k.spoken + tail).split(), kind="term")
                out.used[k.written] = k.spoken
                names.add(i + n - 1)
            elif lang == "tr":
                hit = _compound(keys, parts, i)
                kind = "term"
                if hit is None:
                    hit, kind = _number(parts, i, names), "number"
                if hit is None:
                    hit, kind = _abbreviation(parts, i), "abbr"
                if hit is None:
                    hit, kind = _letters(parts, i), "letters"
                if hit:
                    g = Group([t[0] for t in toks[i:i + hit[0]]], hit[1].split(), kind=kind)
        if g is None:
            g = Group([toks[i][0]], [toks[i][0]])
        take = len(g.written)
        g.a, g.b = toks[i][1], toks[i + take - 1][2]
        out.groups.append(g)
        i += take
    return out


def spoken(text, lang="tr", pron=None):
    """What the TTS receives. The text itself (same bytes, same cache key) when no rule applies."""
    return plan(text, lang, pron).spoken


def spoken_lines(lines, lang="tr", pron=None):
    """The spoken form of each script line, planned over the joined text exactly as the TTS receives it."""
    lines = list(lines)
    p = plan(" ".join(lines), lang, pron)
    bounds, pos = [], 0
    for ln in lines:
        bounds.append((pos, pos + len(ln)))
        pos += len(ln) + 1
    out = [[] for _ in lines]
    for g in p.groups:
        k = next((n for n, (a, b) in enumerate(bounds) if a <= g.a < b + 1), len(lines) - 1)
        out[k].extend(g.spoken)
    return [" ".join(x) for x in out]


def restore_words(timed, p, keep=_has_alnum):
    """[[spoken token, start, end]] (one per kept spoken token, in order) -> [[written token, start, end]].

    One written token that became several spoken words spans their whole time range ("1990'da" over four words); several
    written tokens over a different number of spoken words share the span by letter count."""
    out, k = [], 0
    for g in p.groups:
        sp = [t for t in g.spoken if keep(t)]
        wr = [t for t in g.written if keep(t)]
        seg = [list(t) for t in timed[k:k + len(sp)]]
        k += len(sp)
        if not wr:
            continue
        if not seg:
            at = out[-1][2] if out else 0.0
            seg = [[wr[0], at, at]]
        if len(wr) == len(seg):
            out += [[w, t[1], t[2]] for w, t in zip(wr, seg)]
            continue
        s0, e0 = seg[0][1], seg[-1][2]
        total, pos = sum(max(1, len(w)) for w in wr), s0
        for w in wr:
            end = pos + (e0 - s0) * max(1, len(w)) / total
            out.append([w, pos, end])
            pos = end
    return out


# ---------------------------------------------------------------- context for the TTS call
_CTX = contextvars.ContextVar("speech_ctx", default=None)


@contextlib.contextmanager
def voicing(lang, pron=None):
    """Callers that voice a script wrap the TTS call: `with speech_tr.voicing(lang, overrides): eleven.tts(...)`."""
    token = _CTX.set((lang_of(lang), dict(pron or {})))
    try:
        yield
    finally:
        _CTX.reset(token)


def current():
    return _CTX.get()


TR_WORDS = {"ve", "bir", "bu", "için", "ile", "çok", "gibi", "ama", "olarak", "daha", "kadar", "da", "de", "ne", "değil",
            "var", "yok", "sonra", "ancak", "ise", "her", "o", "şu"}


def guess_lang(text):
    """'tr' when the text clearly is Turkish (letters ğşıİ, ö ü ç, common words), else 'en'. Only for a TTS call that
    nobody wrapped in voicing()."""
    t = text or ""
    score = 2 * sum(t.count(c) for c in "ğşıİĞŞ") + sum(t.count(c) for c in "öüçÖÜÇ")
    score += 2 * sum(w in TR_WORDS for w in re.findall(r"\w+", t.lower()))
    return "tr" if score >= 3 else "en"


def for_tts(text):
    """THE place a TTS request's text is made spoken (eleven.tts calls this once, before the cache key and the call)."""
    ctx = current()
    lang, pron = ctx if ctx else (guess_lang(text), None)
    return spoken(text, lang, pron)


def overrides(p=None, con=None):
    """Pronunciation overrides of a hat project (project.json) or production data: series under project."""
    p = p or {}
    ser = p.get("series")
    layer = {}
    if con is not None and isinstance(ser, dict) and ser.get("id"):
        try:
            from . import series
            layer = series.pronunciations(con, ser["id"])
        except Exception:
            layer = {}
    return merge(layer, p.get("pronunciations"))
