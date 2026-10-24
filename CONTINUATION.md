# Devam rehberi

Bu dosya, AxiomForge'u yeni bir bilgisayarda veya yeni bir Cursor oturumunda kaldığı yerden sürdürmek içindir. Yeni oturumda önce `AI_CONTEXT.md` (en güncel devir dosyası), sonra bu dosya, sonra `README.md` ve `GRAPH.md` okunur. Kullanıcı bir sonraki fazın metnini gönderene kadar yeni faz açılmaz.

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

Sonra `tests/` altında pytest testleri yazıldı (574 test, yaklaşık 6 saniye, hiçbir dış servis çağrılmaz). Ayrıştırma, model adı çıkarma ve `models` sözlüğü sözleşmesi, spesifikasyon doğrulaması ve kod denetimi, planlayıcı planı, istatistik fonksiyonları, doğrulayıcı özeti ve kararı, beraberlik kapısı, araştırma durumu ve düğümler kapsanır. Düğüm testleri `app.graph.nodes` içindeki dış çağrıları `monkeypatch` ile taklit eder. Çalıştırma: `.\.venv\Scripts\python.exe -m pytest`. Bağımlılık `requirements-dev.txt` içindedir. Testlerin hata yakaladığı dört kasıtlı bozmayla doğrulandı. 12. maddenin kalan işleri de bitti: `requirements.txt` kodun doğrudan import ettiği `httpx`, `kombu`, `langchain-core` ve `pydantic` ile tamamlandı (temiz imaj kurulumunda `import app.main, app.tasks` ile doğrulandı). `Dockerfile` tek imajdır ve API, Celery işçisi ve MLflow sunucusu aynı imajdan farklı komutla çalışır (`docker compose up -d --build`). `REDIS_URL` ve `MLFLOW_TRACKING_URI` ortam değişkeniyle okunur. API ve işçi `reports` hacmini paylaşır. Konsol konteynerde değildir. Yerel geliştirmede yalnız `docker compose up -d redis postgres` çalıştırılır, yoksa konteynerlerle 5000 ve 8000 portları çakışır.

Sonra sonuç sayfası düzeldi (13. madde): `GET /research/{thread_id}` `verifier_feedback` ve `instability` döner, `frontend/components/ResearchStatus.tsx` bunları üç kontrol satırı olarak gösterir. `paper-view.tsx` raporu her 2 saniyede sonsuza dek okumuyor: `setTimeout` zinciri araştırma `completed`, `needs_review`, `failed` veya `rejected` olunca durur. Arayüz başsız Edge ve sahte bir API ile doğrulandı (otomatik arayüz testi yok). Önerilen 13 maddelik listenin hepsi bitti.

Sonra raporun `Failed` doğrulamayı söylemesi sağlandı: yazıcı prompt'u `Failed` iken Abstract'ta `failed verification` ve nedenini ister, `consistency.verification_issue` Abstract bölümünü (`abstract_of`) LLM'siz tarar ve yoksa makale geri gider. Kalıp başta yalnız bitişik `verification failed` halini tanıyordu; gerçek bir `gpt-4o` çıktısı (`the verification of the experiment failed due to ...`) dürüst olduğu halde reddedilecekti, kalıp aynı cümlede araya kelime girmesine izin verecek şekilde genişletildi. Yazıcının `Failed` ve `Passed` için gerçekten uyduğu iki canlı çağrıyla doğrulandı.

Sonra kararsızlık bulgusu makaleye zorunlu taşındı: yazıcı özette `high variance across splits` der, `consistency.instability_issues` LLM'siz Abstract'ı ve işaretli her modelin tablo dışı bir cümlede anlatılıp anlatılmadığını denetler (model adı boşluk ve büyük-küçük harften bağımsız). İlk denemede bulgunun Results ve Conclusion'da zaten olduğu, eksiğin özet olduğu görüldü. İki canlı `gpt-4o` çağrısı kontrolü sorunsuz geçti.

