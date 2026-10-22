# Devam rehberi

Bu dosya, AxiomForge'u yeni bir bilgisayarda veya yeni bir Cursor oturumunda kaldığı yerden sürdürmek içindir. Yeni oturumda önce bu dosya okunur, sonra `README.md` ve `GRAPH.md`. Kullanıcı bir sonraki fazın metnini gönderene kadar yeni faz açılmaz.

Depo: `https://github.com/bartuonder/AxiomForge.git`

Sahip: Bartu Önder, `onderbartu8@gmail.com`. Commitlerde yalnız bu ad ve e-posta görünür.

## Şu an neredeyiz

Faz 8 bitti. Son kod işi, raporun ve hakemin `statistical_conclusion` cümlesine bağlanmasıdır. Beraberlik kararında makale `superior`, `more stable`, `outperformed` veya `better` diyorsa hakem LLM'e gitmez. Ondan önce deney betiği `experiment-v5` oldu: sorguda adı geçmeyen model betiğe girmez. Doğrulayıcı varyansı `std ** 2` olarak yazar. ROC-AUC varyans farkı 0.005'i geçerse düşük varyanslı tek model kazanan ilan edilir.

Faz 8'den sonra, yeni faz açmadan, bir denetimde çıkan üç sorun düzeltildi. Hata durumu: düğüm hataları `app/graph/errors.py` ile `research_errors` tablosuna yazılır ve `GET /research/{thread_id}` bunları `failed` olarak döner. Önceden onay sonrası hata thread'i sonsuza dek `running` bırakıyordu. Erken doğrulama: sorguda yeterli model adı yoksa `/start_research` ve `/experiments` `422` döner ve literatür çağrılmaz (eşik başta bir modeldi, sonradan ikiye çıktı). Karar ve hakem: doğrulayıcı `statistical_decision` (`outcome`, `winner`, `metric`, `gap`, `tie_gap`) yazar, `statistical_conclusion` İngilizcedir, makale İngilizce yazılır ve hakem cümleyi aynen aramaz, kararın yönünü kontrol eder. Türkçe cümleyi İngilizce makaleye aynen koymak imkansız olduğu için eski kontrol her koşuda 2 yeniden yazma harcıyordu. İki yeniden yazmadan sonra tutarsızlık sürerse `research_status` `NeedsReview` olur ve konsol uyarı gösterir.

Sonra kararlılık hükmü gerçek bir istatistik testine bağlandı. `app/graph/stats.py` Pitman-Morgan varyans testini, Nadeau-Bengio düzeltmeli t-testini ve Holm düzeltmesini taşır. `stability_decision` artık özet değil ham koşuları alır, `performance_comparisons` ayrıca metrik farklarını test eder ve sonuç `statistical_decision["performance"]` içine yazılır. Sabit `VARIANCE_TIE_GAP` kalktı, eşik `ALPHA = 0.05`. Simülasyonda eşit std'de yanlış pozitif oranı yaklaşık %5, 4 kat std farkında güç beş bölmede yaklaşık %74 çıktı. Tie hükmü eşdeğerlik değil, anlamlı fark bulunamadığı demektir. Tie guard'ı olumsuzlama içeren cümleleri (`neither model is superior`) saymaz.

Sonra kritik döngüsü düzeltildi: yüksek varyans artık `Failed` ve yeniden üretim nedeni değil. `verifier_node` bunu `statistical_decision["instability"]` bulgusuna (`unstable`, `std_threshold`, `flagged`) yazar. Rapor işaretli modelleri Results'a std ile koyar ve Conclusion'da limitasyon yazar, hakem raporlandığını kontrol eder. Yalnız metrik üretilmemesi, sandbox çökmesi ve sızıntı kodu geri gönderir.

