# Ortak sunucu — yol haritası ve kurulum

> Durum: **plan, uygulanmadı** · 2026-11-05 · Cem + Ali
> Amaç: ikimiz de kendi bilgisayarımızda ayrı kopya çalıştırmak yerine **tek bir ortak VPS** kullanalım; günde 2–4
> video, telefondan da. Kod `main`'den gelir, üretim yalnızca bu sunucuda yapılır.

## 1. Neden

Herkes kendi kopyasını çalıştırınca:
- **Kod ayrışıyor.** Contabo'daki kopyada haftalarca upstream'de olmayan üç düzeltme vardı (#25–#27); `soundfile`
  requirements'ta yoktu (#28). Birinde çıkan hata diğerinde çıkmıyor.
- **Veri bölünüyor.** Üretimler, Keşif kartları, kanallar, playbook dersleri ve kredi takibi her makinede ayrı.
  Birinin ürettiğini diğeri görmüyor.
- **Ortam farklılaşıyor.** API anahtarları, ses profilleri, kurulu paketler.

Çok kullanıcılı yapı kodda zaten var (`factory/accounts.py`): sahip/üye rolleri, her üyenin kendi Claude aboneliği ve
ElevenLabs hesabı, her işin kimin adına çalıştığı. Eksik olan ortak bir makine.

## 2. Nasıl çalışacak

```
telefon / bilgisayar ──Tailscale (özel tünel)──▶ ortak VPS
   Studio kısayolu                                 ├─ Studio :8501  Shorts :8095  Streamlit :8503
   (ana ekran ikonu)                               ├─ iş kuyruğu: render (Chromium + ffmpeg), whisper, müzik, QA
                                                   ├─ data/factory.db, out/, assets/, styles/
                                                   └─ cron: start-factory, Keşif, günlük yedek
                     Claude adımları ─▶ işi başlatanın Claude aboneliği
                     seslendirme     ─▶ üretimde seçili ElevenLabs hesabı
```

- **Sunucu** yazılımı çalıştırır ve işlemci isteyen her şeyi yapar. Sabit aylık ücret.
- **Claude** ve **ElevenLabs** maliyeti işi başlatan kişinin hesabından düşer. Sunucu sadece çağırır.
- İkimiz de aynı üretim listesini ve videoları görürüz. Kartlarda ve geçmişte kimin başlattığı ve kimin onayladığı
  yazar (`feat/shared-studio`).
- Biri diğerinin üretimini onaylayabilir. Claude adımları onaylayanın aboneliğinden gider. ElevenLabs, onaylayanın
  kullanamadığı bir hesaba izin vermez; ya hesap paylaşılır ya da üretimin sesi onaylayanın hesabına çevrilir
  (`set_eleven`).

### Roller (tek sahip olmalı)

| | Sahip (owner) | Üye (member) |
|---|---|---|
| Claude | Sunucudaki `claude` girişi (sahibin aboneliği) | Studio → Hesaplar → kendi Claude'unu bağlar (tam giriş) |
| ElevenLabs | Sahibin claude.ai ElevenLabs bağlayıcısı | Kendi bağlayıcısı (tam girişle) veya kendi API anahtarı |
| Cron işleri (Keşif) | Sahibin Claude'undan gider (~$0,08–0,09 / tarama) | — |

`owner` rolündeki **herkes** sunucunun Claude girişini kullanır. İki kişi owner olursa ikisi de aynı aboneliği
tüketir. Bu yüzden bir owner, bir member.

**Karar: sahip Ali, üye Cem.** Kod sahibi zaten `ali` olarak varsayıyor (`accounts.OWNER = "ali"`, sahibin ElevenLabs
hesabının kimliği `ali`), bu yüzden kod değişikliği gerekmez. Sunucudaki `claude` girişi Ali'nin hesabıyla yapılır.

## 3. Sunucu seçimi (Contabo)

Ölçümler (Contabo Cloud VPS, 4 vCPU / 8 GB, 2026-11-05):

| Aşama | Hazır look | `auto` look | Neye bağlı |
|---|---|---|---|
| Fikir + senaryo | 1,5 dk | 2–3 dk | Claude |
| Ses + tasarım + önizleme | 2,7 dk | ~40 dk | çoğu Opus tasarımı (Claude) |
| Doğrulama | 0,6 dk | ~1 dk | Claude + web |
| Final render (33 sn video) | 3,3 dk | 5–7 dk | **sunucunun işlemcisi** |

- Sunucuya bağlı tek büyük kalem render. Videolar 75 sn'den kısaysa tek Chromium'la çiziliyor
  (`bin/htmlmotion.py`, `PAR_MIN_S = 75`), yani bugün çekirdeklerin çoğu boşta.
- Bir shorts ~8–15 MB, ara dosyalarla birlikte bir video ~50–100 MB. Kurulum (venv, Chromium, node) ~2 GB.
- Aynı anda iki kişi render alırsa iki Chromium çalışır, her biri ~1–1,5 GB RAM.

Contabo fiyatları (aylık, EUR, Şubat 2026 itibarıyla; sipariş sayfasında güncelini kontrol edin):

| Plan | Çekirdek | RAM | Disk | Fiyat | Not |
|---|---|---|---|---|---|
| Cloud VPS 10 | 4 vCPU | 8 GB | 75 GB NVMe | ~4,50 | bugünkü sunucu düzeyi |
| Cloud VPS 20 | 6 vCPU | 12 GB | 100 GB NVMe | ~7 | asgari |
| **Cloud VPS 30** | **8 vCPU** | **24 GB** | **200 GB NVMe** | **~14** | **önerilen** |
| Cloud VPS 40 | 12 vCPU | 48 GB | 250 GB NVMe | ~25 | gereğinden büyük |
| Cloud VDS S | 3 fiziksel çekirdek | 24 GB | 180 GB NVMe | ~34–43 | ayrılmış çekirdek; bu iş için pahalı |

**Öneri: Cloud VPS 30, NVMe disk, Avrupa (Almanya) lokasyonu, Ubuntu 24.04.**
- 8 vCPU: paralel render açılınca (bkz. §6) bir shorts'un render süresi kısalır. İki kişi aynı anda üretim
  yapabilir.
- 24 GB RAM: iki Chromium, whisper ve rembg aynı anda rahat sığar.
- 200 GB NVMe: aylık ~120 video ve yedekler için yıllarca yeter. NVMe, SSD'den daha hızlı okuma ve yazma demek.
- Contabo vCPU'ları paylaşımlı ve başka müşterilerle bölüşülüyor. Render bazen yavaşlayabilir. Bu boyutta VDS'e
  (ayrılmış çekirdek) gerek yok.
- GPU'ya gerek yok: render tarayıcıda yazılımla çiziliyor.

## 4. Yol haritası

### Faz 0 — Hazırlık (karar ve satın alma)
- [ ] Açık PR'ları merge et: #24 film stilleri, #25 render hızı, #26 config, #27 oturum çerezi, #28 soundfile,
      `feat/shared-studio` (kim başlattı etiketi + ana ekran kısayolu), bu belge.
- [ ] Contabo'dan Cloud VPS 30 al. Ödeme ve sahiplik kimde olacak, maliyet nasıl bölünecek kararlaştır.
- [ ] Ali'nin Tailscale hesabı yoksa açsın (ücretsiz).

### Faz 1 — Sunucunun temeli (root ile, bir kez)
```bash
adduser factory && usermod -aG sudo factory          # uygulama bu kullanıcıyla çalışır, root'la değil
# SSH: parola yerine anahtar; /etc/ssh/sshd_config → PasswordAuthentication no, PermitRootLogin prohibit-password
timedatectl set-timezone Europe/Istanbul             # cron saatleri Türkiye saatiyle
apt update && apt -y upgrade
apt -y install git python3-venv python3-dev ffmpeg sqlite3 curl unattended-upgrades ufw
curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt -y install nodejs
ufw allow OpenSSH && ufw enable                      # dışarıya sadece SSH açık; Studio Tailscale'den
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab
curl -fsSL https://tailscale.com/install.sh | sh     # normal (kernel) mod; root olduğu için userspace gerekmez
```

### Faz 2 — Content Factory kurulumu (`factory` kullanıcısıyla)
```bash
git clone https://github.com/aliakay/content-factory.git ~/content-factory && cd ~/content-factory
curl -fsSL https://claude.ai/install.sh | bash      # Claude Code CLI
./install.sh                                         # venv, requirements, Chromium, klasörler, testler
(cd motion && sudo npx playwright install-deps chromium)    # Chromium'un sistem kütüphaneleri
claude                                               # Ali'nin (sahip) hesabıyla giriş; claude.ai'de ElevenLabs bağlayıcısı açık olmalı
```
`config.env`: `CF_HOST=127.0.0.1` (dışarıya değil, Tailscale serve'e açılır). Diğer `CF_*` satırları boş kalabilir
(#26 ile boş değer otomatik demek).

### Faz 3 — Verinin taşınması (eski sunucudan)
Eski sunucuda servisleri durdur, sonra kopyala. SQLite'ı dosya kopyasıyla değil `.backup` ile al, açık bir veritabanı
bozuk kopyalanabilir.
```bash
# eski sunucuda
sqlite3 data/factory.db ".backup data/factory.db.tasima" && sqlite3 data/radar.db ".backup data/radar.db.tasima"
rsync -a data/factory.db.tasima data/radar.db.tasima data/*.json data/styles data/own_styles data/channels data/art \
         assets out projects refs .env  factory@<yeni-ip>:~/content-factory/staging/
```
Yeni sunucuda `.tasima` dosyalarını `factory.db` / `radar.db` adıyla `data/` altına, gerisini yerine koy.
- `data/users.json`, `data/eleven_accounts.json`, `.env` gizli dosyalar: izinleri `600` kalsın.
- `data/eleven_profile.json` sahibin ses profili. Sahip değişiyorsa sesler yeniden seçilir.
- Taşımadan sonra eski sunucuda Content Factory'yi tekrar başlatma (iki kopya aynı Keşif işlerini yapar).

### Faz 4 — Tailscale ve erişim
- [ ] Eski sunucunun Tailscale kaydını kaldır (admin panel → Machines → `content-factory` → Remove). Böylece adı
      yeni makine alır ve **telefondaki kısayollar aynı adresle çalışmaya devam eder**:
      `https://content-factory.<tailnet>.ts.net/`
- [ ] `sudo tailscale up --hostname=content-factory`
- [ ] Yayın (sadece tailnet içi, internete kapalı):
```bash
sudo tailscale serve --bg --https=443  http://127.0.0.1:8501   # Studio
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8095   # Shorts
sudo tailscale serve --bg --https=8444 http://127.0.0.1:8503   # Streamlit
```
- [ ] Admin panel → `content-factory` → **Share** → Ali'nin e-postası. Ali sadece bu makineyi görür.
- [ ] Telefonlar: Tailscale açık → Safari/Chrome'da adresi aç → giriş → "Ana Ekrana Ekle".

### Faz 5 — Kullanıcılar ve hesaplar
```bash
.venv/bin/python bin/users.py add ali "Ali" owner     # şifreyi yazdırır
.venv/bin/python bin/users.py add cem "Cem" member
```
- [ ] Üye: Studio → Hesaplar → Claude'u bağla (tam giriş; ElevenLabs bağlayıcısı da gelir) ya da ElevenLabs API
      anahtarı ekle.
- [ ] Sahip: kendi ElevenLabs hesabını paylaşacak mı, aylık sınır ne olacak (Hesaplar sayfası).
- [ ] Kredi tavanı: `credits.MONTHLY_CAP` bugün 100.000. Günde 4 video ≈ 60.000/ay.

### Faz 6 — Servisler ve zamanlanmış işler (`crontab -e`, `factory` kullanıcısı)
```cron
@reboot     sleep 20; cd ~/content-factory && bin/start-factory.sh >> data/start.log 2>&1
*/5 * * * * cd ~/content-factory && bin/start-factory.sh >> data/start.log 2>&1
# Keşif (Türkiye saati)
40 8  * * * cd ~/content-factory && .venv/bin/python -m factory.discover --only tr_gundem >> data/discover_cron.log 2>&1
30 10 * * * cd ~/content-factory && .venv/bin/python -m factory.discover --region global  >> data/discover_cron.log 2>&1
10 11 * * * cd ~/content-factory && .venv/bin/python -m factory.discover --only tr_spor   >> data/discover_cron.log 2>&1
20 13 * * * cd ~/content-factory && .venv/bin/python -m factory.discover --only tr_tech   >> data/discover_cron.log 2>&1
30 23 * * * cd ~/content-factory && .venv/bin/python -m factory.discover --only tr_spor   >> data/discover_cron.log 2>&1
# günlük yedek, 14 gün saklanır
15 4  * * * cd ~/content-factory && mkdir -p backups && sqlite3 data/factory.db ".backup backups/factory-$(date +\%F).db" && find backups -name 'factory-*.db' -mtime +14 -delete
```
- Radar: `.env`'de `YOUTUBE_API_KEY` dolunca `17 9 * * *` ile `radar.cli run` eklenir.
- Yedeği sunucunun dışına da almak iyi olur (Contabo Object Storage ya da birimizin bilgisayarına haftalık rsync).
  Disk arızasında veritabanı tek kopya kalmasın.

### Faz 7 — Doğrulama
- [ ] `.venv/bin/python -m pytest -q` (tamamı geçmeli).
- [ ] İkimiz de telefondan giriş yapıp kısayolu ekleyelim.
- [ ] Her birimiz bir test videosu üretelim. Kartta doğru isim (👤), ses doğru ElevenLabs hesabından, Claude doğru
      abonelikten gitti mi (Hesaplar sayfası ve ElevenLabs bakiyesi)?
- [ ] Biri diğerinin üretimini onaylasın. Geçmişte onaylayanın adı görünüyor mu?
- [ ] Ertesi sabah: Keşif kartları geldi mi, yedek dosyası oluştu mu?

### Faz 8 — Eski kopyaları kapatma
- [ ] Eski sunucuda Content Factory cron satırlarını kaldır, servisleri durdur. Klasörü 2 hafta yedek olarak
      sakla, sonra sil.
- [ ] Yerel kopyalar (Mac'ler) sadece geliştirme için kalır, üretim yapılmaz.

## 5. Günlük işleyiş

- **Kod değişikliği:** yerelde branch → PR → `main`. Sunucuda elle kod değiştirilmez.
- **Sunucuyu güncellemek:**
  ```bash
  cd ~/content-factory && git pull --ff-only && .venv/bin/pip install -q -r requirements.txt \
    && pkill -f 'studio/server.py|shorts/server.py|streamlit run factory/app.py'; bin/start-factory.sh \
    && .venv/bin/python -m pytest -q
  ```
  `git pull` çalışan sunucuları yenilemez, yeniden başlatmak şart.
- **Kim güncelleme yapar:** sırayla değil, merge eden kişi aynı gün sunucuyu günceller ve diğerine haber verir.
- **Gizli dosyalar** (`.env`, `data/users.json`, `data/eleven_accounts.json`) git'e girmez, sadece sunucuda durur.

## 6. Hızlandırma işleri (sunucudan bağımsız, bedava)

1. **Kısa videolarda paralel render:** `PAR_MIN_S` düşürülsün ki 30–60 sn'lik shorts da birden çok Chromium'la
   çizilsin. 8 vCPU'da en büyük kazanç bu olur. Önce/sonra ölçülüp ayrı PR.
2. **Tasarım aşaması (~40 dk):** Opus tasarımının ve kendi kendini kontrol turlarının ne kadar sürdüğü ölçülsün.
   Gereksiz tur ya da bazı adımlarda Sonnet. Kaliteyi etkileyebilir, birlikte karar.
3. **Hazır look tercih etmek:** `tech`, `paper` ve film stilleri ~8 dk. `auto` her video için şart değil.
4. **Kapak karesi:** üç test videosunda da QA kapağı boş buldu. Ayrı düzeltme.

## 7. Maliyet özeti (aylık, günde ~4 video)

| Kalem | Kim öder | Tahmin |
|---|---|---|
| Contabo Cloud VPS 30 | ortak | ~14 € |
| ElevenLabs (~500 kredi/video) | işi başlatan | ~60.000 kredi toplam |
| Claude (araştırma, senaryo, tasarım, QA) | işi başlatan; cron'lar sahipten | abonelik limitleri izlenmeli, `auto` look ağır |
| Tailscale | — | ücretsiz plan yeterli |
