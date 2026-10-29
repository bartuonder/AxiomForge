# Araştırma ajanı: kapalı döngü, keşif / doğrulama ayrımı ve ajanın kendini ölçmesi (tasarım)

Bu belge araştırma ajanı katmanının tasarımıdır. Amaç: sistemi "iddia doğrulayan" bir araçtan, **sonuçlara bakıp kendi takip hipotezlerini üreten ve bunu istatistiksel güvenceyle yapan** bir ajana taşımak.

## 1. Sorun: uyarlamalı analiz sahte pozitifi şişirir

Bir ajan aynı verilerde hipotez üretip aynı verilerle test ederse, "en iyi görünen" hipotezi seçmiş olur ve p değeri anlamını yitirir (kazananın laneti). Model çifti sayısı arttıkça, hiç gerçek fark yokken bile bir şey "bulmak" kaçınılmazdır. Mevcut kampanya motoru bu sorunu yaşamaz çünkü hipotezi dışarıdan alır ve bir kez test eder. Kapalı döngüde bu güvence özel olarak kurulmalıdır.

## 2. Protokol

1. **Veri havuzu ve ayrım.** 16 sayısal ikili sınıflandırma veri seti (9 mevcut + 7 genişletilmiş, bkz. §6). Havuz, tohumlu ve belirleyici (deterministik) biçimde **keşif (E)** ve **doğrulama (C)** kümelerine bölünür; oturum bunu bir kez yazar ve değiştirmez. Varsayılan: E = 6, C = 10.
2. **Mühürlü doğrulama.** Modeller hem E hem C üzerinde koşar ama hipotez üreticiye **yalnız E sonuçları** verilir (`ExplorationView` tipi C'yi içermez). C sonuçları ancak hipotez kayda alındıktan sonra, o hipotezin sınanması için okunur.
3. **Kayıt (pre-registration).** Üretici bir hipotez önerince protokol onu dondurur: alt/üst model grupları, tek birincil ölçüt (`roc_auc`), yön (E'deki işaret), tur, E'deki kanıt özeti, SHA-256 özeti ve zaman. Kayıttan sonra hipotez değiştirilemez; kaydın dışında bir hipotez doğrulama kümesinde sınanamaz.
4. **Tek doğrulayıcı test.** Her kayıtlı hipotez C üzerinde tam bir kez sınanır: veri seti birimli, iki taraflı Wilcoxon (mevcut `compare_scores`), tek birincil ölçüt (hipotez içinde çoklu karşılaştırma yok).
5. **Oturum boyu çoklu karşılaştırma.** Oturumda kaydedilen **tüm** hipotezlerin p değerleri, kaç tanesinin sonuçta raporlandığına bakılmaksızın, Holm (aile hatası) ile düzeltilir; BH (yanlış keşif oranı) ek olarak raporlanır. Bir hipotez "doğrulandı" sayılır: düzeltilmiş p < 0,05 **ve** C'deki işaret kayıtlı yönle aynı.
6. **Etki büyüklüğü yalnız C'den.** E'deki etki, seçim yüzünden şişiktir (kazananın laneti); raporda doğrulayıcı etki yalnız C'den bildirilir, E'deki ise "keşif tahmini" diye ayrı etiketlenir.
7. **Üretici serbesttir, geçerlilik ondan bağımsızdır.** Aşağıdaki ilke korunduğu sürece hipotezi kural tabanlı bir kod da, bir LLM de üretebilir: üretici yalnız E'yi görür ve her öneri kayda girer. Geçerlilik üreticinin akıllılığına değil, mühür ve kayda dayanır.
8. **Bütçe ve uygulanabilirlik.** Wilcoxon'un |C| veri setinde en küçük p değeri `2 / 2^|C|`'dir. Holm ile `K` hipotezin hepsinin anlamlı olabilmesi için `K · 2 / 2^|C| < α` gerekir. Protokol bu yüzden en çok `K_max = floor(α · 2^|C| / 2)` hipotez kaydeder (|C| = 10 için 25) ve her turun bütçesi buradan çıkar; hiçbir hipotezin şansı olmayacak kadar çok hipotez kaydetmek kodla engellenir.
9. **Doğrulama sonuçları üreticiye geri verilmez.** Bir tur doğrulanmış mı yoksa reddedilmiş mi çıktığı, sonraki turun hipotezlerini etkileyemez (aksi hâlde C de uyarlamalı olur). Sonraki tur, yalnız yeni E sonuçlarından beslenir.

## 3. Döngü (aşamalar)

Aşama = bir deney tanımı (model kümesi, varsayılan ya da ayarlı) tüm havuzda koşturulur.

- **Aşama 0 (varsayılan hiperparametre):** model kümesi tüm 16 veri setinde koşar. Üretici E görünümünden hipotezleri çıkarır.
- **Aşama 1 (ayarlı, `tuning`):** aşama 0'da kayda giren hipotezlerden en az biri `|etki| ≥ τ` ise, "bu üstünlük varsayılan hiperparametrenin eseri mi?" sorusu için aynı modeller ayarlı koşar. Üretici ayarlı modeller arasındaki çiftleri ve her modelin ayarlı-varsayılan farkını (ayarlama etkisi) E'den öneri olarak çıkarır.
- Durma: bütçe `K_max` dolduğunda, üretici yeni öneri üretemediğinde (zaten kayıtlı ya da bellekte sınanmış), ya da en çok `R` aşama sonunda.

## 4. Hipotez üretici (E'den, kural tabanlı)

Girdi: E'deki veri setleri üzerinde model başına birincil ölçüt ortalamaları (ayarlı aşamada `X__default` kontrol girdileri dahil). Çift `(a, b)` için E'deki medyan fark `d`, `a`'nın kazandığı veri seti sayısı `w`, `n_E` veri seti: öneri koşulları `|d| ≥ τ_effect` (varsayılan 0,01) ve tutarlılık `max(w, n_E − w) / n_E ≥ τ_consistency` (varsayılan 5/6). Yön: işareti `d`'nin işareti. Sıralama `|d|` büyükten küçüğe; aşama başına `k` öneri. **Yenilik denetimi:** zaten kayıtlı (aynı alt / üst küme, aynı yön) öneri atlanır; ayrıca daha önce tamamlanmış kampanyalarda aynı çift doğrulanmışsa atlanır ve nedeni oturum kaydına yazılır.

## 5. Ajanın kendini ölçmesi: yerleştirilmiş etkili (planted-effect) benchmark

Gerçek verilerde "doğru cevap" bilinmediği için protokolün istatistiksel özellikleri önce **gerçek etkinin bilindiği simülasyonda** ölçülür (`tools/planted_effects.py`):

- `M` model, `D = 16` veri seti. Her modelin bir temel yeteneği, veri setine özgü bir etkisi ve bölme gürültüsü vardır. Bazı çiftlere bilerek gerçek fark `δ` konur, çoğu çift boştur.
- Karşılaştırılan ajanlar: **(A) saf uyarlamalı:** tüm veri setlerinde tüm çiftleri dener, düzeltmesiz p < 0,05 olanları raporlar; **(B) saf düzeltmeli:** tüm veri setlerinde tüm çiftleri, Holm ile dener (uyarlamalı değil); **(C) bu protokol:** E'den seçer, C'de doğrular, Holm ile düzeltir.
- Ölçümler (çok tekrar): yanlış keşif oranı (raporlananların yüzde kaçı boş), aile hatası (en az bir sahte keşif olasılığı), duyarlılık (gerçek etkilerin yüzde kaçı bulundu). Beklenti: (A) yanlış keşifleri şişirir; (B) güvenli ama hipotezlerin önceden seçilmesini gerektirir; (C) (A)'dan çok güvenlidir, (B)'ye göre veri kaybettiği için daha az duyarlıdır; asıl değeri, hipotezin veriye bakarak seçilebilmesidir.
- Bu sonuçlar tasarımın dürüst bedelini gösterir ve rapora olduğu gibi yazılır; tasarım "(C) her şeyde daha iyi" iddiasında bulunmaz.

## 6. Veri havuzu genişletmesi

Wilcoxon'un en küçük p değeri veri sayısına bağlı olduğundan (§2.8) 9 veri seti bölmeye yetmez (C = 4 için en küçük p 0,125). Grinsztajn ve arkadaşlarının benchmark'ındaki kalan 7 sayısal ikili sınıflandırma veri seti (`Bioresponse`, `Diabetes130US`, `Higgs`, `MiniBooNE`, `covertype`, `default-of-credit-card-clients`, `jannis`) ayrı bir `extended` grubuna eklenir; `benchmark_keys()` (9) ve mevcut varsayılan kampanyalar aynen kalır. Havuz = benchmark + extended = 16.

## 7. Çıktılar

`reports/research/{id}/` altında `session.json` (ayrım, bütçe, kayıtlar, sonuçlar), `report.md` (kayıt tablosu, doğrulayıcı sonuçlar, düzeltilmiş p, etiketlenmiş keşif tahmini ve doğrulayıcı etki, sınırlar) ve her aşamanın kampanya kimliği. Komut satırı: `python -m app.research run ...`.

## 8. Sınırlar (rapora da yazılır)

- Hipotez türü model karşılaştırması ve ayarlama etkisiyle sınırlı; yeni model türü ya da veri özelliği (moderatör) hipotezi yok.
- 16 veri seti; E = 6 olduğundan keşif zayıf, C = 10 ile `K_max` = 25.
- Üretici kural tabanlı; LLM üretici arayüzü hazır ama bu sürümde çekirdek ölçümlerde kullanılmaz.
- Bu bir "keşifsel analiz ajanı"dır; yeni bilimsel bulgu iddiası yoktur.

## 9. Uygulama durumu ve sonuçlar (28 Ekim 2026)

**Kod.** `app/research/protocol.py` (ayrım, bütçe, `Hypothesis`, `Registry`, `ExplorationView`, `confirm`, Holm ve BH), `generate.py` (kural tabanlı üretici, tuning tetikleyicisi), `llm_generator.py` (dil modeli üretici; her öneriyi doğrular, kullanılamayan cevapta kurallara döner), `session.py` (aşamalı oturum, kayıt, rapor, aşama sonuçlarının kaydı ve yeniden kullanımı), `__main__.py` (`run`, `list`, `show`, `verify`). Veri havuzu 16 veri seti (`app/datasets.py`, `extended` grubu). API: `GET /research_sessions`, `/research_sessions/{id}` (bütünlük denetimiyle), `/research_sessions/{id}/report`. Konsol: `/research` ve `/research/{id}` sayfaları.

**Tasarımdan sapmalar ve eklemeler.** (1) Aşama sonuçları `reports/research/{id}/stages/` altına yazılır ve `--reuse` ile başka bir oturumda yeniden kullanılır; böylece aynı deneyler üzerinde farklı üreticiler karşılaştırılabilir (`--no-history` önceki oturumların doğruladığı iddiaları atlamayı kapatır). (2) Daha sonraki bir aşama düşerse (ağ kopması, çok az veri seti) oturum önceki aşamaların hipotezleriyle tamamlanır ve neden rapora yazılır; varsayılan aşama düşerse oturum `failed` ya da `aborted` olur. (3) Dil modeli üretici hem yön verir hem gerekçe yazar; gerekçe kayda `evidence.rationale` olarak girer ama özetin parçası değildir.

**Ölçümler** (`TECHNICAL_REPORT.md` bölüm 5 ve 6):
- Yerleştirilmiş etkili simülasyon (400 tekrar, 8 model, 16 veri seti): aile hatası boş dünyada düzeltmesiz tüm çiftlerde %55, aynı veride seçip test eden ajanda %10, tüm çiftli Holm'da %5,5, protokolde %2,2; gerçek fark +0,02 iken güç sırasıyla 1,00 / 0,53 / 0,96 / 0,47. 16 modelde (120 çift) aynı veride seçip test eden ajanın aile hatası %24, protokolünki %3.
- Gerçek oturum `real-2` (6 model, 16 veri seti, ayarlı aşama dahil): 16 hipotez kaydedildi, 15 doğrulandı, 0 tersi çıktı, 1 doğrulanamadı. Ağaç toplulukları lojistik regresyonu doğrulama veri setlerinin hepsinde ~5 ROC-AUC puanı geçti; MLP'yi 1-2 puanla geçti ve keşif tahmini bu fark için ~3 kat şişikti (kazananın laneti).
- Üreticiler aynı sonuçlar üzerinde, 8 bölmede: kural 61 kayıt / 19 doğrulama, dil modeli 55 / 14 ve 1 tersi çıkan.

**Konsoldan başlatma (28 Ekim).** `POST /start_research_session` (`models`, `tuning`, `seed`, `generator`; bilinmeyen alan 422) oturumu `queued` yazar ve `axiomforge.run_research_session` Celery görevini kuyruğa atar; havuz ve bölme parametreleri konsoldan değiştirilemez. Her başlatma günlük sınırdan bir hak düşer, `llm` üreticisi için OpenAI erişimi önceden denetlenir. `app/research/service.py`: işçi her 15 saniyede `heartbeat` dosyası yazar; `running` oturum 90 saniyeden uzun nabızsızsa API onu `failed` ve `stale` gösterir (iş kaybolmaz, kullanıcı yeniden başlatır). İptal: `queued` oturum hemen `cancelled` olur; `running` oturumda `cancel.flag` yazılır, kampanya motoru çalışan veri setleri bitince durur ve oturum hiçbir hipotez kaydetmeden `cancelled` olur. Yeniden başlatma (`failed`, `cancelled`, `aborted`): bitmiş aşamaların sonuçları (`stages/`) varsa yeniden kullanılır, hipotezler baştan ve yine yalnız keşif görünümünden üretilir; doğrulama sonuçları hiçbir zaman diske hipotezden önce çıkmadığı için bu bütünlüğü bozmaz. Canlı denemede (RandomForest + LogisticRegression) iptalin yarım aşama sonucunu `stages/` altına yazdığı, yeniden başlatmanın bunu tam sonuç sanacağı bir hata bulundu; durdurulan aşama artık yazılmıyor.

**Veri seti ilerlemesi (29 Ekim).** Oturum durumunda `progress` (`stage` ve her veri setinin `queued` / `running` / `finished` / `failed` / `cancelled` durumu) çalışan aşama boyunca diske yazılır; kampanya motorunun `on_update` geri çağrısı kullanılır. Özet bunu `{stage, total, finished, failed, running}` olarak verir; oturum bitince `progress` boşaltılır (kalıcı kayıt `stages` altındadır). Konsol çubuğu ve 'şu an çalışan' satırı bundan beslenir. Gerçek koşuda (2 model) çubuk 0 → 9 / 16 ilerledi.

**Bilinen sınırlar.** Tek gerçek oturum; üretici karşılaştırması aynı deneyleri kullandığından 8 bölme bağımsız değil; moderatör hipotezleri, regresyon ve literatür tabanlı yenilik denetimi yok.