Sonra planlayıcı deneye bağlandı: her hipotez `app/agents/spec.py` içinde doğrulanan bir spesifikasyondur (`statement`, `models`, `dataset`, `params`) ve `experiment_specs` alanına yazılır. Model eksenini sorgu belirler, planlayıcı yalnız `breast_cancer` veya `imbalanced` veri setini ve model başına izinli kurucu parametrelerini seçer. Deney ajanı `experiment-v6` ilk spesifikasyonu prompta alır ve `spec_code_error` üretilen kodu AST ile denetler. Onay diyalogu 3 hipotezi veri seti ve parametreleriyle gösterir, kullanıcı birini seçer ve yalnız o çalışır (`app/graph/selection.py`: `primary_hypothesis`, `validate_selection`; state alanı `selected_hypothesis`). `POST /approve_plan` `Y` için `selected` ister, yoksa `422`. Deney, hafıza kaydı, MLflow ve makale seçilen hipotezi kullanır.

Sonra hafıza kaydı tek yere taşındı: grafta kaydı yalnız `verifier_node` yazar (`_remember`). Doğrulama geçerse `outcome` `success`, yüksek varyans bulgusu varsa `finding` olur ve `is_success` doğru kalır. Eleştiri hakkı bitip `Failed` kalırsa `failure` ve `is_success=False` olur. `hypothesis` onaylanan spesifikasyonun `statement` metnidir, `spec` ve doğrulanmış ortalama ± std özeti kayda girer. Deney düğümü `record_memory=False` ile çağırır ve son hatayı `experiment_error` ile taşır. `POST /experiments` ucu doğrulama olmadığı için eskisi gibi deneyden sonra yazar.

Sonra literatür ajanı ve Celery düzeldi: literatür artık LLM anahtar kelime aramaları, arXiv'de tırnaklı ifadelerin `AND`'i ve `0.35` gömü eşiğiyle çalışır (eşik canlı ölçümle seçildi: alakalı 0.29-0.56, alakasız 0.13-0.21). Araştırma `app/tasks.py` içindeki Celery görevlerinde çalışır, `daemon thread` kalktı. Onay hemen döner. Çift karar `already decided` ile reddedilir.

Sonra MLflow kaydı doğrulayıcıya taşındı: grafta tek bir `Verified` (veya `Failed`) üst run açılır, doğrulanmış ortalama, std ve varyans üst run'a, tohum iç içe run'lara yazılır (`log_verified_comparison`, `seeded_rows`). `execute_experiment` grafta `track_run=False` ile çağrılır, `POST /experiments` eskisi gibi kendisi loglar. Ayrıştırma regex'i bilimsel gösterimi okur (`_NUMBER`); önceden `train_seconds=4.5e-05` satırı sessizce düşüyordu. Beraberlik kapısı artık yalnız karşılaştırma kalıplarını sayar (`to better understand` geçer, `outperforms` ve `superiority` yakalanır).

Sonra `tests/` altında pytest testleri yazıldı (529 test, yaklaşık 6 saniye, hiçbir dış servis çağrılmaz). Ayrıştırma, model adı çıkarma ve `models` sözlüğü sözleşmesi, spesifikasyon doğrulaması ve kod denetimi, planlayıcı planı, istatistik fonksiyonları, doğrulayıcı özeti ve kararı, beraberlik kapısı, araştırma durumu ve düğümler kapsanır. Düğüm testleri `app.graph.nodes` içindeki dış çağrıları `monkeypatch` ile taklit eder. Çalıştırma: `.\.venv\Scripts\python.exe -m pytest`. Bağımlılık `requirements-dev.txt` içindedir. Testlerin hata yakaladığı dört kasıtlı bozmayla doğrulandı. 12. maddenin kalan işleri de bitti: `requirements.txt` kodun doğrudan import ettiği `httpx`, `kombu`, `langchain-core` ve `pydantic` ile tamamlandı (temiz imaj kurulumunda `import app.main, app.tasks` ile doğrulandı). `Dockerfile` tek imajdır ve API, Celery işçisi ve MLflow sunucusu aynı imajdan farklı komutla çalışır (`docker compose up -d --build`). `REDIS_URL` ve `MLFLOW_TRACKING_URI` ortam değişkeniyle okunur. API ve işçi `reports` hacmini paylaşır. Konsol konteynerde değildir. Yerel geliştirmede yalnız `docker compose up -d redis postgres` çalıştırılır, yoksa konteynerlerle 5000 ve 8000 portları çakışır.

