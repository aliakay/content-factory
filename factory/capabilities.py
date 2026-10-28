"""The studio's technique catalogue: everything the factory can DO, as small parts the planner (producer + art director)
combines freely for each request, instead of fixed named formats.

A technique is a piece of craft, not a genre: "a second-person rules arc", "characters drawn in code", "one sound for every
visible action", "cut the music when the power dies", "shorten only the real silences", "rebuild the app's screens in
code", "jump-cut a talking head". The planner reads the catalogue (`catalogue()`), writes an art direction and picks the
techniques that serve THIS idea (`recipe`); every stage then reads the same recipe:

  writer      writer_notes(d)    structure, length, hook options, what extra fields to fill (clock, caption colours, ...)
  designer    designer_notes(d)  visual language + which FX kit parts to use (factory/motiondesign.py, fxlib.js)
  sound/voice apply(recipe, d)   data switches the renderers read: voice_fx, captions, sound, music automation, fps
  editor      talk.py            talking-head editing techniques (cut, reframe, punch-ins, B-roll, captions, voice chain)

The parts were distilled from shared workflows (stickman horror story, explainer reel, 30 s product ad, talking-head ad)
and generalised so any of them can serve any topic.
"""

import json, os

from .config import ROOT

AREAS = {"story": "Hikâye yapısı", "style": "Film stili", "look": "Görsel teknik", "sound": "Ses tasarımı",
         "voice": "Ses kaydı", "captions": "Altyazı", "edit": "Kurgu (kendi çekimin)", "check": "Kontrol"}

