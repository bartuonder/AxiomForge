# AxiomForge

Dokuz katman ayakta: Faz 1 deney döngüsü, Faz 2 çoklu ajan grafı, Faz 2.5 deney hafızası, Faz 3 doğrulayıcı ve eleştiri döngüsü, Faz 4 rapor ajanı ve Next.js konsolu, Faz 5 bilimsel sıkılık, Faz 6 iddia doğrulama, Faz 7 deney tasarımı ve oturum izolasyonu, Faz 8 model seçimi ve istatistiksel karar kapısı.

Başka bir bilgisayarda veya yeni bir oturumda devam etmek için önce `CONTINUATION.md` okunur.

Faz 1 tek başına bir sınıflandırma deneyi üretir, kodu E2B sandbox içinde çalıştırır ve hata olursa en fazla 3 denemede kendini düzeltir. Sonuç hem yerel MLflow sunucusuna hem de deney hafızasına yazılır.

Faz 2 araştırma grafıdır. Literatür taranır, üç hipotez üretilir ve deney düğümüne geçmeden önce onay beklenir. Graf durumu PostgreSQL'de tutulur.

Faz 2.5 RAG tabanlı deney hafızasıdır. Geçmiş deneyler `pgvector` içinde gömülür. Planlayıcı yeni hipotez üretirken başarısız kayıtları okur ve aynı yaklaşımı tekrar etmez. Onaydan sonra `experiment_node`, seçilen hipotezi Faz 1 döngüsüne verir. Başarı `is_success=True` ve metriklerle, üç denemenin de başarısızlığı `is_success=False` ve hata loguyla kaydedilir. Grafın içinde bu kayıt deney düğümünden değil, doğrulamadan sonra `verifier_node` içinden bir kez yazılır: `hypothesis` onaylanan spesifikasyonun `statement` metnidir, `spec` alanı spesifikasyonu taşır, `metric` doğrulayıcının ortalama ± standart sapma özetidir. Doğrulama geçtiyse `outcome` `success` olur. Yüksek varyans bulgusu varsa `outcome` `finding` olur, `finding` alanı hangi modelin hangi metriğinin eşiği aştığını yazar ve `is_success` doğru kalır. Planlayıcı yalnız `is_success=False` kayıtları okuyup eler.

