# Otonom çalışma raporu

Bu dosya, kullanıcı bilgisayar başında değilken yürütülen otonom oturumun kaydıdır (25 Ekim 2026 devamı). Kapsam: 1 → 2 → 3 → 4 → 5 sırası (tekrarlanabilirlik künyesi, moderatör analizi, ayarlı protokol, literatür girişi, ajan kıyası).

## Kurallar (kullanıcının talimatı)

- Önce test, sonra özellik; her özellik mutasyonla sınanır; mevcut 2011 testin hiçbiri kırılmaz.
- Biten her mantıksal parça anında yerel dala commit edilir (push yapılmaz).
- API kotası dolarsa ya da bir hata 3 iterasyondan uzun sürerse sonsuz döngüye girilmez: temiz durum commit edilir, süreç dondurulur.
- Mimari kararlar, çözülen hatalar, harcanan maliyet ve 5. adımın kıyas sonuçları bu dosyada tutulur.

## Başlangıç durumu

- Dal `main`, `origin/main` ile eşit, 2011 test geçiyor.
- Docker konteynerleri (Redis, Postgres) kapalı, servisler kapalı; gerçek koşular gerektiğinde açılıp kapatılır.

## Adım günlüğü

(her adım bittikçe aşağıya eklenir)

### Adım 1: tekrarlanabilirlik künyesi (tamam)

- **Ne eklendi:** `app/campaign/provenance.py`. Sandbox betiği veri bloğundan sonra bir `provenance` satırı basıyor: HF veri seti revision'ı (`HfApi().dataset_info(...).sha`), Python sürümü ve numpy/pandas/scikit-learn/scipy/datasets (+ modelin kendi paketi, ör. xgboost) sürümleri. Hub'a ulaşılamazsa `unknown`, hata vermez.
- **Defter ve rapor:** her `dataset` defter kaydı `provenance` taşıyor; rapor Protocol bölümünde veri seti satırında kısa revision (10 karakter), bir `Environment:` cümlesi (ortam tüm veri setlerinde aynı mı, farklıysa hangi veri setleri) ve `Specification: SHA-256 …` satırı var.
- **Ön kayıt (pre-registration):** spec'in SHA-256 özeti kuyruğa alınırken durum dosyasına yazılıyor; `execute_campaign` onaydan sonra spec değişmişse `CampaignSpecError` ile reddediyor ("the specification changed after it was queued"). Önceki durumda özet yoksa (eski kayıt) engellemiyor.
- **Karar:** HF revision'ı sabitleme (pin) yapılmadı, yalnız kaydedildi. Neden: `loader_code` tek veri setli deney hattında LLM'in AST ile birebir yapıştırdığı blok; çıktısını değiştirmek o hattı kırar. Pin gerekirse kampanya betiğine özel yükleyici gerekir (ileri iş).
- **Test:** 48 test (`tests/test_campaign_provenance.py`) + 43 mutasyon; 4 hayatta kalan (kendini referans alan test, ensure_ascii, `sys.version`, rapor kapsamı) bilinen cevaplı testlerle kapatıldı. Tam paket 2099 test geçiyor.
- **Maliyet:** yok (tümü yerel testler).

### Adım 2: moderatör analizi (tamam)

