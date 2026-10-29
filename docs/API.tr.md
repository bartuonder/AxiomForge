# API başvurusu

[English](API.md) · [README'ye dön](../README.tr.md)

Bu sayfa her ucun ne yaptığını ve şemanın tek başına söylemediği davranışları anlatır. Yığın çalışırken etkileşimli OpenAPI belgesi `http://127.0.0.1:8000/docs` adresindedir. İngilizce özet için [API.md](API.md) dosyasına bakın; bu sayfa daha ayrıntılıdır ve geliştirme sırasında yazılmış akış ayrıntılarını da taşır.

## Genel görünüm

Uçların kısa listesi için [API.md](API.md) dosyasındaki tabloya bakın.

## Uçlar

### `GET /health`

Redis ve Celery durumunu döner. İkisi de ayaktaysa `200`, biri kapalıysa `503`.

```json
{"redis": "ok", "celery": "ok"}
```

### `POST /experiments`

Faz 1. Gövde:

```json
{
  "prompt": "Predict whether a customer churned. The target column is churn.",
  "csv_schema": "age:float, monthly_spend:float, tenure_months:int, churn:int"
}
```

Akış:

1. Ajan, sorudaki modelleri aynı bölünmede eğiten bir scikit-learn betiği üretir; veri, sorgunun alanına uyan Hugging Face veri setinin hazır veri bloğudur (`pick_dataset`, varsayılan `customer_churn`). Önce `dataset=<name> samples=<int> features=<int> negative_ratio=<float> positive_ratio=<float>` basar. Her model için `model=<name> accuracy=<float> f1=<float> roc_auc=<float> pr_auc=<float> train_seconds=<float> tn=<int> fp=<int> fn=<int> tp=<int>` basar.
2. Şema yapısına uygun küçük bir CSV sandbox içine yazılır.
3. Betik E2B içinde çalıştırılır.
4. Kod hata verirse traceback ve hatalı kod ajana geri gönderilir. Döngü en fazla 3 denemedir.
5. Çıktıdan veri profili ve model satırları okunur. Grafın dışındaki bu uçta üst MLflow run'ına profil ve `prompt_version=experiment-v9` yazılır. Her model kendi iç içe run'ında Accuracy, F1, ROC-AUC, PR-AUC, eğitim süresi ve karışıklık sayılarını alır. Sayılar bilimsel gösterimle de yazılabilir (`4.5e-05`); ayrıştırıcı bunu okur. Sorguda en az iki model yoksa istek `422` ve `query names fewer than two models` ile reddedilir. Basılan model adları izin listesinden farklıysa betik sandbox başarısı sayılmaz.
6. Grafın dışındaki `POST /experiments` ucunda aynı sonuç `save_experiment` ile vektör hafızaya da yazılır. Başarıda `is_success=true` ve metrik, üç deneme de düşerse `is_success=false` ve hata logu kaydedilir.

Başarılı yanıt:

```json
{
  "code": "...",
  "status": "Finished",
  "attempts": 1,
  "mlflow_run_id": "...",
  "accuracy": 0.8,
  "f1": 0.75
}
```

Üç deneme de başarısızsa:

```json
{
  "code": "...",
  "status": "Failed",
  "attempts": 3,
  "mlflow_run_id": "..."
}
```

Deneme ayrıntısı FastAPI logundaki `sandbox attempt` satırlarındadır. MLflow arayüzü: `http://127.0.0.1:5000`

### `POST /start_research`

Faz 2. Gövde:

```json
{"query": "Compare SVM and Random Forest on tabular data classification", "mode": "experiment"}
```

`mode` `experiment` (varsayılan) ya da `campaign` olur; başka değer `422` döner. `campaign` modunda sorguda model adı aranmaz ve graf kampanya planlayıcısına gider (Faz 13). Yanıt `mode` alanını da taşır. Kampanya modunda `GET /research/{thread_id}` ek olarak `campaign_specs` (üç aday: `spec`, `estimate`, `evidence`, `repeats`), `selected_campaign`, `campaign_id`, `campaign_status` ve `campaign_mlflow_run_id` döner; `POST /approve_plan` `selected` ile aday sırasını alır ve `selected_campaign` döner.

Sorguda en az iki model adı geçmelidir, çünkü her hipotez iki model arasında bir karşılaştırma iddiasıdır. Sıfır, bir ya da aynı modelin farklı yazılışları (`SVM, svm`) geçiyorsa literatür, LLM ve sandbox çalışmadan `422` ve `query names fewer than two models` döner. Aynı kural `POST /experiments` ucunda da geçerlidir.

Akış `literature_node` ve `planner_node` çalıştıktan sonra, `experiment_node` öncesinde durur.

1. Literatür ajanı LLM'e yalnız sorgunun alanını çıkarttırır (en çok 2 konu, en çok 3 kelime, örneğin `customer churn`); model adı, hiperparametre, rakam, ayar ve talimat sözcükleri Python'da süzülür (`clean_topics`, sonu `prediction`, `classification` gibi genel bir sözcükse dördüncü kelime atılır). Modelleri sorgudan Python çıkarır ve arama adlarına eşler (`MODEL_SEARCH_NAMES`). Aramalar en çok iki ifadelidir ve sırayla `[konu, model1]`, `[konu, model2]`, `[konu, machine learning]`, `[model1, model2]`, `[konu]` olur (en çok 5 arama, 12 aday bulununca durur, aramalar arasında 3 saniye). Böylece sorgudaki `n_neighbors=5` gibi ayar ifadeleri aramaya giremez ve dört ifadenin `AND`'i yüzünden boş dönen arama olmaz. Alaka süzgeci aynıdır: orijinal sorgunun gömüsüyle kosinüs benzerliği, `0.35` altı elenir, en iyi 3 makale alınır. Hiç aday yoksa `arxiv returned no papers`, hiçbiri eşiği geçmezse `arxiv returned no relevant papers` ile çalışma `failed` olur. Adaylar tekilleştirilir, sorunun gömüsüyle makale gömüsü arasındaki kosinüs benzerliği hesaplanır, `0.35` altındakiler elenir ve en iyi 3 makalenin başlığı ve özeti `literature_context` listesine yazılır. Hiçbiri eşiği geçmezse çalışma `arxiv returned no relevant papers` ile `failed` olur. Her skor logda `literature relevance` satırı olarak görünür.
2. Planlayıcı `search_past_experiments` ile sorguya en yakın 3 geçmiş deneyi okur. Başarısız kayıtları prompta koyar ve aynı yaklaşımı tekrar etmez.
3. Üç hipotez `hypotheses` listesine, spesifikasyonları `experiment_specs` listesine yazılır. Her hipotez bir deney spesifikasyonudur: `statement`, `models` (sorgudaki modellerin tamamı, Python doldurur), `claim` (iki modelin karşılaştırma iddiası: `kind` `performance` veya `stability`, `metric`, `subject` daha yüksek ya da daha kararlı olduğu iddia edilen model, `other`; en az iki model şartı olduğundan ürün akışında her hipotezde bulunur), `dataset` (`breast_cancer`, `credit_default`, `customer_churn`, `adult_income` veya `credit_fraud`; hepsi gerçek Hugging Face veri setidir) ve `params` (model başına izinli kurucu parametreleri). Hipotez yalnız iki model arasında bir karşılaştırma iddiasıdır (biri diğerinden daha yüksek ROC-AUC, PR-AUC veya F1'e sahiptir, ya da ROC-AUC varyansında daha kararlıdır); `params` yalnız modellerin nasıl yapılandırılacağını belirler, hipotezin konusu olamaz; parametre verilen her model ayrıca varsayılan parametreli bir kontrol girdisiyle (`Model__default`) koşar ve parametrelerin etkisi bu kontrole karşı ölçülür (`parameter_effects`). İki veya daha çok modelli sorguda `claim` zorunludur ve `statement` iki modeli de adlandırmalıdır. Geçersiz bir spesifikasyon bir kez düzeltme istenerek yeniden denenir, yine geçersizse çalışma `failed` olur.
4. Graf `approval_gate` öncesinde duraklar. Eleştiri turları bu kapıdan tekrar geçmez.

Geçmiş hata bulunursa logda `planner memory_note` satırı görünür. Örnek: geçmiş `KeyError: missing_target` deneyi yüzünden planlayıcı farklı bir yaklaşım önerir.

Duraklayan yanıt:

```json
{
  "thread_id": "...",
  "status": "paused",
  "hypotheses": ["...", "...", "..."],
  "state": {}
}
```

Hipotezler FastAPI logunda `paused hypothesis` satırları olarak da görünür.

`GET /research/{thread_id}` durumu `starting`, `running`, `paused`, `rejected`, `completed`, `needs_review` veya `failed` olarak döner. Onay öncesi ya da sonrası bir düğüm hata verirse mesaj PostgreSQL'deki `research_errors` tablosuna yazılır, durum `failed` olur ve mesaj `error` alanında görünür. `needs_review` makalenin iddia kontrolünden geçemediğini gösterir; sebep `consistency_feedback` alanındadır. Yanıt ayrıca `referee_notes` (LLM hakemin danışman notları, durumu belirlemez), `verification_status` ile birlikte `verifier_feedback` (doğrulama reddinin sebebi) ve `instability` alanını taşır: `{unstable, std_threshold, flagged: [{model, metric, std}]}`. Sonuç sayfası (`/result/{thread_id}`) bu alanlarla üç satırlık bir kontrol paneli gösterir: doğrulama geçti veya reddedildi (sebebiyle), eşiği aşan varyans bulgusu, iddia kontrolünün sonucu. Araştırma sürerken sayfa her 2 saniyede durumu okur ve hangi adımda olduğunu yazar. Araştırma `completed`, `needs_review`, `failed` veya `rejected` olunca yoklama durur ve rapor bir kez okunur.

### `POST /start_campaign`

Gövde `demo` (hazır kampanya adı) ya da `spec` (kampanya belirtimi) alanlarından tam birini taşır; `datasets` verilirse belirtimdeki veri setlerinin yerine geçer:

```json
{"demo": "grinsztajn-2022", "datasets": ["tb_credit", "tb_pol"]}
```

Belirtim eşzamanlı doğrulanır; geçersizse `422` döner ve hiçbir şey saklanmaz. Geçerliyse durum `queued` olarak yazılır, `run_campaign` görevi kuyruğa atılır ve `{"campaign_id": "...", "status": "queued"}` döner. Kuyruk kapalıysa `503` döner ve kayıt `failed` olur. Kampanya LLM çağırmaz, yalnız E2B kullanır.

### `GET /campaigns`, `GET /campaign/{campaign_id}`, `GET /campaign/{campaign_id}/report`

`/campaigns` `campaigns` (sıralı kimlikler) ve `items` döner; `items` en yeni başta, her biri `id`, `title`, `statement` (ilk iddia cümlesi), `origin` (api / console / cli), `status`, `updated`, `datasets`, `finished`, `failed` ve `verdicts` taşır. `/campaign/{id}` durumu döner: `status`, her veri setinin `status`, `attempts`, `seconds`, `error` alanları, bitince `verdicts` (iddia kimliği, cümle ve karar), `issues`, `finished_datasets` ve `failed_datasets`. Geçersiz kimlik `400`, bilinmeyen kampanya `404` döner. `/campaign/{id}/report` rapor hazırsa `{"markdown": ..., "ledger": [...]}` döner, değilse `404 report not ready`.

### `POST /campaign/{campaign_id}/cancel`, `POST /campaign/{campaign_id}/retry`

İkisi de API anahtarı tanımlıysa onu ister. İptal sıradaki kampanyayı hemen `cancelled` yapar; çalışan kampanyada iptal isteği bırakır (`cancel_requested`), şu an çalışan veri setleri biter, kalanlar hiç başlamaz ve kampanya analiz üretmeden `cancelled` olur. Bitmiş kampanya için `409`, bilinmeyen kampanya için `404` döner. Yeniden başlatma yalnız `failed` ya da `cancelled` (20 dakika ilerlemeyip bayat sayılanlar dahil) kampanyada çalışır, kayıtlı belirtimle kampanyayı baştan kuyruğa alır, `recoveries` sayacını artırır ve bir günlük başlatma hakkı harcar; kuyruk kapalıysa `503` döner ve kampanya `failed` kalır. 20 dakikadır ilerlemeyen `queued` / `running` kampanya durum ve liste uçlarında `failed` (`stale: true`) görünür; depoya yazılmaz. Kampanya görevi `acks_late` ile çalışır: işçi ölürse ileti (en çok 2 saat sonra) yeniden teslim edilir, bitmiş kampanya ise yeniden çalıştırılmaz.

### `POST /research/{thread_id}/retry`

API anahtarı tanımlıysa onu ister. Başarısız ya da 30 dakika ilerlemeyen (bayat) araştırmayı son checkpoint'ten yeniden başlatır; biten adımlar korunur. Onay bekleyen, bitmiş, reddedilmiş ya da kalan adımı olmayan araştırma için `409`, bilinmeyen iş parçacığı için `404` döner. Kampanya modunda kampanya durmuşsa (`failed`, `cancelled` ya da bayat) kampanya yeniden kuyruğa alınır ve araştırma iş parçacığına bağlanır; kampanya bitince araştırma kaldığı yerden devam eder. Hata kaydı silinir, bir günlük başlatma hakkı harcanır. `GET /research/{id}` yanıtındaki `can_retry` bu uçun kullanılabilir olup olmadığını söyler.

### `GET /campaign/{campaign_id}/summary`, `GET /glossary`, `GET /vocabulary`

`/campaign/{id}/summary?lang=tr|en` kampanyayı herkesin okuyacağı dille özetler: tek cümlelik başlık, her iddia için sade karar etiketi ve tonu, güven düzeyi, "kaç veri setinde üstün" sayıları, veri seti başına skor grafiği noktaları, genel sıralama, yöntem maddeleri, dikkat notları, ilerleme ve (varsa) `error_info` (başlık, sebep, öneri, teknik ayrıntı). Bilinmeyen dil `422` döner. `/glossary?lang=` terim sözlüğünü, `/vocabulary?lang=` model, veri seti ve ölçüt adlarını verir. Karar mantığı değişmez, bu uçlar yalnız sunar.

### Erişim koruması: `API_KEY`, `DAILY_START_LIMIT`, `GET /usage`

`CELERY_VISIBILITY_TIMEOUT` (saniye, varsayılan 7200) kampanya görevinin işçi öldüğünde yeniden teslim edilmeden önce bekleme süresidir; çalışan kampanya 15 saniyede bir nabız yazdığından kopya teslimler canlı işçiyi bekler, ölü işçinin kampanyası ise yeniden çalışır. `.env` içinde `API_KEY` tanımlıysa `POST /experiments`, `/start_research`, `/approve_plan`, `/start_campaign`, `/start_research_session` ile tüm iptal ve yeniden başlatma uçları `X-API-Key` başlığı ister (yoksa ya da yanlışsa `401`, `[unauthorized]`); tanımlı değilse uçlar açıktır. `DAILY_START_LIMIT` (varsayılan 100, `0` sınırsız) günlük başlatma sayısını sınırlar; aşılırsa `429` (`[daily_limit]`). Sayaç `reports/usage.json` dosyasındadır, `GET /usage` bugünkü kullanımı ve kalan hakkı verir. Konsol anahtarı `NEXT_PUBLIC_API_KEY` ile gönderir ve iki durumu da sade dille anlatır.

### `POST /approve_plan`

Gövde:

```json
{"thread_id": "...", "decision": "Y", "selected": 1}
```

`selected` çalıştırılacak hipotezin sıfırdan başlayan sırasıdır ve `Y` için zorunludur. Eksik, aralık dışı veya sayı olmayan bir değer `422` döner ve hiçbir şey değişmez. `N` için gerekmez. Yalnız seçilen hipotez çalışır, hafızaya yazılır ve makaleye girer; öbür ikisi atılır. Konsoldaki onay diyalogu üç hipotezi veri seti ve parametreleriyle gösterir, başta hiçbiri seçili değildir ve onay düğmesi seçim yapılana kadar pasiftir. `GET /research/{thread_id}` `experiment_specs` ve `selected_hypothesis` alanlarını da döner.

`Y` state'i `approval_status="approved"` yapar, devam görevini Celery kuyruğuna atar ve hemen `{"status": "running"}` döner. Graf işçide kaldığı yerden devam eder; ilerleme `GET /research/{thread_id}` ile izlenir. Aynı araştırmaya ikinci karar `research thread was already decided` ile reddedilir. Kuyruk kapalıysa `503` döner ve onay geri alınır. `experiment_node` `Onaylandı, deneylere başlanıyor` logunu basar. Betiğe yalnız sorguda adı geçen modeller girer. Ardından seçilen hipotezi ve `experiment_specs` içindeki spesifikasyonunu şu CSV şemasıyla Faz 1 döngüsüne verir. Üretilen kod veri setini ve `params` değerlerini kurucularda aynen kullanmıyorsa AST denetimi reddeder ve kod düzeltilir:

```text
age:float, monthly_spend:float, tenure_months:int, churn:int
```

Son çalışan kod `current_experiment_code` alanına, ilk modelin Accuracy ve F1 değerleri `experiment_metrics` alanına, tüm modeller `model_results` alanına, veri profili `dataset_profile` alanına yazılır. Ardından `verifier_node` iki kontrol yapar:

1. Betik on bölme tohumunu kendi döngüsünde basıyorsa o satırlar kullanılır. Basılmıyorsa yalnız `train_test_split` içindeki `random_state` 42, 100, 200, 300, 400, 500, 600, 700, 800 ve 900 yapılır ve her değer E2B'de yeniden çalışır (on ayrı sandbox koşusu). Bölmeler stratify'lıdır: deney ajanı her `train_test_split` çağrısına `stratify=y` verir ve üretilen kod bunu taşımıyorsa AST denetimi reddedip kodu düzelttirir. Tohumlar `app/seeds.py` içinde tek yerde durur, prompt ve doğrulayıcı oradan okur. Veri üretim tohumu ve model tohumu değişmez. Her model için Accuracy, F1, ROC-AUC, PR-AUC ve eğitim süresinin ortalaması, standart sapması ve varyansı NumPy ile hesaplanır ve `statistical_results` sözlüğüne yazılır. Varyans, standart sapmanın karesidir. Kontrol girdileri bu sözlükte ve sonuç tablosunda yer alır ama kararlılık, performans ve hipotez testlerine girmez. Aynı sözlüğe `statistical_conclusion` yazılır. Karar ROC-AUC için eşleştirilmiş Pitman-Morgan testi ve Holm düzeltmesiyle verilir, alfa 0.05'tir. Anlamlı fark yoksa beraberlik cümlesi kurulur. Tek bir model her rakibine karşı anlamlı biçimde düşük varyanslıysa o model daha kararlı ilan edilir. ROC-AUC veya F1 standart sapması 0.05'i geçerse doğrulayıcı bunu `statistical_decision` içindeki `instability` bulgusuna yazar (`unstable`, `std_threshold`, `flagged`). Bu bir hata değildir, kodu yeniden ürettirmez ve `Passed` sonucunu bozmaz.
2. Kodu veri sızıntısı için inceler. Örneğin ayrılmadan önce `fit_transform` veya imputation varsa sebebiyle birlikte `Failed` döner.

`verification_status` `Passed` ise akış `report_node`'a gider. Yalnız gerçek hatalar `Failed` yapar: metrik üretilmemesi, sandbox çökmesi ve veri sızıntısı. Yüksek varyans `Failed` yapmaz; rapor onu Results ve Conclusion içinde limitasyon olarak yazar, hakem raporlandığını kontrol eder. `Failed` ise eleştiri `verifier_feedback` olarak `experiment_node`'a geri gider ve kod düzeltilir. Bu dönüş en fazla 2 kez olur. İkinci düzeltmeden sonra doğrulayıcı hâlâ onaylamazsa deney `is_success=False` ile hafızaya yazılır ve yine `report_node` çalışır. Sızıntı mesajı `Leakage çözülemedi` ile başlar.

Rapor `reports/{thread_id}_paper.md` dosyasına yazılır. Tema kullanıcının sorgusudur. Metodoloji örnek, öznitelik ve dengesizlik oranını yazar. Atıf yalnız literatür bağlamındaki kaynaktan gelir. Results tablosu `statistical_results` içindeki Mean ± Std Dev değerleridir. Sütunlar Model, Accuracy, F1, ROC-AUC, PR-AUC ve Train seconds olur. Results ve Conclusion, kazanan seçmez; `statistical_decision` yönünde İngilizce yazılır. Ardından `consistency_checker_node` makaleyi bu sözlük ve karar ile okur. `outcome` `tie` iken makalede üstünlük kelimesi varsa LLM çağrılmaz ve rapor `Yön Çelişkisi: İstatistiksel fark yokken üstünlük iddia edildi` ile yeniden yazılır. Başka tutarsızlık varsa da rapor en fazla 2 kez yeniden yazılır. Kontrol temizse `research_status` `Completed` olur. İki yeniden yazmadan sonra da tutarsızlık sürerse `NeedsReview` olur ve konsol makalenin üstünde uyarı gösterir. Aynı metin `GET /reports/{thread_id}` ucundan ve konsoldaki `/result/{thread_id}` sayfasından okunur.

Konsolda araştırma kutusu boştur. Start Research, kutu doluyken isteği gönderir. Çalışma bitene, plan reddedilene veya doğrulama başarısız olana kadar kutu kilitli kalır. Red veya başarısızlıktan sonra yeni bir sorgu yazılabilir.

`N` state'i `approval_status="rejected"` yapar ve akış orada biter. Deney düğümü çalışmaz.

```json
{"thread_id": "...", "status": "ended", "approval_status": "rejected"}
```

## Araştırma ajanı oturumları

Bir oturum 16 veri setlik havuzu bir kez keşif (6) ve doğrulama (10) diye ayırır, hipotezleri yalnız keşif sonuçlarına bakarak önerir, kaydeder ve her birini mühürlü doğrulama veri setlerinde tek bir Holm düzeltmesiyle bir kez sınar. Tasarım: [`RESEARCH_AGENT.md`](../RESEARCH_AGENT.md).

### `POST /start_research_session`

```json
{"models": ["RandomForest", "ExtraTrees", "MLP", "LogisticRegression"], "tuning": 12, "seed": 0, "generator": "rules"}
```

`models` en az iki farklı model anahtarıdır; `tuning` (isteğe bağlı, model başına 4-40 deneme) ayarlı aşamayı ekler; `generator` `rules` ya da `llm` olur (`llm` için OpenAI erişimi önce denetlenir, yoksa `503`). Bilinmeyen alan ve geçersiz girdi `422` döner. Bir günlük başlatma hakkı harcar. Yanıt `{"session_id": "r-xxxxxxxx", "status": "queued"}` olur.

### `GET /research_sessions`, `GET /research_sessions/{id}`, `GET /research_sessions/{id}/report`

Liste en yeni başta özetleri verir: `status` (`queued`, `running`, `completed`, `aborted`, `failed`, `cancelled`), `phase`, veri seti bazında `progress` (`stage`, `total`, `finished`, `failed`, `running`) ve `confirmed`, `reversed`, `not_confirmed`, `not_testable` sayıları. Ayrıntı ucu özeti, tüm oturumu (SHA-256 özetli hipotezler, doğrulamalar, atlanan öneriler) ve `intact` alanını döner; kayıtlı bir hipotez özetiyle uyuşmuyorsa `intact` `false` olur. `/report` Markdown raporunu verir.

### `POST /research_sessions/{id}/cancel`, `POST /research_sessions/{id}/retry`

İptalde sıradaki oturum hemen `cancelled` olur; çalışan oturumda iptal isteği bırakılır, çalışan veri setleri biter ve hiçbir hipotez kaydedilmeden durur (yarım aşama sonucu diske yazılmaz). Yeniden başlatma `failed`, `cancelled` ve `aborted` oturumlarda çalışır: bitmiş aşamaların sonuçları yeniden kullanılır, hipotezler yine yalnız keşif görünümünden önerilir; bir günlük başlatma hakkı harcar. İşçi 90 saniyedir nabız yazmıyorsa oturum `failed` (bayat) görünür ve yeniden başlatılabilir. İkisi de API anahtarı tanımlıysa onu ister.

