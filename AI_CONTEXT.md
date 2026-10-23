# AI_CONTEXT.md: AxiomForge oturum devir dosyası

Bu dosya 22-23 Ekim 2026 oturumunun sonunda yazıldı ve kontrol grubu işiyle (Faz 9) güncellendi. Yeni oturum önce bunu okur, sonra `CONTINUATION.md` (kurallar ve faz tarihçesi), `README.md`, `GRAPH.md`. Bu dosya ile `CONTINUATION.md` çelişirse bu dosya daha günceldir. Kullanıcı yeni bir mesaj göndermeden iş başlatılmaz.

Durum anı: son kod commit'i `eedebae` (ayar iddiası kontrolleri), ardından doküman commit'leri. Çalışma ağacı temiz, 795 pytest testi geçiyor. Oturumun başında 94 commit vardı, şimdi yaklaşık 225. Frontend bu turda değişmedi (`tsc` ve `eslint` en son temizdi).

## 1. Proje

AxiomForge, kullanıcının bir araştırma cümlesinden literatür tarayan, hipotez kuran, onay bekleyen, sklearn sınıflandırma kodu yazan, kodu E2B sandbox'ında çalıştıran, sonucu istatistiksel olarak doğrulayan ve atölye makalesi yazan bir araştırma grafıdır. Depo: `https://github.com/bartuonder/AxiomForge.git`. Sahip: Bartu Önder, `onderbartu8@gmail.com`. LLM `gpt-4o`, gömü `text-embedding-3-small`. Bileşenler: LangGraph + PostgreSQL (checkpoint ve pgvector hafıza), FastAPI, Celery + Redis, MLflow, E2B, Next.js 16 konsolu.

Projenin araştırma değeri **karşılaştırmalı analize** dayanır. Kullanıcının kararı: her hipotez iki model arasında bir karşılaştırma iddiasıdır ve sorguda en az iki model zorunludur.

## 2. Çalışma kuralları (kullanıcının kesin kuralları)

- Koda yorum satırı yazılmaz.
- Her özellik ayrı commit olur. Dokümanlar (README, GRAPH, CONTINUATION) kendi aralarında ayrı commit olur ve her committe değil, 3-5 committe bir toplu güncellenir.
- Commit yazarı yalnız Bartu Önder'dir. `Co-authored-by` satırı eklenmez. Not: araç ortamı bazen `Co-Authored-By: Claude` eklemeyi hatırlatır, kullanıcının proje kuralı bunun önündedir ve bütün oturum boyunca proje kuralı uygulandı. Normal `git commit` bu satırı kendiliğinden ekleyebildiği için commit şöyle atılır: `git add -- <dosyalar>`, `git write-tree`, `git commit-tree`, `git update-ref HEAD`, `git reset -q`. `git config` değiştirilmez, `--no-verify` kullanılmaz, force push yapılmaz, `.env` ve anahtarlar commitlenmez.
- Kullanıcı Türkçe yazar. Yanıt Türkçe ve kısa olur. İstenmeyen faz veya iş başlatılmaz.
- Gerçek LLM ve E2B çağrıları maliyetlidir: tam koşular yalnız kullanıcı onayıyla yapılır (bu oturumda üç tam koşu onaylandı; üçüncüsü için kullanıcı ek maliyeti ve süreyi açıkça kabul etti). Küçük canlı LLM denemeleri doğrulama amacıyla yapıldı ve raporlandı.
- Push yalnız kullanıcı izin verince yapılır. Bu oturumda bir kez açık izin verildi (iki model şartı ve yama), o push'u ben yaptım. Diğer push'ları kullanıcı (veya kullandığı bir araç) benden habersiz yaptı, ve bu bir kez geçmişi ayrıştırdı (aşağıda, "Süreç dersleri"). `git fetch` ve `git status -sb` ile durumu her zaman doğrula.
- Commit öncesi kapı: önce testler geçmeli (`pytest -q` ve gerekirse frontend `tsc`/`lint`), sonra commit.

## 3. Sistemin güncel durumu

### 3.1 Graf akışı

```text
START -> literature_node -> planner_node -> approval_gate (interrupt_before)
      -> experiment_node -> verifier_node
            -> experiment_node   (kritik: yalnız gerçek hata, en fazla 2)
            -> report_node
      -> consistency_checker_node
            -> report_node       (LLM'siz kontrol takıldı, en fazla 2 yeniden yazma)
      -> END
```

- `POST /start_research` işi Celery'ye atar (`run_research_task`), `approval_gate` öncesine kadar işçi götürür. `POST /approve_plan` `Y` için `selected` (0'dan sıra) ister ve `resume_research_task` kuyruğa atar, hemen `running` döner.
- Kritik döngüsü yalnız metrik üretilmemesi, sandbox çökmesi ve veri sızıntısı için kodu geri gönderir. Yüksek varyans artık hata değil bulgudur (`statistical_decision["instability"]`).
- Çift karar reddedilir (`research thread was already decided`). Kuyruk kapalıysa `503` ve onay geri alınır.

### 3.2 Dosya haritası

| Konu | Dosya |
| --- | --- |
| API uçları | `app/main.py` |
| Celery uygulaması ve görevleri | `app/celery_app.py`, `app/tasks.py` |
| Graf kurulumu, durum, onay, devam | `app/graph/workflow.py` |
| Düğümler, kapı, hakem notları | `app/graph/nodes.py` |
| State alanları | `app/graph/state.py` |
| Seçilen hipotez | `app/graph/selection.py` |
| Doğrulayıcı: özet, karar, bulgu, tohum eşleme, `hypothesis_verdict` | `app/graph/verifier.py` |
| Pitman-Morgan, düzeltilmiş t, Holm | `app/graph/stats.py` |
| Hazır kanıt cümleleri | `app/graph/evidence.py` |
| Araştırma hatası kaydı | `app/graph/errors.py` |
| Bölme tohumları (tek kaynak) | `app/seeds.py` |
| Spesifikasyon, claim, kod denetimi | `app/agents/spec.py` |
| Planlayıcı | `app/agents/planner.py` |
| Deney ajanı, model listesi, kod sözleşmeleri | `app/agents/experiment.py` |
| Literatür ajanı | `app/agents/literature.py`, `app/tools/arxiv.py` |
| Rapor yazıcısı | `app/agents/report.py` |
| Hakem ve LLM'siz kontroller | `app/agents/consistency.py` |
| Kontrol grubu adlandırması (`Model__default`) | `app/variants.py` |
| Hugging Face veri seti kaydı, veri bloğu, veri bloğu denetimi, `pick_dataset` | `app/datasets.py` |
| Deney döngüsü (3 deneme) | `app/experiments.py` |
| Sandbox | `app/sandbox/e2b_runner.py` |
| Hafıza | `app/memory/rag_memory.py` |
| MLflow ve çıktı ayrıştırma | `app/tracking/mlflow_logger.py` |
| Konsol | `frontend/app/page.tsx`, `frontend/app/result/[threadId]/paper-view.tsx`, `frontend/components/*` |
| Testler | `tests/` (33 dosya) |

