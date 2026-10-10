# AxiomForge

Otonom araştırma ajanının ilk iskeleti. Şu an bir sınıflandırma deneyi üretir, üretilen Python kodunu E2B sandbox içinde çalıştırır ve çıkan Accuracy ile F1 değerlerini yerel MLflow sunucusuna yazar.

Henüz yok: LangGraph, PostgreSQL, Next.js ve sandbox hatasında yeniden deneme.

## Ne var

- FastAPI uygulaması
- Celery işçisi, broker olarak Redis
- Experiment Agent: GPT-4o ile scikit-learn sınıflandırma kodu üretir
- E2B sandbox: üretilen kodu izole ortamda çalıştırır
- MLflow: başarılı çalışmanın Accuracy ve F1 metriklerini kaydeder

Sandbox bir istisna verirse hata yalnızca uygulama loguna yazılır. İstek yine üretilen kodu döner. Yeniden deneme yapılmaz.

## Dizin

```text
app/
  main.py                  FastAPI uçları
  config.py                ortam ayarları
  celery_app.py            Celery uygulaması
  agents/experiment.py     kod üreten ajan
  sandbox/e2b_runner.py    E2B çalıştırma
  tracking/mlflow_logger.py  metrik ayrıştırma ve MLflow kaydı
docker-compose.yml         Redis
requirements.txt
.env                       yalnızca OPENAI_API_KEY
```

## Ortam

`.env` içinde şu an yalnızca OpenAI anahtarı durur:

```text
OPENAI_API_KEY=
```

Sandbox için `E2B_API_KEY` süreç ortamından okunur. Bu değişken yoksa sandbox açılmaz ve hata loglanır.

Redis adresi kodda `redis://localhost:6379/0` olarak sabittir. MLflow adresi `http://127.0.0.1:5000` olarak sabittir.

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
3. Betik E2B içinde çalıştırılır. Üretilen kod yerel makinede çalıştırılmaz.
4. Çıktıdan Accuracy ve F1 okunur ve `axiomforge` deneyine loglanır.

Başarılı yanıt:

```json
{
  "code": "...",
  "accuracy": 0.8,
  "f1": 0.75,
  "mlflow_run_id": "..."
}
```

Sandbox başarısız olursa yanıtta yalnızca `code` kalır. Ayrıntı FastAPI logundaki `sandbox execution failed` satırındadır.

MLflow arayüzü: `http://127.0.0.1:5000`
