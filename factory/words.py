"""Small language tools the craft checks share: folding, content words, numbers, action verbs.

Every check in this module family (camera, subjectqc, hookrule, coldtest, originality) has to look at Turkish and
English text the same way, and every one of them must be deterministic and model-free. Turkish needs folding before
any comparison (ı/i, ş/s, ğ/g, ç/c, ö/o, ü/u, and the dotted capital İ which lower-cases to "i" plus a combining
dot); suffixes mean a check matches stems inside a word ("yükseliyor" contains "yüksel"), which is why the verb and
number tables hold stems, not full words.
"""
import re

_FOLD = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ç": "c", "Ç": "c",
                       "ö": "o", "Ö": "o", "ü": "u", "Ü": "u", "â": "a", "î": "i", "û": "u", "\u0307": ""})
_WORD = re.compile(r"[\w']+", re.U)


def fold(text):
    """Lower-case and strip the Turkish letters that make two spellings of the same word compare unequal."""
    return str(text or "").lower().translate(_FOLD)


def tokens(text):
    return _WORD.findall(fold(text))


STOP = {
    "tr": set("""acaba ama ancak ardindan artık aslında az bana bazi bazı belki ben beni benim beri bile bir bircok birçok
        birsey birşey biz bize bu buna bunu bunun burada çok çünkü da daha dahi de defa degil değil diye dolayi dolayı
        eger eğer elbette en fakat gibi göre halen hala hangi hani hem hep hepsi her herkes hiç hiçbir icin için ile ise
        işte kadar kendi kendisi ki kim ki mi mu mü nasil nasıl ne neden nerede nereye nesi niye o olan olarak oldu oldugu
        olduğu olur olursa on ona onu onun orada oysa öyle sanki sen senin siz size son sonra söyle su şu şimdi tüm tümü
        üzere var ve veya ya yani yine yoksa zaten şey şeyi""".split()),
    "en": set("""a about above after again against all also am an and any are as at be because been before being below
        between both but by can could did do does doing done down during each few for from further had has have having he
        her here hers him his how i if in into is it its itself just me more most my no nor not now of off on once only or
        other our out over own same she should so some such than that the their them then there these they this those
        through to too under until up very was we were what when where which while who whom why will with would you your
        yours""".split()),
}

# Number words: a scene whose line says a figure must show a figure (subjectqc), a hook with a number is a hook with
# something concrete in it. Stems, matched inside the folded word.
NUMBERS = {
    "tr": ("bir", "iki", "uc", "dort", "bes", "alti", "yedi", "sekiz", "dokuz", "on", "yirmi", "otuz", "kirk",
           "elli", "altmis", "yetmis", "seksen", "doksan", "yuz", "bin", "milyon", "milyar", "trilyon", "yuzde",
           "yarim", "ceyrek", "sifir", "eksi", "kat", "kati", "katı"),
    "en": ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
           "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand",
           "million", "billion", "trillion", "percent", "half", "quarter", "zero", "minus", "double", "triple", "times"),
}
_DIGIT = re.compile(r"\d")

# Action verbs (stems). A picture that shows a subject must also show it DOING something; these are the verbs that
# say what changes on screen. Not exhaustive by design: the designer may add a verb to `shows` in its own words as
# long as the picture moves, but the check needs a floor it can prove.
VERBS = {
    "tr": ("yuksel", "yüksel", "duser", "düşer", "artar", "azal", "buyu", "büyü", "kucul", "küçül", "girer", "cikar",
           "çıkar", "kayar", "doner", "döner", "kiril", "kırıl", "bolun", "bölün", "birles", "birleş", "akar", "dolar",
           "bosal", "boşal", "cizil", "çizil", "belirir", "kaybol", "acil", "açıl", "kapan", "gecer", "geçer", "kesil",
           "donus", "dönüş", "degis", "değiş", "siler", "yazar", "sayar", "vurur", "iter", "ceker", "çeker", "uzar",
           "kisal", "kısal", "toplan", "dagil", "dağıl", "yigil", "yiğil", "kaydir", "kaydır", "sallan", "titrer",
           "patlar", "yanar", "siner", "yayil", "yayıl", "kaldir", "kaldır", "indir", "firlar", "fırlar", "ziplar",
           "zıplar", "akis", "akış", "kurul", "yikil", "yıkıl", "esles", "eşleş", "ayril", "ayrıl", "tirman", "tırman",
           "sizar", "sızar", "dolan", "saril", "sarıl", "dugum", "düğüm", "catla", "çatla", "savrul", "kaynar",
           "erir", "donar", "parla", "soner", "söner", "vurgula", "isaretle", "işaretle", "etiketle", "hizala",
           "sirala", "sırala", "yaklas", "yaklaş", "uzaklas", "uzaklaş", "bosalt", "boşalt", "doldur", "katla"),
    "en": ("rise", "rises", "fall", "falls", "grow", "grows", "shrink", "shrinks", "enter", "enters", "exit",
           "slide", "slides", "turn", "turns", "break", "breaks", "split", "splits", "merge", "merges", "flow",
           "flows", "fill", "fills", "drain", "drains", "draw", "draws", "appear", "appears", "vanish", "open",
           "opens", "close", "closes", "pass", "passes", "cut", "cuts", "morph", "morphs", "change", "changes",
           "erase", "erases", "write", "writes", "count", "counts", "hit", "hits", "push", "pushes", "pull",
           "pulls", "stretch", "stretches", "compress", "gather", "gathers", "scatter", "scatters", "stack",
           "stacks", "wipe", "wipes", "shake", "shakes", "burst", "bursts", "burn", "burns", "sink", "sinks",
           "spread", "spreads", "lift", "lifts", "drop", "drops", "jump", "jumps", "connect", "connects",
           "collapse", "collapses", "match", "matches", "separate", "separates", "loop", "loops", "reveal",
           "reveals", "sweep", "sweeps", "trace", "traces", "pop", "pops", "crawl", "crawls", "climb", "climbs",
           "puls", "spin", "spins", "rotate", "rotates", "drift", "drifts", "float", "floats", "bounce",
           "bounces", "zoom", "zooms", "pan", "pans", "label", "labels", "mark", "marks", "highlight", "highlights",
           "dim", "dims", "fade", "fades", "flash", "flashes", "glow", "glows", "expand", "expands", "contract",
           "contracts", "sort", "sorts", "align", "aligns", "pour", "pours", "spill", "spills", "flood", "floods",
           "leak", "leaks", "crack", "cracks", "snap", "snaps", "slice", "slices", "peel", "peels", "fold", "folds",
           "unfold", "unfolds", "wrap", "wraps", "hang", "hangs", "land", "lands", "hover", "hovers", "orbit",
           "orbits", "circle", "circles", "arc", "arcs", "bend", "bends", "curve", "curves", "wind", "winds",
           "weave", "weaves", "lock", "locks", "unlock", "unlocks", "click", "clicks", "tick", "ticks", "type",
           "types", "assemble", "assembles", "reassemble", "reassembles", "swap", "swaps", "flip", "flips",
           "step", "steps", "march", "marches", "roll", "rolls", "unroll", "unrolls", "stamp", "stamps", "smash",
           "smashes", "seal", "seals", "strike", "strikes", "hammer", "hammers", "chop", "chops", "pin", "pins"),
}