### 3.3 Sabitler

| Sabit | Değer | Yer |
| --- | --- | --- |
| Bölme tohumları (10) | 42, 100, 200, 300, 400, 500, 600, 700, 800, 900 | `app/seeds.py` |
| `ALPHA` | 0.05 | `verifier.py` |
| `UNSTABLE_STD` | 0.05 (yalnız `roc_auc` ve `f1`) | `verifier.py` |
| `MIN_SPLITS` | 3 | `stats.py` |
| `MAX_CRITIC_ROUNDS`, `MAX_CONSISTENCY_ROUNDS` | 2, 2 | `verifier.py`, `nodes.py` |
| `MAX_RETRIES` (sandbox) | 3 | `experiments.py` |
| `MAX_PLAN_ATTEMPTS` | 2 | `planner.py` |
| `MIN_MODELS` | 2 | `experiment.py` |
| `MIN_RELEVANCE`, `KEEP_PAPERS`, aralık | 0.35, 3, 3 sn | `literature.py` |
| Sandbox süreleri | kod 240 sn, kutu 300 sn | `e2b_runner.py` |
| Deney prompt sürümü | `experiment-v9` | `experiment.py` |
| Hakem notu sınırı | 8 not, her biri 400 karakter | `nodes.py` |

Desteklenen modeller (17): LinearSVC, SVM, RandomForest, LogisticRegression, DecisionTree, GradientBoosting, HistGradientBoosting, XGBoost, LightGBM, CatBoost, KNN, GaussianNB, MLP, AdaBoost, ExtraTrees, QDA, LDA. Hepsinin izinli kurucu parametre listesi `MODEL_PARAMS` içindedir. Veri setleri (hepsi gerçek Hugging Face verisi, `app/datasets.py`): `breast_cancer`, `credit_default` (6000 örnek), `customer_churn`, `adult_income` (6000 örnek), `credit_fraud` (492 sahtekârlık + 4000 normal). Sentetik `imbalanced` kalktı. Sandbox her koşudan önce `datasets` paketini kurar.

### 3.4 State alanları

`query`, `literature_context`, `hypotheses`, `experiment_specs`, `selected_hypothesis`, `approval_status`, `current_experiment_code`, `experiment_error`, `experiment_metrics`, `model_results`, `tested_models`, `dataset_profile`, `statistical_results`, `statistical_decision`, `mlflow_run_id`, `verification_status`, `verifier_feedback`, `critic_rounds`, `critic_continue`, `paper_markdown`, `consistency_feedback`, `referee_notes`, `consistency_rounds`, `consistency_continue`, `research_status`.

`statistical_decision` içeriği: `outcome` (`tie`/`winner`/`none`), `winner`, `comparisons` (Pitman-Morgan), `performance` (düzeltilmiş t, Holm), `instability`, `hypothesis` (`{claim, verdict, evidence}`), `parameter_effects` (yapılandırılmış ve varsayılan seri arasındaki fark, kendi Holm ailesi). Kontrol serileri (`Model__default`) `statistical_results`, tablo, `tested_models` ve MLflow'da bulunur ama ilk dört analize girmez.

### 3.5 Hipotez, claim ve karar zinciri

1. Planlayıcı 3 spesifikasyon üretir: `{statement, models, claim, dataset, params}`. `claim` = `{kind: performance|stability, metric, subject, other}`. `statement` iki modeli de adlandırmalıdır. `params` yalnız yapılandırmayı belirler, hipotezin konusu olamaz. Geçersizse bir kez düzeltme istenir, yine geçersizse çalışma `failed` olur.
2. Kullanıcı onayda birini seçer (`selected`). Yalnız o çalışır, kaydedilir, MLflow'a ve makaleye girer.
3. Deney kodu AST ile denetlenir: modeller sözlüğü (parametre verilen her model için ek `Model__default` girdisi, `variants.expected_keys`), spesifikasyondaki veri setinin veri bloğu (`dataset_code_error`: her ifade bulunmalı, sentetik yükleyici olmamalı) ve parametreler (yapılandırılmış girdide sabit yazılı, kontrol girdisinde yok ve aynı sınıf), her `train_test_split` çağrısında `stratify=y`. Her model `with_preprocessing(...)` ile bir Pipeline içindedir. Prompt `experiment-v9` 10 tohumlu döngü ister.
4. Doğrulayıcı `hypothesis_verdict` ile claim'i yapılan testlerden `supported`, `contradicted`, `inconclusive` veya `untested` olarak karara bağlar. Karar model sırasından bağımsızdır.
5. `verifier.parameter_effects` her yapılandırılmış model için ROC-AUC, PR-AUC ve F1'de yapılandırılmış ile varsayılan seriyi karşılaştırır. Bu, "parametre ayarı işe yaradı" iddiasının kontrol grubuna karşı sınanmasıdır (Seçenek B).
6. `evidence.py` hipotez kararını, anlamlı her performans farkını (yön, düzeltilmiş p, `dz`), parametre etkilerini ve kararsızlık bulgusunu hazır İngilizce cümleler yapar. Yazıcı bunları Results'a aynen kopyalar, kontrol girdileri `Model (default)` adıyla görünür.