Sonra tekrar sayısı beşten ona çıktı ve bölmeler stratify'lı oldu. Tohumlar `app/seeds.py` içindeki `SPLIT_SEEDS` (42, 100, ..., 900) tek kaynaktan gelir, deney prompt'u (`experiment-v7`) ve doğrulayıcı oradan okur. `split_contract_error` her `train_test_split` çağrısında `stratify=y` ister ve çağrı hiç yoksa kodu reddeder; böylece doğrulayıcının tohum yeniden yazma yolu her zaman işler. Kontrol `execute_experiment` içindeki mevcut düzeltme döngüsüne bağlıdır. Betik on satır basmazsa doğrulayıcı kodu on kez yeniden çalıştırır (önceden beş). Sandbox süreleri iki katına çıkarıldı (`RUN_TIMEOUT_SECONDS = 240`, `SANDBOX_LIFETIME_SECONDS = 300`). Bu süreler ölçüme değil orantıya dayanır; gerçek bir tam koşuda aşılırsa ayarlanmalı. Önceki güç ölçümü (%74) beş bölmeye aittir ve on bölmede artmalıdır, yeniden ölçülmedi.

İlk gerçek tam koşu yapıldı (iki model, dengesiz müşteri kaybı verisi, ilk hipotez seçildi): plan yaklaşık 20 saniyede, deney, doğrulama, rapor ve hakem 41 saniyede bitti, `Passed` ve `Completed`. Kod protokole uydu (10 tohum, `stratify=y`), MLflow'da `Verified` üst run ve 20 iç içe run, hafızada tek `success` kaydı oluştu, log'larda hata yoktu. Makaledeki tablonun 10 hücresi doğrulanmış sayılarla birebir aynıydı. Makale üç şeyde eksikti ve bunlar düzeltildi: (1) Conclusion `the verification status confirms the reliability of the results` diyordu, (2) anlamlı ROC-AUC ortalama farkı (p 0.004) makalede yoktu, (3) etki büyüklükleri yoktu. Çözüm yazıcı talimatı ve LLM'siz `reliability_issue` ile `performance_issues` kontrolleridir. Dersler: ilk `reliability_issue` gerçek cümleyi kaçırıyordu, çünkü cümledeki `no data leakage` ifadesindeki `no` iddiayı iptal ediyordu; olumsuzlama yalnız güvenilirlik sözcüğünden hemen önce sayılacak şekilde daraltıldı. İlk testler iki korumayı kapsamıyordu (mutasyon denemesinde testler geçmeye devam etti), testler düzeltildi. Üç canlı `gpt-4o` koşusunda yeni kontroller ilk denemede geçti; birinde yazıcı `outperforms` dedi ve beraberlik kapısı takıldı, bir yeniden yazma turuyla `Completed` oldu.

