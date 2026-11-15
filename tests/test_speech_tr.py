"""Turkish speech normalisation (factory/speech_tr.py), its hook in eleven.tts, the caption mapping back to the written
words, the free voice-stem audit (factory/voiceaudit.py) and the click detector that no longer reports the voice's own
hard consonants. Nothing here calls a paid API: the TTS and whisper are faked."""
import json, sqlite3, sys, types

import numpy as np
import pytest

from factory import captions, eleven, export, soundqa, speech_tr as S, voiceaudit as VA


# ---------------------------------------------------------------- reading rules
SAY = [
    # integers, thousands dots, decimals
    ("1453", "bin dört yüz elli üç"), ("1000", "bin"), ("100", "yüz"), ("2024", "iki bin yirmi dört"),
    ("2.500", "iki bin beş yüz"), ("1.000.000", "bir milyon"), ("3,14", "üç virgül on dört"),
    ("1,5 milyon", "bir buçuk milyon"), ("0,05", "sıfır virgül sıfır beş"), ("007", "sıfır sıfır yedi"),
    ("-5", "eksi beş"), ("1.5 milyon", "bir buçuk milyon"), ("12.345,5", "on iki bin üç yüz kırk beş buçuk"),
    # percent, currencies
    ("%75", "yüzde yetmiş beş"), ("75%", "yüzde yetmiş beş"), ("%0,5", "yüzde sıfır virgül beş"),
    ("%1,5", "yüzde bir buçuk"), ("$5", "beş dolar"), ("€2,5 milyar", "iki buçuk milyar avro"), ("₺100", "yüz lira"),
    ("100 TL", "yüz lira"), ("1,5 milyon TL", "bir buçuk milyon lira"), ("$1 milyarlık", "bir milyar dolarlık"),
    ("5 milyar dolarlık", "beş milyar dolarlık"), ("$500'lük", "beş yüz dolarlık"), ("100 TL'lik", "yüz liralık"),
    # ordinals
    ("II. Mehmed", "ikinci Mehmed"), ("XV. yüzyıl", "on beşinci yüzyıl"), ("21. yüzyılın", "yirmi birinci yüzyılın"),
    ("3. gün", "üçüncü gün"), ("I. Dünya Savaşı", "birinci Dünya Savaşı"), ("4. sınıf", "dördüncü sınıf"),
    ("21. Yüzyıl", "yirmi birinci Yüzyıl"), ("Mehmed II'nin", "Mehmed ikincinin"), ("Louis XIV", "Louis on dördüncü"),
    ("4'üncü", "dördüncü"), ("MÖ 330", "milattan önce üç yüz otuz"), ("M.S. 330", "milattan sonra üç yüz otuz"),
    # fractions, ranges, times, dates
    ("3/4", "dörtte üç"), ("1/2", "ikide bir"), ("1452–1481", "bin dört yüz elli iki ile bin dört yüz seksen bir"),
    ("1452 – 1481", "bin dört yüz elli iki ile bin dört yüz seksen bir"), ("10:30", "on otuz"), ("10:00", "on"),
    ("09:05", "dokuz sıfır beş"), ("12.05.2020", "on iki mayıs iki bin yirmi"), ("2020-05-12", "on iki mayıs iki bin yirmi"),
    # suffixes follow how the number is SPOKEN
    ("1990'da", "bin dokuz yüz doksanda"), ("1453'te", "bin dört yüz elli üçte"), ("1980'ler", "bin dokuz yüz seksenler"),
    ("5'i", "beşi"), ("4'ü", "dördü"), ("100'e", "yüze"), ("10:30'da", "on otuzda"), ("%75'i", "yüzde yetmiş beşi"),
    ("1452–1481'de", "bin dört yüz elli iki ile bin dört yüz seksen birde"), ("2.500'ü", "iki bin beş yüzü"),
    ("12.05.2020'de", "on iki mayıs iki bin yirmide"),
    # units
    ("25°C", "yirmi beş santigrat derece"), ("5 km", "beş kilometre"), ("10kg", "on kilogram"), ("3 m²", "üç metrekare"),
    ("5 km'lik yol", "beş kilometrelik yol"), ("120 km/h", "yüz yirmi kilometre bölü saat"), ("8 GB", "sekiz gigabayt"),
    ("10x", "on kat"), ("64-bit", "altmış dört bit"), ("≈500", "yaklaşık beş yüz"),
    # abbreviations
    ("Dr. Ali geldi", "doktor Ali geldi"), ("Prof. Dr. Ayşe", "profesör doktor Ayşe"),
    ("elma, armut vb. meyveler", "elma, armut ve benzeri meyveler"), ("Hepsi vb. Sonra", "Hepsi ve benzeri. Sonra"),
    ("XV. yy. boyunca", "on beşinci yüzyıl boyunca"), ("örn. bu", "örneğin bu"), ("Av. Mehmet", "avukat Mehmet"),
    ("onu av. Sonra", "onu av. Sonra"),
    # listed terms and acronyms: expansions get the suffix rebuilt, word-like acronyms stay words
    ("C++", "si pılas pılas"), ("C++'ın", "si pılas pılas'ın"), ("C#", "si şarp"), ("iPhone", "ayfon"), ("YouTube", "yutub"),
    ("Wi-Fi", "vay fay"), ("NASA", "nasa"), ("NATO'nun", "nato'nun"), ("COBOL", "kobol"), ("COBOL'u", "kobol'u"),
    ("TBMM'nin", "Türkiye Büyük Millet Meclisi'nin"), ("TBMM'ye", "Türkiye Büyük Millet Meclisi'ne"),
    ("ABD'ye", "Amerika Birleşik Devletleri'ne"), ("BM'ye", "Birleşmiş Milletler'e"), ("ABD'de", "Amerika Birleşik Devletleri'nde"),
    ("BM'nin", "Birleşmiş Milletler'in"), ("Steve Jobs'un", "stiv cobs'un"), ("(NATO)", "(nato)"),
    ("Python 3.12", "paytın üç nokta on iki"), ("iPhone 15", "ayfon on beş"), ("GPT-2", "ci pi ti iki"),
    ("COVID-19", "kovid on dokuz"), ("CHP'nin", "ce he pe'nin"), ("3D", "üç de"),
    # exact-case keys leave the Turkish words alone
    ("ab ram dos basic", "ab ram dos basic"),
]