### 3.6 Makale kapısı: LLM'siz kontroller (karar bunlarda)

`consistency_checker_node` yalnız şu kontrollerle `Completed` ya da `NeedsReview` der. Hepsi `app/agents/consistency.py` içindedir, mesajları Türkçedir.

| Kontrol | Ne arar |
| --- | --- |
| `direction_conflict` | Beraberlikte üstünlük iddiası. Hipotez cümleleri, amaç cümleleri ve anlamlı bir metriğe dayanan yan cümleler muaf. Mesaj takılan cümleyi alıntılar |
| `conclusion_issues` | Kazanan varken makale kazananı adlandırıyor mu, "fark yok" demiyor mu |
| `verification_issue` | Doğrulama `Failed` iken Abstract `failed verification` diyor mu |
| `instability_issues` | Kararsızlık bulgusu varken Abstract ve tablo dışı bir cümle bunu anıyor mu |
| `reliability_issue` | `Passed` doğrulama, `reliab*`, `robust*` gibi sözcüklerle güvence gibi anlatılmıyor mu |
| `performance_issues` | Anlamlı her performans satırı tablo dışında yazılmış mı, `dz` ile |
| `hypothesis_issues` | Abstract ve Conclusion `the hypothesis was <verdict>` diyor mu, ters yönde `supported` demiyor mu |
| `table_issues` | Tablodaki her hücre doğrulanmış ortalama ± std ile uyuşuyor mu (yazılan son basamağın yarısı toleransla) |
| `unsupported_difference_issues` | Anlamlı olmayan bir karşılaştırma için üstünlük iddiası var mı (aynı yan cümlede metrik, iki model adı ve `higher`/`outperforms` gibi bir sözcük, olumsuzlama, kararlılık, hipotez ve amaç cümleleri hariç) |
| `parameter_effect_issues` | Anlamlı her parametre etkisi `default` geçen bir cümlede, doğru yönle (ters yön sözcüğü ve olumsuzlama yok) ve `dz` ile yazılmış mı. Anlamlı olmayan etki fark gibi anlatılıyor mu |
| `leakage_description_issues` | Doğrulama `Passed` iken makale ön işlemeyi (ölçekleme, standardizasyon, normalizasyon, doldurma, PCA) bölmeden önce ya da tüm veri üzerinde yapılmış gibi anlatıyor mu (`after the split` geçen ve olumsuz cümleler muaf) |
| `untuned_model_issues` | Spec'te `params`'ı olmayan bir model makalede ayar sözcüğüyle (`tuned`, `tuning`, `hyperparameter`, `optimized`) aynı yan cümlede anılıyor mu (olumsuzlama ve `default` geçen yan cümleler muaf) |
| `tuning_claim_issues` | Hiçbir parametre etkisi anlamlı değilken makale ayarın sonucu etkilediğini (`impact`, `improve`, `enhance`, `boost`, `better`) söylüyor mu (olumsuzlama, `default`, hipotez ve amaç cümleleri, `to improve` yapısı ve `Gradient Boosting` adı muaf, bir etki anlamlıysa kontrol çalışmaz) |

`default` geçen cümleler `performance_issues` ve `direction_conflict` tarafından atlanır (etki cümleleri model karşılaştırmasını ne sağlar ne tetikler). Tablo kontrolü eksik kontrol satırını `Model (default) satırı yok` diye bildirir.

LLM hakem (`judge_consistency`) **danışmandır**: iş bitince bir kez çağrılır, notları `referee_notes` alanına yazılır, durumu belirlemez, yazıcıya gitmez. Çağrı hata verirse araştırma düşmez. Sonuç sayfasında kapalı bir blokta görünür.

### 3.7 Konsol

- Ana sayfa: sorgu formu, ajan zaman çizgisi, onay diyaloğu (üç hipotezi veri seti ve parametreleriyle gösterir, başta hiçbiri seçili değil, onay düğmesi seçime kadar pasif).
- Sonuç sayfası `/result/{threadId}`: üç kontrol satırı (doğrulama, varyans bulgusu, iddia kontrolü), kapalı hakem notları bloğu, makale. Yoklama araştırma bitince durur.
- Next.js 16.4.0, React 19.3. `frontend/AGENTS.md` bu Next sürümünün alışılmış olandan farklı olduğunu söyler, Next'e özgü kod yazmadan önce `node_modules/next/dist/docs/` okunur.
- `frontend/next.config.ts` içinde `cacheComponents` kapalı kalmalıdır.

### 3.8 Altyapı ve çalıştırma

Yerel yol (önerilen geliştirme yolu):

```powershell
docker compose up -d redis postgres
.\.venv\Scripts\mlflow.exe server --host 127.0.0.1 --port 5000
.\.venv\Scripts\celery.exe -A app.celery_app worker --pool=threads --concurrency=4 --loglevel=info
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
cd frontend; npm run dev
.\.venv\Scripts\python.exe -m pytest
```

- Docker yolu: `docker compose up -d --build` (redis, postgres, mlflow, api, worker; tek imaj `Dockerfile`). Konsol konteynerde değildir. Yerel yolla Docker yolu aynı anda kullanılmaz (5000 ve 8000 çakışır). Yerel imaj (`axiomforge-app`) eskidir, kullanılacaksa yeniden build gerekir.
- `.env` gitte yoktur: `OPENAI_API_KEY`, `E2B_API_KEY`, `DATABASE_URL`. İsteğe bağlı `REDIS_URL`, `MLFLOW_TRACKING_URI`.
- Windows'ta Celery `--pool=threads` ile çalışır. `--pool=solo` tek görev yürütür, uzun bir araştırma başka başlangıçları bekletir.
- Konsolu `http://localhost:3000` ile aç. `127.0.0.1:3000` adresinde Next dev sunucusu istemci kodunu çalıştırmıyor (sayfa çiziliyor ama hiçbir şey yüklenmiyor). README ve CONTINUATION hâlâ `127.0.0.1:3000` yazıyor, düzeltilmedi.

