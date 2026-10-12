# AxiomForge

Altı katman ayakta: Faz 1 deney döngüsü, Faz 2 çoklu ajan grafı, Faz 2.5 deney hafızası, Faz 3 doğrulayıcı ve eleştiri döngüsü, Faz 4 rapor ajanı ve Next.js konsolu, Faz 5 bilimsel sıkılık.

Faz 1 tek başına bir sınıflandırma deneyi üretir, kodu E2B sandbox içinde çalıştırır ve hata olursa en fazla 3 denemede kendini düzeltir. Sonuç hem yerel MLflow sunucusuna hem de deney hafızasına yazılır.

Faz 2 araştırma grafıdır. Literatür taranır, üç hipotez üretilir ve deney düğümüne geçmeden önce onay beklenir. Graf durumu PostgreSQL'de tutulur.

Faz 2.5 RAG tabanlı deney hafızasıdır. Geçmiş deneyler `pgvector` içinde gömülür. Planlayıcı yeni hipotez üretirken başarısız kayıtları okur ve aynı yaklaşımı tekrar etmez. Onaydan sonra `experiment_node`, ilk hipotezi Faz 1 döngüsüne verir. Başarı `is_success=True` ve metriklerle, üç denemenin de başarısızlığı `is_success=False` ve hata loguyla kaydedilir.

Faz 3 doğrulayıcıdır. `verifier_node` kodu veri sızıntısı için inceler. Kararlılık ölçümü Faz 5'teki beş tohumdur. `verification_status` `Passed` veya `Failed` olur. Başarısız sonuç en fazla 2 kez eleştiriyle `experiment_node`'a geri gider. İkinci düzeltmeden sonra da onay yoksa kayıt `is_success=False` ve doğrulayıcının mesajıyla hafızaya yazılır.

Faz 4 rapor ajanı ve onu süren arayüzdür. Doğrulama `Passed` olunca ya da eleştiri hakkı bitip `Failed` hafızaya yazılınca `report_node` çalışır. Atölye makalesi `reports/{thread_id}_paper.md` dosyasına kaydedilir ve `research_status` `Completed` olur. Next.js konsolu aynı akışı `http://127.0.0.1:3000` üzerinde gösterir. Grafın düğüm sırası `GRAPH.md` içindedir.

Faz 5, Faz 4'ten sonraki bilimsel sıkılıktır. Deney ajanı `experiment-v3` ile soruda adı geçen modelleri aynı eğitim-test bölünmesinde karşılaştırır. Veri, `sklearn.datasets` içinden gerçekçi bir sınıflandırma seti ya da bilinçli dengesiz bir `make_classification` setidir. Küçük sentetik CSV tek kaynak olmaz. Dengesiz veride Accuracy tek başına yeterli sayılmaz. Betik önce veri seti satırını, sonra her model için Accuracy, F1, ROC-AUC, PR-AUC, eğitim süresi ve karışıklık matrisini basar. Üst MLflow run'ı veri profilini tutar. Her model iç içe bir run olur. Doğrulayıcı aynı kodu 42, 100, 200, 300 ve 400 tohumlarıyla yeniden çalıştırır. Model başına ROC-AUC ve F1 için ortalama ve örneklem standart sapması hesaplanır. Sapma 0.05'i geçerse sonuç `Kararsız (Unstable)` ve `Failed` olur. Bu özet `statistical_results` alanına yazılır. Raporun teması kullanıcının sorgusudur. Bir modelin daha iyi olduğu yalnız ROC-AUC veya PR-AUC ile yazılır. Düşük F1, modelin kusursuz olduğu iddiasına çevrilmez. Metodoloji örnek sayısını, öznitelik sayısını ve sınıf dengesini içerir. Yöntem atfı yalnız `literature_context` içindeki yazar veya arXiv kaydından gelir. Results metrikleri Mean ± Std Dev biçimindedir. Birden fazla model varsa karşılaştırma tablosu eklenir. Konsolda sorgu kutusu boş açılır. Plan reddedilirse veya çalışma başarısız olursa yeni bir sorgu yazılabilir.

## Ne var