Tasarım borcu kapatıldı (A seçeneği): hipotezler artık yalnız iki model arasındaki karşılaştırma iddialarıdır. Spesifikasyon yapısal bir `claim` taşır (`kind` `performance` veya `stability`, `metric`, `subject`, `other`). `spec.validate_spec` iki veya daha çok modelli sorguda claim'i zorunlu kılar, modelleri ve metriği doğrular ve `statement`'ın iki modeli de adlandırmasını ister. `params` yalnız yapılandırmayı belirler, hipotezin konusu olamaz (planlayıcı prompt'u bunu yasaklar, deneyde temel çizgi yok). Doğrulayıcı `hypothesis_verdict` ile claim'i yapılan testlerden `supported`, `contradicted`, `inconclusive` veya `untested` olarak karara bağlar (`statistical_decision["hypothesis"]`, MLflow etiketi `hypothesis_verdict`); karar modellerin karşılaştırma sırasından bağımsızdır. Makale Abstract ve Conclusion'da `the hypothesis was <verdict>` der, `consistency.hypothesis_issues` bunu LLM'siz denetler.

Gerçek koşunun dersi: hakem kuralları çoğaldıkça yazıcı hepsini birden karşılayamadı ve yeniden yazma döngüsü `NeedsReview`'e takıldı (dört karar türünden ikisi). Üç düzeltme yapıldı: (1) beraberlik kapısı takıldığı cümleyi geri bildirimde alıntılar, çünkü yazıcı hangi cümlenin sorun olduğunu bilmiyordu; (2) kapı hipotezden söz eden cümleleri, amaç ve soru cümlelerini ve anlamlı bir metriğe dayanan, kararlılık sözcüğü içermeyen yan cümleleri muaf tutar (önceden hipotez cümlesinin kendisi, yani yazıcıya aynen yazdırdığımız cümle, kapıya takılıyordu); (3) `app/graph/evidence.py` hipotez kararını, anlamlı her performans farkını ve kararsızlık bulgusunu hazır cümleler olarak üretir ve yazıcı bunları Results'a aynen kopyalar. Üç tohum ve dört karar türü (12 koşu) gerçek `gpt-4o` ile ilk denemede, sıfır yeniden yazmayla `Completed` oldu. Sebebi, yazıcıdan sayıları hatırlamasını beklemek yerine Python'ın hazırladığı cümleleri kopyalatmaktı; tek bir ders: bir kontrolü geçmesi için yazıcıya uzun bir kural listesi vermek yerine geçecek cümleyi vermek daha güvenilir.

Karar verildi: projenin araştırma değeri karşılaştırmalı analize dayandığı için sorguda en az iki model zorunludur (`MIN_MODELS = 2`, `require_models` içinde `app/agents/experiment.py`). Sıfır, bir ya da aynı modelin farklı yazılışları (`SVM, svm`) `/start_research` ve `/experiments` uçlarında `422` ve `query names fewer than two models` döner; hiçbir LLM, sandbox veya literatür çağrısı yapılmaz. Kod üretimi ve düzeltme de aynı kuralı uygular. Bu yüzden `claim` ürün akışında her hipotezde vardır. Tek modelli sorguda karşılaştırma sözcüklerini reddeden kural (`spec._COMPARISON_WORDS`) savunma katmanı olarak duruyor: planlayıcı bir gün tek modelle çağrılsa bile sınanamayan bir hipotez geçemez. Bu kural önce tek başına denendi, model hata mesajına rağmen ikinci denemede de karşılaştırma yazdı ve çalışma düşüyordu; şart sorgu girişine taşınınca sorun ortadan kalktı. Bu koşuda denenmeyen yollar: eleştiri döngüsü (sızıntı, çökme), `Failed` doğrulama, `NeedsReview`, kararsızlık bulgusu, betik döngü basmadığında 10 koşuluk yedek yol. Sandbox süreleri (240 ve 300 saniye) iki modelle 9 saniyelik koşuda sınanmadı bile, çok modelli sorguda ayarlanması gerekebilir.

İkinci gerçek tam koşu (SVM, KNN, RandomForest, kararlılık iddiası) `NeedsReview` ile bitti, ama sebep makale değil LLM hakemdi: LLM'siz yedi kontrolün yedisi makaleyi onaylıyordu, 15 tablo hücresi doğrulanmış sayılarla birebir aynıydı, ve LLM hakem aynı makaleyi dört çağrının dördünde reddetti. Gerekçeler yanlıştı (anlamlı bir F1 farkına "anlamlı değil" dedi, kuralı tersine okudu, PR-AUC vurgusu gibi olmayan kurallar uydurdu) ve ilk turda 5 "sorun"un çoğu onay cümlesiydi. Çözüm iki parçadır: (1) LLM hakem kapı olmaktan çıktı, danışman oldu (`referee_notes`, iş bittiğinde bir kez çağrılır, durumu belirlemez, çağrı hatası araştırmayı düşürmez); (2) hakemin tek başına yakaladığı sayı uyuşmazlığı LLM'siz yapıldı (`consistency.table_issues`). Anlamsız bir farkın makalede iddia edilmesi artık hiçbir kontrolle denetlenmiyor, yalnız hakemin danışman notunda çıkabilir. Gerçek ikinci koşu makalesi yeni kapıdan sıfır yeniden yazmayla `Completed` çıktı.

Tablo kontrolü gerçek veriyle bir hata yakaladı: ilk sürüm başlıkları `Accuracy` gibi sade bekliyordu, yazıcı ise `Accuracy (Mean ± Std)` yazıyordu, bu yüzden gerçek makalede "tablo yok" diyordu ve testlerim bunu görmedi. Başlıklar artık parantezden ve `Mean ± Std` süsünden arındırılıyor, ve yazıcının gerçekten yazdığı tablo test verisi olarak kodlandı. Ders: kalıp tabanlı bir kontrolü yalnız uydurma girdiyle değil gerçek çıktıyla da sına.

Karar verildi (Seçenek B): konfigürasyon karışıklığı, parametre verilen her modelin varsayılan parametreli bir kontrol girdisiyle birlikte koşturulmasıyla çözüldü. Eski sınırlama ("deneyde parametresiz temel çizgi yok") kalktı. Ayrıntı: `experiment-v8`, `app/variants.py` (`Model__default`, `expected_keys`, `display_name`), doğrulayıcıda `without_baselines` ve `parameter_effects`, `evidence.effect_sentences`, kapıda `parameter_effect_issues`, MLflow'da `significant_parameter_effects`. Kontrol serileri kararlılık, performans, hipotez ve kararsızlık analizlerine girmez, yalnız özet, tablo ve MLflow'da bulunur.

Üçüncü gerçek tam koşu (thread `26344d2d-7234-415f-8d2f-ee1e529d4668`, RandomForest ve LogisticRegression, sorgu bilerek StandardScaler'ın tüm veriye bölmeden önce uydurulmasını istiyordu, hipotez 2 seçildi) `Passed` ve `Completed` bitti. Tur 0'da LLM sızıntı yargıcı sızıntıyı yakaladı, doğrulama `Failed` oldu, eleştirmen kodu düzeltti, tur 1'de `Passed`. 4 model (iki asıl, iki kontrol) × 10 bölme = 40 iç içe MLflow run'ı. Parametre etkilerinden yalnız LogisticRegression `C=0.1` F1'de anlamlıydı (varsayılandan düşük, `dz` 2.53, düzeltilmiş `p` 0.012). Kapı ilk denemede geçti. Ama makale çelişiyordu: Methodology "StandardScaler tüm veri üzerinde bölmeden önce uyduruldu" yazıp aynı yerde "veri sızıntısı tespit edilmedi" diyordu, çünkü yazıcı düzeltilmiş kodu değil sorgudaki talimatı aktarmıştı. Hiçbir kontrol bunu yakalamıyordu. Çözüm: `leakage_description_issues` kapıya eklendi ve yazıcı prompt'u ön işlemeyi Final code ile aynı anlatmasını istiyor. Kural gerçek makalede sorunu yakalıyor, reports içindeki diğer dokuz makalede yanlış alarm vermiyor. Bu koşuda denenmeyen yollar: `Failed` doğrulama makalesi, `NeedsReview`, betik döngü basmadığında 10 koşuluk yedek yol, sandbox zaman aşımı.

Dördüncü gerçek tam koşu (thread `96acf4c2-2712-4ea7-9977-a447186a7670`, sorgu tek bölme istiyordu) 10 koşuluk yedek yolu gerçek servislerle denedi: doğrulayıcı kodu bir kez çalıştırdı, bölme döngüsü bulamadı, tohumları 42'den 900'e yazıp 10 ayrı E2B koşusu yaptı (her biri yaklaşık 5 sn), 4 model × 10 bölme = 40 iç içe MLflow run'ı oluştu. Doğrulama `Passed` oldu. Koşu `NeedsReview` bitti, çünkü `parameter_effect_issues` yanlış alarm verdi: Methodology'deki tırnaklı hipotez cümlesi (`...dataset."`) cümle bölücüde bölünmedi ve yanındaki "The control group included models with default parameters" cümlesiyle birleşip anlamlı olmayan iki etki için fark iddiası sayıldı. Çözüm `7673cb7`: bölücü kapanış işaretlerini (`"`, `'`, `)`, `]`) cümle sonuna dahil eder, "default" aynı yan cümlede aranır, hipotez ve amaç cümleleri muaftır. Ders: yeni bir kalıp kontrolünü yalnız eski makalelerle değil, yeni özelliğin gerçek makalesiyle de sına.

Gerçek veri entegrasyonu (Faz 10, `2d29b9e` ve `8a50ef1`) sonrası iki küçük canlı deneme yapıldı (grafın dışında, `execute_experiment`): spesifikasyonlu churn (RF ve LR, kontrol grubuyla, 36 sn) ve spesifikasyonsuz fraud (XGBoost ve KNN, 34 sn). İkisi de ilk denemede geçti, veri bloğu aynen yapıştırıldı. Gerçek veriyle ilk tam araştırma koşusu Koşu 5'tir (aşağıda). Koşu 3 ve 4 sentetik veriyle yapılmıştı.

Beşinci gerçek tam koşu (thread `40222d61-edd7-463e-9d68-a847faa67dfd`, gerçek Hugging Face verisiyle ilk koşu) üç model (RandomForest, LogisticRegression, HistGradientBoosting) ve telekom müşteri kaybı sorgusuyla yapıldı. Planlayıcı `customer_churn` veri setini menüden kendisi seçti. Deney ilk denemede geçti (yaklaşık 27 sn), sızıntı yargıcı Pipeline'ı temiz buldu, 5 model × 10 bölme = 50 iç içe MLflow run'ı oluştu, `Passed` ve `Completed`, kapı ilk turda geçti. Hipotez (LR `C=0.5` PR-AUC'de HistGradientBoosting `max_depth=5`'ten yüksek) `inconclusive`. Altı parametre etkisinin hiçbiri anlamlı değildi. Makale iki konuda yanlıştı ve kapı yakalamadı: Abstract spec'te parametresi olmayan RandomForest'ın `n_estimators` ayarının odak olduğunu söylüyordu (sorgudaki talimat), Conclusion hiçbir etki anlamlı değilken "parametre ayarı performansı etkileyebilir" diyordu. Çözüm `eedebae`: `untuned_model_issues` ve `tuning_claim_issues`, ve yazıcı prompt'una iki kural. Ders: yazıcı sorgudaki talimatı onaylanan spesifikasyon yerine aktarma eğiliminde (Koşu 3'te sızıntı, Koşu 5'te ayar).

Altıncı ve yedinci gerçek koşular (threadler `5fcf65e4-c75c-42af-a1ac-4776b1ed882a` ve `e0785e18-b992-4f3e-9c8c-196635fe26f4`, üç model, `credit_default`) yeni kontrolleri gerçek döngüde sınadı. Koşu 6'da kapı tur 0'da üç sorunu yakaladı (F1 farkı yazılmamış, spec'te parametresi olmayan RandomForest'ın ayarlandığı, anlamlı etki yokken ayarın etkisi) ve tur 1'de yazıcı üçünü de düzeltti, `Completed`. Aynı makalenin son halinde kapının yakalamadığı bir yanlış kalmıştı: Abstract ve Conclusion RF'nin PR-AUC'de "diğer modellerden" yüksek olduğunu söylüyordu, oysa RF-LR farkı anlamlı değildi (`collective_claim_issues` bunu sonradan ekledi, `acdf5f9`). Koşu 7'de planlayıcı ve yazıcı tuzaklarına düşmedi, kapı ilk turda geçti, ama makale RF'ye "yüksek varyans, bölmeye duyarlı" diyordu, oysa `unstable` false idi (`unfounded_instability_issues`, `40f2e35`). Planlayıcıyı tek başına, değerleri zorlayan bir sorguyla denemek gösterdi ki doğrulayıcı `n_estimators=100`, `n_neighbors=5`, `C=1.0` gibi varsayılanları reddediyor ve LLM ikinci çağrıda varsayılan olmayan değerler öneriyor (`3bbeb2f`). Koşu 7'nin iki ilk denemesi literatür adımında `arxiv returned no papers` ile düştü: sorgudaki `n_neighbors=5` gibi ifadeler ve 4 ifadenin `AND`'i arXiv'de 0 sonuç veriyordu. Literatür ajanı yeniden yazıldı (`3f98244`): LLM yalnız alanı çıkarır, modelleri Python bulur, aramalar en çok iki ifadelidir; daha önce düşen üç sorgu ve churn sorgusu gerçek arXiv ile 3 ilgili makale döndürdü.

Sekizinci-on dördüncü gerçek koşular (Koşu 8-14) yeni makale kapılarını gerçek döngüde sınadı. Koşu 8 (dört model, `adult_income`): kapı iki yeniden yazmada geçti; yazıcı RF ve LR'yi sorguya uyarak "ayarlandı" diye yazdı ve toplu üstünlük iddiası kurdu, yakalandı, ama makale "10-fold cross-validation" uyduruyordu ve özet sorgunun "en iyi model" sorusunu cevaplamıyordu (`method_issues`, `summary_completeness_issues`, `repetition_issues`, `031abd4`). Koşu 9 (RF + LR, `breast_cancer`): yeni üç kapı ilk taslakta tetiklenmedi, bir yeniden yazmayla `Completed`. Koşu 10 (dört model, anlamlı KNN etkisi): `NeedsReview`; özet eksiksizliği (lider ve etki iki bölümde de yazılmalı) ile tekrar kontrolü (aynı cümle iki bölümde olmamalı) birbiriyle çelişti, yazıcı aynı cümleleri kopyaladı (`f33fd84`: Abstract ve Conclusion için kasten farklı iki hazır cümle listesi). Koşu 11 OpenAI kredisi bittiği için ilk LLM çağrısında `failed` oldu (`insufficient_quota`); kod hatası değil. Koşu 12: tur 0'da yalnız 1 sorun kaldı ama yazıcı RF ve LR'yi "ayarlandı" diye yazmaya devam etti, `NeedsReview` (`7f650c9`: hazır yapılandırma cümlesi). Koşu 13 (aynı sorgu): kapı tur 0'da geçti, `Completed`, 0 yeniden yazma. Ardından `f5966e5`: doğrulayıcı her metrik için lideri ve ROC-AUC, PR-AUC, F1 sıralama ortalamasına göre genel en iyi modeli hesaplıyor; Abstract ve Conclusion için genel en iyi model cümleleri hazır geliyor. Koşu 14 (`1fb974d7-b0d7-4452-a29b-226ac8aecaba`, Koşu 13 ile aynı sorgu ve parametreler, planlayıcı bu sefer hipotez 1'i kararlılık iddiası olarak yazdı) genel en iyi model özelliğinin canlı doğrulamasıdır: kapı tur 0'da geçti, 0 yeniden yazma, `Completed`, yaklaşık 2,6 dakika. Doğrulayıcı genel en iyi modeli HistGradientBoosting olarak buldu (ortalama sıra 1.00 / 4; PR-AUC'de tüm rakiplerine karşı kanıtlı, ROC-AUC ve F1'de LR'ye karşı kanıtlı değil). Abstract ve Conclusion hazır cümleleri taşıdı (yazar yalnız birer Oxford virgülü ekledi), KNN'nin anlamlı etkisi (ROC-AUC +0.022, PR-AUC +0.042) ikisinde de vardı, Methodology yapılandırma cümlesini aynen kopyaladı ve yöntemi `10 repeated stratified train/test splits` diye anlattı. Dört yeni kontrol (yöntem, özet eksiksizliği, tekrar, uydurma kararsızlık) 0 uyarı verdi. Bu, tek koşudur; Koşu 10-13 gibi planlayıcı ve yazıcı davranışı koşudan koşuya değişebilir.

Strateji kararı: kullanıcının isteği üzerine proje, yayımlanmış bir akademik ML karşılaştırma iddiasını çok veri setinde yeniden sınayan bir replikasyon ajanına doğru genişletildi (Faz 12). Önceki durumun eleştirisi: tek veri setinde doğrulanmış karşılaştırma otomasyonu, soru uzayı dar, literatür sığ, kapalı döngü yok, genelleme yok, LLM çoğunlukla biçimlendiriyor, regex kapıları kırılgan, ajan kıyaslaması yok. Faz 12 bunlardan çok veri seti genellemesini ve izlenebilir kanıtı ele alır; literatür derinliği ve kapalı döngü açık kalır.

Faz 12, `app/campaign/` altında LLM'siz bir motordur: `spec` (belirtim doğrulaması), `protocol` (veri seti başına deterministik betik), `runner` (paralel sandbox, yeniden deneme, eksiksizlik denetimi), `stats` (veri seti birimli Wilcoxon, Holm, Friedman, iddia kararı), `analysis`, `ledger` (E1... kimlikli kanıt defteri, betik SHA-256 özeti), `report` (deterministik rapor, her sayısal satırda `[E#]` ve `report_issues` denetimi), `store` (`reports/campaigns/{id}/` altında atomik kayıt), `service` (`execute_campaign`, `queue_campaign`, `reject_campaign`), `demos` ve `__main__` (komut satırı). Veri havuzu `app/datasets.py` içinde 14 sete çıktı: `core` grubu (5 set, planlayıcı yalnız bunu görür) ve `benchmark` grubu (`inria-soda/tabular-benchmark` içinden 9 sayısal sınıflandırma seti: tb_credit, tb_california, tb_electricity, tb_magic, tb_bank, tb_heloc, tb_house16h, tb_pol, tb_eye; 6000 satırlık sabit tohumlu dengeli örnek). Hedef sütunlar ve pozitif sınıflar gerçek sandbox'ta doğrulandı ve `VERIFIED_BENCHMARK_TARGETS` testiyle sabitlendi. Uçlar `POST /start_campaign`, `GET /campaigns`, `GET /campaign/{id}`, `GET /campaign/{id}/report` ve Celery görevi `axiomforge.run_campaign`. Komut satırı: `python -m app.campaign run --demo grinsztajn-2022` (ayrıca `list`, `show ID`, `demos`, `--datasets`, `--workers`, `--id`). Kampanya servisleri (Redis, Postgres, MLflow) gerektirmez; yalnız `E2B_API_KEY` ister. Testlerde `tests/conftest.py` E2B anahtarını boşaltır, böylece hiçbir test gerçek sandbox'a gidemez (bir mutasyon taraması bir kez gerçek E2B'ye gitmişti, bu yüzden eklendi).

Karar: kesin iki yönlü Wilcoxon p < 0,05 için en az 6 sıfırdan farklı veri seti farkı ister (5 sette en küçük p 0,0625). Holm düzeltmesi üç ölçüt üzerinden yapıldığı için 6 veri setiyle iddia `inconclusive` kalır; 9 sette geçer. Bu yüzden demo varsayılanı dokuz setin tamamıdır.

Koşu 15 (`demo-grinsztajn-1`, Grinsztajn ve ark. 2022, arXiv 2207.08815; RandomForest, HistGradientBoosting, MLP, LogisticRegression; varsayılan hiperparametreler; dokuz benchmark seti; yalnız E2B, LLM yok) yaklaşık 4,5 dakikada `completed` bitti. Veri setleri 40-95 sn sürdü, yeniden deneme olmadı, izlenebilirlik sorunu çıkmadı. C1 (ağaçlar > MLP) ve C2 (ağaçlar > lineer) üç ölçütte de `replicated`, Holm düzeltmeli p = 0,0117. ROC-AUC Friedman sıraları: HistGradientBoosting 1,22, RandomForest 1,89, MLP 3,00, LogisticRegression 3,89. tb_eye'da MLP ağaçlardan belirgin geride; tb_pol'de MLP PR-AUC'de en iyiydi. Makaleden sapmalar raporda yazılıdır: hiperparametre araması yok, 6000 satırlık örnek, sklearn MLP (ResNet ve FT-Transformer yok), dokuz sayısal set, ağaç modeli olarak yalnız RandomForest ve HistGradientBoosting. Koşu raporun protokol bölümünde bir yanlış ifade çıkardı (parametre verilmemişken "yapılandırılmış model kontrolle koşar" diyordu); düzeltildi (`e1d2ad6`).

Sonra operasyonel izlenebilirlik eklendi: `app/campaign/tracking.py` kampanyayı MLflow'a yazar (`axiomforge-campaigns` deneyi, tek `Campaign Run {id}` üst run'ı, Friedman ve Wilcoxon p değerleri, iddia kararları, lider etiketleri, veri seti başına iç içe run'lar, `report.md` ve `ledger.json` artefaktları); Celery görevi ve `python -m app.campaign run --mlflow` açar, hata kampanyayı düşürmez. `GET /campaigns` artık `items` ile en yeni başta özet döner. Konsolda `/campaigns` ve `/campaign/{id}` sayfaları var (`remark-gfm` bağımlılığı eklendi). Doğrulama: pytest 1414 geçti, `tsc` ve `eslint` temiz, `next build` geçti, gerçek `demo-grinsztajn-1` verisiyle başsız Edge'de liste ve ayrıntı sayfası render edildi. Gerçek MLflow sunucusuna yazma yalnız geçici SQLite ile test edildi, sunucuya canlı denenmedi.

Faz 13 (ajanlı kampanya orkestrasyonu) kullanıcının kararlarıyla yapıldı: mod yalnız açıkça seçilir (`mode` `experiment` ya da `campaign`, `auto` yok), dağıtım iki düğümlü asenkron yapıdır (`campaign_dispatch_node` → durur → `campaign_collect_node`), onaya üç aday kampanya sunulur, makalenin Abstract, Results, Methodology, Limitations ve Conclusion bölümleri deterministiktir ve yalnız Introduction ile Discussion LLM'dendir, karar etiketi `Contradicted`'tır. Parçalar: `app/campaign/planning.py` (model eşleme, veri seti seçimi, güç kontrolü, süre tahmini), `app/agents/campaign_planner.py` (alıntı doğrulamalı üç aday, `unsupported`), `app/graph/campaign_nodes.py` (dispatch idempotent, collect, meta report, meta consistency), `app/agents/meta_report.py`, `app/campaign/meta_evidence.py` (atıflı cümleler), `app/agents/consistency_meta.py` (LLM'siz kapı), `app/campaign/memory.py` (hafıza yazma ve tekrar işaretleme). Celery zinciri: `run_campaign_task(campaign_id, spec, thread_id)` biter, `resume_campaign_task` grafı uyandırır ve graf toplama noktasına varmadıysa 5 sn arayla 40 kez yeniden dener; 20 dakika ilerlemeyen kampanya `failed` görünür. Test güvenliği: `tests/conftest.py` hem E2B anahtarını hem vektör hafızayı kapatır (hafıza koruması eklenmeden önce bir test Postgres'e bağlanıp asılı kalmıştı). Doğrulama: 1942 pytest testi geçti; her yeni modül mutasyonla sınandı (planlayıcı 66, grafik/dispatch 74, meta rapor 71, kapı 110 mutasyon), hayatta kalanlar test eklenerek kapatıldı ya da eşdeğer çıktı; konsolun mod seçimi ve kampanya onay penceresi sahte API ile başsız Edge'de uçtan uca denendi. Henüz gerçek LLM ve E2B ile uçtan uca koşu YAPILMADI (kullanıcı onayı bekleniyor): planlayıcı, Introduction ve Discussion yazımı gerçek gpt-4o ile denenmedi.

Açık işler: kampanya başlatma düğmesi konsolda yok (yalnız API ve komut satırı); `highest` ve `best` gibi üstünlük sözcükleri makale kapısında hâlâ denetlenmiyor; OpenAI kredisi ön kontrolü yok; `overall` yokken eski ROC-AUC lider kuralı duruyor. Öneri: ikinci bir iddia (örneğin başka bir makale) ve literatürden iddia çıkarma adımı.

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

Kampanya komut satırı yalnız `E2B_API_KEY` ister, Redis, Postgres ve MLflow gerekmez: `.\.venv\Scripts\python.exe -m app.campaign run --demo grinsztajn-2022 --id demo-grinsztajn-1`. Çıktı `reports/campaigns/demo-grinsztajn-1/` altına yazılır.

Konsol `http://localhost:3000` (`127.0.0.1:3000` adresinde Next dev sunucusu istemci kodunu çalıştırmaz). API `http://127.0.0.1:8000`. MLflow `http://127.0.0.1:5000`. Windows üzerinde Celery `--pool=threads` ile çalışır, `--pool=solo` tek görev yürütür. Postgres imajı `pgvector/pgvector:pg16` olur. Redis `redis://localhost:6379/0`.

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

Faz 9. `experiment-v8`. Parametre verilen her model `Model__default` kontrol girdisiyle birlikte koşar, doğrulayıcı kontrolü ana analizlerden çıkarır ve `parameter_effects` etkiyi kontrole karşı ölçer (`app/variants.py`).

Faz 10. `experiment-v9`. Veri sentetik değil, `app/datasets.py` kaydındaki beş doğrulanmış Hugging Face veri setinden biridir (`breast_cancer`, `credit_default`, `customer_churn`, `adult_income`, `credit_fraud`). Python her set için bir veri bloğu üretir, ajan bloğu aynen yapıştırır, AST denetimi (`dataset_code_error`) bunu zorunlu kılar ve sentetik yükleyicileri reddeder. Ön işleme `with_preprocessing` ile her modelin `Pipeline`'ında eğitim bölümüne uydurulur. Sandbox her koşudan önce `datasets` paketini kurar. Faz 5 ve Faz 7'deki `make_classification` anlatımı artık geçerli değildir.

Faz 11. Makale kapısı ve hazır cümleler (`app/graph/evidence.py`, `app/agents/consistency.py`): LLM'siz kontroller kararı verir, LLM hakem danışmandır. Ayrıntı `AI_CONTEXT.md` ve `README.md` içindedir.

Faz 12. Replikasyon kampanyası (`app/campaign/`). Yayımlanmış bir iddia çok veri setinde LLM'siz sınanır, kanıt defteri ve izlenebilir rapor üretilir. Ayrıntı yukarıda ve `README.md` içindedir.

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
| Deney promptu | `app/agents/experiment.py`, sürüm `experiment-v9` |
| Deney spesifikasyonu | `app/agents/spec.py` |
| Kontrol grubu adlandırması | `app/variants.py` |
| Hugging Face veri seti kaydı ve veri bloğu | `app/datasets.py` |
| Planlayıcı | `app/agents/planner.py` |
| Rapor promptu | `app/agents/report.py` |
| İddia hakemi | `app/agents/consistency.py` |
| Metrik ayrıştırma ve MLflow | `app/tracking/mlflow_logger.py` |
| Sandbox | `app/sandbox/e2b_runner.py` |
| Hafıza | `app/memory/rag_memory.py` |
| Kampanya motoru | `app/campaign/` (`service.py` giriş noktası, `__main__.py` komut satırı) |
| Kampanya uçları ve görevi | `app/main.py` (`/start_campaign`, `/campaigns`, `/campaign/{id}`) ve `app/tasks.py` (`run_campaign_task`) |
| Kampanya çıktıları | `reports/campaigns/{id}/` (gitte yok) |
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
