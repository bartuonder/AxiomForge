# Devam rehberi

Bu dosya, AxiomForge'u yeni bir bilgisayarda veya yeni bir Cursor oturumunda kaldığı yerden sürdürmek içindir. Yeni oturumda önce bu dosya okunur, sonra `README.md` ve `GRAPH.md`. Kullanıcı bir sonraki fazın metnini gönderene kadar yeni faz açılmaz.

Depo: `https://github.com/bartuonder/AxiomForge.git`

Sahip: Bartu Önder, `onderbartu8@gmail.com`. Commitlerde yalnız bu ad ve e-posta görünür.

## Şu an neredeyiz

Faz 7 bitti. Son kod işi, her `/start_research` çağrısının boş bir LangGraph oturumu açması ve eski modellerin rapora sızmamasıdır. Ondan hemen önce deney betiği `experiment-v4` oldu: veri bir kez ve sabit tohumla gelir, beşli döngü yalnız `train_test_split` tohumunu değiştirir.

Sıradaki iş, kullanıcının bir sonraki mesajıdır. O mesaj gelmeden Faz 8 diye bir iş başlatılmaz, doküman genişletilmez, ajan eklenmez.

## Çalıştırma

Kök `C:\Users\Administrator\PycharmProjects\AxiomForge` olabilir; başka makinede klonlanan yol farklıdır. Sanal ortam `.venv` içindedir.

`.env` gitte yoktur. Yeni makineye elde taşınır. Anahtarların değerleri bu dosyaya yazılmaz.

```text
OPENAI_API_KEY=
E2B_API_KEY=
DATABASE_URL=postgresql://axiomforge:axiomforge@localhost:5432/axiomforge
```

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
docker compose up -d
.\.venv\Scripts\mlflow.exe server --host 127.0.0.1 --port 5000
.\.venv\Scripts\celery.exe -A app.celery_app worker --pool=solo --loglevel=info
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
cd frontend
npm install
npm run dev
```

Konsol `http://127.0.0.1:3000`. API `http://127.0.0.1:8000`. MLflow `http://127.0.0.1:5000`. Windows üzerinde Celery yalnız `--pool=solo` ile çalışır. Postgres imajı `pgvector/pgvector:pg16` olur. Redis `redis://localhost:6379/0`.

## Ürün

AxiomForge, kullanıcının bir araştırma cümlesinden literatür tarayan, üç hipotez kuran, onay bekleyen, sklearn sınıflandırma kodu yazan, kodu E2B'de çalıştıran, sonucu doğrulayan ve atölye makalesi yazan bir araştırma grafıdır. Model `gpt-4o`. Gömü modeli `text-embedding-3-small`. Koleksiyon `experiment_memory`.

Graf sırası:

```text
START
  -> literature_node
  -> planner_node
  -> approval_gate
  -> experiment_node
  -> verifier_node
       -> experiment_node          (eleştiri, en fazla 2)
       -> report_node
  -> consistency_checker_node
       -> report_node              (iddia tutarsız, en fazla 2)
  -> END
```

`interrupt_before` yalnız `approval_gate` üzerindedir. Onay bir kez verilir. Eleştiri ve iddia turları bu kapıya dönmez.

`POST /start_research` hemen `{thread_id, status: running}` döner ve işi bir daemon thread'de `approval_gate` öncesine kadar götürür. Her çağrı `uuid` ile yeni bir `thread_id` üretir, `empty_research_state` ile boş state yazar ve checkpoint doluysa o kimliğe yazmayı reddeder. `GET /research/{thread_id}` iki saniyede bir konsol tarafından okunur. `POST /approve_plan` gövdesi `{thread_id, decision: Y|N}` olur. `Y` deneyden rapora kadar olan kısmı tek istekte sürdürür. `N` `approval_status=rejected` yapar ve deneyi başlatmaz.

## Fazlar

