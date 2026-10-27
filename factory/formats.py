"""Video formats ("flows") the factory can produce: what each one is, how it is cut and what it needs.

There are really two pipelines, and the Studio shows them as two MODES:
  footage  the creator's own clips -> idea (productions.generate) -> art direction -> cinecut / stylecut
  topic    no footage, only a topic -> research + script (explainer.generate) -> motion graphics (explainer / html)
Inside a mode a format is only a preset ("tarz"): a short guide for the idea prompt plus duration, voice and series
flags. Formats that said almost the same thing were merged; their ids stay valid for old productions (status "merged",
`merged_into` names the preset that took them over) but are no longer offered.

`ready` formats run end to end in the Studio (idea -> voice -> preview -> render -> QA -> publish tracking).
`planned` formats are shown in the Studio so the line-up is visible, but cannot be generated yet.
Style "calm" = cinematic-calm cut (held shots, hard cuts, own sound, 1-2 plain lines per shot).
Style "story" = the creator's cloned voice tells one story; burned-in captions are the spoken phrases.
"""

VOICE_ID = "vhP2LOWrrIsWMq4m2vP6"  # the creator's cloned ElevenLabs voice "Ali"
VOICE_MODEL = "eleven_v4"
# output canvases: vertical for TikTok / Shorts / Reels, horizontal for regular YouTube videos
ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
MODES = {
    "footage": {"name_tr": "Çekimli", "icon": "🎞",
                "desc_tr": "Kendi çekimlerinden video: Claude fikri ve klipleri seçer, art director kurguyu ve efektleri tasarlar."},
    "topic": {"name_tr": "Çekimsiz", "icon": "✍️",
              "desc_tr": "Sadece bir konu: Claude araştırır, kaynaklı metni yazar; senin sesin okur, sahneler kodla çizilir."},
    "series": {"name_tr": "Seri", "icon": "📚",
               "desc_tr": "Bir hikâye dünyası: Claude önce mini kitabı ve karakterleri yazar, sonra bölüm bölüm aynı "
                          "karakterlerle çizimli videolar üretilir (çizgi film ya da dizi havasında)."},
}

