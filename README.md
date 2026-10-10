# AxiomForge

Birinci haftanın iskeleti. Bir sınıflandırma deneyi üretir, üretilen Python kodunu E2B sandbox içinde çalıştırır, hata olursa en fazla 3 denemede kendini düzeltir ve sonucu yerel MLflow sunucusuna yazar.

Henüz yok: LangGraph, PostgreSQL ve Next.js.

## Ne var

- FastAPI uygulaması
- Celery işçisi, broker olarak Redis
- Experiment Agent: GPT-4o (`experiment-v1`) ile scikit-learn sınıflandırma kodu üretir
- E2B Code Interpreter: üretilen kodu izole ortamda çalıştırır
- Kendi kendini düzeltme: sandbox traceback'i ajana geri verilir, en fazla 3 deneme
- MLflow: Accuracy, F1 ve deneme bilgisi `axiomforge` deneyine yazılır

Başarılı denemede run `Finished` olur. Üç deneme de başarısızsa run `Failed` olarak kapanır. Üretilen kod yerel makinede çalıştırılmaz.

## Dizin

```text
app/
  main.py                    FastAPI uçları
  config.py                  ortam ayarları
  celery_app.py              Celery uygulaması
  experiments.py             3 denemelik düzeltme döngüsü
  agents/experiment.py       kod üreten ve düzelten ajan
  sandbox/e2b_runner.py      E2B çalıştırma
  tracking/mlflow_logger.py  metrik ayrıştırma ve MLflow kaydı
docker-compose.yml           Redis
requirements.txt
.env                         OPENAI_API_KEY ve E2B_API_KEY
```

## Ortam

`.env`:

```text
OPENAI_API_KEY=
E2B_API_KEY=
```

`E2B_API_KEY` yoksa sandbox açılmaz. Redis adresi kodda `redis://localhost:6379/0` olarak sabittir. MLflow adresi `http://127.0.0.1:5000` olarak sabittir.

## Kurulum

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
docker compose up -d redis
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

Gövde:

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