- FastAPI uygulaması
- Celery işçisi, broker olarak Redis
- Experiment Agent: GPT-4o (`experiment-v3`) ile aynı veride model karşılaştırması üretir
- E2B Code Interpreter: üretilen kodu izole ortamda çalıştırır
- Kendi kendini düzeltme: sandbox traceback'i ajana geri verilir, en fazla 3 deneme
- MLflow: veri profili üst run'da, her modelin Accuracy, F1, ROC-AUC, PR-AUC, süre ve karışıklık sayıları iç içe run'da
- LangGraph: literatür → plan → onay → deney → doğrulayıcı → rapor
- Doğrulayıcı: beş tohum, ROC-AUC ve F1 sapması, sızıntı analizi ve en fazla 2 eleştiri turu
- Rapor ajanı: sorgu teması, zorunlu atıf, Mean ± Std Dev ve karşılaştırma tablosu
- Next.js konsolu: canlı zaman çizelgesi, onay ve makale görünümü
- arXiv araması: sorguya en yakın 3 makalenin başlığı ve özeti
- Planlayıcı: literatür ve geçmiş başarısız deneylerden 3 test edilebilir hipotez
- PostgresSaver: graf durumu `DATABASE_URL` üzerinden kaydedilir
- Deney hafızası: `text-embedding-3-small` ile `experiment_memory` koleksiyonu

Başarılı deneyde MLflow run'ı `Finished` olur. Üç deneme de başarısızsa run `Failed` olarak kapanır. Hafıza kaydı MLflow çağrısından önce yazılır. Üretilen deney kodu yerel makinede çalıştırılmaz.

## Dizin

```text
app/
  main.py                    FastAPI uçları
  config.py                  ortam ayarları
  celery_app.py              Celery uygulaması
  experiments.py             3 denemelik düzeltme döngüsü ve hafıza kaydı
  agents/experiment.py       kod üreten ve düzelten ajan
  agents/literature.py       arXiv araçlı literatür ajanı
  agents/planner.py          geçmiş hataları eleyen hipotez ajanı
  agents/report.py           atölye makalesi yazan ajan
  tools/arxiv.py             arXiv arama aracı
  graph/state.py             AgentState
  graph/nodes.py             literatür, plan, deney, doğrulayıcı ve rapor düğümleri
  graph/verifier.py          beş tohum, sapma ve sızıntı kararı
  graph/workflow.py          StateGraph, kesinti, onay ve koşullu dönüş
  memory/enable_pgvector.sql pgvector eklentisi
  memory/rag_memory.py       vektör kayıt ve arama
  sandbox/e2b_runner.py      E2B çalıştırma
  tracking/mlflow_logger.py  metrik ayrıştırma ve MLflow kaydı
test_memory.py               hafızaya yazıp okuma denemesi
GRAPH.md                     araştırma grafının mimarisi
frontend/                    Next.js araştırma konsolu
docker-compose.yml           Redis ve pgvector PostgreSQL
requirements.txt
.env                         OPENAI_API_KEY, E2B_API_KEY, DATABASE_URL
```

## Ortam

`.env`:

```text
OPENAI_API_KEY=
E2B_API_KEY=
DATABASE_URL=postgresql://axiomforge:axiomforge@localhost:5432/axiomforge
```

`E2B_API_KEY` yoksa sandbox açılmaz. `DATABASE_URL` yoksa araştırma grafı ve deney hafızası başlamaz. Redis adresi kodda `redis://localhost:6379/0` olarak sabittir. MLflow adresi `http://127.0.0.1:5000` olarak sabittir. Postgres imajı `pgvector/pgvector:pg16` kullanır.

`AgentState` alanları `GRAPH.md` içindedir. Rapor bitince `research_status` değeri `Completed` olur.

## Kurulum

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
docker compose up -d
```

## Çalıştırma

API, kuyruk, takip ve konsol ayrı ayrı açılır.

```powershell
.\.venv\Scripts\mlflow.exe server --host 127.0.0.1 --port 5000
.\.venv\Scripts\celery.exe -A app.celery_app worker --pool=solo --loglevel=info
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
cd frontend
npm run dev
```

Konsol `http://127.0.0.1:3000` adresindedir. Windows üzerinde Celery `--pool=solo` ile çalışır.