@pytest.mark.parametrize("src,want", SAY)
def test_spoken_table(src, want):
    assert S.spoken(src) == want


def test_a_full_sentence():
    got = S.spoken("II. Mehmed 1452–1481'de TBMM'nin %75'ini ve 1,5 milyon dolarlık C++ kodunu 3/4 oranında okudu.")
    assert got == ("ikinci Mehmed bin dört yüz elli iki ile bin dört yüz seksen birde Türkiye Büyük Millet Meclisi'nin "
                   "yüzde yetmiş beşini ve bir buçuk milyon dolarlık si pılas pılas kodunu dörtte üç oranında okudu.")


def test_punctuation_and_quotes_survive():
    assert S.spoken('"1990\'da", (%75) 3,14.') == '"bin dokuz yüz doksanda", (yüzde yetmiş beş) üç virgül on dört.'
    assert S.spoken("Yıl 1453. İstanbul fethedildi.") == "Yıl bin dört yüz elli üç. İstanbul fethedildi."   # not an ordinal


@pytest.mark.parametrize("text", ["Bkz. https://example.com/1990 ve www.site.com/2024", "mail a1990@site.com", "#2024 @ali",
                                  "bkz. kitap.com", "ASP.NET 4.8 sürümü"])
def test_urls_and_handles_are_left_alone(text):
    out = S.spoken(text)
    for tok in text.split():
        if "/" in tok or "@" in tok or tok.startswith("#") or tok == "kitap.com":
            assert tok in out.split()


@pytest.mark.parametrize("text", ["In 1990 the C++ team spent $5 on 3 laptops, 75% of NASA's budget.", "II. Mehmed", "",
                                  "Hello world. It's 10:30."])
def test_english_is_untouched(text):
    assert S.spoken(text, "en") == text and S.spoken(text, "en-US") == text


