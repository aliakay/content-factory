# Fabrika v2 — Üretim Hatları (tasarım)

> Durum: **taslak, onay bekliyor** · 2026-11-02
> OpenMontage'ın (AGPLv3) *fikir ve düzeni* örnek alındı; **kodu kopyalanmadı**, kopyalanmayacak. Her şey bu repoda,
> kendi modüllerimizin üstüne yeniden yazılır.

## 1. Neden

Bugünkü akışta bir video; planner, 4 aşama (fikir → ses → önizleme → hazır) ve üretim sayfasındaki ~15 yan karttan
geçiyor. Kararlar iki kez soruluyor, pahalı işler (hareket tasarımı) metin onayından önce çalışıyor, revizyonun dört
ayrı yolu var ve bir değişiklik arkasındaki işleri sessizce siliyor. Son iki video (Kuyt, Avrupa gazı) bu yüzden
Studio dışında, elle yazılmış script'lerle bitti.

v2'nin tek fikri: **her video, kendi türüne ait sabit bir hattan, aşama aşama geçer. Her aşama tek bir dosya üretir,
o dosya onaylanmadan bir sonraki aşama başlamaz.**

## 2. Üç katman

| Katman | Ne | Nerede |
|---|---|---|
| **1 · Ne var** | Hat tanımları (manifest) + araç kayıt defteri | `pipelines/*.yaml`, `factory/tools/` |
| **2 · Nasıl yapılır** | Her aşamanın yönetmen talimatı + gözden geçirme kuralları | `skills/pipelines/<hat>/<aşama>.md`, `skills/meta/` |
| **3 · Derin bilgi** | Teknik kataloğu, film stilleri, sanat oyun kitabı, model rehberleri | `factory/capabilities.py`, `data/film_styles.json`, `ART_PLAYBOOK.md`, `skills/knowledge/` |

Python **araç ve kalıcılık** sağlar; yaratıcı kararlar, sıra ve kalite çıtası okunabilir dosyalarda (YAML + Markdown)
durur. Bir aşamayı Studio'daki headless ajan da, Claude Code oturumundaki ajan da aynı talimat dosyasıyla, aynı çıktı
dosyalarına yazarak yürütür. Böylece "sistem dışında elle bitirme" diye bir şey kalmaz: elle yapılan iş de panoda görünür.

## 3. Ortak aşamalar

Her hat bu iskeletin bir alt kümesini, bu sırayla kullanır:

| # | Aşama | Çıktı dosyası | Ne olur | Kapı |
|---|---|---|---|---|
| 1 | **Araştırma** | `research.json` | Kaynaklı veri noktaları, açılar, yaygın yanlışlar, görsel referanslar | — |
| 2 | **Öneri** | `proposal.json` | 3 farklı konsept, seçilen yol, kalem kalem maliyet ve render süresi | ✅ |
| 3 | **Senaryo** | `script.json` | Satırlar, süre, vurgu, doğrulanmış iddialar (kaynaklarıyla) | ✅ |
| 4 | **Sahne planı** | `scene_plan.json` + kareler | Sahne sahne görsel dil, zamanlama, gereken varlıklar; tasarım kareleri | ✅ |
| 5 | **Varlıklar** | `assets.json` | Ses, müzik, çizimler, video klipler, stok; sahne başına alternatifler + gerçek maliyet | ✅ |
| 6 | **Kurgu** | `edit.json` | Kesimler, geçişler, altyazı, ses miksi kararları | — |
| 7 | **Render** | `render.json` + mp4 | Final render + teknik/görsel/ses QA | — |
| 8 | **Yayın** | `publish.json` | Açıklama, etiketler, kapaklar, platform linkleri | ✅ |

Kurallar:
- **Kapı bağlayıcıdır.** Manifest'te kapı olan bir aşama, kayıtlı onay olmadan "tamam" yazılamaz (kod bunu reddeder).
- **Kredi önce, harcama sonra.** Öneri kapısında toplam bütçe onaylanır; Varlıklar aşaması bu bütçeyi aşamaz
  (`credits.guard` +%15 kuralı korunur). Varlıklar kapısında *sonuçlar* onaylanır.
- **Revizyon yalnızca o aşamayı yeniden yapar** (aşama başına en fazla 3). Daha önceki bir aşamaya dönülürse sonraki
  aşamalar "geçersiz" olarak işaretlenir ve bu ekranda açıkça yazar; hiçbir şey sessizce silinmez.