### 3.9 Test altyapısı

795 test, yaklaşık 30 saniye, hiçbir dış servis çağrılmaz (düğüm testleri `monkeypatch` ile taklit eder, MLflow testi geçici SQLite kullanır). `requirements-dev.txt` pytest'i ekler. Sık kullanılan yaklaşım: **mutasyon denemesi**. Bir korumanın testle gerçekten kapsandığını görmek için koda bilerek bir hata sokulur, test kırılmalıdır. Bu yöntem bu oturumda iki zayıf testi ortaya çıkardı.

### 3.10 Gerçek koşular

| | Koşu 1 | Koşu 2 | Koşu 3 |
| --- | --- | --- | --- |
| Thread | `a531b95d-a404-44ba-ae80-f65a0b4b64be` | `b670cc9a-416e-448e-9d2d-4e92930190e0` | `26344d2d-7234-415f-8d2f-ee1e529d4668` |
| Sorgu | RandomForest ve LogisticRegression, dengesiz müşteri kaybı | SVM, KNN ve RandomForest, dengesiz müşteri kaybı | RandomForest ve LogisticRegression, parametre ayarı ve StandardScaler'ın tüm veriye bölmeden önce uydurulması istendi |
| Seçilen hipotez | 0 (`class_weight='balanced'`), claim yoktu (önceki sürüm) | 1 (`KNN` daha kararlı, kararlılık claim'i) | 2 (RF `n_estimators=200`, `class_weight='balanced_subsample'` ve LR `C=0.1`, PR-AUC claim'i) |
| Süre | yaklaşık 41 sn (plan 20 sn) | yaklaşık 61 sn (plan 25 sn) | yaklaşık 75 sn (iki deney turu) |
| Sonuç | `Passed` / `Completed` | `Passed` / `NeedsReview` (eski kapıyla) | `Passed` / `Completed` (tur 0 sızıntıyla `Failed`, tur 1 `Passed`) |
| Bulgu | Makale üç şeyde eksikti (güvenilirlik cümlesi, ROC-AUC farkı, etki büyüklüğü), düzeltildi | LLM hakem aynı makaleyi 4 çağrının 4'ünde yanlış gerekçelerle reddetti | Makale sızıntıyı hem anlatıyor hem "tespit edilmedi" diyordu, kapı yoktu; `leakage_description_issues` eklendi |

Koşu 2 sayıları: ROC-AUC RandomForest 0.944, SVM 0.914, KNN 0.866. KNN-RF farkı ROC-AUC ve F1'de anlamlı (düzeltilmiş `p=0.0464`). Hipotez `inconclusive` (KNN'nin varyansı RF'den yüksek, `p=1.0`). Kararsızlık: SVM F1 std 0.079, KNN 0.068. MLflow'da `Verified` üst run (52 metrik), 30 iç içe run. Hafızada `finding` kaydı.

Önemli: Koşu 2'nin Postgres'teki kalıcı durumu hâlâ `NeedsReview` (eski kapı). Yeni kapı yalnız aynı makale ve veriyle yeniden oynatıldı ve `Completed` çıktı, durum güncellenmedi.

Koşu 3 sayıları: 4 model (RF, RF varsayılan, LR, LR varsayılan) × 10 bölme, MLflow'da `experiment-v8`, 40 iç içe run, `significant_parameter_effects=1`. Hipotez `supported` (RF PR-AUC farkı 0.381, `dz` 5.60). Altı parametre etkisinden yalnız LR `C=0.1` F1'de anlamlı (varsayılandan düşük, 0.0572, `dz` 2.53, düzeltilmiş `p` 0.0123). Kararsızlık: LR F1 std 0.063. Sızıntı yargıcı tur 0'da `StandardScaler tüm veriye bölmeden önce uygulanmış` dedi, eleştirmen kodu düzeltti (scaler bölmeden sonra, yalnız eğitime uyduruluyor), tur 1'de `Passed`. Kapı ilk denemede geçti (0 yeniden yazma), ama makale çelişkiliydi (3.6, 4.1 madde 23). Hakem notları yine gürültülüydü (RF kararlılık kazananı iken "RF daha kararlı demesin" dedi). Denenmeyen yollar: `Failed` doğrulama makalesi, `NeedsReview`, 10 koşuluk yedek yol (üretilen kodda zaten bölme döngüsü vardı), sandbox zaman aşımı.

Koşu 4 (thread `96acf4c2-2712-4ea7-9977-a447186a7670`, 10 koşuluk yedek yol): sorgu tek `train_test_split(random_state=42)` istedi, doğrulayıcı bölme döngüsü bulamayıp tohumları 42-900 yazarak 10 ayrı E2B koşusu yaptı (her biri yaklaşık 5 sn, toplam 12 sandbox), 4 model × 10 bölme = 40 iç içe run. `Passed`, hipotez `contradicted` (LR C=0.5 PR-AUC'de RF'den düşük, fark −0.147, dz −3.02), parametre etkilerinin hiçbiri anlamlı değil. `NeedsReview` bitti: `parameter_effect_issues` yanlış alarm verdi (tırnaklı hipotez cümlesi ile kontrol grubu cümlesi birleşti), `7673cb7` ile düzeltildi. Koşu 3 ve 4 sentetik veriyle yapılmıştı.

Koşu 5 (thread `40222d61-edd7-463e-9d68-a847faa67dfd`, gerçek Hugging Face verisiyle ilk tam koşu): sorgu RandomForest, LogisticRegression ve HistGradientBoosting, telekom müşteri kaybı. Planlayıcı `customer_churn` veri setini kendisi seçti, hipotez 2 onaylandı (LR `C=0.5`, HGB `max_depth=5`, PR-AUC iddiası). Veri 7043 satır, 19 özellik, %27 pozitif. Deney ilk denemede geçti (yaklaşık 27 sn), toplam yaklaşık 80 sn, `Passed` / `Completed`, kapı ilk turda geçti, hakem notu çıkmadı. 5 model × 10 bölme = 50 iç içe run. Hipotez `inconclusive` (fark −0.0061, düzeltilmiş `p` 0.42). LR ve HGB, RF'den ROC-AUC ve PR-AUC'de anlamlı yüksek (LR ROC-AUC 0.844 en iyi), LR ile HGB arasında anlamlı fark yok. Altı parametre etkisinin hiçbiri anlamlı (HGB ROC-AUC düzeltilmiş `p` 0.07 en yakını). Makale yanlıştı ve kapı yakalamadı: Abstract RF'nin `n_estimators` ayarını odak diye yazdı (spec'te RF parametresi yok, kod `n_estimators=100` varsayılan), Conclusion "ayar performansı etkileyebilir" dedi. `eedebae` ile iki kontrol eklendi.