def test_whitespace_and_identity_when_nothing_changes():
    t = "Bu bir  deneme\nmetni, hiç sayı yok."
    assert S.spoken(t) is t or S.spoken(t) == t           # same bytes: the TTS cache key does not move
    assert S.spoken("a  1990'da\nb") == "a  bin dokuz yüz doksanda\nb"        # the gaps between words stay


def test_english_gets_only_the_overrides():
    assert S.spoken("The iPhone costs $5", "en", {"iPhone": "eye phone"}) == "The eye phone costs $5"


def test_version_vs_decimal_context():
    assert S.spoken("Bunu 3.5 kat artırdı") == "Bunu üç buçuk kat artırdı"                # a capital that starts a sentence
    assert S.spoken("sürüm 2.1 çıktı") == "sürüm iki nokta bir çıktı"
    assert S.spoken("Toplam 1.2.3 sürümü") == "Toplam bir nokta iki nokta üç sürümü"


def test_say_integer_edges():
    assert S.say_integer("0") == "sıfır" and S.say_integer("1001") == "bin bir" and S.say_integer("1" + "0" * 22).count("sıfır") == 22
    assert S.ordinal("dört") == "dördüncü" and S.ordinal("yirmi bir") == "yirmi birinci" and S.ordinal("üç") == "üçüncü"
    assert S.roman_value("XIV") == 14 and S.roman_value("IIII") is None and S.roman_value("C") is None


# ---------------------------------------------------------------- the lexicon
def test_builtin_lexicon_size_and_sources():
    terms = S.builtin_terms("tr")
    assert 100 <= len(terms) <= 260
    assert terms["C++"] == "si pılas pılas" and terms["iPhone"] == "ayfon" and terms["YouTube"] == "yutub"
    assert S.builtin_terms("en") == {}


def test_override_precedence_project_over_series_over_builtin():
    assert S.spoken("YouTube'da") == "yutub'da"
    series = {"YouTube": "yu tüp", "Mars": "mars bir"}
    project = {"youtube": "yutuub", "Venüs": "venus"}                     # same term, any case: the project wins
    pron = S.merge(series, project)
    assert S.spoken("YouTube'da Mars ve Venüs", "tr", S.merge(series)) == "yu tüp'da mars bir ve Venüs"
    assert S.spoken("YouTube'da Mars ve Venüs", "tr", pron) == "yutuub'da mars bir ve venus"
    assert S.terms_for("tr", pron)["youtube"] == "yutuub" and "YouTube" not in S.terms_for("tr", pron)


def test_overrides_from_project_and_series(tmp_path):
    from factory import series
    from factory.hat import project as P
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    series.ensure(con)
    con.execute("INSERT INTO series (channel_id, title, status, data) VALUES ('c', 't', 'ready', '{}')")
    con.commit()
    assert series.set_pronunciations(con, 1, {"Pip": "pip", "": "x", "bad": ""}) == {"Pip": "pip"}
    d = str(tmp_path)
    pid = P.create("explainer", "t", d=d)["id"]
    assert P.set_pronunciations(pid, {"Pip": "pipi", "Gull": "gal"}, d) == {"Pip": "pipi", "Gull": "gal"}
    p = P.load(pid, d)
    assert S.overrides(p) == {"Pip": "pipi", "Gull": "gal"}
    assert S.overrides({**p, "series": {"id": 1, "episode": 1}}, con) == {"Pip": "pipi", "Gull": "gal"}
    assert S.overrides({"series": {"id": 1}, "pronunciations": {"Gull": "gal"}}, con) == {"Pip": "pip", "Gull": "gal"}
    assert S.overrides({"series": {"id": 999}}, con) == {}                # an unknown series is not an error