- **Ne eklendi:** `app/campaign/descriptors.py` (sandbox'ta ham `X` üzerinde dört veri seti tanımlayıcısı: kategorik öznitelik payı, öznitelikler arası ortalama mutlak korelasyon, ortalama mutlak çarpıklık, eksik değer payı; profilden iki tanesi: öznitelik sayısı ve azınlık sınıf payı) ve `app/campaign/moderators.py` (her iddia ve ölçüt için "alt ailenin en iyisi eksi diğer ailenin en iyisi" farkının veri setleri arasında her tanımlayıcıyla Spearman korelasyonu, ilgili iddia ve ölçüt ailesi içinde Holm düzeltmesi, en az 6 veri seti ve değişim şartı).
- **Hat:** protokol betiği `descriptors` satırını basıyor; koşucu ayrıştırıp `descriptors` olarak saklıyor; analiz `moderators` döndürüyor; defter `moderator` kayıtları ve veri seti `descriptors` alanı ekliyor; rapor "Exploratory moderator analysis" paragrafı yazıyor (anlamlı olanlar `grew`/`shrank with …` cümleleriyle ve `[E#]` atıfıyla, hiçbiri anlamlı değilse tek düz cümle, test edilebilir satır yoksa bölüm yok); meta rapor için `moderator_sentences` kanıt cümleleri Discussion olgularına eklendi; MLflow'a `moderator/{iddia}/{ölçüt}/{tanımlayıcı}/rho` ve `adjusted_p_value` yazılıyor.
- **Karar:** analiz keşif amaçlı olarak etiketlendi (9 veri setiyle güç düşük); Spearman p değeri scipy'nin standart hesabı (kesin permütasyon değil). Tam korelasyonda scipy p = 0 döndürüyor; Holm testinde bu yüzden tam olmayan bir korelasyon kullanıldı (ilk sürüm bunu yakalayamıyordu, mutasyon taraması gösterdi).
- **Test:** 42 (tanımlayıcı + moderatör) + 28 (hat) test, 64 mutasyon; 3 hayatta kalan (etiket metni, işaretsiz çarpıklık, Holm yerine ham p) testle kapatıldı. Tam paket 2186 test geçiyor (3 atlandı: xgboost, lightgbm, catboost yerelde yok).
- **Maliyet:** yok (yerel).

### Adım 3: ayarlı (tuned) protokol (tamam)

- **Ne eklendi:** `app/campaign/tuning.py` (17 tahminci için ayrık arama uzayları, `validate_tuning`, `tuning_code`, `parse_tuning`). Spec'e `tuning` alanı (`iterations` 4–40, varsayılan 12; `folds` 3–5, varsayılan 3), `params` ile birlikte kullanılamaz. Sandbox betiği veriyi sabit tohumlu (0) bir bölmeyle ikiye ayırıyor: %20 stratified ayarlama kümesi ve %80 değerlendirme kümesi. Her model için `ParameterSampler` ile rastgele arama, ölçüt ROC-AUC (`cross_val_score`, `error_score=nan`); seçilen yapılandırma değerlendirme kümesinde tohumlarla koşuyor ve her model yanında `Model__default` (kütüphane varsayılanı) kontrolü de koşuyor.
- **Hat:** koşucu `execute=None` iken ayarlı spec için uzun sandbox'ı (`TUNED_RUN_TIMEOUT_SECONDS=900`, `TUNED_LIFETIME_SECONDS=1100`) seçiyor; analiz her ayarlı modeli kendi varsayılanıyla karşılaştırıyor (`parameter_effects`); defter veri seti kaydına bulunan yapılandırmaları ve satır sayılarını yazıyor; rapor arama cümlesini, "Selected configurations" bloğunu, "(N used for evaluation)" ifadesini, "tuned by random search" etki cümlelerini ve tuned sınırlılık maddesini ekliyor; meta rapor kanıtına `effect_sentences` giriyor; MLflow'a `tuned/{model}` parametresi ve `tuned/{model}/cv_roc_auc` metriği yazılıyor; planlayıcı adayları `tuned` bayrağı taşıyabiliyor, maliyet tahmini kontrol koşularını ve arama süresini hesaba katıyor; CLI `--tuning N`.
- **Çözülen hatalar:** (1) ayarlı kutunun ömrü 1000 sn idi, 900 sn çalışma + 120 sn kurulumdan az; 1100'e çıkarıldı (test yakaladı). (2) mutasyon taraması, ayarlı modelin kontrol girdisinden sonra `continue` olmazsa sözlükte aynı anahtarla ayarsız modelin ayarlıyı ezeceğini gösterdi; "her model tam bir kez kurulur" testi eklendi. (3) canlı koşu: CLI'den ayarlanan hazır kampanyada "No hyperparameter search" sapma notu kalıyordu; CLI artık onu ayar notuyla değiştiriyor (`planning.tuning_note`).
- **Test:** `tests/test_campaign_tuning.py`, `tests/test_campaign_tuned_pipeline.py`; 87+5 mutasyon, 9 hayatta kalan (biri eşdeğer: bool denetimi, gereksiz olduğu için kaldırıldı; kalan 8 testle kapatıldı). Tam paket 2260 test geçiyor.
- **Canlı doğrulama (gerçek E2B):** `grinsztajn-2022`, `tb_credit` + `tb_electricity`. Adım 1 ve 2'nin sandbox kodu da ilk kez gerçek kutuda sınandı: `provenance` (revision `8d0ff91035`, Python 3.13.16, kütüphane sürümleri) ve `descriptors` satırları doğru ayrıştı, rapora ve deftere girdi. 4 iterasyon: 83 ve 70 sn/veri seti; 12 iterasyon: 132 ve 149 sn/veri seti. Maliyet tahmini 4 iterasyonda 151 sn, 12'de 191 sn (gerçeğin 1,3–1,8 katı, temkinli); kalibrasyon değiştirilmedi.
- **Maliyet:** 4 küçük E2B kutusu (≈10 dakika toplam), LLM yok.