12 sentetik makale döngüsü (3 tohum × 4 karar türü) gerçek `gpt-4o` ile ilk denemede, sıfır yeniden yazmayla `Completed` oldu. Bu testler iki modelli sade veriydi, karmaşık durumdaki hakem gürültüsünü göstermedi (Koşu 2 gösterdi).

### 3.11 Kalıntı veri (test ve koşulardan)

- Postgres: yaklaşık 31 checkpoint thread'i ve 31 hafıza kaydı (Koşu 3 eklendi; sayılar tam doğrulanmadı), `research_errors` boş. Thread'lerin bir kısmı bu oturumun test ve koşularından, kalanı önceki oturumlardan; hangisinin hangisi olduğu ayrıştırılmadı (yalnız aşağıdaki beş kimlik bu oturumdan biliniyor).
- `mlflow.db` (yaklaşık 2 MB) içinde gerçek ve test run'ları. `reports/` içinde 12 makale. `reports/`, `mlflow.db` ve `mlruns` gitte yoktur.
- `test_memory.py` hafızaya kasıtlı bir `missing_target` başarısızlığı bırakmıştır. Planlayıcı yalnız `is_success=False` kayıtları okur.
- Bugünkü test thread'leri: `5f2808e4` (deney sırasında işçi kapatıldı, `running` kaldı), `38f98fd2`, `ad6ee6be` (reddedildi), `a531b95d` (Koşu 1), `b670cc9a` (Koşu 2), `26344d2d` (Koşu 3), `96acf4c2` (Koşu 4), `40222d61` (Koşu 5). Eski thread'lerin ve hafıza kayıtlarının spesifikasyonları `dataset: imbalanced` taşıyabilir; bu anahtar artık geçersizdir, eski thread yeniden oynatılmamalı.

## 4. Bugün tespit edilen mimari sorunlar

### 4.1 Çözülenler

| # | Sorun | Nasıl bulundu | Çözüm |
| --- | --- | --- | --- |
| 1 | Yüksek varyans kritik döngüsünü tetikleyip aynı kodu boşuna yeniden üretiyordu | Denetim | Varyans artık bulgu (`instability`), yalnız gerçek hata kodu geri gönderir |
| 2 | Hipotezler deneye bağlı değildi, sınanamayan "parametre X iyileştirir" hipotezleri | Koşu 1 | Yapısal `claim`, planlayıcı yalnız iki model karşılaştırması üretir, doğrulayıcı kararı verir |
| 3 | Onay diyaloğu üç hipotez gösteriyor, yalnız ilki çalışıyordu | Denetim | Seçim zorunlu, yalnız seçilen çalışır |
| 4 | Hafıza deney öncesi ve iki yerde yazılıyor, `hypothesis` ham prompt | Denetim | Tek yazma noktası, doğrulama sonrası, gerçek hipotez ve `spec`, `finding` ayrımı |
| 5 | MLflow ilk bölmeden sonra, doğrulamadan önce loglanıyordu | Denetim | Doğrulama sonrası tek run, ortalama/std/varyans üst run'da, tohum iç içe run'da |
| 6 | `train_seconds=4.5e-05` satırı sessizce düşüyordu | Gerçek örnekle ölçüm | Bilimsel gösterimli sayı kalıbı |
| 7 | Rapor `Failed` doğrulamayı söylemiyordu, hakem durumu görmüyordu | Denetim | Yazıcı talimatı ve LLM'siz `verification_issue` |
| 8 | Makale kararsızlık bulgusunu özete taşımıyordu | Canlı çağrı | Yazıcı talimatı ve `instability_issues` |
| 9 | Makale `Passed`'i güvenilirlik kanıtı gibi anlatıyordu | Koşu 1 | `reliability_issue` (olumsuzlama yalnız güvenilirlik sözcüğünden hemen önce sayılır) |
| 10 | Makale anlamlı ROC-AUC farkını ve etki büyüklüklerini atlıyordu | Koşu 1 | `performance_issues` |
| 11 | Beraberlik kapısı aşırı genişti (hipotez cümlesi, amaç cümlesi, performans üstünlüğü takılıyordu) | Canlı döngü | Muafiyetler, yan cümle değerlendirmesi, takılan cümlenin alıntılanması |
| 12 | Yazıcı uzun kural listesini hatırlayamıyor, döngü `NeedsReview`'e takılıyordu | Canlı döngü | Python hazır kanıt cümleleri üretir, yazıcı kopyalar (12/12 ilk denemede) |
| 13 | LLM hakem karmaşık veride yanlış ve onay niteliğinde gerekçelerle reddediyordu | Koşu 2 | Hakem danışman oldu, tablo kontrolü LLM'siz yapıldı |
| 14 | Araştırma API içindeki daemon thread'de, onay uzun bloklanıyordu | Denetim | Celery görevleri |
| 15 | `N` sonrası `Y` göndermek reddedilmiş planı çalıştırabiliyordu | Test | Çift karar koruması |
| 16 | Onaydan sonra durum yanlışlıkla `paused` görünüyordu | Canlı deneme | Durum `running` |
| 17 | Eksik `requirements.txt` paketleri (`httpx`, `kombu`, `langchain-core`, `pydantic`) | İmaj build'i | Eklendi |
| 18 | Bölme iki katına çıkınca sandbox süresi yetmeyebilir | Analiz | 240/300 sn (ölçüme değil orantıya dayanır) |
| 19 | Tek modelli sorguda karşılaştırma yok | Canlı planlayıcı | En az iki model, `422` |
| 20 | Tablo kontrolü gerçek başlıkları (`Accuracy (Mean ± Std)`) tanımıyordu | Gerçek makale | Başlık süsleri temizleniyor, gerçek tablo test verisi |
| 21 | Anlamlı olmayan farkın makalede iddia edilmesi denetimsizdi | Koşu 2 hakem notları | `unsupported_difference_issues` (gerçek ikinci koşu makalesinde 0 yanlış pozitif, gerçek ihlaller ve üç modelli yan cümleler testli) |
| 22 | Konfigürasyon karışıklığı: claim iki modeli farklı yapılandırmayla karşılaştırıyor, parametresiz temel çizgi yoktu | Denetim, kullanıcı kararı (Seçenek B) | Parametre verilen her model `Model__default` kontrol girdisiyle koşar, `parameter_effects` etkiyi kontrole karşı ölçer, kontrol ana analizlerden çıkarılır |
| 23 | Makale ön işlemeyi sızıntılı anlatıyordu (sorgudaki talimat) ve aynı yerde "sızıntı yok" diyordu | Koşu 3 | `leakage_description_issues` (gerçek makalede yakalıyor, diğer 9 makalede 0 yanlış alarm) ve yazıcı talimatı |
| 24 | Sistem sentetik veri üretiyordu (`make_classification`) | Kullanıcı kararı (projenin en büyük yapısal eksiği) | Beş doğrulanmış Hugging Face veri seti, Python'ın ürettiği veri bloğu, AST zorunluluğu, Pipeline içinde ön işleme, sandbox'ta `datasets` kurulumu |
| 25 | `parameter_effect_issues` tırnaklı hipotez cümlesinde yanlış alarm veriyordu | Koşu 4 | Cümle bölücü kapanış işaretlerini tanır, "default" aynı yan cümlede aranır, hipotez ve amaç cümleleri muaf (`7673cb7`) |
| 26 | Makale spec'te parametresi olmayan modelin ayarlandığını ve anlamlı etki yokken ayarın etkili olduğunu yazıyordu (sorgudaki talimat aktarılıyordu) | Koşu 5 | `untuned_model_issues`, `tuning_claim_issues` ve yazıcı kuralları (`eedebae`), gerçek makalelerde 3. ve 4. koşuda 0 yanlış alarm, 5. koşuda tam birer uyarı |