# ---------------------------------------------------------------- token mapping and captions
def test_plan_mapping_and_restore_words():
    text = "II. Mehmed 1990'da C++ yazdı"
    p = S.plan(text)
    assert p.mapping() == [("II.", "ikinci", "number"), ("1990'da", "bin dokuz yüz doksanda", "number"),
                           ("C++", "si pılas pılas", "term")]
    spoken = p.tokens()
    assert " ".join(spoken) == p.spoken == S.spoken(text)
    timed = [[t, i * 0.5, i * 0.5 + 0.4] for i, t in enumerate(spoken)]         # the TTS words with timings
    back = S.restore_words(timed, p)
    assert [w[0] for w in back] == text.split()
    by = dict((w[0], w[1:]) for w in back)
    assert by["II."] == [0.0, 0.4]                                              # one spoken word: its own time
    assert by["1990'da"] == [1.0, 2.9] and by["C++"] == [3.0, 4.4]              # the whole spoken range
    assert by["yazdı"] == [4.5, 4.9]


def test_restore_words_splits_a_multi_token_group_by_letters():
    p = S.plan("5 km yol")
    assert p.tokens() == ["beş", "kilometre", "yol"]
    back = S.restore_words([["beş", 0, 1], ["kilometre", 1, 2], ["yol", 2, 3]], p)
    assert back == [["5", 0, 1], ["km", 1, 2], ["yol", 2, 3]]
    p = S.plan("1452 – 1481 arası")           # 3 written tokens -> 9 spoken words
    spoken = p.tokens()
    back = S.restore_words([[t, i, i + 1] for i, t in enumerate(spoken)], p)
    assert [w[0] for w in back] == ["1452", "–", "1481", "arası"] or [w[0] for w in back][-1] == "arası"
    assert back[0][1] == 0 and back[-1][2] == len(spoken)
    assert all(a[2] <= b[1] + 1e-9 for a, b in zip(back, back[1:]))             # in order, no overlap


def test_spoken_lines_follow_the_joined_text():
    lines = ["1990'da başladı.", "II. Mehmed geldi.", "Hepsi bu."]
    assert S.spoken_lines(lines) == ["bin dokuz yüz doksanda başladı.", "ikinci Mehmed geldi.", "Hepsi bu."]


class _W:
    def __init__(self, word, start, end):
        self.word, self.start, self.end, self.probability = word, start, end, 0.9


def _fake_whisper(monkeypatch, step=0.5, say=None):
    """faster_whisper that 'hears' exactly the spoken text it was prompted with (or `say`), one word per `step` s."""
    heard = {}

    class Model:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, audio, language=None, word_timestamps=True, initial_prompt=None, **k):
            toks = (say if say is not None else (initial_prompt or "")).split()
            heard["prompt"] = initial_prompt
            words = [_W(" " + t, i * step, i * step + step * 0.8) for i, t in enumerate(toks)]
            return [types.SimpleNamespace(words=words)], None

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Model))
    from factory import productions
    monkeypatch.setattr(productions, "decode", lambda p: np.zeros(16000 * 12, np.float32))
    return heard


def test_align_words_matches_the_spoken_text_and_returns_the_written_tokens(monkeypatch):
    from factory import explainer
    heard = _fake_whisper(monkeypatch)
    lines = ["1990'da C++ öğrendi.", "II. Mehmed %75 dedi."]
    words = explainer.align_words("x.wav", lines, "tr")
    assert heard["prompt"] == S.spoken(" ".join(lines))                    # whisper is primed with the spoken text
    assert [w[0] for w in words] == " ".join(lines).split()               # ... and the caption words are the script's own
    t = {w[0]: (w[1], w[2]) for w in words}
    assert t["1990'da"] == (0.0, 1.9)                                      # 4 spoken words: 0 .. 3*0.5+0.4
    assert t["C++"] == (2.0, 3.4) and t["öğrendi."][0] == 3.5
    assert all(a[2] <= b[1] + 0.06 for a, b in zip(words, words[1:]))


def test_productions_align_hands_the_voicing_overrides_to_the_aligner(monkeypatch):
    from factory import explainer, productions
    seen = []
    monkeypatch.setattr(explainer, "align_words", lambda path, lines, lang="en", pron=None:
                        seen.append(pron) or [["a", 0.0, 0.5], ["b", 0.6, 1.0]])
    monkeypatch.setattr(productions, "decode", lambda p: np.zeros(16000 * 2, np.float32))
    productions.align("x.wav", ["a b"], "tr")
    with S.voicing("tr", {"Pip": "pipi"}):
        productions.align("x.wav", ["a b"], "tr")
    assert seen == [None, {"Pip": "pipi"}]