FORMATS = [
    {"id": "unreal_places", "name": "Places That Don't Look Real", "name_tr": "Gerçek dışı görünen yerler",
     "status": "ready", "style": "calm", "source": "footage", "voice": False, "duration": [15, 30],
     "series": True, "platforms": ["tiktok", "youtube", "instagram"],
     "desc_tr": "Numaralı seri (Part N). Her yer tek bir uzun çekim + küçük konum yazısı. Radar'da küçük kanallarda "
                "1-6 M izlenme alan format.",
     "guide": "Numbered series 'Places that don't look real – Part N'. 4-6 places, ONE held shot each (2.5-5 s), the "
              "most surreal-looking frames first. Shot text = the place name and country only (e.g. 'Eibsee, "
              "Germany'). The first shot's text is two lines: 'Places that don't look real · Part N\\N<Place>, "
              "<Country>'. No voice."},
    {"id": "this_looks_unreal", "name": "This X Looks Unreal", "name_tr": "Bu X gerçek dışı",
     "status": "merged", "merged_into": "cinematic_calm", "style": "calm", "source": "footage", "voice": False,
     "duration": [10, 20],
     "series": False, "platforms": ["tiktok", "youtube", "instagram"],
     "desc_tr": "Tek bir yer, 3-5 uzun çekim. 'This lake looks unreal' tarzı tek satırlık hook.",
     "guide": "One single place. Hook line like 'This lake in Germany looks unreal' on the first shot (frame 0). "
              "3-5 held shots of the same place that prove the hook, last shot gives the location."},
    {"id": "cinematic_calm", "name": "Cinematic calm", "name_tr": "Sinematik",
     "status": "ready", "style": "calm", "source": "footage", "voice": False, "duration": [10, 35],
     "series": False, "platforms": ["tiktok", "youtube", "instagram"],
     "desc_tr": "Bir gün ya da tek bir yer: uzun tutulan çekimler, doğal ses, 1-2 sade satır. Tek bir çarpıcı yerse "
                "'This lake looks unreal' tarzı hook ile açar (eski 'Bu X gerçek dışı' formatı burada).",
     "guide": "One day or one place told calmly through its own sound. 5-8 held shots (2.5-6 s), 1-2 plain lines "
              "in the whole video plus the end location line. Let the footage breathe. When the video is about ONE "
              "striking place, open with a one-line hook like 'This lake in Germany looks unreal' on the first shot "
              "(frame 0), let 3-5 held shots of that place prove it, and give the location on the last shot."},
    {"id": "story_vo", "name": "Story (own voice)", "name_tr": "Hikâye (kendi sesin)",
     "status": "ready", "style": "story", "source": "footage", "voice": True, "duration": [20, 50],
     "series": False, "platforms": ["tiktok", "youtube", "instagram"],
     "desc_tr": "Senin klon sesin tek bir hikâye anlatır; altyazı = konuşulan cümleler, kesmeler cümle sonlarında. "
                "Klipler tek bir günü kapsıyorsa 'Day N in …' gün vlogu olur (eski 'Gün gün vlog' burada).",
     "guide": "First-person story in the creator's own voice, one concrete arc (setup -> turn -> payoff), facts "
              "taken from clip metadata (times, places). 5-9 spoken lines, each a short phrase. Shots cut on line "
              "starts. Ends on the place with a location line. When the clips cover one day in order (or the brief "
              "asks for a day vlog), make it a day-numbered vlog ('Day N in <region>') that follows the real capture "
              "times; the lines then name the moments plainly (time, place, what happened)."},
    {"id": "day_vlog", "name": "Day N vlog", "name_tr": "Gün gün vlog",
     "status": "merged", "merged_into": "story_vo", "style": "story", "source": "footage", "voice": True,
     "duration": [25, 50],
     "series": True, "platforms": ["tiktok", "youtube", "instagram"],
     "desc_tr": "'Day 1 in the Alps' gibi gün numaralı seri; çekim saatlerine göre sıralı, senin sesinle.",
     "guide": "Day-numbered vlog ('Day N in <region>') following the real capture times of one day in order. "
              "Voice lines name the moments plainly (time, place, what happened)."},
    {"id": "travel_facts", "name": "Travel facts (sourced)", "name_tr": "Seyahat bilgileri (kaynaklı)",
     "status": "ready", "style": "story", "source": "footage", "voice": True, "duration": [15, 35],
     "series": False, "platforms": ["tiktok", "youtube", "instagram"],
     "desc_tr": "Çektiğin yer hakkında 2-3 doğrulanmış bilgi. Her iddia render'dan önce kaynakla kontrol edilir.",
     "guide": "2-3 surprising but verifiable facts about a filmed place, each shown over footage of that place. "
              "Every fact goes into claims; no fact without a picture of it."},
    {"id": "long_compilation", "name": "Long compilation (>1 min)", "name_tr": "Uzun derleme (>1 dk)",
     "status": "ready", "style": "calm", "source": "footage", "voice": False, "duration": [61, 120],
     "series": False, "platforms": ["tiktok", "youtube"],
     "desc_tr": "TikTok Creator Rewards için 1 dakikanın üstünde derleme (ör. bir bölgenin en iyi yerleri).",
     "guide": "Compilation over 61 s (TikTok Creator Rewards pays only for >1 min). 12-20 held shots grouped by "
              "place, each place introduced by a plain location line. Strong first shot."},
    {"id": "explainer_short", "name": "Faceless explainer short", "name_tr": "Konu anlatımı (çekimsiz)",
     "status": "ready", "style": "story", "source": "topic", "voice": True, "duration": [28, 36],
     "series": False, "platforms": ["tiktok", "youtube", "instagram"],
     "desc_tr": "Bir konu ver: Claude araştırır, kaynaklı ~30 sn metin yazar; senin sesin okur; kodla çizilmiş motion "
                "grafik + kinetik altyazı ile 9:16 video olur. Çekim gerekmez.",
     "guide": "Topic -> researched, sourced script (75-85 words) -> cloned voice -> code-rendered motion graphics."},
    {"id": "facts_listicle", "name": "Facts listicle", "name_tr": "Bilgi listesi (3 bilgi)",
     "status": "ready", "style": "story", "source": "topic", "voice": True, "duration": [22, 40],
     "series": False, "platforms": ["tiktok", "youtube", "instagram"],
     "desc_tr": "Bir konu hakkında 3 şaşırtıcı, kaynaklı bilgi: her bilgi ayrı sahne (1/3, 2/3, 3/3), açık lisanslı "
                "görsel ya da kendi çekimin arkada, senin sesin okur.",
     "guide": "STRUCTURE OVERRIDE (replaces the hook/beat plan of SCRIPT): a numbered listicle of exactly 3 surprising, "
              "sourced facts about the topic. Hook (1 sentence) promises the three ('Three things about X nobody tells "
              "you'); then one scene per fact, each opening with a label element '1/3', '2/3', '3/3' and one big visual "
              "(stat_card, counter, hero or title) for the fact's key number or word, with a source element; strongest "
              "fact last; CTA scene last. 70-85 words, one sentence per idea."},
    {"id": "series_episode", "name": "Story series episode", "name_tr": "Seri bölümü",
     "status": "ready", "style": "story", "source": "series", "voice": True, "duration": [30, 90],
     "series": True, "platforms": ["tiktok", "youtube", "instagram"],
     "desc_tr": "Bir serinin bölümü: anlatıcı + karakter sesleri, her sahne serinin kilitli çizim stilinde, aynı "
                "karakterlerle; Opus çizimleri kamera hareketleri ve işaretlerle canlandırır.",
     "guide": "One episode of an illustrated story series (see the series bible)."},
    {"id": "avatar_news", "name": "Avatar news / explainer", "name_tr": "Avatar ile haber",
     "status": "planned", "style": "story", "source": "avatar", "voice": True, "duration": [45, 60],
     "series": False, "platforms": ["tiktok", "youtube"],
     "desc_tr": "Konuşan avatar + klon ses. Fiyat testi ve fotoğrafların gerekiyor; AI etiketi zorunlu.",
     "guide": ""},
]

BY_ID = {f["id"]: f for f in FORMATS}
for _f in FORMATS:
    _f["mode"] = _f["source"] if _f["source"] in ("footage", "series") else "topic"   # avatar videos are topic-first too


def offered(mode=None):
    """Presets the Studio offers (ready or planned, not merged), optionally for one mode."""
    return [f for f in FORMATS if f["status"] != "merged" and (mode is None or f["mode"] == mode)]


def canonical(fid):
    """The preset a (possibly merged) format id lives on in."""
    f = BY_ID.get(fid)
    return f.get("merged_into", fid) if f else fid


def for_data(fid, data):
    """The format as this production uses it: a silent format with a narration layer (data.narrate) behaves like a
    spoken one (voice step, captions = spoken lines, cuts on line starts)."""
    f = get(fid)
    if (data or {}).get("narrate") and not f["voice"]:
        f = dict(f, voice=True, style="story")
    return f


def get(fid):
    f = BY_ID.get(fid)
    if not f:
        raise ValueError(f"unknown format {fid!r}")
    return f