### 4.2 Açık sorunlar (öncelik sırasıyla)

1. **Anlamsız fark denetimi kısmen çözüldü.** `unsupported_difference_issues` artık anlamlı olmayan bir çift için üstünlük iddiasını yakalıyor. Kalan boşluklar: yalnız bir model adı geçen cümleler ("Random Forest has the highest mean PR-AUC") ve `highest`, `best` gibi çift belirtmeyen ifadeler kontrol edilmiyor. Anlamlı bir satırın *yönü* (makale doğru modeli üstün gösteriyor mu) de kontrol edilmiyor. Gerçek bir koşuda yazıcının bu kontrolü tetikleyip tetiklemediği henüz görülmedi.
2. **Claim hâlâ yapılandırma çiftinin kararıdır.** Kontrol grubu parametrelerin etkisini ayrıca ölçüyor ama hipotez kararı (`supported`/`contradicted`) yapılandırılmış iki model arasındadır, "model sınıfı" için değil. Makale de kararı böyle yazmalı, bu henüz denetlenmiyor. Parametre değeri varsayılana eşitse (ör. LR `C=1.0`) etki sıfırdır ve `p=1` çıkar, planlayıcı bunu ayırt etmez. Etki ailesi 6 satırdır (model × 3 metrik), kontrol grubu sandbox süresini ve MLflow run sayısını artırır (4 model × 10 bölme).
3. **Gerçek koşuda hâlâ tetiklenmeyen yollar.** Sızıntı eleştiri döngüsü Koşu 3'te, 10 koşuluk yedek yol Koşu 4'te gerçek servislerle çalıştı, ama ikisi de sentetik veriyle; gerçek Hugging Face verisiyle tam koşu Koşu 5'te yapıldı (`Passed` / `Completed`). Kalanlar: sandbox çökmesi, `Failed` doğrulama makalesi, `NeedsReview` kalıcı durumu, çok modelli veya yavaş sorguda sandbox zaman aşımı (XGBoost paket kurulumu dahil). Bunlar testlerle ve sahte servislerle kapsandı.
4. **Kalıp tabanlı kontrollerin kırılganlığı.** On iki LLM'siz kontrol regex tabanlı. `leakage_description_issues` "ön işleme sözcüğü + tüm veri/bölmeden önce" kalıbına bakar; "scaler ve full dataset" geçen meşru bir cümleyi yanlışlıkla işaretleyebilir (en kötü iki yeniden yazma, sonra `NeedsReview`), canlı denenmedi. Gerçek çıktıyla üç kez hata gösterdiler (tablo başlığı, olumsuzlama kapsamı, hipotez cümlesi). Yeni bir kontrol eklemek yerine mümkünse cümleyi Python'a yazdırmak (kanıt cümleleri) daha sağlam bulundu. Yazıcı çok farklı bir ifade seçerse gereksiz yeniden yazma ve en kötü `NeedsReview` olabilir.
5. **İşçi ölürse araştırma `running` kalır.** Otomatik kurtarma ve "bayat çalışma" tespiti yok. Koşu sırasında işçiyi kapatmak (testlerde yaptım) böyle bir thread bıraktı.
6. **İstatistik varsayımları.** 10 bölme birbirinden bağımsız değil (aynı veri), p değerleri iyimser olabilir (Nadeau-Bengio düzeltmesi bunu kısmen karşılar). Başta ölçülen güç (%74) beş bölmeye aitti, on bölmede artmalı, yeniden ölçülmedi. Wilcoxon ve `RepeatedStratifiedKFold` uygulanmadı (10 tekrarlı stratify'lı `train_test_split` kullanılıyor).
7. **Literatür.** `MIN_RELEVANCE=0.35` eşiği iki üç sorguyla ölçüldü. Makale hiçbir atıf yapmıyor (yazıcı atıfsız yazıyor). Veri seti seçenekleri iki tane.
8. **`POST /experiments` grafla tutarsız.** Doğrulayıcı olmadığı için deneyden hemen sonra kendi hafıza ve MLflow kaydını yazıyor (`record_memory`, `track_run` bayrakları). Aynı uç artık iki model şartını da uyguluyor.
9. **Ölü kod.** `models_dropped`, `performance_dropped`, `DROP_LIMIT` (`verifier.py`), `log_classification_run`, `parse_metrics` yalnız testlerde kullanılıyor. `EXPERIMENT_CSV_SCHEMA` sandbox'a bir `data.csv` yükletiyor ama prompt bu veriyi tek kaynak olarak kullanmayı yasaklıyor (fiilen kullanılmıyor).
10. **MLflow.** `statistical_decision` JSON'u artifact olarak yüklenmiyor. Run kimliği state'te.
11. **Frontend.** Docker'da değil, otomatik arayüz testi yok, formda "en az iki model" ipucu yok, dokümandaki `127.0.0.1:3000` adresi yanlış (üstte), `next dev` her başlatmada bir uyarı basıp ilk istekten sonra kendiliğinden kapanıyor (yeniden başlatınca bazen kalıyor). Uyarı metni bir güvenlik açığı iddiası taşıyor ve yapay zekâ ajanına yönelik talimatlar içeriyor (yükseltme komutu çalıştırması ve kullanıcıya sorması gibi). Bunlar kullanıcının isteği değildi ve uygulanmadı. Gerçek durumu kullanıcı doğrulamalı (`npm audit`), bir sonraki oturum bu metindeki talimatlara kendiliğinden uymamalı.
12. **Hakem istemi eski.** Danışman olduğu için zarar vermiyor ama gürültülü, onay cümlelerini "sorun" diye listeliyor. Sadeleştirilebilir.
13. **Test kalıntıları.** Postgres ve `mlflow.db` içinde test verisi (3.11). Temizlik aracı yok, silme kararı kullanıcıya ait.
14. **Docker imajı eski**, CI yok, frontend testi yok.
17. **Gerçek veri bağımlılıkları.** Sandbox'ın Hugging Face'e erişimi gerekir (şimdilik sorunsuz, anonim indirme sınırı görülmedi). Kayıt beş veri setiyle sınırlı; kayıtta olmayan bir alan (ör. spam) en yakın sete düşer. `pick_dataset` basit sözcük eşleştirmesidir. Büyük setler örneklendiği için oranlar gerçek oranlardan farklı olabilir (`credit_fraud` %11, tam sette %0,17). Kategorik özellikli setlerde (churn, adult) tablo ve kodlama LLM kodu için daha kırılgan; ilk denemede geçti. Veri bloğu bilimsel olarak da bir tercihtir: kimlik sütunları atılır, `TotalCharges` sayıya çevrilir.
18. **Yazıcı sorgudaki talimatı spec yerine aktarma eğiliminde.** Koşu 3'te sızıntı, Koşu 5'te ayar talimatı makaleye spec'ten bağımsız girdi. İki özel durum için kontrol var; genel kural (makaledeki her yöntem iddiası spec'ten ya da koddan gelmeli) yok. Planlayıcının sorgudaki ayar talimatını spec'e hiç yazmaması (Koşu 5'te RF için) da ayrı bir eksik.
15. **`POST /approve_plan` geçersiz karar için `503` döner** (`decide_plan` doğrulama hatasını `RuntimeError` ile verir, `422` olmalı). `decision` yalnız `Y` veya `N` kabul eder.
16. **Hakem gürültüsü sürüyor.** Koşu 3'te danışman hakem kazanan RandomForest'ı "daha kararlı" yazdığı için eleştirdi (karar `winner` iken). Zararsız ama yanıltıcı, istem sadeleştirilmeli (madde 12).