# id: area, tr (label), what (planner), kinds (where it applies), writer / designer notes, data (fields it pins),
#     shape (story arc: one per video), fiction, words / seconds (length it implies)
CAPS = {
    # ---------- story structure (shapes: at most one per video) ----------
    "story.rules_arc": {
        "area": "story", "tr": "Kurallar + seçim arkı", "shape": True, "fiction": True, "words": [200, 245],
        "seconds": [78, 98], "kinds": ("topic",),
        "what": "Second-person survival story ('Imagine you...'): official warning, a list of RULES, a rule tested, quiet "
                "then dark, someone asks to come in, the last rule says NEVER, something worse behind them, ends on a "
                "direct choice question + 'follow for part 2'. Built for comments and series.",
        "writer": "STORY SHAPE (fiction; replaces the explainer's hook/beat plan): second person ('Imagine you...'), short "
                  "sentences, one sentence per line. In order: (1) hook that puts the viewer inside the setting with "
                  "something already wrong; (2) an official warning (phone alert, radio, siren); (3) a list of RULES is "
                  "found; (4) rules 1-3, each its own scene with ONE visible action; (5) something creepy tests a rule "
                  "and the viewer obeys; (6) quiet, then the power dies; (7) someone who seems safe asks to come in, then "
                  "one clue they might be lying; (8) the last rule says NEVER; (9) something worse appears behind them; "
                  "(10) end on 'So... do you <ACTION>?' and 'Follow for <part> 2'. Leave ONE mystery open. Scenes 8-14 "
                  "(a rule = a scene).",
        "designer": "Each rule gets FX.rule; the power cut is FX.lightsOut (music cuts with it); the end is FX.choice then "
                    "FX.flipCard to the next part.",
        "data": {"captions": {"mode": "word", "pos": "mid"}},
    },
    "story.problem_fix": {
        "area": "story", "tr": "Dert -> çözüm (reklam arkı)", "shape": True, "words": [58, 75], "seconds": [26, 36],
        "kinds": ("topic",),
        "what": "Direct-response arc for a product / service / offer: the customer's concrete problem in 3 s, the old way "
                "and why it fails (one negation per line), the product as the fix, one proof line, CTA with the name.",
        "writer": "STORY SHAPE (replaces the explainer's hook/beat plan): hook in the first 3 s = the customer's concrete "
                  "problem; the old way and why it fails ('No hunting, no fake codes...' style, one negation per line); "
                  "the product as the fix (what you tap, what you get); one proof line; CTA with the product name. Claims "
                  "ONLY from the creator's brief or the product's own page; prices / rates not given stay placeholders "
                  "('Nxx,xxx'); facts[].source may be 'creator brief'. Set sound.drop_line to the reveal line.",
        "designer": "The old way is shown as UI that gets FX.slash + FX.shatter on each negation; the product's screens are "
                    "rebuilt in FX.phone; the logo lands at the end with FX.sfx('logo_hit').",
    },
    "story.numbered_twist": {
        "area": "story", "tr": "Numaralı liste + twist", "shape": True, "words": [110, 145], "seconds": [40, 60],
        "kinds": ("topic",),
        "what": "Numbered list with a number hook ('These 7 repos...'), a twist line that keeps people watching ('Number 7 "
                "made this video'), one name + one short line per item, CTA 'Comment KEYWORD and I'll send you...'.",
        "writer": "STORY SHAPE (replaces the explainer's hook/beat plan): (1) number hook; (2) a twist line that makes "
                  "them stay; (3) the items in order: a name, then ONE short line each (researched, sourced); (4) CTA: "
                  "'Comment <KEYWORD> and I'll send you <the list>'. Acronyms written as words for the voice (HTML, not "
                  "H T M L). One scene per item (label '#n' + the name) plus hook and CTA scenes.",
        "designer": "A big '#n' badge per item; one animated card per item that shows what it does (app window, terminal, "
                    "checklist, phone).",
    },
    "story.beat_film": {
        "area": "story", "tr": "Beat'te kinetik tanıtım filmi", "shape": True, "words": [40, 95], "seconds": [15, 50],
        "kinds": ("topic",),
        "what": "A launch film / teaser / promo in kinetic type on a fast beat (the viral motion-design reel): huge words on "
                "every beat, one claim per phrase, a turn every 3-4 phrases (a denial, a gag, a number, a reveal), the "
                "biggest visual change on the music's drop, ends on the name and holds. Music-led energy, the voice short "
                "and punchy.",
        "writer": "STORY SHAPE (replaces the explainer's hook/beat plan): write it as a short spoken script cut into "
                  "phrases of 2-8 words, ONE claim each, concrete nouns and verbs (THEY STOMP., not AMAZING VISUALS); a "
                  "turn every 3-4 phrases: a denial ('No timeline. No plugins.'), a gag, a number, a reveal; the last "
                  "line is the name. Numbers only from the brief or a source. Write sound.music_prompt: an instrumental "
                  "at 160-175 BPM for a teaser (120-128 for a calm brand film), 'eight bars of build, then a huge drop, "
                  "punchy kick on every downbeat, ends on one hard final hit, no vocals'; set sound.drop_line to the turn "
                  "line. Every scene hide_captions: true (the type on screen IS the words).",
        "designer": "Build on the beat: FX.B(k) is beat k (beat 0 = the drop). One idea per beat or half beat with "
                    "FX.kinetic (slam / punch3d / stack / split / pair / cut), the ground flipping colour on phrase "
                    "changes, FX.cutRun for runs of denials, FX.charge before the first hit, the drop = the biggest change.",
        "data": {"motion_blur": 4, "post_fx": {"bloom": 0.35, "grain": 0.25}},
    },
    "story.hook_options": {
        "area": "story", "tr": "3 hook seçeneği", "kinds": ("topic", "talk"),
        "what": "Write 3 clearly different hooks; the creator picks one before voice credits are spent.",
        "writer": "Give 3 clearly different hook_options (the first is the one used in the script).",
    },
    "story.part_hook": {
        "area": "story", "tr": "Part 2 kancası", "kinds": ("topic",),
        "what": "End on an open mystery and a 'follow for part 2' line; the next part continues with the same characters, "
                "voice and look (Studio: 'Devamını üret').",
        "writer": "Leave one mystery unanswered and end with 'Follow for part 2' (in the video's language).",
    },
    # ---------- visual techniques (motion designer, code-drawn) ----------
    "look.code_characters": {
        "area": "look", "tr": "Kodla çizilen karakterler", "kinds": ("topic",),
        "what": "People and props drawn in code (round-headed stickman rig with poses, walking, waving, knocking; flat "
                "vector sets) instead of photos or AI images: free, consistent across parts, fully animatable.",
        "designer": "Draw every person with FX.stickman (poses via FX.pose, man.walk, FX.wave, man.mouth) and every place "
                    "with flat SVG shapes. Characters stay inside their set (behind windows, inside doors). Each scene = "
                    "a slow camera push + ONE clear action.",
    },
    "look.story_hud": {
        "area": "look", "tr": "Saat / yer HUD'u", "kinds": ("topic",),
        "what": "A small clock in the corner (NIGHT 1 · 2:17 AM · place) that jumps forward as the story goes.",
        "writer": "Fill hud = {label: 'NIGHT 1', place: '<short place>', times: ['2:17 AM', ...one per scene, jumping "
                  "forward]}.",
        "designer": "FX.hud(root, {label, place, times: [[scene start, time], ...]}) in every scene, same position.",
    },
    "look.night_palette": {
        "area": "look", "tr": "Gece paleti, tek uyarı rengi", "kinds": ("topic",),
        "what": "Dark night palette with ONE warning colour (red) used only for danger.",
        "designer": "Dark night palette; red is the ONLY warning colour and appears only on danger (rules, blood, NEVER).",
    },
    "look.ui_rebuild": {
        "area": "look", "tr": "Uygulama ekranlarını kodla kur", "kinds": ("topic",),
        "what": "Rebuild app / website screens in code inside a phone frame (cards, lists, buttons, amounts) with taps on "
                "every interaction, so they animate and stay sharp. Screenshots are references only.",
        "designer": "Build the product's screens inside FX.phone(...).screen as real-looking UI (cards, lists, buttons, "
                    "amounts); every interaction gets FX.tap; notifications use FX.alert.",
    },
    "look.kinetic_headline": {
        "area": "look", "tr": "Konuşulan başlık (kelime kelime)", "kinds": ("topic",),
        "what": "The headline at the top IS the spoken sentence, each word appearing exactly when it is said; one keyword "
                "per sentence in an accent italic serif; below it one card per sentence showing what the voice says.",
        "designer": "Headline at the top = the spoken sentence; every word fades up at T.at(word); one keyword per "
                    "sentence in the accent colour, italic serif (Instrument Serif); below it one animated card per "
                    "sentence (app window, checklist, phone, counter). Text inside the middle 80 % of the frame.",
    },
    "look.paper_dots": {
        "area": "look", "tr": "Sıcak kâğıt + nokta doku", "kinds": ("topic",),
        "what": "Warm paper ground with a faint dot texture, dark ink, one red/orange accent.",
        "designer": "Warm paper background (#efe9df-ish) with a faint dot grid texture, near-black ink, ONE accent colour.",
    },
    "look.break_the_old": {
        "area": "look", "tr": "Eskiyi kes / kır", "kinds": ("topic",),
        "what": "What the video argues against (the old way, a fake card, a bad search) gets slashed and shattered on its "
                "word, with matching swish and glass sounds.",
        "designer": "Show the old way as a real object, then FX.slash + FX.shatter it on the negation word.",
    },
    "look.choice_ending": {
        "area": "look", "tr": "Seçim kartıyla bitiş", "kinds": ("topic",),
        "what": "End card with the question and two answer buttons + 'comment below' (drives comments), optionally a card "
                "that flips to the next part.",
        "designer": "Last scene: FX.choice({q, a, b}); for a series also FX.flipCard('PART 1', 'PART 2').",
    },
    "look.logo_end": {
        "area": "look", "tr": "Logo vuruşu", "kinds": ("topic",),
        "what": "Logo / product lands at the end on a hit (brand logo of the channel is burned in by the brand pass).",
        "designer": "Final beat: the product name / logo lands with FX.sfx('logo_hit') and holds 1 s.",
    },
    # ---------- sound ----------
    "sound.event_sfx": {
        "area": "sound", "tr": "Her harekete bir ses", "kinds": ("topic", "talk"),
        "what": "One synthesised sound for every visible action (knock, light clunk, flip, tap, glass, impact, logo hit, "
                "whoosh on zooms, pop on highlights), timed to the frame and kept off the words.",
        "designer": "Declare FX.sfx(kind, at) next to every visible action (see SOUND DESIGN).",
        "data": {"sound": {"sfx": True, "level": "full"}},
    },
    "sound.music_automation": {
        "area": "sound", "tr": "Müziği olayda kes / geri getir", "kinds": ("topic",),
        "what": "Music cuts out on a story event (the power dies) and comes back on another (the knock); silence as a tool.",
        "writer": "Set sound.cut_line / sound.back_line to the line indexes where the music cuts out and comes back.",
        "designer": "FX.music('cut', at) / FX.music('back', at) on the events (FX.lightsOut cuts it automatically).",
    },
    "sound.drop_on_key": {
        "area": "sound", "tr": "Drop anahtar cümlede", "kinds": ("topic", "talk"),
        "what": "Measure the track's drop and start the music so the drop lands on the key line / the reveal.",
        "writer": "Set sound.drop_line to the line index of the key line (the reveal).",
        "designer": "FX.music('drop', at) on the reveal.",
    },
    "sound.music_bed": {
        "area": "sound", "tr": "Müzik altlığı (ses altında)", "kinds": ("topic", "talk", "footage"),
        "what": "An instrumental track written for this video (ElevenLabs, credit approval), carved at 2.6 kHz and ducked "
                "under the voice.",
        "writer": "Write sound.music_prompt: an instrumental brief for THIS video (instruments, mood, tempo, where it "
                  "builds / drops).",
    },
    # ---------- voice ----------
    "voice.tighten": {
        "area": "voice", "tr": "Sadece gerçek sessizlikleri kısalt", "kinds": ("topic", "talk"),
        "what": "Shorten only the real silences between words (measured), never chopping word endings.",
        "data": {"voice_fx": {"tighten": True}},
    },
    "voice.fit_length": {
        "area": "voice", "tr": "Uzun gelirse hafif hızlandır", "kinds": ("topic",),
        "what": "If the take runs past the target length, speed it up slightly (max 12 %, pitch kept).",
        "data": {"voice_fx": {"fit": True}},
    },
    "voice.tight_read": {
        "area": "voice", "tr": "Sıkı okuma (%4)", "kinds": ("topic",),
        "what": "A 4 % tighter read for ads and hooks (pitch kept).",
        "data": {"voice_fx": {"tempo": 1.04}},
    },
    "voice.deeper": {
        "area": "voice", "tr": "Bir yarım ton kalın", "kinds": ("topic",),
        "what": "Pitch the voice one semitone down for a deeper ad / narrator register (only when asked: it changes the "
                "creator's voice).",
        "data": {"voice_fx": {"pitch": -1}},
    },
    # ---------- captions ----------
    "captions.word_mid": {
        "area": "captions", "tr": "Ortada kelime kelime", "kinds": ("topic",),
        "what": "One big word at a time in the middle of the frame (story / horror register).",
        "data": {"captions": {"mode": "word", "pos": "mid"}},
    },
    "captions.color_roles": {
        "area": "captions", "tr": "Anahtar yeşil, tehlike kırmızı", "kinds": ("topic", "talk"),
        "what": "Caption colour roles: key words green (setting, key nouns), danger words red (blood, never, door).",
        "writer": "Fill cap_keys = {key: [4-10 words to colour as key words], danger: [4-10 words to colour red]}.",
    },
    # ---------- editing the creator's own talking video ----------
    "edit.jump_cuts": {
        "area": "edit", "tr": "Boşluk / ıı / tekrar kesme", "kinds": ("talk",),
        "what": "Transcribe, then fast jump cuts: every pause, filler word, breath, false start and repeated take removed; "
                "the story must still make sense; the strongest line first as the hook.",
    },
    "edit.face_reframe": {
        "area": "edit", "tr": "Yüz takipli 9:16 kadraj", "kinds": ("talk",),
        "what": "Keep the face centred when reframing to 9:16 (face track per cut; centre crop without a detector).",
    },
    "edit.punch_ins": {
        "area": "edit", "tr": "Vurgu zoom'ları (1.1-1.25x)", "kinds": ("talk",),
        "what": "Zoom punch-ins on key moments only, with a whoosh.",
    },
    "edit.hook_text": {
        "area": "edit", "tr": "Büyük hook yazısı (ilk 2 sn)", "kinds": ("talk",),
        "what": "Hook text from the strongest line, big in the first 1-2 seconds (behind the speaker when a subject matte "
                "is available).",
    },
    "edit.motion_broll": {
        "area": "edit", "tr": "Kodla motion B-roll (~%20)", "kinds": ("talk",),
        "what": "4-6 motion-graphics cutaways (1-2 s) on the biggest moments, built in code (kinetic type with a serif "
                "accent word, corner brackets, numbers, checklists, shapes); no stock footage; the voice keeps playing.",
    },
    "edit.highlight_captions": {
        "area": "edit", "tr": "Vurgu kutulu altyazı", "kinds": ("talk",),
        "what": "Captions over the speaker with colour-coded keywords and a highlight box on the active word.",
    },
    "edit.voice_clean": {
        "area": "edit", "tr": "Ses temizliği (HPF, denoise, de-ess, comp)", "kinds": ("talk",),
        "what": "Voice: 80 Hz high-pass, light denoise, EQ, de-ess, gentle compression, limiter; natural, never processed.",
    },
    "edit.grade": {
        "area": "edit", "tr": "Sinematik renk", "kinds": ("talk",),
        "what": "Cinematic grade with accent colours taken from the footage itself.",
    },
    "edit.fps60": {
        "area": "edit", "tr": "60 fps final", "kinds": ("talk",),
        "what": "Final render at 60 fps, best quality.",
        "data": {"fps60": True},
    },
    # ---------- acting, sets, seams (character animation craft) ----------
    "look.acting": {
        "area": "look", "tr": "Karakter oyunculuğu (duygular)", "kinds": ("topic",),
        "what": "Characters ACT: emotions change with anticipation -> take -> settle (squint and squash first, then the "
                "reaction, then an overshoot), painted emote marks (! ? sweat zzz heart bulb), an idle motion per emotion "
                "so nobody is ever still, two characters never move as twins.",
        "designer": "Give every character an emotion track with FX.emotions(tl, man, [[t, 'neutral'], [t2, 'scared'], ...]) "
                    "(emotions: see FX.EMOTIONS); cause first, then the reaction, in sequence (never on top of each other); "
                    "the eyes lead, the body follows.",
    },
    "look.alive": {
        "area": "look", "tr": "Canlı karakter (hiç donmaz)", "kinds": ("topic",),
        "what": "Drawn characters and creatures feel ALIVE instead of a slideshow of poses: eyes glide to what they look at "
                "and blink every 3-4 s (on every big glance too), the body breathes, every limb drifts on its own period "
                "(moving holds: never a frozen frame, left and right never mirror), poses FLOW through each other instead "
                "of stopping dead, forearms / tails / hair follow a beat later, landings squash and keep the volume, "
                "anything in the air hangs its feet over a shadow that shrinks with the height.",
        "designer": "A lead character is an illustrated FX.character (live face; designed for THIS film: skin, hair, "
                    "outfit, a prop); FX.stickman stays for diagrams and crowds. "
                    "Every character gets FX.alive(man, {look: [[t, gx, gy], ...]}) (gaze at what matters in the scene, "
                    "e.g. the prop as it comes; tired: lid 0.35) and its pose chain as ONE FX.act(man, [[t, 'stand'], "
                    "[t2, 'point'], [t3, 'point'], ...]) (repeat a pose to hold it), not several FX.pose tweens; arrivals "
                    "with FX.land / FX.hop / FX.float; joy = FX.alive cheek squint, speech = FX.alive talk windows. "
                    "Small amplitudes: when unsure, halve them. Per scene ONE main action "
                    "(the story beat); everything else only says 'this is alive'.",
    },
    "look.living_world": {
        "area": "look", "tr": "Yaşayan dünya (idle döngüler)", "kinds": ("topic",),
        "what": "The drawn set lives too: one main action per scene plus 2-3 quiet idle loops picked by subject (plants "
                "and signs sway from their base, a flame leans and stretches, steam rises and fades, water ripples, rain / "
                "snow / leaves / stars each with their own phase, clouds drift in parallax, gears turn, a phone buzzes in "
                "bursts, a gift jiggles waiting to be tapped). Nothing in sync, nothing random per frame; UI and titles "
                "stay still once they land.",
        "designer": "Pick 2-3 idle loops that suit the place, from FX.sway (array = root-to-tip chain), FX.breathe, FX.bob, "
                    "FX.flicker, FX.glow, FX.spin, FX.drift, FX.steam, FX.ripples, FX.weather({kind}), FX.buzz, FX.jiggle; "
                    "draw every moving part as its own SVG group and give it its real pivot (stem base, hinge, hook). "
                    "Repeated items differ by FX.life.seeded(i); things on one screen breathe out of phase. Never on "
                    "captions, titles or UI chrome.",
    },
    "look.kinetic_type": {
        "area": "look", "tr": "Kinetik tipografi (hiç park etmez)", "kinds": ("topic",),
        "what": "Words as the visuals, at motion-design-reel energy: one or two words filling the frame width per beat, "
                "letters tumbling in with ghost rows scrolling past, extruded words punching out of depth, colour flips "
                "of the whole ground, accelerating cut runs, a zoom through a letter's hole into the next scene, a typed "
                "prompt that pushes into Enter on the drop; nothing ever parks (measured: <= 40 % still frames, no hold "
                "over 0.6 s). Real motion blur and bloom in the final render.",
        "designer": "FX.kinetic(tl, root, at, {style, text, until, ground, fx}) per beat (FX.B(k)); FX.ground flips on "
                    "phrase changes; FX.hitFx only on the biggest hits; transitions are moves (FX.whip / FX.whipIn, "
                    "FX.zoomLetter through an O D 0 A B P R, FX.tvOff); FX.typePrompt for an input -> result moment; "
                    "FX.picture for any picture (it pushes, pans, punches in per word, cuts in to details). After a word "
                    "lands it keeps moving; the camera always drifts. Only the end card rests.",
        "data": {"motion_blur": 4, "post_fx": {"bloom": 0.3}},
    },
    "look.picture_alive": {
        "area": "look", "tr": "Görsel asla durmaz (push + punch-in)", "kinds": ("topic",),
        "what": "Every picture (key art, a product shot, a screenshot, a stock photo) keeps moving: it cuts in along a "
                "slash, pushes and pans with a slight 3D tilt, punches in on every word, hard-cuts in to a detail on a "
                "beat and can carry rain / snow / dust over it. A picture is the easiest place for a film to park.",
        "designer": "Show pictures with FX.picture(tl, root, at, dur, {src, words, focus, tint, cutIns, weather}); "
                    "tint for type instead of asking an image for empty space; cut-ins above 1.7x look soft.",
    },
    "look.motion_blur": {
        "area": "look", "tr": "Gerçek hareket bulanıklığı + bloom", "kinds": ("topic",),
        "what": "The final render averages sub-frame samples into real motion blur (180° shutter, never across a cut) "
                "and adds a soft bloom on the highlights: fast moves read as film, not as a slideshow. Costs render "
                "time (x4), nothing else.",
        "data": {"motion_blur": 4, "post_fx": {"bloom": 0.3}},
    },
    "look.handmade": {
        "area": "look", "tr": "El yapımı titreşim (boil) + on twos", "kinds": ("topic",),
        "what": "Hand-drawn feel: lines boil (re-drawn 12 times a second), characters animate on twos, no text on screen "
                "unless it is the joke (show, don't write).",
        "designer": "FX.boil(root, {px: 3}) on drawn scenes; FX.stickman(..., {twos: true}); avoid on-screen words: show the "
                    "meaning with action and painted marks instead (a sign that repeats the story is a failed shot).",
    },
    "look.set3d": {
        "area": "look", "tr": "3D set (ölçekli, ışıklı)", "kinds": ("topic",),
        "what": "Build the set in 3D at real-world scale (metres), light it like a set (three-point, night interior with "
                "practical lamps, moonlight, product, daylight), shoot it with a real lens (24 mm interiors, 35-50 natural, "
                "85 product) and dolly the camera.",
        "designer": "Block out with FX.set3d(root, T, {lens, light, fog}) -> set.room / set.floor / set.box / set.practical "
                    "/ set.dolly; big shapes first, ground contact (nothing floats), foreground-midground-background.",
    },
    "look.caused_transitions": {
        "area": "look", "tr": "Sebebi olan geçişler", "kinds": ("topic",),
        "what": "Every seam gets a transition caused by something on screen (iris from the click or an eye, a fat brush "
                "wipe, a whip with a smear, a colour flood, a dip cut, an object that grows into the next world); 3-5 "
                "kinds per film, at most a third hard cuts, never the same one twice in a row.",
        "designer": "Use FX.iris / FX.brushWipe / FX.whip + FX.whipIn / FX.colorFlood / FX.dipCut, or grow an object past "
                    "the frame into the next scene; cut on action (finish a move in the next scene).",
    },
    "story.reads_timing": {
        "area": "story", "tr": "Okuma zamanlaması", "kinds": ("topic", "talk"),
        "what": "Time every moment for a first-time viewer: list each shot's 'reads' (what must be understood), one read "
                "at a time, fast actions but held meanings, lead the eye before an important read.",
        "designer": "In @@SPEC list per scene its reads with start-end; no two important reads overlap; each read gets "
                    "time to be found, understood and to land before the next one.",
    },
    "story.native_move": {
        "area": "story", "tr": "Tek imza hamlesi", "kinds": ("topic",),
        "what": "One moment only this medium can do (a fold that becomes a transition, ink that blooms into the next scene, "
                "a grid that snaps into the logo), placed at the emotional peak; the ending rhymes with the opening.",
        "designer": "Design ONE signature move at the peak and make the last frame echo the first (same place / pose / "
                    "motif, changed).",
    },
    "sound.silence_turn": {
        "area": "sound", "tr": "Dönüşten önce sessizlik", "kinds": ("topic", "talk"),
        "what": "At least two real near-silences before the turn / the peak; the first sound after the silence is one of "
                "the most important sounds of the film.",
        "designer": "Before the turn: FX.music('cut', t) and no effects for 0.4-0.8 s, then the key sound (impact / knock).",
    },
    "sound.logo_resolve": {
        "area": "sound", "tr": "Logoda çözülme", "kinds": ("topic",),
        "what": "At the end mark the music stops on a bar or filters down, 0.2-0.7 s of near-silence, then ONE soft "
                "resolved element, a tail into silence (no boom on the logo).",
        "designer": "End: FX.music('cut', t_logo - 0.5) then FX.sfx('logo_hit', t_logo, {db: -12}); hold 1 s.",
    },
    "captions.energy": {
        "area": "captions", "tr": "Enerjiye göre altyazı grubu", "kinds": ("topic", "talk"),
        "what": "Caption groups sized to the energy: 2-3 words for high energy, 3-5 conversational, 4-6 calm; break at a "
                "sentence end or a pause of 150 ms.",
        "data": {"captions": {"energy": "talk"}},
    },
    # ---------- checks (always on) ----------
    "check.layout": {
        "area": "check", "tr": "Otomatik yerleşim kontrolü", "kinds": ("topic",), "always": True,
        "what": "Every design round measures text boxes on the stills: safe zones, caption band, overlaps, contrast, tiny "
                "text; the designer must fix the findings.",
    },
    "check.readcheck": {
        "area": "check", "tr": "Okunabilirlik + hareket kontrolü", "kinds": ("topic",), "always": True,
        "what": "Every text must stay on screen long enough to read (~0.3 s a word + 0.5 s); the timeline is checked for "
                "linear spatial easing, staggers over 0.5 s, titles that keep creeping after they land and dead "
                "stretches over 3 s.",
    },
    "check.ears": {
        "area": "check", "tr": "Miksi dinleme (ses QA)", "kinds": ("topic", "talk", "footage", "series"), "always": True,
        "what": "The final mix is measured: loudness and where the loudest moment sits, clicks, tail into silence, low end "
                "a phone cannot play, harsh 2-6 kHz, effect density, machine-gun repeats, effects on words, voice over "
                "music; drawn as a sound sheet.",
    },
    "check.master": {
        "area": "check", "tr": "-14 LUFS master", "kinds": ("topic", "talk", "footage", "series"), "always": True,
        "what": "Final audio mastered to -14 LUFS, true peak under -1 dBTP; checked in QA.",
    },
}