def test_align_words_english_is_what_it_was(monkeypatch):
    from factory import explainer
    _fake_whisper(monkeypatch)
    words = explainer.align_words("x.wav", ["It costs 5 dollars."], "en")
    assert [w[0] for w in words] == ["It", "costs", "5", "dollars."]


def test_captions_and_srt_show_the_original_spelling(monkeypatch):
    from factory import explainer
    _fake_whisper(monkeypatch)
    words = explainer.align_words("x.wav", ["1990'da TBMM'nin %75'i C++ olduğunu söyledi."], "tr")
    shown = " ".join(b["text"] for b in captions.blocks([tuple(w) for w in words], "9:16"))
    assert shown == "1990'da TBMM'nin %75'i C++ olduğunu söyledi."
    srt = export.srt(export.cues([tuple(w) for w in words]))
    for tok in ("1990'da", "TBMM'nin", "%75'i", "C++"):
        assert tok in srt
    assert "doksanda" not in srt and "yüzde" not in srt and "Millet" not in srt


def test_pretrim_compares_spoken_tokens():
    from factory import pretrim
    toks = S.plan("1990'da Pip geldi", "tr", {"Pip": "pipi"}).tokens()
    assert toks == ["bin", "dokuz", "yüz", "doksanda", "pipi", "geldi"]
    assert pretrim.extras(toks, [[t, i * .4, i * .4 + .3, .9] for i, t in enumerate(toks)], "tr") == []


# ---------------------------------------------------------------- the TTS hook and its cache key
@pytest.fixture
def gemini_voice(tmp_path, monkeypatch):
    from factory import accounts, credits, gemini, mediaprov
    f = tmp_path / "users.json"
    f.write_text(json.dumps({"secret": "x", "users": {"ali": {"name": "Ali", "role": "owner"}}}))
    monkeypatch.setattr(accounts, "USERS", str(f))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    accounts.set_gemini_key("ali", "AIza" + "w" * 35)
    mediaprov.set_settings("ali", {"voice": "gemini"})
    monkeypatch.setattr(eleven, "OUT", str(tmp_path / "assets"))
    monkeypatch.setattr(accounts, "eleven", lambda aid=None: {"type": "apikey", "key": "k", "owner": "ali", "shared": True})
    monkeypatch.setattr(accounts, "can_use", lambda aid=None, uid=None: True)
    con = sqlite3.connect(tmp_path / "t.db")
    con.row_factory = sqlite3.Row
    con.executescript(credits.SCHEMA)
    credits.ensure(con)
    asked = []
    monkeypatch.setattr(gemini, "tts", lambda text, voice="Kore", model=None, style=None: asked.append(text) or (b"WAV", "audio/wav", "i"))
    return con, asked


def test_tts_gets_the_spoken_text_once_and_the_key_follows_it(gemini_voice):
    con, asked = gemini_voice
    with S.voicing("tr"):
        p1, _ = eleven.tts(con, "1990'da C++ ve %75", "v")
        again, _ = eleven.tts(con, "1990'da C++ ve %75", "v")
    assert asked == ["bin dokuz yüz doksanda si pılas pılas ve yüzde yetmiş beş"]          # one call, spoken, cached after
    assert again == p1
    with S.voicing("tr", {"C++": "ce artı artı"}):                  # the project's own respelling: a NEW key, re-voiced
        p2, _ = eleven.tts(con, "1990'da C++ ve %75", "v")
    assert p2 != p1 and asked[-1] == "bin dokuz yüz doksanda ce artı artı ve yüzde yetmiş beş" and len(asked) == 2
    with S.voicing("en"):                                               # English: the text goes as written
        eleven.tts(con, "In 1990 the C++ team", "v")
    assert asked[-1] == "In 1990 the C++ team"
    import hashlib
    from factory import gemini
    key = "gtts_" + hashlib.sha1(f"{gemini.DEFAULT['voice']}|v|{asked[0]}".encode()).hexdigest()[:16]
    assert p1.endswith(key + ".wav")                                    # the cache key is the SPOKEN text