- **Öz denetim.** Her aşama bittiğinde ajan, manifest'teki `review_focus` maddelerine göre kendi çıktısını en çok
  2 tur denetler (kritik / öneri / ayrıntı). Kritikler düzeltilir, diğerleri not olarak kapıya taşınır.

## 3b. Ajan yapısı

Bugün orkestratör Python ve her ajan tek seferlik bir CLI çağrısı (~20 adet: scout, art director, eskizciler,
eleştirmen, yazar, hareket tasarımcısı, görsel QA…). Ajanların elinde yalnızca WebSearch/Read var; kare render etme,
lint, düzeltme döngüsünü Python sabit sırayla yapıyor. OpenMontage'da ise orkestratör tek bir uzun ajan. v2 ikisinin
karmasıdır:

| Rol | Kim | Görev |
|---|---|---|
| **Hat yöneticisi** (`factory/hat.py`) | Python, deterministik | Manifest'i okur, sıradaki aşamayı başlatır; kapıyı, bütçeyi, revizyon sayısını ve geçersiz kılmayı kodla uygular. Yaratıcı karar vermez. |
| **Aşama ajanı** (`factory/agent.py`) | Aşamaya göre model (araştırma: Sonnet + web; öneri, senaryo, tasarım: Opus) | Talimat dosyasını ve önceki çıktıları okur; araçları kendisi çağırır (kare çek, bak, lint, düzelt), şemaya uyan çıktı dosyasını yazar. Tur ve süre limiti vardır. |
| **Denetçi** | Yazandan farklı model (örn. Claude yazar, Codex denetler) | Taze bağlamla `review_focus` maddelerini denetler; kritik bulgular aşama ajanına döner (en çok 2 tur), diğerleri kapıya not olur. |
| **Paralel işçiler** | Küçük, ucuz çağrılar | Varlıklar aşamasında sahne başına görsel/video/ses üretimi. |
| **İnsan** | Studio panosu | Yalnızca kapılarda karar verir; notu o aşamanın ajanına revizyon girdisi olarak gider. |

Kurallar:
- Ajanlar birbiriyle konuşmaz; tek iletişim yolu diskteki çıktı dosyalarıdır. Her karar gerekçesiyle
  `decisions.jsonl`'e, her araç çağrısı süre ve maliyetiyle `events.jsonl`'e yazılır.
- Araçlar bir MCP sunucusu (`factory-tools`) olarak sunulur; aşama ajanı yalnızca manifest'te o aşamaya izin verilen
  araçları görür. Studio'nun headless ajanları ile Claude Code'daki etkileşimli ajan **aynı araçları ve aynı talimatları**
  kullanır, böylece elle yürütülen bir aşama da panoda görünür.
- Kredi koruması araçtadır, prompt'ta değil: ElevenLabs araçları hat yöneticisinin verdiği onaylı bütçe olmadan
  çalışmaz (`credits.guard` buraya taşınır).
- Bugünkü director ekibi korunur: scout → Araştırma aşaması; art director + eskizciler + eleştirmen → Öneri aşaması
  (3 konsept, 3 kare, eleştiri).

## 4. Proje klasörü

Her video bir klasördür; SQLite `productions` tablosu yalnızca dizin olarak kalır (liste, kanal, takip).

```
projects/<NNN-kisa-ad>/
  project.json            hat, kanal, dil, kadraj, başlık, oluşturan
  artifacts/              research.json, proposal.json, script.json, scene_plan.json, assets.json, edit.json, render.json, publish.json
  checkpoints/<aşama>.json  durum (bekliyor/çalışıyor/onay bekliyor/onaylandı/revize/başarısız), denetim notları, maliyet, onay geçmişi
  assets/{audio,music,images,video,stock}/
  stills/                 sahne kareleri (panonun film şeridi)
  renders/preview.mp4, final.mp4
  events.jsonl            araç çağrıları, süreler, maliyetler (pano canlı akışı)
```

Numara tek sayaçtan gelir (bugünkü "113 hem fiber hem gaz" çakışması biter).

## 5. Araç kayıt defteri