def _film_styles():
    try:
        return json.load(open(os.path.join(ROOT, "data", "film_styles.json")))["styles"]
    except (OSError, ValueError, KeyError):
        return []


def film_style_bible(st):
    """One film style as the designer's visual bible."""
    keys = ("essence", "not", "render", "composition", "colour", "type", "motion", "camera", "transitions", "sound")
    return f"FILM STYLE {st['name']} (the whole visual bible; follow it):\n" + "\n".join(
        f"  {k.upper()}: {st[k]}" for k in keys if st.get(k))


for _st in _film_styles():
    CAPS["style." + _st["id"]] = {
        "area": "style", "tr": _st.get("tr") or _st["name"], "kinds": ("topic",), "style": True,
        "what": f"{_st['name']}: {_st['essence']}",
        "designer": film_style_bible(_st),
        "writer": f"If you write sound.music_prompt, use this film style's sound palette: {_st.get('sound', '')}",
        "data": {"post_fx": _st.get("post") or {}},
    }


DEFAULTS = {
    "topic": ["sound.event_sfx", "voice.tighten"],
    "talk": ["edit.jump_cuts", "edit.face_reframe", "edit.punch_ins", "edit.hook_text", "edit.motion_broll",
             "edit.highlight_captions", "edit.voice_clean", "edit.grade", "sound.event_sfx"],
}


