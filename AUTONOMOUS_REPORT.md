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

### Adım 4: literatür alımı (tamam)

- **Ne eklendi:** `app/tools/arxiv.py`: `arxiv_ids(metin)` sorguda `arxiv.org/abs|pdf|html/ID`, `arXiv:ID` ve eski biçim (`cs/0112017`) kimliklerini bulur (sürüm eki atılır, en çok 3); `fetch_arxiv_papers(ids)` arXiv API'sinden `id_list` ile başlık, özet, yazarlar, yıl ve kanonik bağlantıyı getirir (bulunamayan kimlik hata verir); `citation(kağıt)` "Grinsztajn, Oyallon and Varoquaux, arXiv:2207.08815 (2022)" biçiminde künye üretir (4+ yazar: "X et al."); `fetch_passages(id)` arxiv.org/html ve ar5iv'den makalenin Conclusion/Discussion/Summary bölümlerini (en çok 3000 karakter) alır, sayfa yoksa sessizce boş döner.
- **Hat:** `run_literature_search` sorguda arXiv kimliği varsa aramayı ve LLM'i atlar, anılan makaleleri (başlık, özet, url, `citation`, `passages`) doğrudan kaynak yapar. Planlayıcı kaynak metnine sonuç bölümünü ekler (alıntı doğrulaması sonuç bölümünden de yapılır), kaynağın künyesini spec'e `source.citation` olarak yazar ve makaleden gelen her iddianın alıntısını spec'e `claims[].quote` olarak saklar (`spec.py` doğrular, 500 karakter sınırı).
- **"Makale vs bizim" karşılaştırması:** alıntılı iddialar için rapora "Comparison with the source" bölümü eklendi: "The source states: “…”. The campaign result agrees with the source / disagrees with the source, the opposite held / …" ve her ölçüt için `[E#]` atfı; aynı bilgi tartışma olguları arasına (`comparison_sentences`) girdi. Kaynağı kullanıcı sorgusu olan iddialarda bölüm yok.
- **Canlı doğrulama:** gerçek arXiv'de `2207.08815` (yazarlar, künye, 1745 karakterlik sonuç bölümü) ve `2106.03253` getirildi. İkincisinde planlayıcı "Deep Models" adını eşleyemeyip tüm adayları reddetti; bu bir hata sınıfıydı: `deep models`, `deep learning models`, `deep neural networks` MLP vekili olarak eşlendi (TabNet bilinçli olarak eşlenmeden bırakıldı), yeniden denemede 3 aday üretildi.
- **Gözlem (çözülmedi):** aynı koşuda ikinci adayın alıntısı ("it is much more challenging to optimize deep models than XGBoost") iddiasını ("…even when models are tuned") tam desteklemiyor; alıntı doğrulaması yalnızca alıntının kaynakta bulunduğunu denetler, iddiayı desteklediğini değil.
- **Test:** `test_arxiv_references`, `test_literature_references`, `test_campaign_planner_references`, `test_campaign_source_comparison` (+ spec/planlama testleri); 63 mutasyon, 13 hayatta kalan: 12'si testle kapatıldı, 1'i eşdeğer (hata girdisini atlama).
- **Maliyet:** arXiv istekleri ücretsiz; LLM yalnızca adım 5'in planlayıcı koşusunda.

### Adım 5: ajan kıyası (tamam)

Kod: `app/campaign/benchmark.py` (10 bilinen iddia: 5 yerleşik doğru, 5 tersi; `score_campaign`, `score_plan`), 30 test, 15 mutasyon (hepsi yakalandı). Sonuçlar bu oturumda gerçek E2B ve gpt-4o ile alındı.

**A. Motor doğruluğu (LLM yok; 9 benchmark veri seti, 7 model, 10 iddia, 3 ölçüt):**

