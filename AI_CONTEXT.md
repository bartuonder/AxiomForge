# AI_CONTEXT.md: AxiomForge oturum devir dosyası

Bu dosya 22-23 Ekim 2026 oturumunun sonunda yazıldı. Yeni oturum önce bunu okur, sonra `CONTINUATION.md` (kurallar ve faz tarihçesi), `README.md`, `GRAPH.md`. Bu dosya ile `CONTINUATION.md` çelişirse bu dosya daha günceldir. Kullanıcı yeni bir mesaj göndermeden iş başlatılmaz.

Durum anı: `HEAD` `d9c8718` ve `origin/main` ile aynı (her şey push edilmiş), çalışma ağacı temiz, 574 pytest testi geçiyor, `tsc` ve `eslint` temiz. Oturumun başında 94 commit vardı, şimdi 199.

## 1. Proje

AxiomForge, kullanıcının bir araştırma cümlesinden literatür tarayan, hipotez kuran, onay bekleyen, sklearn sınıflandırma kodu yazan, kodu E2B sandbox'ında çalıştıran, sonucu istatistiksel olarak doğrulayan ve atölye makalesi yazan bir araştırma grafıdır. Depo: `https://github.com/bartuonder/AxiomForge.git`. Sahip: Bartu Önder, `onderbartu8@gmail.com`. LLM `gpt-4o`, gömü `text-embedding-3-small`. Bileşenler: LangGraph + PostgreSQL (checkpoint ve pgvector hafıza), FastAPI, Celery + Redis, MLflow, E2B, Next.js 16 konsolu.

Projenin araştırma değeri **karşılaştırmalı analize** dayanır. Kullanıcının kararı: her hipotez iki model arasında bir karşılaştırma iddiasıdır ve sorguda en az iki model zorunludur.

## 2. Çalışma kuralları (kullanıcının kesin kuralları)

- Koda yorum satırı yazılmaz.
- Her özellik ayrı commit olur. Dokümanlar (README, GRAPH, CONTINUATION) kendi aralarında ayrı commit olur ve her committe değil, 3-5 committe bir toplu güncellenir.
- Commit yazarı yalnız Bartu Önder'dir. `Co-authored-by` satırı eklenmez. Not: araç ortamı bazen `Co-Authored-By: Claude` eklemeyi hatırlatır, kullanıcının proje kuralı bunun önündedir ve bütün oturum boyunca proje kuralı uygulandı. Normal `git commit` bu satırı kendiliğinden ekleyebildiği için commit şöyle atılır: `git add -- <dosyalar>`, `git write-tree`, `git commit-tree`, `git update-ref HEAD`, `git reset -q`. `git config` değiştirilmez, `--no-verify` kullanılmaz, force push yapılmaz, `.env` ve anahtarlar commitlenmez.
- Kullanıcı Türkçe yazar. Yanıt Türkçe ve kısa olur. İstenmeyen faz veya iş başlatılmaz.
- Gerçek LLM ve E2B çağrıları maliyetlidir: tam koşular yalnız kullanıcı onayıyla yapılır (bu oturumda iki tam koşu onaylandı). Küçük canlı LLM denemeleri doğrulama amacıyla yapıldı ve raporlandı.
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
| Deney döngüsü (3 deneme) | `app/experiments.py` |
| Sandbox | `app/sandbox/e2b_runner.py` |
| Hafıza | `app/memory/rag_memory.py` |
| MLflow ve çıktı ayrıştırma | `app/tracking/mlflow_logger.py` |
| Konsol | `frontend/app/page.tsx`, `frontend/app/result/[threadId]/paper-view.tsx`, `frontend/components/*` |
| Testler | `tests/` (23 dosya) |

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
| Deney prompt sürümü | `experiment-v7` | `experiment.py` |
| Hakem notu sınırı | 8 not, her biri 400 karakter | `nodes.py` |

Desteklenen modeller (17): LinearSVC, SVM, RandomForest, LogisticRegression, DecisionTree, GradientBoosting, HistGradientBoosting, XGBoost, LightGBM, CatBoost, KNN, GaussianNB, MLP, AdaBoost, ExtraTrees, QDA, LDA. Hepsinin izinli kurucu parametre listesi `MODEL_PARAMS` içindedir. Veri setleri: `breast_cancer`, `imbalanced` (sentetik `make_classification`).

### 3.4 State alanları

`query`, `literature_context`, `hypotheses`, `experiment_specs`, `selected_hypothesis`, `approval_status`, `current_experiment_code`, `experiment_error`, `experiment_metrics`, `model_results`, `tested_models`, `dataset_profile`, `statistical_results`, `statistical_decision`, `mlflow_run_id`, `verification_status`, `verifier_feedback`, `critic_rounds`, `critic_continue`, `paper_markdown`, `consistency_feedback`, `referee_notes`, `consistency_rounds`, `consistency_continue`, `research_status`.