Hafızayı grafın dışında denemek için:

```powershell
.\.venv\Scripts\python.exe test_memory.py
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
5. Çıktıdan veri profili ve model satırları okunur. Üst MLflow run'ına profil ve `prompt_version=experiment-v3` yazılır. Her model kendi iç içe run'ında Accuracy, F1, ROC-AUC, PR-AUC, eğitim süresi ve karışıklık sayılarını alır.
6. Aynı sonuç `save_experiment` ile vektör hafızaya da yazılır. Başarıda `is_success=true` ve metrik, üç deneme de düşerse `is_success=false` ve hata logu kaydedilir.

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
{"query": "tabular data classification"}
```

Akış `literature_node` ve `planner_node` çalıştıktan sonra, `experiment_node` öncesinde durur.

1. Literatür ajanı arXiv'den 3 makalenin başlık ve özetini alır, `literature_context` listesine yazar.
2. Planlayıcı `search_past_experiments` ile sorguya en yakın 3 geçmiş deneyi okur. Başarısız kayıtları prompta koyar ve aynı yaklaşımı tekrar etmez.
3. Üç test edilebilir hipotez `hypotheses` listesine yazılır.
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

### `POST /approve_plan`

Gövde:

```json
{"thread_id": "...", "decision": "Y"}
```

`Y` state'i `approval_status="approved"` yapar ve graf kaldığı yerden devam eder. `experiment_node` `Onaylandı, deneylere başlanıyor` logunu basar, ardından ilk hipotezi şu CSV şemasıyla Faz 1 döngüsüne verir:

```text
age:float, monthly_spend:float, tenure_months:int, churn:int
```

Son çalışan kod `current_experiment_code` alanına, ilk modelin Accuracy ve F1 değerleri `experiment_metrics` alanına, tüm modeller `model_results` alanına, veri profili `dataset_profile` alanına yazılır. Ardından `verifier_node` iki kontrol yapar:

1. Koddaki `random_state`, `random_seed` ve `seed` değerlerini sırayla 42, 100, 200, 300 ve 400 yapar. Her tohum E2B'de yeniden çalışır. Model başına ROC-AUC ve F1 için ortalama ve standart sapma `statistical_results` alanına yazılır. Sapma 0.05'i geçerse bu `Kararsız (Unstable)` sayılır.
2. Kodu veri sızıntısı için inceler. Örneğin ayrılmadan önce `fit_transform` veya imputation varsa sebebiyle birlikte `Failed` döner.

`verification_status` `Passed` ise akış `report_node`'a gider. `Failed` ise eleştiri `verifier_feedback` olarak `experiment_node`'a geri gider ve kod düzeltilir. Bu dönüş en fazla 2 kez olur. İkinci düzeltmeden sonra doğrulayıcı hâlâ onaylamazsa deney `is_success=False` ile hafızaya yazılır ve yine `report_node` çalışır. Sızıntı mesajı `Leakage çözülemedi` ile başlar.

Rapor `reports/{thread_id}_paper.md` dosyasına yazılır. Tema kullanıcının sorgusudur. Metodoloji örnek, öznitelik ve dengesizlik oranını yazar. Atıf yalnız literatür bağlamındaki kaynaktan gelir. Results, doğrulayıcının Mean ± Std Dev değerlerini kullanır. Birden fazla model varsa tablo sütunları Model, Accuracy, F1, ROC-AUC, PR-AUC, Train seconds, TN, FP, FN ve TP olur. `research_status` `Completed` olur. Aynı metin `GET /reports/{thread_id}` ucundan ve konsoldaki `/result/{thread_id}` sayfasından okunur.

Konsolda araştırma kutusu boştur. Start Research, kutu doluyken isteği gönderir. Çalışma bitene, plan reddedilene veya doğrulama başarısız olana kadar kutu kilitli kalır. Red veya başarısızlıktan sonra yeni bir sorgu yazılabilir.

`N` state'i `approval_status="rejected"` yapar ve akış orada biter. Deney düğümü çalışmaz.

```json
{"thread_id": "...", "status": "ended", "approval_status": "rejected"}
```
