# AxiomForge

İki faz ayakta.

Faz 1 tek başına bir sınıflandırma deneyi üretir, kodu E2B sandbox içinde çalıştırır, hata olursa en fazla 3 denemede kendini düzeltir ve sonucu yerel MLflow sunucusuna yazar.

Faz 2 çoklu ajan grafıdır. Literatür taranır, üç hipotez üretilir ve deney düğümüne geçmeden önce onay beklenir. Graf durumu PostgreSQL'de tutulur. `experiment_node` şimdilik yalnızca onay logu basar; Faz 1 deney döngüsüne henüz bağlı değildir.

Henüz yok: Next.js ve grafın içinden Faz 1 deneyinin çalıştırılması.

## Ne var

- FastAPI uygulaması
- Celery işçisi, broker olarak Redis
- Experiment Agent: GPT-4o (`experiment-v1`) ile scikit-learn sınıflandırma kodu üretir
- E2B Code Interpreter: üretilen kodu izole ortamda çalıştırır
- Kendi kendini düzeltme: sandbox traceback'i ajana geri verilir, en fazla 3 deneme
- MLflow: Accuracy, F1 ve deneme bilgisi `axiomforge` deneyine yazılır
- LangGraph: `literature_node` → `planner_node` → onay → `experiment_node`
- arXiv araması: sorguya en yakın 3 makalenin başlığı ve özeti
- Planlayıcı: literatürden 3 test edilebilir hipotez
- PostgresSaver: graf durumu `DATABASE_URL` üzerinden kaydedilir

Başarılı deneyde MLflow run'ı `Finished` olur. Üç deneme de başarısızsa run `Failed` olarak kapanır. Üretilen deney kodu yerel makinede çalıştırılmaz.

## Dizin

```text
app/
  main.py                    FastAPI uçları
  config.py                  ortam ayarları
  celery_app.py              Celery uygulaması
  experiments.py             3 denemelik düzeltme döngüsü
  agents/experiment.py       kod üreten ve düzelten ajan
  agents/literature.py       arXiv araçlı literatür ajanı
  agents/planner.py          hipotez üreten ajan
  tools/arxiv.py             arXiv arama aracı
  graph/state.py             AgentState
  graph/nodes.py             literatür, plan ve deney düğümleri
  graph/workflow.py          StateGraph, kesinti ve onay
  sandbox/e2b_runner.py      E2B çalıştırma
  tracking/mlflow_logger.py  metrik ayrıştırma ve MLflow kaydı
docker-compose.yml           Redis ve PostgreSQL
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

`E2B_API_KEY` yoksa sandbox açılmaz. `DATABASE_URL` yoksa araştırma grafı başlamaz. Redis adresi kodda `redis://localhost:6379/0` olarak sabittir. MLflow adresi `http://127.0.0.1:5000` olarak sabittir.

`AgentState` alanları: `query`, `literature_context`, `hypotheses`, `approval_status`.

## Kurulum

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
docker compose up -d
```

## Çalıştırma

Üç süreç ayrı ayrı açılır.

```powershell
.\.venv\Scripts\mlflow.exe server --host 127.0.0.1 --port 5000
.\.venv\Scripts\celery.exe -A app.celery_app worker --pool=solo --loglevel=info
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```

Windows üzerinde Celery `--pool=solo` ile çalışır.

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

1. Ajan, `/home/user/data.csv` okuyan ve `accuracy=<float>` ile `f1=<float>` basan bir scikit-learn betiği üretir.
2. Şema yapısına uygun küçük bir CSV sandbox içine yazılır.
3. Betik E2B içinde çalıştırılır.
4. Kod hata verirse traceback ve hatalı kod ajana geri gönderilir. Döngü en fazla 3 denemedir.
5. Çıktıdan Accuracy ve F1 okunur. MLflow'a metriklerle birlikte `prompt_version`, `algorithm`, `model`, `attempts` ve `status` yazılır.

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
2. Planlayıcı bu bağlamdan 3 test edilebilir hipotez üretir ve `hypotheses` listesine yazar.
3. Graf `interrupt_before=["experiment_node"]` ile duraklar.

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

`Y` state'i `approval_status="approved"` yapar ve graf kaldığı yerden `experiment_node`'a devam eder. Bu düğüm şu an `Onaylandı, deneylere başlanıyor` logunu basar.

`N` state'i `approval_status="rejected"` yapar ve akış orada biter. Deney düğümü çalışmaz.

```json
{"thread_id": "...", "status": "ended", "approval_status": "rejected"}
```