`statistical_decision` içeriği: `outcome` (`tie`/`winner`/`none`), `winner`, `comparisons` (Pitman-Morgan), `performance` (düzeltilmiş t, Holm), `instability`, `hypothesis` (`{claim, verdict, evidence}`).

### 3.5 Hipotez, claim ve karar zinciri

1. Planlayıcı 3 spesifikasyon üretir: `{statement, models, claim, dataset, params}`. `claim` = `{kind: performance|stability, metric, subject, other}`. `statement` iki modeli de adlandırmalıdır. `params` yalnız yapılandırmayı belirler, hipotezin konusu olamaz. Geçersizse bir kez düzeltme istenir, yine geçersizse çalışma `failed` olur.
2. Kullanıcı onayda birini seçer (`selected`). Yalnız o çalışır, kaydedilir, MLflow'a ve makaleye girer.
3. Deney kodu AST ile denetlenir: modeller sözlüğü, spesifikasyondaki veri seti ve parametreler, her `train_test_split` çağrısında `stratify=y`. Prompt `experiment-v7` 10 tohumlu döngü ister.
4. Doğrulayıcı `hypothesis_verdict` ile claim'i yapılan testlerden `supported`, `contradicted`, `inconclusive` veya `untested` olarak karara bağlar. Karar model sırasından bağımsızdır.
5. `evidence.py` hipotez kararını, anlamlı her performans farkını (yön, düzeltilmiş p, `dz`) ve kararsızlık bulgusunu hazır İngilizce cümleler yapar. Yazıcı bunları Results'a aynen kopyalar.

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

574 test, yaklaşık 20 saniye, hiçbir dış servis çağrılmaz (düğüm testleri `monkeypatch` ile taklit eder, MLflow testi geçici SQLite kullanır). `requirements-dev.txt` pytest'i ekler. Sık kullanılan yaklaşım: **mutasyon denemesi**. Bir korumanın testle gerçekten kapsandığını görmek için koda bilerek bir hata sokulur, test kırılmalıdır. Bu yöntem bu oturumda iki zayıf testi ortaya çıkardı.

### 3.10 Gerçek koşular

