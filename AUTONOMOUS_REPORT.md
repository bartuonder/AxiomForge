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

## Takip: yüksek öncelikli üç madde (26 Ekim 2026)

1. **Meta makale kapısının geçiş oranı.** Yeniden yazım turu modele reddedilen taslağı göstermiyordu, bu yüzden her turda sıfırdan yazıp aynı "supported" kelimesine dönüyordu. `write_prose` artık reddedilen Introduction ve Discussion'ı da brief'e koyuyor ("Keep every sentence that the reasons do not touch and change only what they require"). Üretimdeki üç taslaklı döngüyle (ilk taslak + 2 yeniden yazım) 10 iddialık kampanyada ölçüm: **6/10 → 10/10** geçiş (ilk taslakta 7/10, kalan 3'ü üçüncü taslakta). 10 örnekle gösterge, istatistik değil. 12 mutasyon, 1 hayatta kalan test ile kapatıldı.
2. **Alıntının iddiayı desteklediği denetimi.** `campaign_planner._support_issues`: makaleden gelen iddialar için aday başına tek ek LLM çağrısı ("hakem"), alıntının öznenin diğerlerinden daha iyi olduğunu söyleyip söylemediğine bakıyor; ilgili ama farklı bulgu (ayar zorluğu, hız, maliyet), ters yön veya yanlış model çifti desteklemiyor sayılıyor. Reddedilen aday nedeniyle birlikte planlayıcıya geri dönüyor (mevcut yeniden deneme döngüsü); hakem bozuk cevap verirse planlama durur (sessizce geçmez). Kullanıcı sorgusundan gelen iddialar hakemden geçmez. Canlı doğrulama: önceki zayıf alıntı ("…more challenging to optimize deep models than XGBoost…"), ters yönlü iddia ve yanlış çift reddedildi; iyi iki vaka geçti (5/5). İki gerçek arXiv sorgusunda planlayıcı yine 3'er aday üretti. Testler: 22 yeni test, 26 mutasyon (1 hayatta kalan test ile kapatıldı); `tests/conftest.py` hakem çağrısını varsayılan olarak engelliyor, planlayıcıyı gerçekten çalıştıran testler `approve_judge` fixture'ını kullanıyor. Maliyet: aday başına bir ek gpt-4o çağrısı (en çok 3 çağrı/deneme).
3. **XGBoost, LightGBM, CatBoost ayarlı protokolde canlı.** `smoke-boost` kampanyası (2 veri seti, 6 iterasyon, 4 model) gerçek E2B'de 1 dk 16 sn'de bitti; üç kütüphane de ayarlandı ve koştu, rapora sürümler yazıldı (xgboost 3.4.1, lightgbm 4.7.0, catboost 1.2.10), seçilen yapılandırmalar listelendi. Kod değişikliği gerekmedi. Not: XGBoost ve LightGBM aynı ızgara ve tohumla aynı yapılandırmayı seçti, bu beklenen.

Tam paket 2431 test geçiyor (3 atlandı).

## Takip 2: Holm ailesinin daraltılması (26 Ekim 2026)

- **Sorun:** ayar (ve listelenen parametre) etkileri tek bir Holm ailesinde düzeltiliyordu: 7 model × 3 ölçüt = 21 test. 9 veri setinde tek bir testin ulaşabileceği en küçük kesin p 2/512 = 0,0039; ×21 = 0,082 > 0,05. Yani 9 veri setinde ayarın etkisi, her veri setinde aynı yönde olsa bile anlamlı çıkamazdı (`benchmark-tuned` koşusunda hiçbir etki anlamlı çıkmamasının nedeni buydu).
- **Karar:** aile artık bir modelin üç ölçütü (iddiaların ölçütlerle düzeltilmesiyle aynı mantık: "ayar bu modele yarar mı?" tek bir soru, üç ölçüt onun üç görünümü). `adjusted_p_value` / `significant` bu ailedir; en küçük ulaşılabilir değer 3 × 2/512 = 0,0117.
- **Dürüstlük önlemi:** modeller arası çoklu test artık düzeltilmiyor, bu yüzden katı ayarlama da hesaplanıyor: `adjusted_p_value_all` / `significant_all` (tüm model ve ölçütler tek ailede). Rapor Statistics paragrafında aileyi söylüyor ("The effect of tuning is adjusted across the metrics of each model.") ve Limitations'a "Significant tuning effects within their model: N; of these, K remain significant when the adjustment spans all models and metrics." cümlesini ekliyor (en az iki etki modeli ve en az bir anlamlı etki varsa). 7 model ve 9 veri setiyle her veri setinde aynı yönde etki durumunda: 21 etki model içinde anlamlı, 0'ı katı ayarlamada anlamlı; bu fark okuyucuya açıkça gösteriliyor. MLflow'a `adjusted_p_value_all` ve `significant_parameter_effects_all` yazılıyor.
- **Test:** `tests/test_campaign_effect_family.py` (17 test), 24 mutasyon, hayatta kalan 1 eşdeğer (aile sırası). Tam paket 2448 test geçiyor.
- **Eksik:** canlı doğrulama yapılmadı. Eski `benchmark-tuned` kaydında varsayılan kontrol skorları olmadığı için yeniden analiz edilemiyor; yeni bir ayarlı koşu (≈11 dk E2B) gerekir.

## Takip 3: 12 maddelik liste, otonom oturum (26 Ekim 2026)

Kullanıcı dışarıdayken, onay beklemeden, TDD ve mutasyon testiyle, her parça ayrı commit olarak yapıldı. Push yapılmadı. Başlangıç 2448 test, bitiş **2628 test geçiyor** (3 atlandı: xgboost, lightgbm, catboost yerelde yok). Servisler (Postgres, Redis, MLflow) iş bitince kapatıldı.

### Canlı koşu: Holm doğrulaması + zor kıyas birleşik (`hard-tuned`)
- **Kurgu:** 10 bilinen iddia (B1-B10) + 6 yakın çift iddiası (N1-N6: RandomForest↔ExtraTrees, HistGradientBoosting↔GradientBoosting, LogisticRegression↔LinearSVC, iki yönlü), 10 model, 9 benchmark veri seti, ayarlı protokol (12 iterasyon, 3 katlı). E2B, LLM yok, **10 dk 35 sn**.
- **Bilinen iddialar:** 10/10 doğru (5 replicated, 5 contradicted).
- **Yakın çiftler:** 6 iddianın 6'sı `inconclusive`; karar verilen iddia oranı 0/6; iki yönde de `replicated` çıkan çift yok. Yani bu 3 çiftte motor sahte pozitif üretmedi (az sayıda çift; kesinlik iddiası değil).
- **Ayar etkileri (Holm'ün model başına daraltılmasının canlı doğrulaması):** 30 etki, 27 testlenebilir; **model içinde 9'u anlamlı, katı (tüm model ve ölçütler tek aile) düzeltmede 0'ı**. Önceki tek ailede hiçbiri anlamlı olamıyordu. ROC-AUC'ta öne çıkanlar: DecisionTree +0,0889 (9/9 veri setinde kazanç, p_düz. 0,0117), KNN +0,0225 (9/9), LogisticRegression +0,0002 (8/9, p_düz. 0,0234) ve **MLP −0,0022 (0/9)**: ayarlı MLP 9 veri setinin hepsinde varsayılandan biraz kötü çıktı. Muhtemel neden: ayarlama yalnız %20'lik (≈1200 satır) bir kümede 12 yapılandırmalık küçük bir aramayla yapılıyor ve sklearn MLP varsayılanı zaten güçlü; bu bir bulgu olarak raporda "tuned ... lower" cümleleriyle görünür.
- **Ders:** rapor katı ayarlamada kaç etkinin ayakta kaldığını açıkça yazıyor (Limitations), bu yüzden "9 anlamlı etki"yi tek başına okumak yanıltıcı olur.

### Madde madde
1. **Holm ailesini model başına daraltma (Takip 2'de yapılmıştı):** canlı doğrulama yukarıda.
2. **Zor kıyas:** `app/campaign/hard_benchmark.py` (yakın çiftler, etki sayıları, Wilson aralığı, 8 muğlak planlayıcı sorgusu). **Planlayıcı (gpt-4o, 8 sorgu):** ilk koşuda 6/8 kabul edilen sonuç; iki gerçek hata yakalandı: (a) "Random forests do *not* outperform a decision tree" cümlesini planlayıcı ters çevirip "DecisionTree RandomForest'ı geçer" iddiasına çeviriyordu, (b) "Transformers outperform SVMs" cümlesini "transformer çalıştırılamaz" diye reddediyordu (oysa MLP vekiline eşlenir). İstem düzeltildi (olumsuz cümlede olumlu iddia test edilir, ters çevrilmez; çalıştırılamayan mimari MLP'ye eşlenir, `unsupported` gerekçesi olmaz). **Yeniden koşuda 8/8 (Wilson %95: 0,68-1,00).** Kapı geçiş oranı için `tools/bench_gate_loop.py` Wilson aralığıyla raporluyor.
3. **Konsol:** onay penceresi ayarlı kampanyayı ("Tuned: random search of N configurations per model, K-fold cross-validation") ve künyeyi gösteriyor; sorguda arXiv kimliği/bağlantısı varsa form bunu söylüyor; `/campaigns` sayfasında hazır kampanya (`grinsztajn-2022`) için onaylı başlatma düğmesi var. `frontend/lib/campaignView.ts` + `npm test` (Node'un yerleşik test koşucusuyla 10 test); `tsc`, `eslint` ve `next build` temiz.
4. **MLflow canlı sunucu:** gerçek `mlflow server` karşısında kampanya 132 metrik, 7 parametre, `ledger.json` ve `report.md` artefaktıyla kaydedildi (artefakt vekili çalışıyor, sessiz atlama yok). Eksik olan **meta makale** artık kampanyanın MLflow run'ına `paper.md`, `paper_status` etiketi ve `paper_rewrites` metriği olarak yazılıyor (`log_meta_paper`, hata durumunda araştırmayı düşürmez); canlı run'da doğrulandı. Deney hattı için `statistical_decision.json` artefaktı eklendi.
5. **HF revision sabitleme:** spec'te `revisions` ({veri seti: 40 karakter commit}); protokol `load_dataset(..., revision=...)` ve `dataset_info(..., revision=...)` kullanır, rapor "Dataset revisions pinned in the specification" yazar, CLI `--pin-from KAMPANYA` eski kampanyanın deftere yazdığı revision'ları kopyalar. Canlı doğrulama: `live-pinned-1` iki veri setinde sabitlenmiş revision'la tamamlandı. Eski deney hattının `loader_code`'u değişmedi.
6. **Planlayıcı adayları:** model 3'ten az aday önerirse ilk adaydan belirleyici üretilen "ROC-AUC only" ve "tuned" varyantlarıyla tamamlanır (`FILL_VARIANTS`), varyantlar tek bir spec dönüşümüdür (başlık sınırı aşarsa atlanır); imza artık ayar bilgisini de içerir.
7. **`/approve_plan`:** `PlanDecisionError` ile bilinmeyen thread 404, yanlış durumda/ikinci karar 409, geçersiz karar harfi 422; gerçek çalışma zamanı hatası 503 kalır.
8. **Bayat işçi (deney hattı):** son checkpoint 30 dakikadan eskiyse araştırma `failed` ve "its worker may have stopped" gerekçesiyle görünür (`STALE_RESEARCH_SECONDS=1800`); onay bekleyen, reddedilen, biten ve kampanya bekleyen thread'ler muaf.
9. **Temizlik:** ölü kod (`models_dropped`, `performance_dropped`, `DROP_LIMIT`, `parse_metrics`, `log_classification_run`) testleriyle birlikte silindi. Hakem istemi sadeleştirmesi **yapılmadı**: istem zaten "temiz kontrolü issues'a koyma" diyor; ölçülebilir bir gürültü kanıtı yok.
10. **OpenAI kredisi ve kalıp kapıları:** araştırma kuyruğa girmeden önce tek token'lık bir çağrıyla anahtar ve kota denetlenir (`insufficient_quota` ve reddedilen anahtar 503; ağ hatası/geçici hız sınırı engellemez). Kalıp kırılganlığında somut bir yanlış alarm bulunup düzeltildi: "tam veri seti bölündü, ölçekleyici eğitim satırlarına uydurulduğu" cümlesi sızıntı sayılıyordu (`_FITTED_ON_TRAINING` muafiyeti, 10 mutasyon, 2'si eşdeğer/ihmal edilebilir sınır). On yedi kontrolün genel yanlış alarm oranı **ölçülmedi**.
11. **Altyapı:** `.github/workflows/ci.yml` (backend `pytest`, frontend `npm ci`/`npm test`/`tsc`/`lint`/`build`) ve yapısını denetleyen test; Dockerfile **yerelde yeniden inşa edildi** (`python -c "import app.main, app.tasks"` adımı dahil, başarılı), imaj silindi. Test kalıntısı silme aracı **yazılmadı**: silme kararı kullanıcıya ait, hangi satırın test verisi olduğu güvenle ayırt edilemiyor.
12. **İstatistik varsayımı (simülasyon, `tools/sim_power.py`, 150 tekrar):** düzeltilmiş yeniden örneklemeli t testi deney hattında **muhafazakâr**: boş durumda ret oranı 5 bölmede %2,0, 10 bölmede %0,7 (hedef %5); orta fark (derinlik 6'ya karşı tam) gücü 5 bölmede %47 → 10 bölmede **%72**, büyük fark %93 → %99. "p değerleri iyimser olabilir" kaygısı bu kurulumda desteklenmedi; test aşırı değil, fazla temkinli. Kampanya hattı bölmeleri değil veri setlerini birim aldığı için bundan etkilenmez.

### Maliyet (oturum)
E2B: yaklaşık 35 dakikalık sandbox (hard-tuned 10 dk 35 sn × 3 eşzamanlı, birkaç duman koşu); LLM: planlayıcı sorguları ≈25 çağrı, gate kıyası önceki bölümde; OpenAI kredi denetimi 1 küçük çağrı. Tahmini toplam birkaç dolar.

### Açık kalanlar
- Katı düzeltmede ayakta kalan ayar etkisi yok; ayar protokolü küçük (20% küme, 12 yapılandırma). Daha büyük bir arama ya da daha büyük ayarlama kümesi MLP bulgusunu değiştirebilir.
- 17 regex kapısının genel yanlış alarm oranı hâlâ ölçülmedi; test kalıntısı temizliği, GitHub'da CI'ın ilk koşusu kırmızıydı (temiz checkout'ta `tsc` için `next typegen` gerekiyordu), düzeltmeden sonra yeşil; Linux'ta backend 2664 test geçti.
- Hakem isteminin sadeleştirilmesi (kanıt yok).

## Takip 4: ayarlı MLP bulgusunun yeniden sınanması (26 Ekim 2026)

**Soru:** `hard-tuned` koşusunda ayarlı MLP 9 veri setinin hepsinde varsayılandan biraz kötüydü (−0,0022, 0/9, model içinde anlamlı). Neden ayarlama kümesinin küçüklüğü (%20 ≈ 1200 satır, 3 katlı) ve aramanın küçüklüğü (12 yapılandırma) müydü?

**Yeni özellik:** spec'te `tuning.share` (0,1-0,6, varsayılan 0,2) ve CLI `--tuning-share`; rapor ve planlama notu payı yazıyor. 32 test, 24 mutasyon (hayatta kalanlar fazlalık denetimleriydi, koddan çıkarıldı ya da testle kapatıldı).

**Deney** (MLP + HistGradientBoosting, ROC-AUC, 9 benchmark veri seti, aynı bölmeler ve tohumlar, E2B, LLM yok; her biri ≈6-8 dk):

| Koşu | Ayarlama / değerlendirme satırı | MLP ayar etkisi (medyan fark) | Kazanç | Model içi düz. p | HGB ayar etkisi |
|---|---|---|---|---|---|
| `hard-tuned` (taban) | 1200 / 4800, 12 iterasyon | **−0,0022** | 0/9 | 0,0117 (anlamlı, olumsuz) | +0,0005 (6/9, n.s.) |
| `mlp-share50` | 3000 / 3000, 12 iterasyon | −0,0005 | 3/9 | 1,0 (n.s.) | +0,0016 (7/9, p 0,078) |
| `mlp-iter36` | 1200 / 4800, 36 iterasyon | −0,0006 | 2/9 | 0,92 (n.s.) | +0,0001 (5/9, n.s.) |

**Sonuç:** "Ayar MLP'yi tutarlı biçimde kötüleştirir" bulgusu **küçük ayarlama kümesi ve küçük arama artefaktıydı**: ayarlama kümesi büyüyünce de, arama 3 kat büyüyünce de etki sıfıra yakın ve anlamsız. Ayar MLP'yi iyileştirmiyor da: etki hâlâ ≤0. Seçilen yapılandırmalar bunu destekliyor: 36 iterasyonda 9 veri setinin 4'ü varsayılan `alpha=1e-4`'ü, 7'si varsayılan `learning_rate_init=0,001`'i seçti (arama varsayılana yakınsıyor); %50 kümede daha büyük ağlar (200 nöron) 1 yerine 3 veri setinde seçildi. Yani sklearn MLP varsayılanı bu ızgaranın zaten iyi bir noktası. Dikkat: %50 koşuda değerlendirme kümesi 3000 satıra düştü, gürültü arttı; bu yüzden "iyileşmedi" demek "zarar vermedi"den daha güvenli bir okuma.

**Sınır:** tek model, 9 veri seti, tek tohum seti; ızgara küçük ve ayrık. Ayar protokolünü HGB gibi güçlü modellerde bu kadar kanıtla değerlendirmek mümkün değil (etkiler binde bir basamakta).

## Takip 5: yakın çift kontrolünün 7 çifte genişletilmesi (26 Ekim 2026)

**Kod:** `NEAR_PAIRS` 3'ten 7 çifte çıktı (14 iddia, N1-N14): önceki üçe ek olarak LightGBM↔HistGradientBoosting, XGBoost↔LightGBM, LogisticRegression↔LDA, XGBoost↔HistGradientBoosting; yalnız bu iddiaları soran `near_spec()` (9 model) eklendi, `hard_spec()` 24 iddiaya çıktı. 41 test, 24 yeni mutasyonun hepsi yakalandı. Tam paket 2671 test geçiyor.

**Canlı koşular** (9 benchmark veri seti, E2B, LLM yok): `near-default` (varsayılan parametreler, ≈7 dk) ve `near-tuned` (12 iterasyon, ≈15 dk).

| | Karar verilen iddia | İki yönde de "replicated" çift | Kararsız çift |
|---|---|---|---|
| `near-default` | 3 / 14 | 0 | 5 / 7 (iki yönde de karar yok) |
| `near-tuned` | 2 / 14 | 0 | 6 / 7 |

Kararsız iddia payı için Wilson %95 aralığı: varsayılan 0,52-0,92 (11/14), ayarlı 0,60-0,96 (12/14).

**Karar verilen çiftlerin incelemesi (ön bilgi yanlış çıktı, motor değil):**
- **LogisticRegression↔LDA:** iki koşuda da LR öne çıktı (ROC-AUC farkları 9 veri setinin 9'unda pozitif: +0,0002 ile +0,131 arası, medyan +0,0038; ayarlıda 8/9). Bu bir sahte pozitif değil, gerçek ve tutarlı bir fark; LDA'nın düzenlileştirmesiz çözücüsü `credit` verisinde belirgin geride kalıyor. Çiftin "eşdeğer" ön kabulü hatalıydı.
- **XGBoost↔LightGBM (yalnız varsayılan):** LightGBM 8/9 veri setinde önde (medyan +0,0038, en çok +0,018); ayar iki modeli birbirine yaklaştırınca (ayarlı koşu) çift kararsıza döndü. Yani ayarsız karşılaştırmadaki fark büyük ölçüde varsayılan hiperparametre farkı.
- **Diğer beş çift** (RF↔ExtraTrees, HGB↔GB, LR↔LinearSVC, LightGBM↔HGB, XGBoost↔HGB) iki koşuda da kararsız.

**Sonuç:** 7 çift ve 2 koşuda motor hiçbir çiftte çelişkili karar (iki yönde de replicated) üretmedi ve kararlarını gerçek, tutarlı farklara dayandırdı. Ama "yakın çift" etiketi kendi başına bir doğru cevap değildir: iki çift ön bilgiyi çürüttü, bu yüzden bu kontrol sahte pozitif oranını **ölçmez**, yalnız aşırı tutarsızlık (çelişki) olmadığını gösterir. Gerçek bir sahte pozitif oranı için iki özdeş modelin yalnız rastgele tohumla ayrıldığı bir boş (null) karşılaştırma gerekir; protokol `random_state`'i sabit tuttuğu için bu şimdilik kurulamıyor (açık iş).
**Ayar etkileri (`near-tuned`):** 27 etkinin 24'ü testlenebilir, model içinde 1'i anlamlı, katı düzeltmede 0'ı.

## Takip 6: frontend'in ilk gerçek denemesi (26 Ekim 2026)

- Kullanıcı sunucuları açtırıp konsolu denedi. **9 veri setinde ağaç tabanlı modellerin daha iyi çıktığı sonuç göründü ve doğru**, ama sayfa "sayı cümbüşü" olarak geri bildirildi: kullanıcıya göre değil, geliştirici gözüyle yazılmış.
- **Gerçek hata:** `Replicate the central claim of arXiv:2207.08815 on tabular data.` sorgusu planlayıcıdan "kaynakta yok / iddia yok" mesajıyla döndü. Worker logunda makale doğru çekilmişti; sorun, bellekteki 3 eski "Tree-based vs Neural Networks" kampanyasının prompt'a "daha önce yapıldı" diye girip modeli reddettirmesiydi. Aynı sorgu geçmişsiz üç plan, geçmişle üç ret üretti (3/3 tekrar). Düzeltme: geçmiş yalnız bilgi için verilir, 'replicate' isteyen sorguda reddetme yasağı eklendi, ret gelirse geçmişsiz bir kez daha sorulur; tekrar işaretleri yine geçmişle hesaplanır. 10 test, 10 mutasyon (1 hayatta kalan test ile kapatıldı); gerçek bellekle canlıda doğrulandı.
- **Kullanıcıya dönük ders:** ekranda görünen hata metni asıl sebebi söylemiyordu. Hata mesajlarının sebepli ve sade yazılması `ROADMAP.md` B1-6'da.
- **Bellek kirliliği:** benchmark ve test kampanyaları kullanıcının "geçmiş" listesine karışıyor; ayrım `ROADMAP.md` A2-6'da.
- `ROADMAP.md` oluşturuldu: kalan işler (A) ve frontend / ürün yenileme listesi (B), önerilen sıra (C).

## Takip 7: kullanıcıya dönük yenileme, otonom oturum (27 Ekim 2026)

Kullanıcı yokken yol haritası adım adım, her adım ayrı commit ile yapıldı. Hedef kitle "herkes"; arayüz arka plandaki iş mantığını sade ve açıklayıcı anlatmalıydı. Hiçbiri push edilmedi (yerel dal origin'den çok commit önde). Bu bölümde canlı LLM / E2B koşusu yapılmadı; ölçümler yalnız istatistik katmanında.

### Arka uç
- `app/campaign/vocabulary.py`: 17 model, 14 veri seti, 3 ölçüt, 5 karar, durum ve 13 terimlik sözlük için TR/EN sade adlar.
- `app/campaign/summary.py::build_summary`: ham kampanya durumundan sade özet (karar cümlesi, güven düzeyi, veri seti başına skorlar, sıralama, yöntem maddeleri, dikkat notları, ilerleme, hata bilgisi). Karar kapılarına dokunmaz, yalnız sunar. 62 test, mutasyon taraması tamamen yakaladı.
- `app/friendly_errors.py`: 18 hata kodu, her biri TR/EN başlık, sebep ve "ne yapabilirsiniz" önerisi; hata metinleri `[kod] ...` etiketiyle saklanır (planlayıcı reddi, OpenAI kotası, bayat işçi, sandbox hatası vb.). 59 test.
- Yeni uçlar: `GET /campaign/{id}/summary?lang=`, `GET /glossary?lang=`, `GET /vocabulary?lang=`, `GET /usage`; `GET /research/{id}?lang=` artık `error_info` döner. Kampanyada `origin` (api / console / cli; `g-` ile başlayan kimlikler console sayılır) ve `spec.json` saklanır.
- `app/guard.py`: isteğe bağlı `API_KEY` (`X-API-Key`, sabit zamanlı karşılaştırma, 401) ve `DAILY_START_LIMIT` (varsayılan 100, 0 = sınırsız, `reports/usage.json`, 429). Başlatan dört uca bağlı. 43 test.
- `tools/null_calibration.py`: karar makinesinin sahte pozitif oranı (Monte Carlo, 4000 tekrar, 9 veri seti). **Gerçek fark yokken karar verme oranı %2,1 (Wilson %1,7–2,6), herhangi bir iddiada %3,1.** Gerçek fark +0,005 iken %4,5, +0,01 iken %18,7, +0,03 iken %98,5. Yani karar katmanı muhafazakâr: sahte pozitifi düşük tutuyor, ama 9 veri setiyle küçük farkları (≤0,01) yakalama gücü düşük. Bu yalnız istatistik katmanının ölçümüdür; gerçek iki modelin tohum-farklı karşılaştırması (`random_state` parametresi) hâlâ açık.
- `tools/memory_report.py`: planlayıcının okuduğu geçmiş kampanyaları listeler; `delete ID... --yes` yalnız açık onayla ve yalnız `experiment_memory` koleksiyonunda siler. Hiçbir şey silinmedi.

### Ön yüz
- Yeni kitaplıklar: `lib/i18n.ts` (TR/EN iletiler), `lib/format.ts`, `lib/campaignList.ts` (test/benchmark koşularını gizleme), `lib/apiErrors.ts`, `lib/download.ts`.
- Yeniden yazılan konsol: dil anahtarı (TR varsayılan, tarayıcıda hatırlanır), ana sayfada tek cümlelik açıklama + 3 adım + hazır örnek sorular, modlar "Çok veri setli sınama" / "Tek deney", sözlük balonları (`Term`), karar rozeti (renk + simge), güven göstergesi, veri seti başına çubuk grafik, katlanır sayılar, hata kutusu ("ne yapabilirsiniz" + katlanır teknik ayrıntı), onay penceresinde sade plan kartları, kampanya geçmişinde arama ve test koşularını gizleme, kampanya sayfasında Özet / Ayrıntılı rapor / Kanıtlar sekmeleri, "Raporu indir (.md)" düğmesi, API anahtarı ve günlük sınır hatalarının sade anlatımı.
- Başsız Edge ekran görüntüleriyle ana sayfa, geçmiş ve iki kampanya özeti (`hard-tuned`, `near-default`) gözle doğrulandı.
- Testler: 71 Node testi (yardımcı kitaplıklar + bileşenlerin sunucuda TR/EN çizimi, `tsx` ile); mutasyon kontrolleri yakaladı. `tsc`, `eslint`, `next build` temiz.

### Dağıtım
- `frontend/Dockerfile` (çok aşamalı, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_API_KEY` yapı argümanları), `docker-compose.yml`'a `frontend` servisi; gerçek `docker build` başarılı (görüntü doğrulama sonrası silindi). Tek komut: `docker compose up`.

### Sayılar
- Backend: 2953 pytest geçti, 3 atlandı. Frontend: 71 Node testi. GitHub CI son bilinen durumda yeşil; yeni commitler push edilmedi, dolayısıyla CI'dan geçmedi.

### Açık kalanlar
- Tek deney hattı ekranları (`ApprovalDialog`, `ResearchStatus`, makale görünümü, sonuç sayfası) hâlâ İngilizce ve teknik.
- İşçi ölümünden otomatik kurtarma yok (yalnız `failed` raporlanıyor); canlı ilerleme için tahmini süre ve iptal düğmesi yok.
- Gerçek modelle null karşılaştırma ve 17 regex kapısının yanlış alarm oranı ölçülmedi; meta makale kapısı örneklemi hâlâ küçük.
- Tarayıcıda uçtan uca (Playwright) test ve 3-5 kişilik kullanıcı gözlemi yapılmadı.
- Veritabanı test kalıntılarının silinmesi kullanıcının kararında.

## Takip 8: yapılmayanların tamamlanması (27 Ekim 2026)

Takip 7'nin "açık kalanlar" listesi üzerinde çalışıldı; her madde ayrı commit.

### Kampanya kontrolü ve işçi kurtarma
- **İptal ve yeniden başlatma.** `POST /campaign/{id}/cancel` ve `POST /campaign/{id}/retry` (ikisi de API anahtarı ister; yeniden başlatma bir başlatma hakkı harcar). İptal iş birliği yoluyladır: `cancel.flag` dosyası konur, çalıştırıcı her veri setinden ve her denemeden önce bakar; çalışmakta olan sandbox kesilmez, o veri setleri biter, sonra kampanya `cancelled` olur ve analiz üretilmez. Sıradaki kampanya hemen `cancelled` olur ve hiç başlamaz. Yeniden başlatma yalnız `failed` ve `cancelled` (bayat dahil) için, kayıtlı `spec.json` ile çalışır ve `recoveries` sayacını artırır.
- **Bayat kampanya.** 20 dakika ilerlemeyen `queued` / `running` kampanya, depoya yazılmadan, durum ve liste uçlarında `failed` (`stale: true`, `stale_worker` açıklaması) görünür. Önceden yalnız araştırma iş parçacığı bunu gösteriyordu; kampanya sayfası sonsuza dek "çalışıyor" diyordu.
- **Otomatik kurtarma.** `run_campaign_task` artık `acks_late` ve `reject_on_worker_lost`: işçi ölürse ileti yeniden teslim edilir. Redis `visibility_timeout` 2 saat (daha kısası, çalışan uzun bir kampanyanın ikinci kez teslim edilmesine yol açardı); yani tam otomatik kurtarma en çok 2 saat sonra olur, kullanıcı hemen "Yeniden başlat" ile beklemeden de başlatabilir. Tamamlanmış kampanya yeniden teslim edilirse yeniden çalıştırılmaz (para harcamamak için), yalnız grafın devamı tetiklenir. Çalışan işçiyi gerçekten öldürüp redelivery'yi canlı denemedim; davranış ayar ve birim testleriyle doğrulandı.
- **Özet.** `live` (şu an çalışan veri setleri, tahmini kalan süre = kalan tur sayısı × bitenlerin ortalama süresi, `DEFAULT_WORKERS` ile), `actions` (iptal / yeniden başlat) ve `recoveries` eklendi; ilk veri seti bitmeden süre tahmini verilmez.
- **Testler.** `tests/test_campaign_control.py` (80), `tests/test_campaign_summary_live.py` (31). Mutasyon taraması: 70 civarı mutasyon, ilk turda 6 hayatta kalan, testler güçlendirilip hepsi yakalandı; 2 eşdeğer mutant koddan sadeleştirilerek kaldırıldı.

### Konsol
- Canlı ilerleme (veri setleri, kalan süre), iptal (iki adımlı onay) ve yeniden başlat düğmeleri; iptal edilmiş / başarısız kampanya artık "deneyler sürüyor" demez.
- **Koyu tema:** sistem tercihini izler, üstteki düğmeyle elle değişir ve hatırlanır; sabit hex renkler yerine adlandırılmış renk jetonları (`globals.css`). Kontrast ölçüldü: koyu temada düğme yazısı için ayrı jeton (`on-solid`) gerekti, açık temada `faint` rengi koyulaştırıldı. Başsız Edge ile ana sayfa, geçmiş ve kampanya özeti iki temada gözle doğrulandı.
- **Tek deney hattı ekranları** (onay, kontrol satırları, makale sayfası) Türkçe/İngilizce oldu, hata kutusu ve üst menü kullanıyor; makale metni ise akademik biçim için İngilizce kalır ve sayfada bu yazar.
- **Tarayıcı testleri (Playwright):** 12 test, API tarayıcıda taklit edilir (arka uç gerekmez): ana sayfa, dil ve tema kalıcılığı, özet / sekmeler / indirme, iptal ve yeniden başlat akışı, reddedilmiş isteğin sade anlatımı, geçmiş süzgeci. Yerelde Edge ile, CI'daki tarif ise (node:24 + `playwright install --with-deps chromium`) Linux konteynerinde çalıştırıldı: 12/12 geçti. Mutasyon (iptal düğmesini boşaltma) yeniden derlenerek denendi ve yakalandı. CI'ya ayrı `e2e` işi eklendi.
- Node testleri 113.

### Ölçümler
- **Meta makale kapısı, ayarlı kıyas (`benchmark-tuned`, `--tuning 12`):** 10 örnekte 10/10 geçti (Wilson %72–100), yeniden yazımla en çok 3. taslakta. Aynı araç ayarsız spesifikasyonla yanlışlıkla çalıştırıldığında 'No hyperparameter search' sapma cümlesini bulamayıp hiç geçemedi: araca `--tuning` eklendi, çünkü kapı doğru spesifikasyonla ölçülmeli.
- **Kapı taslak denetimi (`benchmark-default`, 10 örnek):** ilk taslakların 4'ü temiz, 6'sı işaretlendi; hepsi en çok 3. taslakta temizlendi (10/10). İşaretlerin türü: 'supported' sözcüğü 7 kez (hepsi "was **not** supported" olumsuz kullanımı, yani iddiayı abartmıyor: zararsız sözcük alarmı), 'demonstrating / demonstrated' 2 kez ve 'on any dataset' 2 kez. Elle okuyunca 6 işaretli ilk taslağın 2'si (demonstrate: gerçek abartı), 3'ü yalnız olumsuz 'not supported' (yanlış alarm) ve 1'i olumsuz 'not supported' + 'any dataset' (hafif). Yani ilk taslakta yanlış alarm oranı kabaca 3–4/10 (küçük örnek, tek kampanya, tek yazar modeli); döngü hepsini düzeltiyor ama gereksiz bir yeniden yazım turu ve para harcıyor. Öneri (uygulanmadı, bir yazım politikası kararı): "not supported" biçimini, kapıda yalnız olumlu kullanımı yasaklayacak şekilde ayırmak.
- **Gerçek modellerle boş (null) karşılaştırma (`tools/null_seed.py`, tohum 1):** 6 model (RandomForest, ExtraTrees, MLP, DecisionTree, GradientBoosting, AdaBoost) her biri kendisinin yalnız `random_state`'i farklı kopyasıyla 9 benchmark veri setinde karşılaştırıldı; 18 ayar etkisi satırından 15'i testlenebilirdi (AdaBoost iki kopyada da birebir aynı skoru verdi, hepsi eşit), **ham p < 0,05 olan 0, aile (Holm) düzeltmeli 0, katı düzeltmeli 0** (ham oran %0, Wilson %0–20). Medyan farklar 1e-4 mertebesinde (en büyüğü DecisionTree +0,0014). Yani boş farkta kampanya makinesi beklenen yanlış alarmı (%5 civarı) vermedi, ama 15 test çok az: tek bir koşu "oran %5'in altında" demeye yetmez, yalnız "sistematik bir yanlış alarm görülmedi" der. Önemli bir yan bulgu: Wilcoxon 9 veri setinde en küçük p'si 0,0039'dur; katı (tek aile) Holm düzeltmesi 13 ve daha fazla etkide matematiksel olarak anlamlı sonuç veremez, bu yüzden büyük kampanyalarda `significant_all` neredeyse hep yanlıştır ve ailevi `significant` esas alınmalıdır.
- **Boş karşılaştırma, üç tohum birlikte (1, 2, 3):** her tohumda 18 etki satırından 15'i testlenebilirdi, toplam 45 testlenebilir etki; **ham p < 0,05 olan 0, aile düzeltmeli 0, katı düzeltmeli 0** (ham oran %0, Wilson %0–7,9). Beklenen yanlış alarm %5 olsaydı yaklaşık 2 anlamlı etki görülürdü; 0 görülmesi %5'in altındaki bir oranla uyumlu, ama tek bir 45'lik örnekle %5'in üstünü kesin dışlamaz (üst sınır %7,9). Üç tohum aynı 9 veri seti ve aynı 6 model üzerinde olduğundan birbirinden tam bağımsız değildir.

## Takip 9: kalanların tamamlanması, üçüncü tur (27 Ekim 2026)

Kullanıcının "kalanları otonom yap" isteğiyle roadmap'teki yapılabilir her madde sırayla işlendi; her biri ayrı commit, hepsi testli ve mutasyon denetimli.

### Kapı yazım politikası
- Makale kapısı artık `supported` / `supports` sözcüğünü **olumsuz** kullanımda ("was not supported", "wasn't supported", "cannot be supported", "never supports", en çok bir ara sözcükle) işaretlemiyor; olumlu kullanım ve `confirm / refute / prove / demonstrate` ailesi (olumsuzda bile) yasak kalıyor. 14 mutasyonun hepsi yakalandı; 1 eşdeğer mutant koddan sadeleştirilerek kaldırıldı.
- Yeniden ölçüm (`benchmark-default`, 10 örnek, aynı araç): ilk taslakların **7/10'u temiz** (önce 4/10); kalan 3 işaretin üçü de gerçek abartı (`demonstrated`). Hepsi en geç 3. taslakta geçti (10/10). Yani gereksiz yeniden yazım turlarının çoğu kalktı.

### Erişilebilirlik
- Terim düğmesi `aria-label` ile kendi görünen metnini eziyordu (axe: `label-content-name-mismatch`); artık görünen sözcükler düğmenin adı, açıklama `aria-describedby` ile tooltip'e bağlı. Test için `LanguageProvider`'a `initialGlossary` verilebiliyor.
- Sekmeler tam ARIA desenine geçti: yalnız seçili sekme sekme sırasında, ok tuşları / Home / End ile gezinme, kenarlarda başa sarma (`lib/tabs.ts`, birim testli). Her yerde görünür odak halkası (`:focus-visible`), iptal sorusu Escape ile kapanıyor.
- `@axe-core/playwright` ile 5 sayfa × 2 tema + rapor sekmesi + iptal sorusu WCAG A/AA kurallarıyla taranıyor (12 test; ilk koşuda tek ihlal yukarıdaki terim düğmesiydi, düzelince hepsi temiz), 5 klavye testi eklendi. Mutasyon (düğmeyi yeniden `aria-label`'a çevirme) yeniden derlenerek yakalandı. Tarayıcı testleri toplam 32. Ekran okuyucuyla gerçek dinleme yapılmadı; axe yalnız otomatik denetlenebilen kuralları (yaklaşık üçte biri) kapsar.

### Tek araştırma hattında kurtarma
- `POST /research/{thread_id}/retry`: başarısız ya da bayat (30 dk) araştırmayı **son checkpoint'ten** (`compiled.invoke(None)`, biten adımlar korunur) yeniden başlatır; onay bekleyen, bitmiş, reddedilmiş ya da kalan adımı olmayan araştırma için 409. Kampanya modunda kampanya durmuşsa (`failed` / `cancelled` / bayat) kampanyayı yeniden kuyruğa alıp araştırma iş parçacığını ona bağlar, böylece kampanya bitince graf devam eder. Hata satırı temizlenir, bir günlük hak harcanır; kuyruk kapalıysa hata yeniden yazılır. `GET /research/{id}` artık `can_retry` döner.
- Kampanya durumu artık araştırma iş parçacığının kimliğini (`thread_id`) saklar; kampanya sayfasından "Yeniden başlat" da grafı devam ettirir (önceden kampanya biter ama makale hiç yazılmazdı).
- Konsol: ana sayfada ve rapor sayfasında "Kaldığı yerden yeniden dene" düğmesi, 3 yeni tarayıcı testi. Testler: `tests/test_research_retry.py` (51), `tests/test_campaign_thread.py` (8); mutasyon taramasında 4 hayatta kalan test güçlendirilerek kapatıldı.

### Canlı işçi ölümü denemesi
`CELERY_VISIBILITY_TIMEOUT` ortam değişkeniyle yeniden teslim bekleme süresi ayarlanabilir oldu (varsayılan 7200 sn, testli). Gerçek bir işçi, çalışan bir kampanyanın ortasında öldürülüp yeniden başlatıldı:
- **Windows, `--pool=threads`:** iletinin Redis'te `unacked` kaldığı görüldü ama **yeniden teslim edilmedi** (3 dakika beklendi). Neden: Celery, olay döngüsünü (kombu'nun geri yükleme zamanlayıcısı) Windows'ta kullanmaz. Windows'ta otomatik kurtarma yoktur; kampanya 20 dakika sonra `failed` görünür ve "Yeniden başlat" çalışır.
- **Linux (Docker `worker`, compose):** `docker kill` ile öldürülen işçi yeniden başlayınca aynı görev kimliği ~90 sn sonra yeniden teslim edildi ve kampanya yeniden çalıştı. Yani üretim yolunda otomatik kurtarma çalışıyor; gecikme = bekleme süresi + en çok ~100 sn (kombu geri yüklemeyi 10 sn'lik 10 çağrıda bir yapar).
- **Bulunan sorun:** bekleme süresi kampanyadan kısaysa (testte 30 sn) görev kampanya hâlâ çalışırken her ~100 sn'de bir **tekrar** teslim edildi ve her yeniden başlatma ilerlemeyi sıfırladı (çift çalışma).

### Çift çalışmaya karşı nabız (heartbeat)
- Çalışan her kampanya 15 saniyede bir `heartbeat` dosyasına zaman yazar (`service._beating`, kampanya bitince ya da hata / iptalde durur). Görev teslim edilince `is_alive` (nabız ≤ 90 sn) ise çalışmaz, `self.retry(countdown=60)` ile bekler (en çok 480 kez, 8 saat); nabız yoksa ya da bayatsa (işçi ölmüş) çalışır; bitmiş kampanya hemen atlanır. Aynı nabız bir kampanyanın "bayat" görünmesini de engeller: 20 dakikadan uzun süren tek bir veri seti artık yanlışlıkla `failed` görünmez (önceden görünürdü).
- Testler: `tests/test_campaign_heartbeat.py` (30); 21 mutasyonun 20'si yakalandı, hayatta kalan `thread.join()` kaldırma mutantı yalnız zamanlamayı etkiler (eşdeğer).
- **Canlı doğrulama (Linux / Docker, bekleme 30 sn):** 9 veri setli, 4 modelli kampanya ortasında `docker kill` ile işçi öldürüldü ve hemen yeniden başlatıldı. İleti ~94 sn sonra yeniden teslim edildi, nabız bayat olduğu için çalıştı (tek çalışma, 269 sn) ve kampanya `completed`, 9 veri seti `finished`, sorun yok bitti. Aynı sırada çoğalan kopya teslimler `retry: Retry in 60s` ile bekledi, kampanya bitince 0,0005 sn'de atlanıp çıktı: çift çalışma görülmedi. Bekleme süresi artık en uzun kampanyadan kısa da olabilir (kurtarma gecikmesi = bekleme + en çok ~100 sn + nabız bayatlığı ~90 sn); varsayılan 2 saat kaldı.

### Diğer
- `tools/memory_report.py`, ölü kod temizliği: istenen ölü kod adayları (`models_dropped`, `performance_dropped`, `DROP_LIMIT`, `log_classification_run`, `parse_metrics`) zaten kodda yok; `EXPERIMENT_CSV_SCHEMA` canlı kullanımda (silinmedi).
- **Test yalıtımı hatası (benim eski eksiğim):** günlük başlatma sayacı (`reports/usage.json`) gerçek dosyaya yazıyordu ve başlatma uçlarını çağıran eski testler (`test_two_models` vb.) her tam koşuda gerçek sayaca başlatma ekliyordu; sayaç bugün 100'e (sınıra) dayanmıştı ve gerçek başlatmaları 429 ile reddedecekti, tam test koşusunda da 10 test 429 aldı. `tests/conftest.py` artık her teste geçici bir sayaç dosyası verir ve ortamdaki `API_KEY` / `DAILY_START_LIMIT` değerlerini siler (`tests/test_isolation.py`). Gerçek sayaç dosyasını (gitignore'lu çalışma verisi) test kirliliğinden arındırmak için bugünün sayısını gerçek başlatma sayısına (3 canlı deneme) indirdim.
- **17 regex kapısının yanlış alarmı:** 45 ilk taslak (benchmark-default 10 + benchmark-tuned 15, kapı değişikliğinden sonra; değişiklikten önceki 10 örnekle birlikte 55 taslak) elle okunarak incelendi: 17 kapıdan yalnızca üçü ateşledi (`supported`, `demonstrat*`, `any dataset`). Düzeltmeden sonra işaretlerin tamamı gerçek bir kural ihlaliydi (`demonstrated` 10, `any dataset` 1); gerçek yanlış alarm sınıfı yalnız olumsuz 'not supported' idi ve kaldırıldı. Diğer 14 kapı bu örneklerde hiç ateşlemedi, yani onların yanlış alarm oranı bu örneklemle ölçülemez (hiç tetiklenmediler); onları sınamak için bilerek bozulmuş (etiketli) makaleler gerekir. Tuned kıyasta ilk taslak temizliği 7/15, hepsi en geç 3. taslakta geçti (15/15).
- Doğrulama: backend 3220 test, frontend 123 Node testi, 32 tarayıcı testi.

### Hâlâ açık
Kullanıcı gözlemi (insan gerekir), ekran okuyucuyla gerçek dinleme, iki paralel hattın birleştirilmesi (tasarım kararı), iç içe çapraz doğrulamalı ayar (protokol değişikliği, önceki sonuçları geçersiz kılar, karar ister), test kalıntılarının silinmesi (kullanıcı kararı).

## Takip 10: araştırma ajanı (28 Ekim 2026)

Kullanıcının isteğiyle `ROADMAP.md` E4 (araştırma ajanına dönüşüm) baştan sona yapıldı; tasarım `RESEARCH_AGENT.md`, ölçümler ve sonuçlar `TECHNICAL_REPORT.md`. Hepsi ayrı commit, testli ve mutasyon denetimli.

### Ne yapıldı
- **Veri havuzu:** Grinsztajn benchmark'ının kalan 7 sayısal ikili sınıflandırma veri seti `extended` grubuna eklendi (havuz 16); `benchmark_keys()` (9) ve mevcut kampanyalar değişmedi. Gerçek bir sondayla doğrulandı; Bioresponse örnekleme yapılamayacak kadar küçüktü (6000 satırdan az), tüm satırlar kullanılacak şekilde düzeltildi.
- **Protokol çekirdeği** (`app/research/protocol.py`): tohumlu keşif / doğrulama ayrımı, `⌈α·2ⁿ⁻¹⌉−1` ile sınırlı kayıt bütçesi, donduran ve özet (SHA-256) tutan `Registry`, yalnız keşif veri setlerini kopyalayan `ExplorationView`, tek doğrulayıcı test ve oturum boyu Holm + BH. 65 test; mutasyonların hepsi yakalandı.
- **Üretici** (`generate.py`): keşifte tutarlı (5/6) ve en az 0,01 farklı her çiftin kazananı, ayarlı aşamada her modelin kendi varsayılan kontrolüyle farkı; yenilik denetimi. 37 test, mutasyonlar yakalandı. **Dil modeli üretici** (`llm_generator.py`): öneriyi doğrular, kullanılamazsa kurallara döner; protokol güvencesi saldırgan bir üreticiyle boş dünyada sınandı (aile hatası %10'un altında).
- **Oturum** (`session.py`) ve **komut satırı**: aşamalı koşu, hipotezler diske doğrulama sonuçları okunmadan yazılır (testle kilitli), ayarlı aşama keşif etkisi 0,02 ve üstünde tetiklenir, rapor, `verify` ile kayıt bütünlüğü denetimi, aşama sonuçlarının kaydı ve `--reuse`, `--no-history`, `--generator rules|llm`. 120'den fazla test.
- **Salt okunur API ve konsol sayfaları** (`/research`, `/research/{id}`): protokolün sade anlatımı, hipotez tablosu (keşif tahmini ile doğrulama etkisi ayrı), bütünlük uyarısı, rapor indirme; Playwright (axe dahil) ile iki temada doğrulandı.
- **Ajanın kendini ölçmesi:** `tools/planted_effects.py` (yerleştirilmiş etkili simülasyon) ve `tools/llm_baseline.py` (veri görmeyen dil modeli). Sonuçlar README ve `TECHNICAL_REPORT.md`'de.
- **Gerçek oturum `real-2`:** 16 hipotez, 15 doğrulandı, 0 tersi çıktı, 1 doğrulanamadı; ağaç toplulukları lojistik regresyonu ~5, MLP'yi 1-2 ROC-AUC puanı geçti; MLP için keşif tahmini ~3 kat şişikti.
- **Tek ağ kopması bütün koşuyu düşürüyordu (gerçek bulgu):** ilk gerçek oturum, ayarlı aşamada bir sandbox bağlantısı kopunca (`RemoteProtocolError`) 17 dakikalık varsayılan aşama sonuçlarıyla birlikte düştü, çünkü kampanya çalıştırıcısı yalnız `SandboxCodeError` ve `RuntimeError`'u yeniden deniyordu. Kök neden düzeltildi: bir veri seti denemesindeki her istisna başarısız deneme sayılır. Ayrıca oturum, sonraki aşama düşse bile önceki aşamaları korur ve her aşamanın sonuçlarını diske yazar.
- Dil modeli üreticinin ilk istemi yönü karıştırdı (8 önerinin 3'ü kendi gerekçesiyle çelişti); protokol bunları tersi çıkan / doğrulanamayan diye yakaladı, istem "higher / lower" alanlarıyla düzeltildi.

### Kullanıcıya dönük belgeler
README'nin başına özet, ekran görüntüleri, ölçümler ve sınırlar eklendi; İngilizce `TECHNICAL_REPORT.md` yazıldı (teknik rapor, CV ve portföy için).

### Dürüst sınırlar
Tek gerçek oturum; üretici karşılaştırması aynı deneyleri yeniden kullandığı için 8 bölme bağımsız değil; küçük etkilerde güç düşük; hipotez türü yalnız model karşılaştırması ve ayarlama etkisi; yeni bilimsel bulgu iddiası yok; kullanıcı gözlemi ve halka açık demo yapılmadı (insan ve sunucu gerekir). İç içe çapraz doğrulamalı ayar ve iki hattın birleştirilmesi (A2-8, A2-9) yapılmadı: ikisi de önceki sonuçları değiştiren ya da bir ürün kararı gerektiren işler, onay beklemede.

### Yan temizlik
Başarısız ilk gerçek oturumun çalışma dizini (`reports/research/real-1`, gitignore'lu, yalnız 8 kayıtlı hipotez ve hata içeriyordu) yeniden koşudan önce silindi.
