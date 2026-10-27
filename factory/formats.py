"""Video formats ("flows") the factory can produce: what each one is, how it is cut and what it needs.

`ready` formats run end to end in the Studio (idea -> voice -> preview -> render -> QA -> publish tracking).
`planned` formats are shown in the Studio so the line-up is visible, but cannot be generated yet.
Style "calm" = cinematic-calm cut (held shots, hard cuts, own sound, 1-2 plain lines per shot).
Style "story" = the creator's cloned voice tells one story; burned-in captions are the spoken phrases.
"""

VOICE_ID = "vhP2LOWrrIsWMq4m2vP6"  # the creator's cloned ElevenLabs voice "Ali"
VOICE_MODEL = "eleven_v4"
# output canvases: vertical for TikTok / Shorts / Reels, horizontal for regular YouTube videos
ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}

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
     "status": "ready", "style": "calm", "source": "footage", "voice": False, "duration": [10, 20],
     "series": False, "platforms": ["tiktok", "youtube", "instagram"],
     "desc_tr": "Tek bir yer, 3-5 uzun çekim. 'This lake looks unreal' tarzı tek satırlık hook.",
     "guide": "One single place. Hook line like 'This lake in Germany looks unreal' on the first shot (frame 0). "
              "3-5 held shots of the same place that prove the hook, last shot gives the location."},
    {"id": "cinematic_calm", "name": "Cinematic calm", "name_tr": "Sinematik sakin",
     "status": "ready", "style": "calm", "source": "footage", "voice": False, "duration": [15, 35],
     "series": False, "platforms": ["tiktok", "youtube", "instagram"],
     "desc_tr": "Bir gün / bir yer. Uzun tutulan çekimler, doğal ses, 1-2 sade satır (101 Como örneği).",
     "guide": "One day or one place told calmly through its own sound. 5-8 held shots (2.5-6 s), 1-2 plain lines "
              "in the whole video plus the end location line. Let the footage breathe."},
    {"id": "story_vo", "name": "Story (own voice)", "name_tr": "Hikâye (kendi sesin)",
     "status": "ready", "style": "story", "source": "footage", "voice": True, "duration": [20, 45],
     "series": False, "platforms": ["tiktok", "youtube", "instagram"],
     "desc_tr": "Senin klon sesin tek bir hikâye anlatır; altyazı = konuşulan cümleler, kesmeler cümle sonlarında "
                "(102 Eibsee, 103 Partnach örnekleri).",
     "guide": "First-person story in the creator's own voice, one concrete arc (setup -> turn -> payoff), facts "
              "taken from clip metadata (times, places). 5-9 spoken lines, each a short phrase. Shots cut on line "
              "starts. Ends on the place with a location line."},
    {"id": "day_vlog", "name": "Day N vlog", "name_tr": "Gün gün vlog",
     "status": "ready", "style": "story", "source": "footage", "voice": True, "duration": [25, 50],
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
    {"id": "facts_listicle", "name": "Facts listicle", "name_tr": "Bilgi listesi (3 facts)",
     "status": "planned", "style": "story", "source": "topic", "voice": True, "duration": [20, 40],
     "series": True, "platforms": ["tiktok", "youtube", "instagram"],
     "desc_tr": "Stok görüntü + sade tipografi + senin sesin. Konu modunun ardından gelecek.",
     "guide": ""},
    {"id": "avatar_news", "name": "Avatar news / explainer", "name_tr": "Avatar ile haber",
     "status": "planned", "style": "story", "source": "avatar", "voice": True, "duration": [45, 60],
     "series": False, "platforms": ["tiktok", "youtube"],
     "desc_tr": "Konuşan avatar + klon ses. Fiyat testi ve fotoğrafların gerekiyor; AI etiketi zorunlu.",
     "guide": ""},
]

BY_ID = {f["id"]: f for f in FORMATS}


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