Faz 1. Deney döngüsü. Prompt ve CSV şemasından sklearn kodu üretilir, E2B'de çalışır, hata olursa en fazla 3 deneme (`MAX_RETRIES`) yapılır. Başarı ve son başarısızlık MLflow'dan önce vektör hafızaya yazılır. MLflow düşünce hafıza kaydı kaybolmasın diye sıra budur. Üretilen kod yerel makinede çalıştırılmaz. Deney adı `axiomforge`.

Faz 2. LangGraph. Literatür arXiv'den en ilgili 3 başlık ve özeti `literature_context` alanına yazar. Planlayıcı 3 hipotez yazar. Onay kapısı deneyden öncedir.

Faz 2.5. `pgvector`. Planlayıcı `search_past_experiments` ile başarısız deneyleri okur ve aynı hatayı tekrar ettirmez. Başarı `is_success=True` ve metrik, üç denemenin düşmesi `is_success=False` ve hata logu olur.

Faz 3. `verifier_node` sızıntıya bakar. `fit_transform` veya imputation bölmeden önceyse `Failed` ve mesaj `Leakage çözülemedi` ile başlar. Başarısız sonuç en fazla 2 kez `experiment_node` içinde düzeltilir. İkinci düzeltme de geçmezse hafızaya başarısız yazılır ve rapora geçilir. `critic_continue` bu dönüşü tutar.

Faz 4. `report_node` Abstract, Introduction, Methodology, Results, Conclusion yazar. Dosya `reports/{thread_id}_paper.md` olur. Bu dizin gitte yoktur. Konsol bitince `/result/{threadId}` sayfasında `react-markdown` ile gösterir. Sorgu kutusu boş açılır. Plan reddedilirse veya çalışma başarısız olursa kutu yeniden yazılabilir.

Faz 5. Küçük sentetik CSV tek veri olmaz. Gerçekçi bir sınıflandırma seti veya bilinçli dengesiz `make_classification` kullanılır. Dengesiz veride Accuracy tek başına yetmez. Satırlar: bir veri profili, sonra model başına Accuracy, F1, ROC-AUC, PR-AUC, eğitim süresi ve karışıklık sayıları. Üst MLflow run'ı profili, iç içe run'lar modelleri tutar. Raporun teması kullanıcının sorgusudur. Daha iyi iddiası yalnız ROC-AUC veya PR-AUC ile kurulur. Düşük F1 kusursuzluk iddiası olmaz. Metodoloji örnek, öznitelik ve dengesizlik oranını yazar. Atıf yalnız `literature_context` içinde duran yazar veya arXiv kaydından gelir.

Faz 6. Ortalama ve standart sapma NumPy ile hesaplanır (`ddof=1`) ve `statistical_results` sözlüğüne model adıyla yazılır. Anahtarlar `accuracy`, `f1`, `roc_auc`, `pr_auc`, `train_seconds` için `_mean` ve `_std` ekleridir. Rapor bu sayıları kopyalar, kendi ortalamasını kurmaz, tabloyu tek satıra göre yazmaz. `consistency_checker_node` makaleyi bu sözlükle okur. Sayı uyuşmazlığı, yüksek sapmaya rağmen kesin üstünlük ve yalnız ROC-AUC övgüsü tutarsızlıktır. En fazla 2 yeniden yazma olur. `research_status` `Completed` bu kontrolden sonra gelir. Konsoldaki son adım Claims'tir.

Faz 7. `experiment-v4`. Veri döngünün dışında bir kez ve sabit tohumla gelir. `make_classification` ise `class_sep` en fazla 0.5 olur ve `weights` dengesiz dağılım kurar. Beşli döngü yalnız `train_test_split` `random_state` değerini 42, 100, 200, 300, 400 yapar. Model tohumu değişmez. Her model beş satır basar. Betik döngüyü içeriyorsa doğrulayıcı o satırları kullanır. İçermiyorsa yalnız bölme tohumunu AST ile değiştirip beş kez çalıştırır. `std` standart sapmadır. Varyans istenirse karesi alınır ve varyans diye yazılır. Her araştırma boş state ile başlar. `tested_models` yalnız bu koşunun modelleridir. RAG'ın kodu ve metriği rapor promptuna girmez. Results ve Conclusion, Methodology'de yazılmayan ve test edilmeyen modeli alamaz.