def get(cid):
    return CAPS.get(cid)


def catalogue(kind=None):
    """Compact catalogue for the planner prompt (and the plan card)."""
    return [{"id": k, "area": v["area"], "what": v["what"], "for": list(v["kinds"]),
             **({"shape": True} if v.get("shape") else {}), **({"one_per_video": True} if v.get("style") else {}),
             **({"length_s": v["seconds"]} if v.get("seconds") else {})}
            for k, v in CAPS.items() if not v.get("always") and (kind is None or kind in v["kinds"])]


def chips(kind=None):
    """Studio chips: id, Turkish label, area label."""
    return [{"id": k, "tr": v["tr"], "area": v["area"], "area_tr": AREAS[v["area"]]}
            for k, v in CAPS.items() if not v.get("always") and (kind is None or kind in v["kinds"])]


def clean(ids, kind, defaults=True):
    """Valid technique ids for this kind of video, in catalogue order, with at most one story shape."""
    want = list(ids or []) + (DEFAULTS.get(kind, []) if defaults and not ids else [])
    out, shape, style = [], None, None
    for k in dict.fromkeys(want):          # the planner's order wins when two shapes / styles compete
        v = CAPS.get(k)
        if v and kind in v["kinds"] and not v.get("always"):
            if v.get("shape"):
                if shape:
                    continue
                shape = k
            if v.get("style"):     # one film style per video
                if style:
                    continue
                style = k
            out.append(k)
    return out