def test_unwrapped_calls_guess_the_language(gemini_voice):
    con, asked = gemini_voice
    eleven.tts(con, "Bu film 1990'da çekildi ve çok güzel", "v")
    eleven.tts(con, "The 1990 film was great", "v")
    assert asked == ["Bu film bin dokuz yüz doksanda çekildi ve çok güzel", "The 1990 film was great"]
    assert S.guess_lang("Merhaba dünya, bu çok güzel") == "tr" and S.guess_lang("Hello there, nice 1990") == "en"


def test_a_script_with_no_numbers_keeps_its_old_cache_key(gemini_voice):
    con, asked = gemini_voice
    with S.voicing("tr"):
        eleven.tts(con, "Merhaba dünya, nasılsın?", "v")
    assert asked == ["Merhaba dünya, nasılsın?"]


def test_narrate_sends_written_lines_and_hands_over_the_context(tmp_path, monkeypatch):
    from factory.hat import explainer as X, project as P
    d = str(tmp_path)
    pid = P.create("explainer", "t", video_lang="tr", d=d)["id"]
    P.set_pronunciations(pid, {"Pip": "pipi"}, d)
    seen = []
    monkeypatch.setattr(eleven, "tts", lambda con, text, vid, model, approved=None, account=None:
                        seen.append((text, S.current())) or ("a.mp3", 1.0))
    monkeypatch.setattr(X, "remaining_budget", lambda *a, **k: 100)
    X.narrate(pid, None, ["Pip 1990'da geldi."], "v", None, [], d)
    assert seen == [("Pip 1990'da geldi.", ("tr", {"Pip": "pipi"}))]
    assert S.current() is None                                          # the context never leaks


def test_voice_estimate_counts_spoken_characters():
    from factory import productions
    d = {"lang": "tr", "voice": {"lines": ["1990'da %75 oldu."]}}
    from factory import credits
    assert len(S.spoken("1990'da %75 oldu.")) > len("1990'da %75 oldu.")
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(credits.SCHEMA)
    credits.ensure(con)
    est = productions.voice_estimate(con, d)
    assert est["chars"] == len(S.spoken("1990'da %75 oldu."))


# ---------------------------------------------------------------- the click detector
SR = soundqa.SR


def _stem(spike_at=(3.0,)):
    t = np.arange(SR * 10) / SR
    y = np.zeros(len(t), np.float32)
    for a, b in ((1.0, 5.0), (6.5, 9.0)):                          # two voiced stretches, silence between
        m = (t >= a) & (t < b)
        y[m] = 0.3 * np.sin(2 * np.pi * 200 * t[m])
    for s in spike_at:
        y[int(s * SR)] += 0.6
    return y


def _review(monkeypatch, tmp_path, mix, stem, cuts=(), with_stem=True):
    arrays = {"mix.wav": mix, "stem.wav": stem}
    monkeypatch.setattr(soundqa, "decode", lambda p, sr=SR: arrays[str(p).split("/")[-1]])
    (tmp_path / "stem.wav").write_bytes(b"x")
    kw = {"voice_file": str(tmp_path / "stem.wav")} if with_stem else {}
    return soundqa.review("mix.wav", [], total=10, lufs=(-14.0, -3.0), cuts=cuts, **kw)


def _clicks(rep):
    return [f for f in rep["findings"] if f["kind"] == "clicks"]


def test_a_consonant_inside_the_voice_is_not_a_click(monkeypatch, tmp_path):
    stem = _stem((3.0,))                       # the raw TTS file has a hard burst inside a voiced word
    assert soundqa.click_times(stem, SR) == [3.0]
    assert _clicks(_review(monkeypatch, tmp_path, stem, stem, with_stem=False))        # the old detector: a "click"
    assert not _clicks(_review(monkeypatch, tmp_path, stem, stem))                    # now: it is the voice