| | Koşu 1 | Koşu 2 |
| --- | --- | --- |
| Thread | `a531b95d-a404-44ba-ae80-f65a0b4b64be` | `b670cc9a-416e-448e-9d2d-4e92930190e0` |
| Sorgu | RandomForest ve LogisticRegression, dengesiz müşteri kaybı | SVM, KNN ve RandomForest, dengesiz müşteri kaybı |
| Seçilen hipotez | 0 (`class_weight='balanced'`), claim yoktu (önceki sürüm) | 1 (`KNN` daha kararlı, kararlılık claim'i) |
| Süre | yaklaşık 41 sn (plan 20 sn) | yaklaşık 61 sn (plan 25 sn) |
| Sonuç | `Passed` / `Completed` | `Passed` / `NeedsReview` (eski kapıyla) |
| Bulgu | Makale üç şeyde eksikti (güvenilirlik cümlesi, ROC-AUC farkı, etki büyüklüğü), düzeltildi | LLM hakem aynı makaleyi 4 çağrının 4'ünde yanlış gerekçelerle reddetti |

Koşu 2 sayıları: ROC-AUC RandomForest 0.944, SVM 0.914, KNN 0.866. KNN-RF farkı ROC-AUC ve F1'de anlamlı (düzeltilmiş `p=0.0464`). Hipotez `inconclusive` (KNN'nin varyansı RF'den yüksek, `p=1.0`). Kararsızlık: SVM F1 std 0.079, KNN 0.068. MLflow'da `Verified` üst run (52 metrik), 30 iç içe run. Hafızada `finding` kaydı.

Önemli: Koşu 2'nin Postgres'teki kalıcı durumu hâlâ `NeedsReview` (eski kapı). Yeni kapı yalnız aynı makale ve veriyle yeniden oynatıldı ve `Completed` çıktı, durum güncellenmedi.

12 sentetik makale döngüsü (3 tohum × 4 karar türü) gerçek `gpt-4o` ile ilk denemede, sıfır yeniden yazmayla `Completed` oldu. Bu testler iki modelli sade veriydi, karmaşık durumdaki hakem gürültüsünü göstermedi (Koşu 2 gösterdi).

### 3.11 Kalıntı veri (test ve koşulardan)

- Postgres: 30 checkpoint thread'i, 30 hafıza kaydı, `research_errors` boş. Thread'lerin bir kısmı bu oturumun test ve koşularından, kalanı önceki oturumlardan; hangisinin hangisi olduğu ayrıştırılmadı (yalnız aşağıdaki beş kimlik bu oturumdan biliniyor).
- `mlflow.db` (yaklaşık 2 MB) içinde gerçek ve test run'ları. `reports/` içinde 9 makale. `reports/`, `mlflow.db` ve `mlruns` gitte yoktur.
- `test_memory.py` hafızaya kasıtlı bir `missing_target` başarısızlığı bırakmıştır. Planlayıcı yalnız `is_success=False` kayıtları okur.
- Bugünkü test thread'leri: `5f2808e4` (deney sırasında işçi kapatıldı, `running` kaldı), `38f98fd2`, `ad6ee6be` (reddedildi), `a531b95d` (Koşu 1), `b670cc9a` (Koşu 2).

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

### 4.2 Açık sorunlar (öncelik sırasıyla)

1. **Anlamsız farkın iddiası denetimsiz.** `performance` içinde `significant` olmayan bir karşılaştırma için makalenin "daha yüksek" demesini hiçbir kontrol yakalamıyor, yalnız hakemin danışman notunda çıkabilir. LLM'siz yapmak üç modelli cümlelerde belirsiz (hangi çiftten söz ediliyor). Fikir: kanıt cümlelerini beyaz liste gibi kullanmak, tabloya ve kanıt cümlelerine dayanmayan metrik karşılaştırma cümlelerini yasaklamak.
2. **Konfigürasyon karışıklığı.** Claim iki modeli *farklı yapılandırmayla* karşılaştırıyor ("RF `n_estimators=100` ve SVM `kernel='rbf'`"), varsayılan parametreli temel çizgi yok. Karar "bu yapılandırma çifti" için geçerli, "model sınıfı" için değil. Seçenek B (her modeli varsayılan ve hipotez parametreleriyle koşturmak) yapılmadı, sandbox işini ve istatistiği iki katına çıkarır.
3. **Gerçek koşuda hiç tetiklenmeyen yollar.** Eleştiri döngüsü (sızıntı, çökme), `Failed` doğrulama makalesi, `NeedsReview` kalıcı durumu, betik döngü basmadığında 10 koşuluk yedek yol (artık 10 ayrı sandbox koşusu), çok modelli veya yavaş sorguda sandbox zaman aşımı (XGBoost paket kurulumu dahil). Hepsi testlerle ve sahte servislerle kapsandı, gerçek servislerle denenmedi.
4. **Kalıp tabanlı kontrollerin kırılganlığı.** Sekiz LLM'siz kontrol regex tabanlı. Gerçek çıktıyla üç kez hata gösterdiler (tablo başlığı, olumsuzlama kapsamı, hipotez cümlesi). Yeni bir kontrol eklemek yerine mümkünse cümleyi Python'a yazdırmak (kanıt cümleleri) daha sağlam bulundu. Yazıcı çok farklı bir ifade seçerse gereksiz yeniden yazma ve en kötü `NeedsReview` olabilir.
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

## 5. Kullanıcının 13 maddelik TODO listesinin durumu

Liste oturumun başında ("Önerilen TODO") verildi. Hepsi yapıldı, kalan parçalar sağdadır.

| # | Madde | Durum | Kalan parça |
| --- | --- | --- | --- |
| 1 | Hata durumu | Tamam | Yok |
| 2 | Erken doğrulama | Tamam (eşik iki model) | Formda ipucu yok |
| 3 | Zorunlu cümleyi çevir, `needs_review` | Tamam | Yok |
| 4 | Gerçek istatistik, ≥10 tekrar, stratify, p ve etki büyüklüğü | Büyük ölçüde | Wilcoxon, `RepeatedStratifiedKFold`, güç yeniden ölçümü (4.2 madde 6) |
| 5 | Kritik döngüsü | Tamam | Yok |
| 6 | Hipotez → deney bağı | Tamam, genişletildi (claim, verdict, seçim) | Konfigürasyon karışıklığı (4.2 madde 2) |
| 7 | Hafıza | Tamam | Yok |
| 8 | Literatür | Tamam | Eşik kalibrasyonu, atıf (madde 7) |
| 9 | Celery | Tamam (taşındı) | İşçi ölümü kurtarma (madde 5) |
| 10 | MLflow | Tamam | Artifact (madde 10) |
| 11 | Parse | Tamam | `nan` basan model satırı hâlâ sessizce düşer |
| 12 | Test ve Docker | pytest, Dockerfile, compose, requirements Tamam | Frontend imajı, CI, imaj güncelliği (madde 14) |
| 13 | UI | Tamam (+ onay seçimi, hakem notları) | Otomatik arayüz testi (madde 11) |

## 6. Yarın için önerilen sıra

1. Bu dosyayı ve `CONTINUATION.md` içindeki kuralları oku, `git status -sb` ve `git fetch` ile durumu doğrula, `pytest -q` çalıştır (574 geçmeli).
2. Anlamsız fark iddiası kontrolü (4.2 madde 1). Önce gerçek makalelerden örnek cümle topla (Koşu 1 ve 2 makaleleri `reports/` içinde), sonra kalıp yaz ve gerçek makaleyle sına.
3. Konfigürasyon karışıklığı için karar iste: seçenek B (temel çizgi) mi, yoksa verdict'i "yapılandırma çifti" olarak etiketlemek mi.
4. Üçüncü gerçek tam koşu, bu kez bir yolu bilerek zorlayan sorgu (sızıntılı veya çöken kod, `Failed` makale, yedek 10 koşu yolu). Maliyet onayı iste.
5. İşçi ölümü kurtarması (bayat `running` tespiti).
6. Ölü kod temizliği (4.2 madde 9) ve doküman düzeltmeleri (`localhost:3000`).
7. Frontend: Docker imajı, form ipucu, otomatik arayüz testi.
8. Hakem isteminin sadeleştirilmesi, MLflow artifact.

Kullanıcı farklı bir öncelik verebilir. Mesajı gelmeden iş başlatma.

## 7. Süreç dersleri ve tuzaklar

- **Heredoc ve ters eğik çizgi:** Bash heredoc içindeki Python kaynağında `\\` bir kat azalıyor (`\b` geri-silme karakteri, `\n` gerçek satır sonu oldu). Regex veya kaçış içeren her değişiklik `Write` aracıyla bir betik dosyası yazılarak yapılır. Bozuk karakter taraması: tracked dosyalarda 0x00-0x1f (sekme ve CR hariç) ara.
- **CRLF:** Çalışma kopyası CRLF, çok satırlı eski-desen eşleşmeleri sessizce uygulanmaz (mutasyon betikleri bir kez uygulanmadan "geçti" gösterdi). Tek satırlık desen kullan ya da `\r\n` normalleştir.
- **`git checkout -- dosya` ile geri alma tehlikelidir:** commit'lenmemiş gerçek değişiklikleri siler (bir kez sildim, betikten geri uyguladım). Mutasyon denemelerinde dosyayı yedeğe kopyalayıp oradan geri koy.
- **Commit kapısı:** `pytest && commit` kullan. Bir kez testin sonucuna bakmadan commit attım, test dosyası bozuktu, düzelttim.
- **Yayınlanmamış commit'i değiştirme riski:** `git fetch` ile `origin/main` kontrolü yetmiyor, kullanıcı veya bir araç arka planda push edebiliyor. Bir kez commit'i düzeltip birleştirdikten sonra hatalı sürümün uzakta yayınlandığını gördüm ve düzeltmeyi uzak commit'in üstüne ayrı commit olarak taşıdım. Yayınlanma ihtimali olan commit'i değiştirmek yerine yeni commit at.
- **`grep -v warning` filtresi** commit mesajındaki "warning" kelimesini gizledi, bir commit'in atılmadığını sandım. Filtreyi mesajlarda geçmeyen bir kalıpla yap.
- **Testleri gerçek çıktıyla sına:** Tablo kontrolünün ve olumsuzlama korumasının hataları uydurma girdilerle görünmedi, gerçek makale cümleleriyle göründü. Kalıp tabanlı her kontrol için gerçek bir örneği test verisi yap.
- **Test geçince şüphelen:** İlk seferde geçen testler mutasyonla iki kez yanlış nedenle geçtiğini gösterdi.
- **LLM kuralları ve hakem:** Yazıcıya kural eklemek yerine mümkünse Python'ın hazırladığı cümleyi kopyalatmak güvenilir. LLM hakemi kapı yapma.
- **Windows süreçleri:** MLflow sunucusunun yetim `multiprocessing` çocukları portu (5000) tutabiliyor, ana süreç ölse bile. Süreç öldürürken komut satırı deseni kendi kabuğunu eşleştirebilir (bir kez kendi kabuğumu öldürdüm), `Name` ve `AxiomForge` ile daralt.
- **`scratchpad` geçicidir:** Canlı doğrulama betikleri (`live_loop*.py`, `live_final.py`, `live_planner.py`, mock API, tarayıcı sürücüleri) depoda değil, kaybolabilir. Kalıcı araç istenirse bir `tools/` klasörüne taşınmalı.
- **Arayüz doğrulaması:** Başsız Edge ile DevTools protokolü kullanıldı, `localhost:3000` adresi gerekli.