Her araç aynı sözleşmeyi taşır: `ad`, `yetenek` (tts, görsel, video, müzik, sfx, transkript, kompozisyon, analiz, QA…),
`sağlayıcı` (elevenlabs / claude / yerel), `çalışma yeri` (yerel/bulut), `maliyet tahmini`, `iyi olduğu`, `iyi olmadığı`,
`hazır mı` (+ değilse neden), `çalıştır()`. Hatlar araçları *yetenek* adıyla ister; **seçici** o an hazır olanlar
arasından uygunluk, kalite, kontrol, güvenilirlik, maliyet, hız ve süreklilik puanıyla seçer ve seçimi gerekçesiyle
karar günlüğüne yazar. Sağlayıcı sessizce değişmez.

Bizim sağlayıcılarımız: **ElevenLabs connector** (bugün şemasını okuduğumuz modeller), **Claude/Codex** (araştırma,
yazım, tasarım, görsel denetim), **yerel** (ffmpeg, Chromium, faster-whisper, numpy, Pillow, rembg).

| Aile | Araçlar (ilk liste) | Kaynak |
|---|---|---|
| **Ses (TTS)** | eleven_v3, eleven_v4, multilingual_v2, flash_v2_5, ses tasarımı, ses klonu | EL |
| **Müzik** | eleven_music v2.5, video-to-music, beat analizi, müzik kütüphanesi (lisanslı dosyalar) | EL + yerel |
| **SFX** | 19 sentez efekt + otomatik yerleşim, eleven_text_to_sound v2 | yerel + EL |
| **Görsel** | gpt-image-2, gpt-image-2.5, flux-3, flux-2-pro, gemini-3-pro-image, seedream-5, recraft-v4, ideogram-4.5, krea-3, Wikimedia stok | EL + yerel |
| **Video üretimi** | kling-3-pro/4, veo-3.1, seedance-2.5, runway-gen4.5, minimax-h3, ltx-v2, wan-2.6, flux-3-video | EL |
| **Avatar / dudak** | omnihuman-1.5, heygen-avatar4, creatify-aurora, sync-lipsync-v3, veed-lipsync | EL |
| **Dönüştürme** | dublaj (ses/video), ses izolasyonu, voice changer, topaz upscale, birefnet arka plan silme | EL |
| **Analiz** | faster-whisper (kelime zamanlı), scribe, sahne kesim tespiti, kare örnekleme, yüz takibi, hareket profili, efekt tespiti, referans video analizi | yerel + EL |
| **Kurgu** | kes/birleştir, sessizlik kesici, yeniden kadrajlama, renk/film görünümü, altyazı, ses zinciri + ducking + loudness | yerel |
| **Kompozisyon** | htmlmotion (HTML/GSAP/Three.js), explainer (Pillow), stylecut, cinecut, talkcut | yerel |
| **Yakalama** | Playwright ekran kaydı, terminal simülasyonu | yerel |
| **Denetim** | layout lint, okuma kontrolü, hareket lint, görsel QA (Claude), ses QA, slayt-gösterisi riski, kapak adayları | yerel + Claude |
| **Araştırma/yazım** | web araştırma, iddia doğrulama, senaryo, hareket tasarımı, art direction | Claude/Codex |

Bu liste ~100 araca karşılık gelir; çoğu bugün var olan modüllerin ince sarmalayıcısıdır.

## 6. Hatlar

Her hatın Studio'da bir kartı olur: **ne üretir, ne için iyi, ne için değil, ne ister, tipik süre, tipik maliyet,
hangi aşamalar ve kapılar.** Aşağıdaki açıklamalar o kartların metnidir.

### 6.1 Konu anlatımı · `explainer`
**Ne üretir:** Çekim gerektirmeyen, araştırmaya dayalı 30–90 sn anlatım videosu: seslendirme, kod ile çizilmiş
hareketli grafik, kinetik altyazı, ses tasarımı.
**İyi olduğu:** Haber açıklamaları, "neden/nasıl" soruları, veri hikâyeleri (Avrupa gazı, fiber rekoru).
**İyi olmadığı:** Gerçek mekân hissi gereken konular; yüz/kişi odaklı hikâyeler.
**İster:** Bir konu ya da Keşif kartı. **Aşamalar:** 1→8, kapılar 2·3·4·5·8.
**Durum:** Var (explainer + motiondesign + htmlmotion); omurgaya taşınacak ilk hat.