| Koşu | Doğru | Yanlış yön | Kararsız | Süre |
|---|---|---|---|---|
| Varsayılan parametreler (`benchmark-default`) | 10/10 | 0 | 0 | 4 dk 20 sn |
| Ayarlı, 12 iterasyon (`benchmark-tuned`) | 10/10 | 0 | 0 | 10 dk 56 sn |
| Yakın çiftler kontrolü (RF↔ExtraTrees, HGB↔GB, iki yönlü; `benchmark-near-equal`) | 4/4 "inconclusive", 0 sahte pozitif | – | – | ≈3 dk |

Sınırlar: iddialar büyük etkili ve ön bilgiyle seçildi, yani zor vaka yok; yakın çiftler kontrolü yalnızca 4 iddia. Ayarlı koşuda hiçbir ayar etkisi anlamlı çıkmadı (9 veri setinde Holm 21 karşılaştırma üzerinden en küçük ulaşılabilir p 0,08'in üzerinde; bu bir güç sınırı, ayarın etkisiz olduğu anlamına gelmez). Bunu ileri iş olarak bırakıyorum: Holm ailesini model başına daraltmak.

**B. Planlayıcı (gpt-4o, 10 sorgu, kaynak yok, ≈30 sn):** 10 sorgudan 9'unda ilk aday birebir doğru yönde ve doğru model kümeleriyle çıktı (`exact_first` 9/10), ters yön 0. B2'de ("gradient boosting … decision tree") planlayıcı "gradient boosting"i beş modelli bir aileye genişletti (GB, HGB, XGBoost, LightGBM, CatBoost); yön doğru, küme farklı. Her sorguda yalnızca 1 aday döndü (üçe tamamlayan farklı iddia bulunamadı). Arxiv kimlikli iki sorgudan biri ilk denemede "Deep Models" adı yüzünden reddedildi (yukarıda düzeltildi), diğeri 3 aday verdi.

**C. Meta makale kapısı (gpt-4o, benchmark-default'un 10 iddiası):**

| Durum | İlk taslak geçti | Bir yeniden yazımdan sonra |
|---|---|---|
| Değişiklikten önce (6 örnek) | 0/6 | 0/6 |
| Sonra (8 örnek) | 3/8 | 5/8 |

Neden: model Discussion'da "on all datasets" (kapı tarafından reddedilen genelleme ifadesi) ve "demonstrated/supported" yazıyordu; geri bildirim de hangi kelimenin alternatifi olduğunu söylemiyordu. Yapılanlar: (1) olgu cümlesi "on every dataset tested (9 of 9)" biçimine alındı; (2) üretilen düzyazıdaki kapsamsız "all/every dataset(s)" deterministik olarak "all the datasets tested" biçimine çevriliyor (kapsamlı ifadeler dokunulmadan kalıyor); (3) kapı, "tested/examined/studied/evaluated/included/in this campaign…" ile kapsamı belli "all datasets"i artık reddetmiyor; (4) sistem istemi yasak ifadeleri ve alternatifini söylüyor, kapının kesinlik-kelimesi geri bildirimi yasak kelimeleri ve "scored higher" gibi düz karşılaştırmayı öneriyor. Kalan başarısızlık "supported/demonstrated" kelimeleri; üretimde iki tur yeniden yazım var, buna rağmen bu 10 iddialık geniş kampanyada kalan ≈%40 oran `needs_review`'a düşebilir. Bu oran 8 örnekten, istatistik değil gösterge.

**Maliyet (oturum toplamı, tahmini):** E2B: ≈40 kutu-koşusu (adım 3 duman koşuları 4, kıyas 3 kampanya × 9 veri seti + 4 duman), LLM: planlayıcı ≈15 çağrı, kapı kıyası 20 örnek ≈ 35 çağrı, her biri ≈4–6 bin token; toplam ≈1–2 USD gpt-4o ve birkaç dolar altında E2B.

## Dondurulan / yapılmayan

- Holm ailesinin model başına daraltılması (ayar etkilerinin gücü), alıntının iddiayı gerçekten desteklediğinin denetimi, HF veri seti revision'ının sabitlenmesi (yalnız kaydediliyor) ve kapının "supported/demonstrated" kalıntısı açık ileri iştir. Hiçbir hata 3 iterasyonu aşmadı, kota sorunu yaşanmadı.