def test_a_click_that_is_only_in_the_mix_is_still_reported(monkeypatch, tmp_path):
    stem = _stem((3.0,))
    mix = stem.copy()
    mix[int(5.7 * SR)] += 0.6                  # a splice in the silence between the two phrases: not in the stem
    rep = _review(monkeypatch, tmp_path, mix, stem)
    c = _clicks(rep)
    assert len(c) == 1 and "5.70s" in c[0]["detail"] and "3.00s" not in c[0]["detail"]


def test_a_mix_click_inside_speech_is_ignored_unless_it_is_an_edit_point(monkeypatch, tmp_path):
    stem = _stem(())
    mix = stem.copy()
    mix[int(8.0 * SR)] += 0.6                  # inside the voiced stretch, the stem has nothing there
    assert not _clicks(_review(monkeypatch, tmp_path, mix, stem))
    rep = _review(monkeypatch, tmp_path, mix, stem, cuts=[8.0])                      # ... but a cut sits there: flagged
    assert len(_clicks(rep)) == 1


def test_voice_offset_shifts_the_stem(monkeypatch, tmp_path):
    stem = _stem((3.0,))
    mix = np.concatenate([np.zeros(int(1.0 * SR), np.float32), stem])[:SR * 10]
    arrays = {"mix.wav": mix, "stem.wav": stem}
    monkeypatch.setattr(soundqa, "decode", lambda p, sr=SR: arrays[str(p).split("/")[-1]])
    (tmp_path / "stem.wav").write_bytes(b"x")
    rep = soundqa.review("mix.wav", [], total=10, lufs=(-14.0, -3.0), voice_file=str(tmp_path / "stem.wav"), voice_offset=1.0)
    assert not _clicks(rep)


# ---------------------------------------------------------------- the voice audit
def _take(amps, gap_in_line=None, rushed=None, slow=None):
    """A synthetic take: line k has 4 words; tone only inside words. Returns (y, words, lines)."""
    t = np.arange(SR * 40) / SR
    y = np.zeros(len(t), np.float32)
    words, lines, t0 = [], [], 0.5
    for k, amp in enumerate(amps):
        toks = ["Bu", "bir", "deneme", "cümlesidir"] if k % 2 else ["Burada", "başka", "söz", "var."]
        lines.append(" ".join(toks))
        step = 0.45 if rushed != k else 0.21
        if slow == k:
            step = 1.0
        for i, w in enumerate(toks):
            if gap_in_line == (k, i):
                t0 += 0.7
            a, b = t0, t0 + step * 0.9
            words.append([w, round(a, 3), round(b, 3)])
            m = (t >= a) & (t < b)
            y[m] = amp * np.sin(2 * np.pi * 180 * t[m])
            t0 += step
        t0 += 0.6
    return y, words, lines


def kinds(rep):
    return [f["kind"] for f in rep["findings"]]


def test_audit_clean_take_has_no_findings():
    y, words, lines = _take([0.2] * 6)
    rep = VA.audit(None, words, lines, "tr", y=y)
    assert rep["findings"] == [], rep["findings"]
    assert rep["metrics"]["clipped_runs"] == 0 and len(rep["metrics"]["line_db"]) == 6


def test_audit_inner_gap_level_jump_pace_and_clipping():
    y, words, lines = _take([0.2, 0.2, 0.2, 0.2, 0.9, 0.2, 0.2, 0.2], gap_in_line=(1, 2), rushed=6, slow=2)
    rep = VA.audit(None, words, lines, "tr", y=y)
    k = kinds(rep)
    assert "word_gap" in k and k.count("word_gap") == 1
    gap = next(f for f in rep["findings"] if f["kind"] == "word_gap")
    assert "'bir' and 'deneme'" in gap["detail"] or "'deneme'" in gap["detail"]
    jumps = [f for f in rep["findings"] if f["kind"] == "level_jump"]
    assert len(jumps) == 2 and jumps[0]["detail"].startswith("line 5 is +") and jumps[1]["detail"].startswith("line 6 is -")
    paces = {f["detail"].split()[1]: f["severity"] for f in rep["findings"] if f["kind"] == "pace"}
    assert paces.get("7") == "warn" and paces.get("3") == "info"
    assert "clipped" not in k
    y2 = y.copy()
    y2[int(2.0 * SR):int(2.0 * SR) + 6] = 1.0
    assert "clipped" in kinds(VA.audit(None, words, lines, "tr", y=y2))