def _merge(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def recipe(d):
    return (d or {}).get("recipe") or {}


def techniques(d):
    return recipe(d).get("techniques") or []


def has(d, cid):
    return cid in techniques(d)


def apply(rec, d, kind="topic"):
    """Pin a recipe on production data: the techniques' data switches (voice_fx, captions, sound, fps), fiction and
    the target length. The creator's explicit values already in `d` win."""
    rec = dict(rec or {})
    rec["techniques"] = clean(rec.get("techniques"), kind, defaults=False) if rec.get("techniques") is not None \
        else clean([], kind)
    pinned = {}
    for k in rec["techniques"]:
        pinned = _merge(pinned, CAPS[k].get("data") or {})
    for k, v in pinned.items():
        d[k] = _merge(v, d[k]) if isinstance(v, dict) and isinstance(d.get(k), dict) else d.get(k, v)
    shape = next((CAPS[k] for k in rec["techniques"] if CAPS[k].get("shape")), None)
    if shape and shape.get("fiction"):
        d["fiction"] = True
    sec = rec.get("seconds") or (shape or {}).get("seconds")
    if sec:
        if isinstance(sec, (int, float)):
            sec = [max(8, int(sec) - 5), int(sec) + 5]
        d["duration_cap"] = int(sec[1])
    d["recipe"] = {"direction": str(rec.get("direction") or "")[:1500], "techniques": rec["techniques"],
                   **({"seconds": [int(sec[0]), int(sec[1])]} if sec else {}),
                   **{k: rec[k] for k in ("sketch", "research", "ref_motion") if rec.get(k)}}
    return d


def seconds(d, fallback):
    """Target length [lo, hi] of a production: its recipe, else the format's."""
    return recipe(d).get("seconds") or fallback


def words(d, lang="en"):
    """Script length [lo, hi] implied by the recipe (shape words, else ~2.6 words / s of the target), or None."""
    shape = next((CAPS[k] for k in techniques(d) if CAPS.get(k, {}).get("shape")), None)
    if shape and shape.get("words"):
        lo, hi = shape["words"]
    elif recipe(d).get("seconds"):
        a, b = recipe(d)["seconds"]
        lo, hi = round(a * 2.4), round(b * 2.7)
    else:
        return None
    return (round(lo * 0.8), round(hi * 0.85)) if lang == "tr" else (lo, hi)


def fiction(d):
    return bool((d or {}).get("fiction")) or any(CAPS.get(k, {}).get("fiction") for k in techniques(d))


def _notes(d, field):
    return [f"- [{k}] {CAPS[k][field]}" for k in techniques(d) if CAPS.get(k, {}).get(field)]


def writer_notes(d):
    """The recipe as instructions for the script writer ('' without a recipe)."""
    r = recipe(d)
    if not r:
        return ""
    out = []
    if r.get("direction"):
        out.append(f"ART DIRECTION (the producer's plan for this video; data): {r['direction']}")
    w = words(d, (d or {}).get("lang", "en"))
    if r.get("seconds") or w:
        out.append(f"LENGTH: {r.get('seconds', ['?', '?'])[0]}-{r.get('seconds', ['?', '?'])[1]} s"
                   + (f", {w[0]}-{w[1]} words" if w else "") + " (this overrides the default length).")
    notes = _notes(d, "writer")
    if notes:
        out.append("TECHNIQUES chosen for this video (apply every one):\n" + "\n".join(notes))
    if r.get("research"):
        out.append("SCOUT'S RESEARCH (leads, not proof: re-verify every fact with its source before it goes on screen; the "
                   "script must make the insight land and break the misconception): " + json.dumps(r["research"], ensure_ascii=False))
    if (r.get("sketch") or {}).get("moment"):
        out.append(f"THE CHOSEN KEY FRAME (the creator approved this hook image; the first line must fit it): {r['sketch']['moment']}")
    return "\n".join(out)


def designer_notes(d):
    """The recipe as instructions for the motion designer ('' without a recipe)."""
    r = recipe(d)
    if not r:
        return ""
    out = []
    if r.get("direction"):
        out.append(f"ART DIRECTION (from the producer; your design must deliver it): {r['direction']}")
    notes = _notes(d, "designer")
    if notes:
        out.append("TECHNIQUES chosen for this video (use every one):\n" + "\n".join(notes))
    if r.get("ref_motion"):
        out.append("REFERENCE MOTION (measured frame by frame in the creator's references; their life is in these numbers, "
                   "reproduce the amplitudes and periods, not just the poses): "
                   + "; ".join(f"{m['ref']}: {m['motion']}" for m in r["ref_motion"]))
    sk = r.get("sketch") or {}
    if sk.get("design"):
        code = sketch_code(sk["design"])
        out.append("THE APPROVED STYLE FRAME: the creator chose this treatment after seeing its sketch. Keep its world, "
                   f"palette, characters and type; the hook scene starts from it and the other scenes belong to the same film. "
                   f"Moment: {sk.get('moment', '')} Concept: {sk.get('concept', '')} Palette: {json.dumps(sk.get('palette') or {})}"
                   + (f" The creative director's note to fix while building: {sk['fix']}" if sk.get("fix") else "")
                   + (f"\nIts code (for reference, adapt it):\n{code}" if code else ""))
    return "\n".join(out)


def sketch_code(rel, limit=7000):
    """The HTML / CSS / JS of a chosen sketch, as blocks (trimmed)."""
    try:
        d = json.load(open(os.path.join(ROOT, rel)))
        sc = next(iter(d.get("scenes", {}).values()), {})
        txt = f"@@GLOBAL_CSS\n{d.get('global_css', '')}\n@@HTML\n{sc.get('html', '')}\n@@CSS\n{sc.get('css', '')}\n@@JS\n{sc.get('js', '')}"
        return txt[:limit]
    except (OSError, ValueError, StopIteration):
        return ""


def labels(d):
    """Turkish labels of a production's techniques (Studio)."""
    return [{"id": k, "tr": CAPS[k]["tr"], "area_tr": AREAS[CAPS[k]["area"]]} for k in techniques(d) if k in CAPS]