### 6.2 Hareketli grafik · `animation`
**Ne üretir:** Anlatımın değil hareketin öne çıktığı kısa işler: kinetik tipografi, diyagram, veri animasyonu,
Three.js 3D dünyalar.
**İyi olduğu:** Lansman, duyuru, istatistik vurgusu, döngü içerikler, müzikli anlatımsız videolar.
**İyi olmadığı:** Uzun sözlü anlatım; gerçek görüntü isteyen konular.
**İster:** Konu ya da mesaj + istenirse müzik. **Kapılar:** 2·3·4·5·8.
**Durum:** Hazır (t201). Konu anlatımının kod aşamalarını kullanır; senaryo `narrate: false` ise ses yok, her satır `holds` saniye kalan bir ekran vuruşu, altyazı kapalı, müzik zorunlu.

### 6.3 Seyahat vlog · `travel_vlog` *(bize özel)*
**Ne üretir:** Kendi çekimlerinden sakin, sinematik ya da referans tarzında kurgu: en iyi anlar, ritim, yazılar, müzik.
**İyi olduğu:** iCloud albümünden gezi videoları, rota, "gerçek gibi durmayan yerler".
**İyi olmadığı:** Çekim olmayan konular.
**İster:** Albüm/klip seçimi. **Kapılar:** 2·4·5·8.
**Durum:** Hazır (t202). Eski klip motoru (fikir, sanat yönetmeni, cinecut, QA) köprü ile aşamalara bağlı; proje başına bir üretim satırı (project["prods"]). Fikir aşaması 3 fikir üretir; geri bildirime harf yazmak (B) yeni çağrı yapmadan seçer.

### 6.4 Sinematik · `cinematic`
**Ne üretir:** Fragman, marka filmi, duygu odaklı kısa kurgular; kendi görüntün + gerektiğinde üretilen video klipler.
**İyi olduğu:** Teaser, motivasyon, "bir dünya kur" videoları.
**İyi olmadığı:** Bilgi yoğun anlatım.
**İster:** Konsept + varsa görüntü. **Kapılar:** 2·3·4·5·8.
**Durum:** Hazır (t302). Fikir aşaması iki konsept ve çekim listesi yazar (kendi klipler + en fazla 3 üretilen çekim, maliyet kalem kalem; "ucuz" notu ucuz video modeline geçer). Çekim listesi kapısında ödeme yok; sahne planında her üretilen çekim için bir anahtar kare, varlıklarda o kareden başlayan klip (Seedance). Üretilen klipler yalnız o projenin albümünde (gen:<proje>), seyahat envanterine karışmaz; kurgu, final ve yayın klip motoruyla.

### 6.5 Hibrit · `hybrid`
**Ne üretir:** Kaynak görüntü + üstüne tasarlanmış destek katmanları (diyagram, harita, veri kartı, etiket).
**İyi olduğu:** Röportaj + grafik, ürün görüntüsü + açıklama, gezi + bilgi kartları.
**İyi olmadığı:** Görüntüsüz konular (→ Konu anlatımı).
**İster:** Görüntü + konu. **Kapılar:** 2·3·4·5·8.
**Durum:** Hazır, v1 (t204): klip motorunun "travel_facts" biçimi üzerinde; Bilgi kontrolü kapısında her bilgi kaynakla doğrulanır, doğrulanamayanlar adıyla gösterilir. Tasarlanmış (htmlmotion) bilgi katmanları v2 işi.

### 6.6 Konuşan kafa · `talking_head`
**Ne üretir:** Kameraya konuştuğun ham videodan sıkı, dikey, altyazılı kısa video: tekrarlar ve duraklamalar kesilir,
yüz takibiyle kadraj, B-roll, ses zinciri.
**İyi olduğu:** Görüş, ipucu, hikâye anlatımı.
**İyi olmadığı:** Konuşmasız görüntü.
**İster:** Ham video. **Kapılar:** 3 (kesim kararı) · 5 · 8.
**Durum:** Hazır (t203). Fikir: video analizi + ilk kesim; Kesim kararı kapısında kalan/kesilen cümleler, geri bildirim yeniden keser; ses yok, müzik onaylı bütçeyle. Video panodan yüklenir (raw/talk/, dokunulmaz).

### 6.7 Klip fabrikası · `clip_factory`
**Ne üretir:** Uzun bir kaynaktan (yayın, sunum, röportaj) puanlanmış N adet bağımsız kısa klip.
**İyi olduğu:** Bir uzun içerikten haftalık kısa video stoku.
**İyi olmadığı:** Zaten kısa olan kaynaklar.
**İster:** Uzun video/ses. **Kapılar:** 2 (klip listesi) · 5 · 8.
**Durum:** Yeni; talk.py'nin transkript ve kesim altyapısı kullanılır.