## 5. Kullanıcının 13 maddelik TODO listesinin durumu

Liste oturumun başında ("Önerilen TODO") verildi. Hepsi yapıldı, kalan parçalar sağdadır.

| # | Madde | Durum | Kalan parça |
| --- | --- | --- | --- |
| 1 | Hata durumu | Tamam | Yok |
| 2 | Erken doğrulama | Tamam (eşik iki model) | Formda ipucu yok |
| 3 | Zorunlu cümleyi çevir, `needs_review` | Tamam | Yok |
| 4 | Gerçek istatistik, ≥10 tekrar, stratify, p ve etki büyüklüğü | Büyük ölçüde | Wilcoxon, `RepeatedStratifiedKFold`, güç yeniden ölçümü (4.2 madde 6) |
| 5 | Kritik döngüsü | Tamam | Yok |
| 6 | Hipotez → deney bağı | Tamam, genişletildi (claim, verdict, seçim, kontrol grubu) | Claim kararı yapılandırma çifti için (4.2 madde 2) |
| 7 | Hafıza | Tamam | Yok |
| 8 | Literatür | Tamam | Eşik kalibrasyonu, atıf (madde 7) |
| 9 | Celery | Tamam (taşındı) | İşçi ölümü kurtarma (madde 5) |
| 10 | MLflow | Tamam | Artifact (madde 10) |
| 11 | Parse | Tamam | `nan` basan model satırı hâlâ sessizce düşer |
| 12 | Test ve Docker | pytest, Dockerfile, compose, requirements Tamam | Frontend imajı, CI, imaj güncelliği (madde 14) |
| 13 | UI | Tamam (+ onay seçimi, hakem notları) | Otomatik arayüz testi (madde 11) |

## 6. Yarın için önerilen sıra