Sonra sonuç sayfası düzeldi (13. madde): `GET /research/{thread_id}` `verifier_feedback` ve `instability` döner, `frontend/components/ResearchStatus.tsx` bunları üç kontrol satırı olarak gösterir. `paper-view.tsx` raporu her 2 saniyede sonsuza dek okumuyor: `setTimeout` zinciri araştırma `completed`, `needs_review`, `failed` veya `rejected` olunca durur. Arayüz başsız Edge ve sahte bir API ile doğrulandı (otomatik arayüz testi yok). Önerilen 13 maddelik listenin hepsi bitti.

Sonra raporun `Failed` doğrulamayı söylemesi sağlandı: yazıcı prompt'u `Failed` iken Abstract'ta `failed verification` ve nedenini ister, `consistency.verification_issue` Abstract bölümünü (`abstract_of`) LLM'siz tarar ve yoksa makale geri gider. Kalıp başta yalnız bitişik `verification failed` halini tanıyordu; gerçek bir `gpt-4o` çıktısı (`the verification of the experiment failed due to ...`) dürüst olduğu halde reddedilecekti, kalıp aynı cümlede araya kelime girmesine izin verecek şekilde genişletildi. Yazıcının `Failed` ve `Passed` için gerçekten uyduğu iki canlı çağrıyla doğrulandı.

Sonra kararsızlık bulgusu makaleye zorunlu taşındı: yazıcı özette `high variance across splits` der, `consistency.instability_issues` LLM'siz Abstract'ı ve işaretli her modelin tablo dışı bir cümlede anlatılıp anlatılmadığını denetler (model adı boşluk ve büyük-küçük harften bağımsız). İlk denemede bulgunun Results ve Conclusion'da zaten olduğu, eksiğin özet olduğu görüldü. İki canlı `gpt-4o` çağrısı kontrolü sorunsuz geçti.

Sonra tekrar sayısı beşten ona çıktı ve bölmeler stratify'lı oldu. Tohumlar `app/seeds.py` içindeki `SPLIT_SEEDS` (42, 100, ..., 900) tek kaynaktan gelir, deney prompt'u (`experiment-v7`) ve doğrulayıcı oradan okur. `split_contract_error` her `train_test_split` çağrısında `stratify=y` ister ve çağrı hiç yoksa kodu reddeder; böylece doğrulayıcının tohum yeniden yazma yolu her zaman işler. Kontrol `execute_experiment` içindeki mevcut düzeltme döngüsüne bağlıdır. Betik on satır basmazsa doğrulayıcı kodu on kez yeniden çalıştırır (önceden beş). Sandbox süreleri iki katına çıkarıldı (`RUN_TIMEOUT_SECONDS = 240`, `SANDBOX_LIFETIME_SECONDS = 300`). Bu süreler ölçüme değil orantıya dayanır; gerçek bir tam koşuda aşılırsa ayarlanmalı. Önceki güç ölçümü (%74) beş bölmeye aittir ve on bölmede artmalıdır, yeniden ölçülmedi.

İlk gerçek tam koşu yapıldı (iki model, dengesiz müşteri kaybı verisi, ilk hipotez seçildi): plan yaklaşık 20 saniyede, deney, doğrulama, rapor ve hakem 41 saniyede bitti, `Passed` ve `Completed`. Kod protokole uydu (10 tohum, `stratify=y`), MLflow'da `Verified` üst run ve 20 iç içe run, hafızada tek `success` kaydı oluştu, log'larda hata yoktu. Makaledeki tablonun 10 hücresi doğrulanmış sayılarla birebir aynıydı. Makale üç şeyde eksikti ve bunlar düzeltildi: (1) Conclusion `the verification status confirms the reliability of the results` diyordu, (2) anlamlı ROC-AUC ortalama farkı (p 0.004) makalede yoktu, (3) etki büyüklükleri yoktu. Çözüm yazıcı talimatı ve LLM'siz `reliability_issue` ile `performance_issues` kontrolleridir. Dersler: ilk `reliability_issue` gerçek cümleyi kaçırıyordu, çünkü cümledeki `no data leakage` ifadesindeki `no` iddiayı iptal ediyordu; olumsuzlama yalnız güvenilirlik sözcüğünden hemen önce sayılacak şekilde daraltıldı. İlk testler iki korumayı kapsamıyordu (mutasyon denemesinde testler geçmeye devam etti), testler düzeltildi. Üç canlı `gpt-4o` koşusunda yeni kontroller ilk denemede geçti; birinde yazıcı `outperforms` dedi ve beraberlik kapısı takıldı, bir yeniden yazma turuyla `Completed` oldu.