### 6.8 Podcast dönüştürme · `podcast`
**Ne üretir:** Podcast sesinden altyazılı/dalga formlu klipler, alıntı kartları; istenirse bölüm eşlik videosu.
**İyi olduğu:** Sesli içeriği sosyal medyaya taşımak.
**İyi olmadığı:** Kötü kayıtlı ses (önce ses izolasyonu gerekir).
**İster:** Ses ya da video podcast. **Kapılar:** 2 · 4 · 8.
**Durum:** Yeni; transkript + htmlmotion + EL ses izolasyonu.

### 6.9 Avatar sunucu · `avatar`
**Ne üretir:** Dijital bir sunucunun konuştuğu duyuru, eğitim, tanıtım videoları; sade destek grafikleriyle.
**İyi olduğu:** Yüzünü göstermeden "biri anlatıyor" hissi.
**İyi olmadığı:** Duygusal/doğal oyunculuk isteyen sahneler.
**İster:** Metin + sunucu görseli/avatarı. **Kapılar:** 2·3·4·5·8.
**Durum:** Hazır (t303). `factory/hat/avatar.py`: senaryo + sunucu (yüklenen portre `raw/avatar/`, kayıtlı fotoğraf ya da üretilen) → ses (TTS) → kelime zamanlaması → ses sunucunun flow'una yüklenir → creatify-aurora konuşan video → 4 kelimelik yakılmış altyazı, -14 LUFS. Avatar fiyatı öğrenilene kadar öneride saniye başına tavan (1500 kredi) ayrılır; guard onaydan fazlasını harcatmaz. Gerçek ücretli uçtan uca çalışma henüz yok.

### 6.10 Karakter animasyonu · `character`
**Ne üretir:** Tekrar kullanılabilir çizgi karakterlerle bölümlü hikâyeler: karakter tasarımı, poz kütüphanesi,
sahne sahne oyunculuk.
**İyi olduğu:** Seriler, maskot içerikler, çocuk/eğitim hikâyeleri.
**İyi olmadığı:** Gerçekçi insan sahneleri.
**İster:** Hikâye/seri fikri. **Aşamalar:** + karakter tasarımı (kapı), + rig planı. **Kapılar:** 2·3·kt·4·5·8.
**Durum:** Kısmen var (Seriler, çizimli görünüm, stickman rig).

### 6.11 Belgesel montaj · `documentary`
**Ne üretir:** Açık lisanslı gerçek görüntülerden (Wikimedia, Archive.org, NASA, Pexels) tematik montaj; anlatımlı
ya da yalnız müzikli.
**İyi olduğu:** Tarih, şehir, doğa, "bir duygu" videoları; üretim maliyeti olmadan gerçek görüntü.
**İyi olmadığı:** Güncel haber (arşivde görüntü yoktur).
**İster:** Tema + ton. **Kapılar:** 2 · 4 · 5 · 6 (kurgu da onaylanır).
**Durum:** Yeni; stok video arşivi + anlamsal arama gerekir.

### 6.12 Yerelleştirme & dublaj · `localize`
**Ne üretir:** Bitmiş bir videonun başka dillerde altyazılı ve dublajlı sürümleri.
**İyi olduğu:** TR videoyu EN/DE kanallarına taşımak (ve tersi).
**İyi olmadığı:** Dudak senkronu kritik, yüzü yakın planlı videolar (ek lip-sync adımı gerekir).
**İster:** Bitmiş video + hedef diller. **Kapılar:** 3 (çeviri) · 5 · 8.
**Durum:** Hazır (t304). `factory/hat/localize.py`: whisper transkript → zamanlı satırlar → zaman dilimine sığan çeviri (kapı) → tek TTS + kelime zamanlaması → her satır kaynaktaki yerine (en fazla 1.25× hızlandırma) → isteğe bağlı sync-lipsync-v3 (açıklamada "dudak senkronu") → hedef dilde yakılmış altyazı. Orijinal ses tamamen değişir (müzik ayrıştırma yok). Dudak senkronu fiyatı öğrenilene kadar saniye başına tavan. Bir seferde tek hedef dil. Gerçek ücretli çalışma henüz yok.

