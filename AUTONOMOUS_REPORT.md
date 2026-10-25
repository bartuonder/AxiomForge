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