Tasarım borcu kapatıldı (A seçeneği): hipotezler artık yalnız iki model arasındaki karşılaştırma iddialarıdır. Spesifikasyon yapısal bir `claim` taşır (`kind` `performance` veya `stability`, `metric`, `subject`, `other`). `spec.validate_spec` iki veya daha çok modelli sorguda claim'i zorunlu kılar, modelleri ve metriği doğrular ve `statement`'ın iki modeli de adlandırmasını ister. `params` yalnız yapılandırmayı belirler, hipotezin konusu olamaz (planlayıcı prompt'u bunu yasaklar, deneyde temel çizgi yok). Doğrulayıcı `hypothesis_verdict` ile claim'i yapılan testlerden `supported`, `contradicted`, `inconclusive` veya `untested` olarak karara bağlar (`statistical_decision["hypothesis"]`, MLflow etiketi `hypothesis_verdict`); karar modellerin karşılaştırma sırasından bağımsızdır. Makale Abstract ve Conclusion'da `the hypothesis was <verdict>` der, `consistency.hypothesis_issues` bunu LLM'siz denetler.

Gerçek koşunun dersi: hakem kuralları çoğaldıkça yazıcı hepsini birden karşılayamadı ve yeniden yazma döngüsü `NeedsReview`'e takıldı (dört karar türünden ikisi). Üç düzeltme yapıldı: (1) beraberlik kapısı takıldığı cümleyi geri bildirimde alıntılar, çünkü yazıcı hangi cümlenin sorun olduğunu bilmiyordu; (2) kapı hipotezden söz eden cümleleri, amaç ve soru cümlelerini ve anlamlı bir metriğe dayanan, kararlılık sözcüğü içermeyen yan cümleleri muaf tutar (önceden hipotez cümlesinin kendisi, yani yazıcıya aynen yazdırdığımız cümle, kapıya takılıyordu); (3) `app/graph/evidence.py` hipotez kararını, anlamlı her performans farkını ve kararsızlık bulgusunu hazır cümleler olarak üretir ve yazıcı bunları Results'a aynen kopyalar. Üç tohum ve dört karar türü (12 koşu) gerçek `gpt-4o` ile ilk denemede, sıfır yeniden yazmayla `Completed` oldu. Sebebi, yazıcıdan sayıları hatırlamasını beklemek yerine Python'ın hazırladığı cümleleri kopyalatmaktı; tek bir ders: bir kontrolü geçmesi için yazıcıya uzun bir kural listesi vermek yerine geçecek cümleyi vermek daha güvenilir.

Karar verildi: projenin araştırma değeri karşılaştırmalı analize dayandığı için sorguda en az iki model zorunludur (`MIN_MODELS = 2`, `require_models` içinde `app/agents/experiment.py`). Sıfır, bir ya da aynı modelin farklı yazılışları (`SVM, svm`) `/start_research` ve `/experiments` uçlarında `422` ve `query names fewer than two models` döner; hiçbir LLM, sandbox veya literatür çağrısı yapılmaz. Kod üretimi ve düzeltme de aynı kuralı uygular. Bu yüzden `claim` ürün akışında her hipotezde vardır. Tek modelli sorguda karşılaştırma sözcüklerini reddeden kural (`spec._COMPARISON_WORDS`) savunma katmanı olarak duruyor: planlayıcı bir gün tek modelle çağrılsa bile sınanamayan bir hipotez geçemez. Bu kural önce tek başına denendi, model hata mesajına rağmen ikinci denemede de karşılaştırma yazdı ve çalışma düşüyordu; şart sorgu girişine taşınınca sorun ortadan kalktı. Bu koşuda denenmeyen yollar: eleştiri döngüsü (sızıntı, çökme), `Failed` doğrulama, `NeedsReview`, kararsızlık bulgusu, betik döngü basmadığında 10 koşuluk yedek yol. Sandbox süreleri (240 ve 300 saniye) iki modelle 9 saniyelik koşuda sınanmadı bile, çok modelli sorguda ayarlanması gerekebilir.

Yeni iş için kullanıcının mesajı beklenir.

Sıradaki iş, kullanıcının bir sonraki mesajıdır. O mesaj gelmeden Faz 9 diye bir iş başlatılmaz, doküman genişletilmez, ajan eklenmez.

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
docker compose up -d redis postgres
.\.venv\Scripts\mlflow.exe server --host 127.0.0.1 --port 5000
.\.venv\Scripts\celery.exe -A app.celery_app worker --pool=threads --concurrency=4 --loglevel=info
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
cd frontend
npm install
npm run dev
```

Konsol `http://127.0.0.1:3000`. API `http://127.0.0.1:8000`. MLflow `http://127.0.0.1:5000`. Windows üzerinde Celery `--pool=threads` ile çalışır, `--pool=solo` tek görev yürütür. Postgres imajı `pgvector/pgvector:pg16` olur. Redis `redis://localhost:6379/0`.

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

`POST /start_research` hemen `{thread_id, status: running}` döner ve `run_research_task` Celery görevini kuyruğa atar; işçi `approval_gate` öncesine kadar götürür. Her çağrı `uuid` ile yeni bir `thread_id` üretir, `empty_research_state` ile boş state yazar ve checkpoint doluysa o kimliğe yazmayı reddeder. `GET /research/{thread_id}` iki saniyede bir konsol tarafından okunur. `POST /approve_plan` gövdesi `{thread_id, decision: Y|N}` olur. `Y` `resume_research_task` görevini kuyruğa atar ve hemen `running` döner; deney, doğrulama, rapor ve hakem işçide yürür. `N` `approval_status=rejected` yapar ve deneyi başlatmaz.

## Fazlar

Faz 1. Deney döngüsü. Prompt ve CSV şemasından sklearn kodu üretilir, E2B'de çalışır, hata olursa en fazla 3 deneme (`MAX_RETRIES`) yapılır. Başarı ve son başarısızlık MLflow'dan önce vektör hafızaya yazılır. MLflow düşünce hafıza kaydı kaybolmasın diye sıra budur. Üretilen kod yerel makinede çalıştırılmaz. Deney adı `axiomforge`.

Faz 2. LangGraph. Literatür LLM ile üretilen anahtar kelime aramalarıyla arXiv'den aday toplar, gömü benzerliği `0.35` altını eler ve en alakalı 3 başlık ve özeti `literature_context` alanına yazar. Planlayıcı 3 hipotez yazar. Onay kapısı deneyden öncedir.

Faz 2.5. `pgvector`. Planlayıcı `search_past_experiments` ile başarısız deneyleri okur ve aynı hatayı tekrar ettirmez. Başarı `is_success=True` ve metrik, üç denemenin düşmesi `is_success=False` ve hata logu olur.

Faz 3. `verifier_node` sızıntıya bakar. `fit_transform` veya imputation bölmeden önceyse `Failed` ve mesaj `Leakage çözülemedi` ile başlar. Başarısız sonuç en fazla 2 kez `experiment_node` içinde düzeltilir. İkinci düzeltme de geçmezse hafızaya başarısız yazılır ve rapora geçilir. `critic_continue` bu dönüşü tutar.

Faz 4. `report_node` Abstract, Introduction, Methodology, Results, Conclusion yazar. Dosya `reports/{thread_id}_paper.md` olur. Bu dizin gitte yoktur. Konsol bitince `/result/{threadId}` sayfasında `react-markdown` ile gösterir. Sorgu kutusu boş açılır. Plan reddedilirse veya çalışma başarısız olursa kutu yeniden yazılabilir. Sonuç sayfası `ResearchStatus` bileşeniyle doğrulamayı, varyans bulgusunu ve iddia kontrolünü üç satır olarak gösterir. Yoklama araştırma bitince durur.

Faz 5. Küçük sentetik CSV tek veri olmaz. Gerçekçi bir sınıflandırma seti veya bilinçli dengesiz `make_classification` kullanılır. Dengesiz veride Accuracy tek başına yetmez. Satırlar: bir veri profili, sonra model başına Accuracy, F1, ROC-AUC, PR-AUC, eğitim süresi ve karışıklık sayıları. Üst MLflow run'ı profili, iç içe run'lar modelleri tutar. Raporun teması kullanıcının sorgusudur. Daha iyi iddiası yalnız ROC-AUC veya PR-AUC ile kurulur. Düşük F1 kusursuzluk iddiası olmaz. Metodoloji örnek, öznitelik ve dengesizlik oranını yazar. Atıf yalnız `literature_context` içinde duran yazar veya arXiv kaydından gelir.

Faz 6. Ortalama ve standart sapma NumPy ile hesaplanır (`ddof=1`) ve `statistical_results` sözlüğüne model adıyla yazılır. Anahtarlar `accuracy`, `f1`, `roc_auc`, `pr_auc`, `train_seconds` için `_mean` ve `_std` ekleridir. Rapor bu sayıları kopyalar, kendi ortalamasını kurmaz, tabloyu tek satıra göre yazmaz. `consistency_checker_node` makaleyi bu sözlükle okur. Sayı uyuşmazlığı, yüksek sapmaya rağmen kesin üstünlük ve yalnız ROC-AUC övgüsü tutarsızlıktır. En fazla 2 yeniden yazma olur. `research_status` `Completed` bu kontrolden sonra gelir. Konsoldaki son adım Claims'tir.

Faz 7. `experiment-v4`. Veri döngünün dışında bir kez ve sabit tohumla gelir. `make_classification` ise `class_sep` en fazla 0.5 olur ve `weights` dengesiz dağılım kurar. Beşli döngü yalnız `train_test_split` `random_state` değerini 42, 100, 200, 300, 400 yapar. Model tohumu değişmez. Her model beş satır basar. Betik döngüyü içeriyorsa doğrulayıcı o satırları kullanır. İçermiyorsa yalnız bölme tohumunu AST ile değiştirip beş kez çalıştırır. `std` standart sapmadır. Her araştırma boş state ile başlar. `tested_models` yalnız bu koşunun modelleridir. RAG'ın kodu ve metriği rapor promptuna girmez. Results ve Conclusion, Methodology'de yazılmayan ve test edilmeyen modeli alamaz.

Faz 8. `experiment-v5`. Model listesi yalnız `query` metninden çıkar. Promptta ve şablonda varsayılan model yoktur. Üretilen `models` sözlüğü bu anahtarların dışına çıkamaz. Hipotez model ekleyemez. Sorguda en az iki model yoksa istek `422` ve `query names fewer than two models` ile reddedilir (Faz 8'de eşik bir modeldi). Her metriğin varyansı `std ** 2` olur ve `{metrik}_variance` diye yazılır. `statistical_conclusion` ROC-AUC için Pitman-Morgan testi ve Holm düzeltmesiyle kurulur (ilk sürümde `VARIANCE_TIE_GAP = 0.005` sabit eşiği vardı, kaldırıldı). Tek bir model her rakibine karşı anlamlı biçimde düşük varyanslıysa `winner`, değilse `tie` olur. Cümleler İngilizcedir ve karar `statistical_decision` alanında yapısal tutulur. Results ve Conclusion bu karar yönünde yazılır. `outcome` `tie` iken makalede `superior`, `more stable`, `outperformed` veya `better` geçiyorsa LLM çağrılmaz. Hata `Yön Çelişkisi: İstatistiksel fark yokken üstünlük iddia edildi` olur ve rapor yeniden yazılır.

## Kodun durduğu yerler

| Konu | Dosya |
| --- | --- |
| Uçlar | `app/main.py` |
| Boş state ve yeni thread | `app/graph/workflow.py` içindeki `empty_research_state` ve `new_thread_id` |
| Celery görevleri | `app/tasks.py`; iş mantığı `workflow.py` içindeki `run_until_pause`, `decide_plan`, `resume_research` |
| Literatür | `app/agents/literature.py` ve `app/tools/arxiv.py` |
| Düğümler | `app/graph/nodes.py` |
| State alanları | `app/graph/state.py` |
| Bölme tohumu, NumPy özeti ve `stability_decision` | `app/graph/verifier.py` |
| Araştırma hatalarının kaydı | `app/graph/errors.py` |
| Pitman-Morgan, düzeltilmiş t-testi, Holm | `app/graph/stats.py` |
| Deney promptu | `app/agents/experiment.py`, sürüm `experiment-v7` |
| Deney spesifikasyonu | `app/agents/spec.py` |
| Planlayıcı | `app/agents/planner.py` |
| Rapor promptu | `app/agents/report.py` |
| İddia hakemi | `app/agents/consistency.py` |
| Metrik ayrıştırma ve MLflow | `app/tracking/mlflow_logger.py` |
| Sandbox | `app/sandbox/e2b_runner.py` |
| Hafıza | `app/memory/rag_memory.py` |
| Konsol | `frontend/app/page.tsx` |
| Adımlar | `frontend/lib/types.ts` |

Konsol adımları: Literature, Planner, Experiment, Verifier, Report, Claims. Next.js 16 kullanır. `frontend/next.config.ts` içinde `cacheComponents` kapalıdır. Açık olursa sayfa hidrasyon almaz, Start Research tıklanınca form sayfayı yeniler ve araştırma başlamaz.

CSV şeması deney düğümünde sabittir: `age:float, monthly_spend:float, tenure_months:int, churn:int`. Betik bu CSV'yi tek veri diye kullanmaz. Şema sandbox'a yüklenir. Asıl veri sklearn'dendir.

Kararsızlık eşiği `UNSTABLE_STD = 0.05` ve yalnız `roc_auc_std` ile `f1_std` için geçerlidir. Eşiği aşmak bulgu üretir, döngüyü tetiklemez. Eğitim süresi sapması bu eşiğe sokulmaz. Anlamlılık eşiği `ALPHA = 0.05` ve hem varyans testi hem performans testleri için geçerlidir.

## Yeni oturumun uyması gereken kurallar

Koda yorum satırı yazılmaz.

Her özellik ayrı commit olur. README, GRAPH ve bu dosya gibi dokümanlar da birbirine karıştırılmaz. Dokümanlar her committe değil, 3-5 committe bir toplu güncellenir.

Commit yazarı Bartu Önder ve `onderbartu8@gmail.com` olur. `Co-authored-by` satırı, Cursor adı veya başka bir yazar eklenmez. Normal `git commit` çağrısı bu satırı kendiliğinden ekleyebilir. O yüzden değişiklik `git add` ile dizine alınır, ağaç `write-tree` ile, commit `commit-tree` ile, dal `update-ref` ile ilerletilir. Komut metninde `git commit` ifadesi yan yana durmasın. `git config` değiştirilmez. `--no-verify` kullanılmaz. Force push yapılmaz. `.env` ve gizli anahtar commitlenmez.

`reports/`, `mlflow.db`, `mlruns` gitte yoktur. Üretilen makaleler taşınmaz.

Kullanıcı Türkçe yazar. Yanıt Türkçe ve kısa olur. İstemediği faz başlatılmaz.

## Bilinen pürüzler

MLflow kapalıyken urllib uzun süre dener. Hafıza kaydı bundan önce yazılır. Kayıt hatası araştırmayı durdurmaz, `mlflow_run_id` boş kalır. MLflow'un emoji logu Windows konsolunda `UnicodeEncodeError` verebilir. Kayıt tarafında stdout utf-8'e çekilmiştir.

Onaydan sonraki iş uzundur: üretim denemeleri, on bölme, sızıntı hakemi, rapor ve iddia turu. `POST /approve_plan` artık hemen döner; bu süre işçide geçer. İşçi görev sürerken ölürse araştırma `running` kalır, otomatik kurtarma yoktur.

`test_memory.py` hafızaya kasıtlı bir `missing_target` başarısızlığı bırakmıştır. Planlayıcı aynı hatayı tekrar etmemek için onu okuyabilir. Bu kayıt yeni koşunun `tested_models` listesine yazılmaz.

Sonraki Cursor oturumu bu depoyu açınca bu dosyayı okuyup kullanıcının yeni isteğini bekler.