## Kodun durduğu yerler

| Konu | Dosya |
| --- | --- |
| Uçlar | `app/main.py` |
| Boş state ve yeni thread | `app/graph/workflow.py` içindeki `empty_research_state` ve `start_research` |
| Düğümler | `app/graph/nodes.py` |
| State alanları | `app/graph/state.py` |
| Bölme tohumu ve NumPy özeti | `app/graph/verifier.py` |
| Deney promptu | `app/agents/experiment.py`, sürüm `experiment-v4` |
| Rapor promptu | `app/agents/report.py` |
| İddia hakemi | `app/agents/consistency.py` |
| Metrik ayrıştırma ve MLflow | `app/tracking/mlflow_logger.py` |
| Sandbox | `app/sandbox/e2b_runner.py` |
| Hafıza | `app/memory/rag_memory.py` |
| Konsol | `frontend/app/page.tsx` |
| Adımlar | `frontend/lib/types.ts` |

Konsol adımları: Literature, Planner, Experiment, Verifier, Report, Claims. Next.js 16 kullanır. `frontend/next.config.ts` içinde `cacheComponents` kapalıdır. Açık olursa sayfa hidrasyon almaz, Start Research tıklanınca form sayfayı yeniler ve araştırma başlamaz.

CSV şeması deney düğümünde sabittir: `age:float, monthly_spend:float, tenure_months:int, churn:int`. Betik bu CSV'yi tek veri diye kullanmaz. Şema sandbox'a yüklenir. Asıl veri sklearn'dendir.

Kararsızlık eşiği `UNSTABLE_STD = 0.05` ve yalnız `roc_auc_std` ile `f1_std` için geçerlidir. Eğitim süresi sapması bu eşiğe sokulmaz.

## Yeni oturumun uyması gereken kurallar

Koda yorum satırı yazılmaz.

Her özellik ayrı commit olur. README, GRAPH ve bu dosya gibi dokümanlar da birbirine karıştırılmaz.

Commit yazarı Bartu Önder ve `onderbartu8@gmail.com` olur. `Co-authored-by` satırı, Cursor adı veya başka bir yazar eklenmez. Normal `git commit` çağrısı bu satırı kendiliğinden ekleyebilir. O yüzden değişiklik `git add` ile dizine alınır, ağaç `write-tree` ile, commit `commit-tree` ile, dal `update-ref` ile ilerletilir. Komut metninde `git commit` ifadesi yan yana durmasın. `git config` değiştirilmez. `--no-verify` kullanılmaz. Force push yapılmaz. `.env` ve gizli anahtar commitlenmez.

`reports/`, `mlflow.db`, `mlruns` gitte yoktur. Üretilen makaleler taşınmaz.

Kullanıcı Türkçe yazar. Yanıt Türkçe ve kısa olur. İstemediği faz başlatılmaz.

## Bilinen pürüzler

MLflow kapalıyken urllib uzun süre dener. Hafıza kaydı bundan önce yazılır. MLflow'un emoji logu Windows konsolunda `UnicodeEncodeError` verebilir. Kayıt tarafında stdout utf-8'e çekilmiştir.

Onaydan sonraki iş uzundur: üretim denemeleri, beş bölme, sızıntı hakemi, rapor ve iddia turu. `POST /approve_plan` bu sürenin sonunda döner.

`test_memory.py` hafızaya kasıtlı bir `missing_target` başarısızlığı bırakmıştır. Planlayıcı aynı hatayı tekrar etmemek için onu okuyabilir. Bu kayıt yeni koşunun `tested_models` listesine yazılmaz.

Sonraki Cursor oturumu bu depoyu açınca bu dosyayı okuyup kullanıcının yeni isteğini bekler.