def has_number(text, lang="tr"):
    """Does this text carry a figure the picture must show? Digits, or a number word of either language."""
    if _DIGIT.search(fold(text)):
        return True
    toks = tokens(text)
    en_numbers = set(NUMBERS["en"]) | {"first", "second", "third"}
    # English number words are complete words; matching substrings made ordinary words such as "money" count as
    # numerals. Turkish inflection is allowed only with a known suffix, so "ikiye" counts but "birikim" does not.
    tr_suffixes = ("de", "da", "den", "dan", "te", "ta", "ye", "ya", "yi", "yı", "yu", "yü",
                   "nin", "nın", "nun", "nün", "ler", "lar", "şer", "şar", "inci", "ıncı", "uncu", "üncü")
    tr_numbers = {fold(x) for x in NUMBERS["tr"]} | {"birinci", "ikinci", "üçüncü", "dördüncü", "beşinci"}
    for tok in toks:
        if tok in en_numbers or tok in tr_numbers:
            return True
        for stem in tr_numbers:
            suffix = tok[len(stem):] if tok.startswith(stem) else ""
            if suffix in tr_suffixes and stem not in {"bir", "on", "bin", "kat"}:
                return True
    return False


def has_action(text, lang="tr"):
    """Does this text name something happening (a verb stem of either language)? Stems, so suffixes still match."""
    toks = tokens(text)
    stems = {fold(v) for v in VERBS["tr"] + VERBS["en"]}
    return any(tok.startswith(stem) for tok in toks for stem in stems if len(stem) >= 3)


def has_phrase(text, phrase):
    """Match a phrase on word boundaries, so ``so`` is not found inside ``also``."""
    parts = tokens(phrase)
    if not parts:
        return False
    toks = tokens(text)
    n = len(parts)
    return any(toks[i:i + n] == parts for i in range(len(toks) - n + 1))


def shares_content(a, b, lang="tr"):
    """Whether two short phrases carry a common content word, allowing inflected Turkish and English forms."""
    aa, bb = content(a, lang), content(b, lang)
    for x in aa:
        for y in bb:
            if x == y:
                return True
            # Prefix matching handles ordinary inflections (enerjinin/enerji, prices/price) without
            # treating short generic fragments as a shared subject.
            if min(len(x), len(y)) >= 5 and (x.startswith(y) or y.startswith(x)):
                return True
            for suffix in ("s", "es", "ed", "ing", "er", "ers", "ies"):
                if x.endswith(suffix) and len(x[:-len(suffix)]) >= 5 and x[:-len(suffix)] == y:
                    return True
                if y.endswith(suffix) and len(y[:-len(suffix)]) >= 5 and y[:-len(suffix)] == x:
                    return True
    return False


def content(text, lang="tr"):
    """The words that carry meaning in a line: folded, without stop words or one-letter tokens."""
    stop = STOP.get(lang if lang in STOP else "en", STOP["en"])
    return [w for w in tokens(text) if len(w) > 1 and w not in stop]


def proper_nouns(text):
    """Capitalised tokens that are not the first word of their sentence: names that survive translation. A name that
    opens a sentence is missed on purpose (a sentence's first capital says nothing about the word being a name)."""
    out = []
    for s in sentences(text):
        toks = re.findall(r"[\wçğıöşüÇĞİÖŞÜ-]+", s)
        for i, t in enumerate(toks):
            if len(t) > 2 and t[0].isupper() and (i > 0 or t.isupper()):
                out.append(t)          # not the first word, or an acronym, which never opens a sentence
    return out


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+", str(text or "").strip()) if s.strip()]