Faz 3 doğrulayıcıdır. `verifier_node` kodu veri sızıntısı için inceler. Kararlılık ölçümü bölme tohumlarıdır (Faz 5'te beş, sonradan on). `verification_status` `Passed` veya `Failed` olur. Başarısız sonuç en fazla 2 kez eleştiriyle `experiment_node`'a geri gider. İkinci düzeltmeden sonra da onay yoksa kayıt `is_success=False` ve doğrulayıcının mesajıyla hafızaya yazılır.

Faz 4 rapor ajanı ve onu süren arayüzdür. Doğrulama `Passed` olunca ya da eleştiri hakkı bitip `Failed` hafızaya yazılınca `report_node` çalışır. Atölye makalesi `reports/{thread_id}_paper.md` dosyasına kaydedilir. `research_status` `Completed` olması Faz 6'daki iddia kontrolünden sonradır. Next.js konsolu aynı akışı `http://127.0.0.1:3000` üzerinde gösterir. Grafın düğüm sırası `GRAPH.md` içindedir.

Faz 5, Faz 4'ten sonraki bilimsel sıkılıktır. Deney ajanı `experiment-v3` ile soruda adı geçen modelleri aynı eğitim-test bölünmesinde karşılaştırır. Veri, `sklearn.datasets` içinden gerçekçi bir sınıflandırma seti ya da bilinçli dengesiz bir `make_classification` setidir. Küçük sentetik CSV tek kaynak olmaz. Dengesiz veride Accuracy tek başına yeterli sayılmaz. Betik önce veri seti satırını, sonra her model için Accuracy, F1, ROC-AUC, PR-AUC, eğitim süresi ve karışıklık matrisini basar. Üst MLflow run'ı veri profilini tutar. Her model iç içe bir run olur. Doğrulayıcı aynı kodu 42, 100, 200, 300 ve 400 tohumlarıyla yeniden çalıştırır. Model başına ROC-AUC ve F1 için ortalama ve örneklem standart sapması hesaplanır. Sapma 0.05'i geçerse bu bir bulgu olarak kaydedilir ve sonuç `Failed` olmaz. Bu özet `statistical_results` alanına yazılır. Raporun teması kullanıcının sorgusudur. Bir modelin daha iyi olduğu yalnız ROC-AUC veya PR-AUC ile yazılır. Düşük F1, modelin kusursuz olduğu iddiasına çevrilmez. Metodoloji örnek sayısını, öznitelik sayısını ve sınıf dengesini içerir. Yöntem atfı yalnız `literature_context` içindeki yazar veya arXiv kaydından gelir. Results metrikleri Mean ± Std Dev biçimindedir. Birden fazla model varsa karşılaştırma tablosu eklenir. Konsolda sorgu kutusu boş açılır. Plan reddedilirse veya çalışma başarısız olursa yeni bir sorgu yazılabilir.

Faz 6 iddia doğrulamadır. Beş tohumun Accuracy, F1, ROC-AUC, PR-AUC ve eğitim süresi ortalaması ile standart sapması NumPy ile hesaplanır. Sonuç, model adına göre `statistical_results` sözlüğüne yazılır. Rapor bu sayıları kopyalar; kendi ortalamasını üretmez ve tabloyu tek koşuya göre kurmaz. `report_node` ardından `consistency_checker_node` çalışır. Hakem makaledeki sayıları bu sözlükle karşılaştırır, yüksek sapmaya rağmen kesin üstünlük iddiasını ve yalnız ROC-AUC övgüsünü arar. Tutarsızlık varsa eleştiri `consistency_feedback` olur ve rapor en fazla 2 kez yeniden yazılır. Kontrol temizse `research_status` `Completed` olur. İki yeniden yazmadan sonra da tutarsızlık sürerse `NeedsReview` olur. Konsoldaki son adım Claims'tir.

Faz 7 deney tasarımı ve bağlam izolasyonudur. Deney ajanı `experiment-v4` kullanır. Veri, döngünün dışında bir kez ve sabit bir tohumla yüklenir veya üretilir. `make_classification` kullanılıyorsa `class_sep` 0.5 veya daha düşüktür ve `weights` ile dengesiz bir dağılım kurulur. Beşli döngü yalnız `train_test_split` içindeki `random_state` değerini 42, 100, 200, 300 ve 400 yapar. Model tohumu ve veri üretim tohumu değişmez. Her model için beş satır basılır. Betik bu döngüyü içeriyorsa doğrulayıcı o satırlardan ortalama ve standart sapma hesaplar. İçermiyorsa doğrulayıcı yalnız bölme tohumunu değiştirerek beş kez çalıştırır. Standart sapma ile varyans ayrıdır. Varyans, standart sapmanın karesidir. `statistical_results` içindeki `std` alanları standart sapmadır. Her `/start_research` yeni bir `thread_id` ve boş `AgentState` açar. Checkpoint doluysa o oturuma yazılmaz. `tested_models` yalnız bu koşunun modelleridir. RAG kaydındaki eski kod ve metrik rapora verilmez. Results ve Conclusion, Methodology bölümünde yazılmayan ve test edilmeyen hiçbir modeli alamaz.

Faz 8 model seçimi ve istatistiksel karar kapısıdır. Deney ajanı `experiment-v5` kullanır. Betik yalnız sorguda açıkça adı geçen modelleri eğitir. Promptta varsayılan model yoktur. `models` sözlüğünün anahtarları bu listeyle birebir aynıdır. Hipotez listeye model ekleyemez. Sorguda model adı yoksa deney başlamaz. Doğrulayıcı her metrik için `std ** 2` değerini `{metrik}_variance` alanına yazar. `statistical_conclusion` ve `statistical_decision` Python'da kurulur. Karar sabit bir fark eşiğine değil istatistik testine dayanır. Aynı beş bölme her modelde kullanıldığı için ROC-AUC değerleri eşleştirilmiş sayılır ve her model çifti Pitman-Morgan varyans eşitliği testiyle karşılaştırılır. Çoklu karşılaştırma Holm yöntemiyle düzeltilir, eşik `ALPHA = 0.05`. Bir model kendisine karşı tüm çiftlerde düzeltilmiş p < 0.05 ve daha düşük varyansa sahipse `winner`, aksi halde `tie` olur. `tie` eşdeğerliği kanıtlamaz, yalnız anlamlı fark bulunmadığını söyler. En az 3 bölme ve tüm modellerde eşit uzunlukta seri yoksa karar `none` olur. Tek modelde cümle boştur. Performans farkı için her model çifti ve ROC-AUC, PR-AUC, F1 üzerinde eşleştirilmiş farka düzeltilmiş yeniden örnekleme t-testi (Nadeau-Bengio) uygulanır. Test boyutu karışıklık matrisinden, eğitim boyutu veri profilindeki örnek sayısından okunur. Karar `statistical_decision` alanında yapısal olarak da tutulur: `outcome` (`tie`, `winner` veya `none`), `winner`, `metric`, `test`, `alpha`, `n_splits`, `min_adjusted_p`, çift başına `comparisons` ve `performance`. `performance` satırları `mean_difference`, `effect_size_dz`, `p_value`, Holm düzeltmeli `adjusted_p_value` ve `significant` taşır. Rapor bir metrikte fark iddiasını yalnız `significant` olan satır için kurabilir. `statistical_conclusion` bu kararın İngilizce cümlesidir ve tablo satırı değildir. Makale İngilizce yazılır. Rapor cümleyi aynen kopyalamak zorunda değildir ama kararın yönünü değiştiremez, kazanan seçmez. `outcome` `tie` iken olumsuzlama içermeyen bir cümlede `superior`, `more stable`, `outperformed` veya `better` geçiyorsa hakem LLM çağrısı yapmaz. Geri bildirim `Yön Çelişkisi: İstatistiksel fark yokken üstünlük iddia edildi` olur ve rapor yeniden yazılır. `outcome` `winner` iken makale kazananı adlandırmalı ve fark olmadığını yazmamalıdır.

## Ne var

- FastAPI uygulaması
- Celery işçisi, broker olarak Redis: araştırma onaya kadar ve onaydan sonra rapora kadar işçide çalışır
- Experiment Agent: GPT-4o (`experiment-v7`) ile sabit veride, sorguda adı geçen modelleri ve yalnız bölme tohumunu değiştiren, stratify'lı on bölmelik karşılaştırma üretir
- E2B Code Interpreter: üretilen kodu izole ortamda çalıştırır
- Kendi kendini düzeltme: sandbox traceback'i ajana geri verilir, en fazla 3 deneme
- MLflow: grafta doğrulamadan sonra tek bir üst run açılır. Veri profili, her modelin doğrulanmış ortalama, standart sapma ve varyansı ve karar etiketleri üst run'a, her bölme `seed` ve `split_index` ile iç içe run'a yazılır
- LangGraph: literatür → plan → onay → deney → doğrulayıcı → rapor → iddia kontrolü
- Doğrulayıcı: on tohum, NumPy ortalama, sapma ve varyans, Pitman-Morgan ve düzeltilmiş t-testleri, `statistical_conclusion`, sızıntı analizi ve en fazla 2 eleştiri turu
- Rapor ajanı: makale İngilizcedir, Results ve Conclusion `statistical_decision` yönünde yazılır
- İddia kontrolü: beraberlikte İngilizce üstünlük kelimesi LLM'den önce reddedilir. Doğrulama `Failed` iken özette bunu söylemeyen makale de LLM'siz reddedilir. Kararsızlık bulgusu varken özette `high variance across splits` yoksa veya işaretli model bir cümlede anlatılmıyorsa da reddedilir. En fazla 2 yeniden yazma. İki yeniden yazmadan sonra da tutarsızlık varsa `research_status` `NeedsReview` olur
- Next.js konsolu: canlı zaman çizelgesi, onay ve makale görünümü
- arXiv araması: LLM sorudan anahtar kelime aramaları üretir, adaylar gömü benzerliğiyle süzülür ve en alakalı 3 makalenin başlığı ve özeti alınır
- Planlayıcı: literatür ve geçmiş başarısız deneylerden, deney ajanının yapabildiği 3 doğrulanmış deney spesifikasyonu
- PostgresSaver: her araştırma boş bir `thread_id` ile `DATABASE_URL` üzerine kaydedilir
- Deney hafızası: `text-embedding-3-small` ile `experiment_memory` koleksiyonu

Grafın dışındaki `POST /experiments` ucunda başarılı deneyde MLflow run'ı `Finished` olur, üç deneme de başarısızsa run `Failed` olarak kapanır. Grafın içinde run doğrulamadan sonra bir kez açılır: doğrulama geçtiyse `Verified`, eleştiri hakkı bitip reddedildiyse `Failed`. Run kimliği state'te `mlflow_run_id` olarak durur. MLflow kapalıysa araştırma sürer ve kimlik boş kalır. Grafın dışındaki `POST /experiments` ucunda hafıza kaydı MLflow çağrısından önce yazılır. Üretilen deney kodu yerel makinede çalıştırılmaz.

## Dizin

```text
app/
  main.py                    FastAPI uçları
  config.py                  ortam ayarları
  celery_app.py              Celery uygulaması
  experiments.py             3 denemelik düzeltme döngüsü ve hafıza kaydı
  agents/experiment.py       kod üreten ve düzelten ajan
  agents/literature.py       anahtar kelime sorgusu ve alaka süzgeciyle literatür ajanı
  agents/planner.py          geçmiş hataları eleyen hipotez ajanı
  agents/spec.py             deney spesifikasyonu doğrulaması ve kod denetimi
  agents/report.py           atölye makalesi yazan ajan
  agents/consistency.py      makale sayıları ile istatistik sözlüğünü karşılaştıran hakem
  tools/arxiv.py             arXiv arama aracı
  tasks.py                   Celery görevleri: araştırmayı başlat ve onaydan sonra sürdür
  graph/state.py             AgentState
  graph/nodes.py             literatür, plan, deney, doğrulayıcı, rapor ve iddia düğümleri
  graph/verifier.py          on tohum, sapma, yapısal karar ve sızıntı kararı
  graph/errors.py            araştırma hatalarının PostgreSQL'e kaydı
  graph/stats.py             Pitman-Morgan testi, düzeltilmiş t-testi ve Holm düzeltmesi
  graph/workflow.py          StateGraph, kesinti, onay ve koşullu dönüş
  memory/enable_pgvector.sql pgvector eklentisi
  memory/rag_memory.py       vektör kayıt ve arama
  sandbox/e2b_runner.py      E2B çalıştırma
  tracking/mlflow_logger.py  metrik ayrıştırma ve MLflow kaydı
tests/                       pytest testleri: ayrıştırma, model adları, spesifikasyon, istatistik, doğrulayıcı, hakem, durum ve düğümler
test_memory.py               hafızaya yazıp okuma denemesi
pytest.ini                   test dizini ve import yolu
GRAPH.md                     araştırma grafının mimarisi
frontend/                    Next.js araştırma konsolu
docker-compose.yml           Redis, pgvector PostgreSQL, MLflow, API ve Celery işçisi
Dockerfile                   API, işçi ve MLflow için tek imaj
requirements.txt
requirements-dev.txt          requirements.txt ve pytest
.env                         OPENAI_API_KEY, E2B_API_KEY, DATABASE_URL
```

## Ortam

`.env`:

```text
OPENAI_API_KEY=
E2B_API_KEY=
DATABASE_URL=postgresql://axiomforge:axiomforge@localhost:5432/axiomforge
```

`E2B_API_KEY` yoksa sandbox açılmaz. `DATABASE_URL` yoksa araştırma grafı ve deney hafızası başlamaz. `REDIS_URL` varsayılanı `redis://localhost:6379/0`, `MLFLOW_TRACKING_URI` varsayılanı `http://127.0.0.1:5000` olur ve ortam değişkeniyle değiştirilir. Postgres imajı `pgvector/pgvector:pg16` kullanır.

`AgentState` alanları `GRAPH.md` içindedir. İddia kontrolü temiz bitince `research_status` değeri `Completed`, tutarsızlık sürerse `NeedsReview` olur.

## Kurulum

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
docker compose up -d redis postgres
```

## Çalıştırma

İki yol var. Yerelde API, kuyruk, takip ve konsol ayrı ayrı açılır. Ya da API, işçi ve MLflow konteynerde çalışır (aşağıdaki Docker bölümü).

Yerel yol:

```powershell
.\.venv\Scripts\mlflow.exe server --host 127.0.0.1 --port 5000
.\.venv\Scripts\celery.exe -A app.celery_app worker --pool=threads --concurrency=4 --loglevel=info
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
cd frontend
npm run dev
```

Konsol `http://127.0.0.1:3000` adresindedir. Windows üzerinde Celery `--pool=threads` ile çalışır. `--pool=solo` da çalışır ama tek görev yürüttüğü için uzun bir araştırma başka araştırmaların başlamasını bekletir.

Hafızayı grafın dışında denemek için:

```powershell
.\.venv\Scripts\python.exe test_memory.py
```

## Docker

API, Celery işçisi ve MLflow sunucusu tek imajdan (`Dockerfile`) çalışır. Komut servise göre değişir. Redis ve Postgres hazır imajlardır.

```powershell
docker compose up -d --build
```

API `http://127.0.0.1:8000`, MLflow `http://127.0.0.1:5000` adresindedir. Konteynerler `DATABASE_URL`, `REDIS_URL` ve `MLFLOW_TRACKING_URI` değerlerini compose içinden alır (`postgres`, `redis`, `mlflow` servis adları). `OPENAI_API_KEY` ve `E2B_API_KEY` yerel `.env` dosyasından gelir; dosya imaja girmez ve yoksa compose yine çalışır. Makaleler `reports` hacmindedir ve API ile işçi aynı hacmi paylaşır. MLflow verisi `mlflow` hacmindedir. Konsol (Next.js) konteynerde değildir, `npm run dev` ile yerelde açılır. Yerel yolu kullanırken konteynerdeki API, işçi ve MLflow'u açmayın, 5000 ve 8000 portları çakışır: yalnız `docker compose up -d redis postgres` çalıştırın.

## Testler

Testler LLM, E2B, MLflow, Postgres ve Redis çağırmaz. Bu servisler düğüm testlerinde taklit edilir.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

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

1. Ajan, sorudaki modelleri aynı bölünmede eğiten bir scikit-learn betiği üretir. Önce `dataset=<name> samples=<int> features=<int> negative_ratio=<float> positive_ratio=<float>` basar. Her model için `model=<name> accuracy=<float> f1=<float> roc_auc=<float> pr_auc=<float> train_seconds=<float> tn=<int> fp=<int> fn=<int> tp=<int>` basar.
2. Şema yapısına uygun küçük bir CSV sandbox içine yazılır.
3. Betik E2B içinde çalıştırılır.
4. Kod hata verirse traceback ve hatalı kod ajana geri gönderilir. Döngü en fazla 3 denemedir.
5. Çıktıdan veri profili ve model satırları okunur. Grafın dışındaki bu uçta üst MLflow run'ına profil ve `prompt_version=experiment-v7` yazılır. Her model kendi iç içe run'ında Accuracy, F1, ROC-AUC, PR-AUC, eğitim süresi ve karışıklık sayılarını alır. Sayılar bilimsel gösterimle de yazılabilir (`4.5e-05`); ayrıştırıcı bunu okur. Sorgu model adı vermezse istek `422` ve `query names no model` ile reddedilir. Basılan model adları izin listesinden farklıysa betik sandbox başarısı sayılmaz.
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
{"query": "Compare SVM and Random Forest on tabular data classification"}
```

Sorguda en az bir model adı geçmelidir. Geçmiyorsa literatür çalışmadan `422` ve `query names no model` döner.

Akış `literature_node` ve `planner_node` çalıştıktan sonra, `experiment_node` öncesinde durur.

1. Literatür ajanı LLM ile sorudan en fazla 3 anahtar kelime araması üretir. Her arama 2-4 kısa ifadedir ve arXiv'e `all:"ifade" AND all:"ifade"` olarak gider. Aramalar arasında 3 saniye beklenir. Adaylar tekilleştirilir, sorunun gömüsüyle makale gömüsü arasındaki kosinüs benzerliği hesaplanır, `0.35` altındakiler elenir ve en iyi 3 makalenin başlığı ve özeti `literature_context` listesine yazılır. Hiçbiri eşiği geçmezse çalışma `arxiv returned no relevant papers` ile `failed` olur. Her skor logda `literature relevance` satırı olarak görünür.
2. Planlayıcı `search_past_experiments` ile sorguya en yakın 3 geçmiş deneyi okur. Başarısız kayıtları prompta koyar ve aynı yaklaşımı tekrar etmez.
3. Üç hipotez `hypotheses` listesine, spesifikasyonları `experiment_specs` listesine yazılır. Her hipotez bir deney spesifikasyonudur: `statement`, `models` (sorgudaki modellerin tamamı, Python doldurur), `dataset` (`breast_cancer` veya `imbalanced`) ve `params` (model başına izinli kurucu parametreleri). Geçersiz bir spesifikasyon bir kez düzeltme istenerek yeniden denenir, yine geçersizse çalışma `failed` olur.
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

`GET /research/{thread_id}` durumu `starting`, `running`, `paused`, `rejected`, `completed`, `needs_review` veya `failed` olarak döner. Onay öncesi ya da sonrası bir düğüm hata verirse mesaj PostgreSQL'deki `research_errors` tablosuna yazılır, durum `failed` olur ve mesaj `error` alanında görünür. `needs_review` makalenin iddia kontrolünden geçemediğini gösterir; sebep `consistency_feedback` alanındadır. Yanıt ayrıca `verification_status` ile birlikte `verifier_feedback` (doğrulama reddinin sebebi) ve `instability` alanını taşır: `{unstable, std_threshold, flagged: [{model, metric, std}]}`. Sonuç sayfası (`/result/{thread_id}`) bu alanlarla üç satırlık bir kontrol paneli gösterir: doğrulama geçti veya reddedildi (sebebiyle), eşiği aşan varyans bulgusu, iddia kontrolünün sonucu. Araştırma sürerken sayfa her 2 saniyede durumu okur ve hangi adımda olduğunu yazar. Araştırma `completed`, `needs_review`, `failed` veya `rejected` olunca yoklama durur ve rapor bir kez okunur.

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

1. Betik on bölme tohumunu kendi döngüsünde basıyorsa o satırlar kullanılır. Basılmıyorsa yalnız `train_test_split` içindeki `random_state` 42, 100, 200, 300, 400, 500, 600, 700, 800 ve 900 yapılır ve her değer E2B'de yeniden çalışır (on ayrı sandbox koşusu). Bölmeler stratify'lıdır: deney ajanı her `train_test_split` çağrısına `stratify=y` verir ve üretilen kod bunu taşımıyorsa AST denetimi reddedip kodu düzelttirir. Tohumlar `app/seeds.py` içinde tek yerde durur, prompt ve doğrulayıcı oradan okur. Veri üretim tohumu ve model tohumu değişmez. Her model için Accuracy, F1, ROC-AUC, PR-AUC ve eğitim süresinin ortalaması, standart sapması ve varyansı NumPy ile hesaplanır ve `statistical_results` sözlüğüne yazılır. Varyans, standart sapmanın karesidir. Aynı sözlüğe `statistical_conclusion` yazılır. Karar ROC-AUC için eşleştirilmiş Pitman-Morgan testi ve Holm düzeltmesiyle verilir, alfa 0.05'tir. Anlamlı fark yoksa beraberlik cümlesi kurulur. Tek bir model her rakibine karşı anlamlı biçimde düşük varyanslıysa o model daha kararlı ilan edilir. ROC-AUC veya F1 standart sapması 0.05'i geçerse doğrulayıcı bunu `statistical_decision` içindeki `instability` bulgusuna yazar (`unstable`, `std_threshold`, `flagged`). Bu bir hata değildir, kodu yeniden ürettirmez ve `Passed` sonucunu bozmaz.
2. Kodu veri sızıntısı için inceler. Örneğin ayrılmadan önce `fit_transform` veya imputation varsa sebebiyle birlikte `Failed` döner.

`verification_status` `Passed` ise akış `report_node`'a gider. Yalnız gerçek hatalar `Failed` yapar: metrik üretilmemesi, sandbox çökmesi ve veri sızıntısı. Yüksek varyans `Failed` yapmaz; rapor onu Results ve Conclusion içinde limitasyon olarak yazar, hakem raporlandığını kontrol eder. `Failed` ise eleştiri `verifier_feedback` olarak `experiment_node`'a geri gider ve kod düzeltilir. Bu dönüş en fazla 2 kez olur. İkinci düzeltmeden sonra doğrulayıcı hâlâ onaylamazsa deney `is_success=False` ile hafızaya yazılır ve yine `report_node` çalışır. Sızıntı mesajı `Leakage çözülemedi` ile başlar.

Rapor `reports/{thread_id}_paper.md` dosyasına yazılır. Tema kullanıcının sorgusudur. Metodoloji örnek, öznitelik ve dengesizlik oranını yazar. Atıf yalnız literatür bağlamındaki kaynaktan gelir. Results tablosu `statistical_results` içindeki Mean ± Std Dev değerleridir. Sütunlar Model, Accuracy, F1, ROC-AUC, PR-AUC ve Train seconds olur. Results ve Conclusion, kazanan seçmez; `statistical_decision` yönünde İngilizce yazılır. Ardından `consistency_checker_node` makaleyi bu sözlük ve karar ile okur. `outcome` `tie` iken makalede üstünlük kelimesi varsa LLM çağrılmaz ve rapor `Yön Çelişkisi: İstatistiksel fark yokken üstünlük iddia edildi` ile yeniden yazılır. Başka tutarsızlık varsa da rapor en fazla 2 kez yeniden yazılır. Kontrol temizse `research_status` `Completed` olur. İki yeniden yazmadan sonra da tutarsızlık sürerse `NeedsReview` olur ve konsol makalenin üstünde uyarı gösterir. Aynı metin `GET /reports/{thread_id}` ucundan ve konsoldaki `/result/{thread_id}` sayfasından okunur.

Konsolda araştırma kutusu boştur. Start Research, kutu doluyken isteği gönderir. Çalışma bitene, plan reddedilene veya doğrulama başarısız olana kadar kutu kilitli kalır. Red veya başarısızlıktan sonra yeni bir sorgu yazılabilir.

`N` state'i `approval_status="rejected"` yapar ve akış orada biter. Deney düğümü çalışmaz.

```json
{"thread_id": "...", "status": "ended", "approval_status": "rejected"}
```