def test_audit_silent_word_window_and_missing_voice():
    y, words, lines = _take([0.2] * 4)
    a, b = words[5][1], words[5][2]
    y[int((a - 0.05) * SR):int((b + 0.6) * SR)] = 0                         # the aligner says a word is here; the stem is silent
    words[5][2] = a + 0.9
    f = [x for x in VA.audit(None, words, lines, "tr", y=y)["findings"] if x["kind"] == "word_silent"]
    assert f and f[0]["detail"].startswith(f"'{words[5][0]}'")
    assert kinds(VA.audit(None, words, lines, "tr", y=np.zeros(SR, np.float32))) == ["voice_silent"]


def test_audit_pace_uses_the_spoken_length():
    # "1990" is 4 written characters but 22 spoken ones: a line of numbers read at a normal speed is not "slow"
    lines = ["1990'da 2024'te başladı bitti", "Bu bir deneme cümlesidir tamam", "Burada başka söz var dedi",
             "Her şey çok güzel gitti sonra", "Sonunda hepsi yerine oturdu artık"]
    words, y, t0 = [], np.zeros(SR * 40, np.float32), 0.5
    sp = S.spoken_lines(lines)
    for ln, spoken in zip(lines, sp):
        toks = ln.split()
        dur = len(spoken.replace(" ", "")) / 12.0                              # 12 spoken characters per second
        w = dur / len(toks)
        for tk in toks:
            words.append([tk, round(t0, 3), round(t0 + w * 0.9, 3)])
            t0 += w
        t0 += 0.5
    rep = VA.audit(None, words, lines, "tr", y=np.where(np.arange(len(y)) % 40 < 20, 0.1, -0.1).astype(np.float32))
    assert not [f for f in rep["findings"] if f["kind"] == "pace"], rep["findings"]
    assert 11 < rep["metrics"]["chars_per_s"] < 13


def test_audit_misreads_against_the_expected_spoken_text():
    lines = ["Ali 1990'da kitabı okudu ve eve gitti."]
    plan = S.plan(lines[0])
    exp = plan.tokens()
    assert exp[:5] == ["Ali", "bin", "dokuz", "yüz", "doksanda"]
    heard = [[t, i * .4, i * .4 + .3, 0.9] for i, t in enumerate(exp)]
    heard[0][3] = 0.2                                                       # low confidence on a plain word
    heard[5] = ["yedi", heard[5][1], heard[5][2], 0.9]                      # kitabı -> yedi
    heard[4] = ["1990'da", heard[4][1], heard[4][2], 0.9]                   # digits for a number: fine
    found, share = VA.misreads(plan, heard)
    msgs = [f["detail"] for f in found]
    assert any("expected 'kitabı', heard 'yedi'" in m for m in msgs)
    assert any("'Ali' heard with low confidence" in m for m in msgs)
    assert not any("doksanda" in m or "1990" in m for m in msgs)
    assert share > 0.7
    # a drifted whisper pass is not trusted
    found, share = VA.misreads(plan, [["tamamen", 0, 1, .9], ["başka", 1, 2, .9]])
    assert len(found) == 1 and "not reliable" in found[0]["detail"]
    # respelled foreign names are not misreads (whisper spells them its own way)
    p2 = S.plan("C++ ve Python güzel dil")
    assert VA.misreads(p2, [[t, i, i + .5, .9] for i, t in enumerate("ci plas plas ve payton güzel dil".split())])[0] == []


def test_audit_through_the_whole_call_and_text():
    y, words, lines = _take([0.2, 0.2, 0.2, 0.9], gap_in_line=(1, 1))
    heard = [[w[0], w[1], w[2], 0.9] for w in words]
    rep = VA.audit(None, words, lines, "tr", heard=heard, y=y)
    assert rep["metrics"]["heard_match"] == 1.0 and "word_gap" in kinds(rep)
    assert any("word_gap" in line for line in soundqa.as_text(rep))