1. Bu dosyayı ve `CONTINUATION.md` içindeki kuralları oku, `git status -sb` ve `git fetch` ile durumu doğrula, `pytest -q` çalıştır (676 geçmeli).
2. ~~Anlamsız fark iddiası kontrolü~~ yapıldı (04b4448). ~~Konfigürasyon karışıklığı~~ Seçenek B ile yapıldı. ~~Üçüncü gerçek koşu~~ yapıldı (sızıntı yolu). İstenirse anlamlı satırın yönünün denetimi, tek model adlı cümleler ve claim kararının "yapılandırma çifti" olarak yazıldığının denetimi eklenebilir.
3. Kalan yollar: `Failed` doğrulama makalesi, sandbox çökmesi, diğer veri setlerinde (`breast_cancer`, `credit_default`, `adult_income`, `credit_fraud`) tam koşu. Maliyet onayı iste.
4. `POST /approve_plan` doğrulama hatasını `422` yap (4.2 madde 15).
5. İşçi ölümü kurtarması (bayat `running` tespiti).
6. Ölü kod temizliği (4.2 madde 9).
7. Frontend: Docker imajı, form ipucu, otomatik arayüz testi.
8. Hakem isteminin sadeleştirilmesi, MLflow artifact.

Kullanıcı farklı bir öncelik verebilir. Mesajı gelmeden iş başlatma.

## 7. Süreç dersleri ve tuzaklar

- **Heredoc ve ters eğik çizgi:** Bash heredoc içindeki Python kaynağında (tırnaklı `'EOF'` ile bile) `\\` bir kat azalıyor (`\b` geri-silme karakteri, `\n` gerçek satır sonu oldu). Regex veya kaçış içeren her değişiklik `Write` aracıyla bir betik dosyası yazılarak yapılır. Bozuk karakter taraması: tracked dosyalarda 0x00-0x1f (sekme ve CR hariç) ara.
- **CRLF:** Çalışma kopyası CRLF, çok satırlı eski-desen eşleşmeleri sessizce uygulanmaz (mutasyon betikleri bir kez uygulanmadan "geçti" gösterdi). Tek satırlık desen kullan ya da `\r\n` normalleştir.
- **`git checkout -- dosya` ile geri alma tehlikelidir:** commit'lenmemiş gerçek değişiklikleri siler (bir kez sildim, betikten geri uyguladım). Mutasyon denemelerinde dosyayı yedeğe kopyalayıp oradan geri koy.
- **Commit kapısı:** `pytest && commit` kullan. Bir kez testin sonucuna bakmadan commit attım, test dosyası bozuktu, düzelttim.
- **Yayınlanmamış commit'i değiştirme riski:** `git fetch` ile `origin/main` kontrolü yetmiyor, kullanıcı veya bir araç arka planda push edebiliyor. Bir kez commit'i düzeltip birleştirdikten sonra hatalı sürümün uzakta yayınlandığını gördüm ve düzeltmeyi uzak commit'in üstüne ayrı commit olarak taşıdım. Yayınlanma ihtimali olan commit'i değiştirmek yerine yeni commit at.
- **`grep -v warning` filtresi** commit mesajındaki "warning" kelimesini gizledi, bir commit'in atılmadığını sandım. Filtreyi mesajlarda geçmeyen bir kalıpla yap.
- **Testleri gerçek çıktıyla sına:** Tablo kontrolünün ve olumsuzlama korumasının hataları uydurma girdilerle görünmedi, gerçek makale cümleleriyle göründü. Kalıp tabanlı her kontrol için gerçek bir örneği test verisi yap.
- **Test geçince şüphelen:** İlk seferde geçen testler mutasyonla iki kez yanlış nedenle geçtiğini gösterdi.
- **LLM kuralları ve hakem:** Yazıcıya kural eklemek yerine mümkünse Python'ın hazırladığı cümleyi kopyalatmak güvenilir. LLM hakemi kapı yapma.
- **Windows süreçleri:** MLflow sunucusunun yetim `multiprocessing` çocukları portu (5000) tutabiliyor, ana süreç ölse bile. Süreç öldürürken komut satırı deseni kendi kabuğunu eşleştirebilir (bir kez kendi kabuğumu öldürdüm), `Name` ve `AxiomForge` ile daralt.
- **Testler arası içe aktarma çalışmaz:** `tests/` paket değil (`__init__.py` yok), bir test dosyasından `from tests.test_nodes import ...` ModuleNotFoundError verir. Ortak yardımcıyı her dosyada yeniden tanımla.
- **Kontrol grubu eklerken:** ana aileyi (kararlılık, performans, hipotez, kararsızlık) `without_baselines` ile süz, yoksa kontrol serileri çiftlere girer. `default` geçen cümleleri model karşılaştırması kontrollerinden hariç tut, yoksa etki cümlesi bir karşılaştırmayı sağlamış gibi sayılır.
- **Arka plan servisleri:** `Monitor` ile `until` döngüsü kullanıldı, `sleep` zincirleri engelleniyor. `POST /approve_plan` için `decision` değeri `Y`.
- **Python dizgisinde `\n`:** heredoc ile yazılan bir betikte dizgi içindeki `\n` gerçek satır sonuna dönüşüp betiği bozdu (ikinci kez). Escape içeren her şey `Write` ile dosya olarak yazılır.
- **Veri bloğu yaklaşımı:** LLM'e veri yükleme kodu yazdırmak yerine Python'ın ürettiği bloğu aynen yapıştırtmak ve AST ile ifade ifade doğrulamak güvenilir çıktı (iki canlı denemede ilk denemede geçti). `sample(random_state=0)` kullan, `train_test_split` değil: doğrulayıcı `train_test_split` çağrılarının tohumunu yeniden yazar, bir örnekleme çağrısı da yazılırsa veri her tohumda değişir.
- **Etki sözcüğü kalıpları model adlarına takılır:** `boost*` kalıbı "Hist Gradient Boosting" adına eşleşti ve temiz bir cümleyi işaretledi. Model adı içeren her kalıbı model adlarıyla da sına.
- **`scratchpad` geçicidir:** Canlı doğrulama betikleri (`live_loop*.py`, `live_final.py`, `live_planner.py`, mock API, tarayıcı sürücüleri) depoda değil, kaybolabilir. Kalıcı araç istenirse bir `tools/` klasörüne taşınmalı.
- **Arayüz doğrulaması:** Başsız Edge ile DevTools protokolü kullanıldı, `localhost:3000` adresi gerekli.