### 6.13 Ekran demosu · `screen_demo`
**Ne üretir:** Uygulama/web gezintisi ya da kod anlatımından cilalı demo: yakınlaştırmalar, işaretler, altyazı.
**İyi olduğu:** Ürün tanıtımı, "nasıl yapılır".
**İyi olmadığı:** Gerçek dünya görüntüsü.
**İster:** URL/uygulama ya da ekran kaydı. **Kapılar:** 3·4·5·8.
**Durum:** Yeni; Playwright kaydı (Chromium hazır).

### 6.14 Seri bölümü · `series_episode` *(bize özel)*
Var olan bir serinin sıradaki bölümü; seri kitabı, karakterler ve çizim dili sabit. Karakter animasyonu hattının
"karakter tasarımı" aşamasını atlar (seri kitabından gelir).

**Durum:** Hazır (t205). Kitap ve karakter sayfaları Seriler sayfasında; hat bir bölümü üretir: bölüm metni + maliyet, konuşanlarıyla satırlar, karakter sayfalarından çizimler (bütçe içinde), sesler + müzik, final.

## 7. Studio: sade arayüz

- **Ana sayfa:** "Ne üretelim?" kutusu + 14 hat kartı. Yazılan istekten planner bir hat önerir; kart seçmek de olur.
  Kanal, dil ve kadraj **burada bir kez** seçilir.
- **Üretim sayfası = pano:** üstte aşama şeridi (tamamlananlar ✓, şimdiki vurgulu, kapılar 🔒). Ortada **yalnızca
  şimdiki aşamanın çıktısı**, okunur biçimde: araştırma = kaynak listesi, öneri = 3 konsept kartı + maliyet, senaryo =
  senaryo sayfası, sahne planı = film şeridi, varlıklar = sahne sahne alternatifler, render = oynatıcı + QA.
  Sağda tek kart: **Onayla** · **Not yaz, bu aşamayı yeniden yap** · **Önceki aşamaya dön**.
- Önceki aşamalar katlanmış ve salt okunur. Yan kartlar (kadraj, görünüm, gramer, müzik…) kalkar; hepsi ilgili aşamanın
  çıktısının parçası olur.
- **Canlı akış:** aşama çalışırken `events.jsonl`'den adım adım ne yapıldığı, süre ve harcama görünür.
- Menü sadeleşir: Stüdyo · Üretimler · Keşif · Takip · Ayarlar (kanallar, sesler, hesaplar, bütçe, stiller tek yerde).

## 8. Fazlar

| Faz | Kapsam | Bitince |
|---|---|---|
| **1 · Omurga** | Manifest formatı, proje klasörü, checkpoint + kapı kuralı, araç kayıt defteri (mevcut ~40 araç), aşama yürütücü (headless Claude/Codex + talimat dosyası + öz denetim), Studio pano sayfası. **Konu anlatımı** hattı uçtan uca bu omurgada. | Bir haber videosu, tek ekranda 5 onayla, Studio dışına çıkmadan biter. |
| **2 · Mevcutları taşı** | Hareketli grafik, Seyahat vlog, Konuşan kafa, Hibrit, Seri bölümü. Eski üretim sayfası ve planner kartları kaldırılır. | Bugün yapabildiğimiz her şey yeni hatlarda. |
| **3 · ElevenLabs ile yeniler** | Sinematik (üretilen video), Avatar, Yerelleştirme, Klip fabrikası, Podcast; tam görsel/video/avatar araç ailesi + seçici. | 11 hat. |
| **4 · Arşiv ve ekran** | Belgesel montaj (stok video arşivi + anlamsal arama), Ekran demosu, Karakter animasyonu tam hali. | 14 hat. |

Her faz kendi testleriyle gelir (manifest doğrulama, kapı kuralı, araç sözleşmesi, her hat için kuru çalıştırma).

## 9. Açık kararlar

1. **Talimat dosyalarının dili:** ajanlar için İngilizce (daha tutarlı sonuç), Studio'da görünen her metin Türkçe. *Öneri.*
2. **Varsayılan otomatiklik:** her kapıda dur (önerilen) / "güvenli kapıları otomatik geç" seçeneği hat başına.
3. **Eski üretimler:** mevcut 11 üretim yeni klasör yapısına taşınsın mı, yoksa eski sayfada mı kalsın?
