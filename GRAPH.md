# Araştırma grafı

LangGraph akışı `app/graph/workflow.py` içinde kurulur. Her `/start_research` yeni bir `thread_id` ve `empty_research_state` ile başlar. Checkpoint'te o kimlik için kayıt varsa yazma yapılmaz. Graf API sürecinde değil Celery işçisinde çalışır: `POST /start_research` ve `POST /approve_plan` işi kuyruğa atar (`app/tasks.py`), işçi `run_until_pause` ve `resume_research` fonksiyonlarını yürütür. Durum checkpoint'te durur; arayüz `GET /research/{thread_id}` ile aynı kaydı okur. Onay verildikten sonra işçi devralana kadar durum `running` sayılır.

## Sıra

```text
START
  -> literature_node
  -> planner_node
  -> approval_gate          (burada durur)
  -> experiment_node
  -> verifier_node
       -> experiment_node   (eleştiri, en fazla 2 kez)
       -> report_node       (Passed veya eleştiri hakkı bitmiş Failed)
  -> consistency_checker_node
       -> report_node    (iddia tutarsız, en fazla 2 kez)
  -> END
```

`approval_gate` öncesinde `interrupt_before` vardır. İnsan kararı gelmeden deney başlamaz. Eleştiri turları bu kapıya uğramaz; onay bir kez verilir.

## Düğümler

`literature_node` LLM ile sorudan en fazla 3 anahtar kelime araması üretir ve her birini arXiv'de tırnaklı ifadeler arasında `AND` ile aratır. Adayları sorunun gömüsüyle kosinüs benzerliğine göre puanlar, `0.35` altını eler ve en alakalı 3 makalenin `başlık: özet` metnini `literature_context` listesine yazar. Metni LLM değil Python kurar. Alakalı makale yoksa çalışma hata verir.

`planner_node` literatürü ve RAG hafızasındaki başarısız deneyleri okur. Aynı hatayı tekrar etmeyen 3 hipotezi `hypotheses` listesine yazar. Her hipotez deney ajanının yapabildiği bir spesifikasyondur ve `experiment_specs` listesine yazılır: `statement`, `models` (sorgudaki modellerin tamamı), `dataset` (`breast_cancer` veya `imbalanced`) ve `params` (model başına izinli kurucu parametreleri). Model adı, parametre adı ve veri seti Python'da doğrulanır. Geçersizse planlayıcıya bir kez hata gösterilir ve yeniden denenir.

`approval_gate` boş bir kapıdır. Graf burada bekler. `POST /approve_plan` kararı yazar; `Y` ise `selected` ile çalıştırılacak hipotezi `selected_hypothesis` alanına yazar ve devamı Celery'ye atar. Seçim olmadan `Y` kabul edilmez. Karar bir kez verilir.

`Y` ise `approval_status` `approved` olur ve akış devam eder. `N` ise `approval_status` `rejected` olur; deney, doğrulayıcı ve rapor çalışmaz.

`experiment_node` onayda seçilen hipotezi (`selected_hypothesis`) ve `experiment_specs` içindeki spesifikasyonunu Faz 1 döngüsüne verir. Ajan `experiment-v7` ile kod yazar. Üretilen kod AST ile denetlenir: spesifikasyondaki veri seti çağrısı bulunmalı, öteki veri seti çağrısı bulunmamalı ve `params` değerleri ilgili kurucuda sabit olarak yazılmış olmalıdır. Aksi halde hata deneme mekanizmasıyla düzeltilir. Betikte yalnız `query` içinde açıkça adı geçen modeller vardır. Promptta varsayılan model yoktur. `models` sözlüğünün anahtarları bu listeyle aynıdır. Hipotez yeni model ekleyemez. Sorguda model adı yoksa deney başlamaz. Veri döngünün dışında bir kez ve sabit tohumla gelir. `make_classification` için `class_sep` en fazla 0.5'tir ve `weights` dengesizdir. Döngü yalnız `train_test_split` `random_state` değerini sırayla 42, 100, 200, 300, 400, 500, 600, 700, 800 ve 900 yapar (on bölme). Her `train_test_split` çağrısı `stratify=y` alır. AST bunu zorunlu kılar: `train_test_split` hiç yoksa veya bir çağrı `stratify` almıyorsa kod sandbox'a gitmeden düzeltilir. CSV şeması `age`, `monthly_spend`, `tenure_months`, `churn` kolonlarıdır. Çalışan kod `current_experiment_code` alanına, ilk modelin Accuracy ve F1 değerleri `experiment_metrics` alanına, satırlar `model_results` alanına, bu koşunun model adları `tested_models` alanına, veri profili `dataset_profile` alanına yazılır. Doğrulayıcıdan eleştiri gelmişse yeni kod üretmek yerine mevcut kodu o eleştiriyle düzeltir.

`verifier_node` iki kontrol yapar.

1. Betik her model için on satır bastıysa o satırlar kullanılır. Bastıysa değil, yalnız `train_test_split` içindeki `random_state` 42, 100, 200, 300, 400, 500, 600, 700, 800 ve 900 yapılır (on ayrı sandbox koşusu). Sandbox koşusu için süre iki katına çıkarıldı: kod en çok 240 saniye çalışır, kutu 300 saniye yaşar. Veri üretim tohumu ve model tohumu değişmez. Her model için Accuracy, F1, ROC-AUC, PR-AUC ve eğitim süresinin ortalaması, standart sapması ve varyansı NumPy ile hesaplanır. Varyans, standart sapmanın karesidir ve `{metrik}_variance` anahtarına yazılır. `statistical_conclusion` aynı sözlüğe Python tarafından yazılır. Karar ROC-AUC üzerindedir ve istatistik testine dayanır: her model çifti eşleştirilmiş bölmeler üzerinde Pitman-Morgan varyans testiyle karşılaştırılır, p değerleri Holm ile düzeltilir, alfa 0.05'tir. Bir model her rakibine karşı anlamlı biçimde düşük varyanslıysa o model daha kararlı ilan edilir. Aksi halde cümle beraberliktir ve eşdeğerlik iddia etmez. Üç bölmeden azı, tek model veya eşit olmayan seri uzunluğu `none` verir ve cümle boştur. Karar `statistical_decision` alanına da yapısal yazılır: `outcome` (`tie`, `winner`, `none`), `winner`, `metric`, `test`, `alpha`, `n_splits`, `min_adjusted_p` ve çift başına `comparisons`. `performance` alanı her çift ve ROC-AUC, PR-AUC, F1 için eşleştirilmiş farka uygulanan Nadeau-Bengio düzeltmeli t-testini taşır: `mean_difference`, `effect_size_dz`, `p_value`, `adjusted_p_value`, `significant`. Cümle İngilizcedir. ROC-AUC veya F1 standart sapması 0.05'i geçerse bu `statistical_decision["instability"]` bulgusuna yazılır: `unstable`, `std_threshold` ve model ile metrik başına `flagged`. Bulgu ret nedeni değildir.
2. Kodu veri sızıntısı için okur. Ayrılmadan önce imputation veya `fit_transform` varsa sebebiyle `Failed` döner.

İkisi de temizse `verification_status` `Passed` olur. Metrik üretilmemesi, sandbox çökmesi veya sızıntı varsa `Failed` olur ve sebep `verifier_feedback` alanına yazılır. Yüksek varyans `Failed` yapmaz.

MLflow kaydı doğrulayıcıda bir kez açılır. `Passed` ise `Verified` üst run'ına veri profili, her model için `{model}/{metrik}_mean`, `_std`, `_variance`, `min_adjusted_p`, `unstable`, anlamlı performans farkı sayısı, `outcome` ve `winner` etiketleri yazılır. Her bölme `seed`, `split_index` ve metrikleriyle iç içe run olur. Tohum bölme sırasından çıkarılır: 42, 100, 200, 300, 400, 500, 600, 700, 800, 900. Eleştiri hakkı bitip `Failed` kalırsa `Failed` run açılır. Kimlik `mlflow_run_id` alanına yazılır.

`critic_continue` doğruysa ve `critic_rounds` 2'den küçükse akış `experiment_node`'a döner. İkinci düzeltmeden sonra doğrulayıcı hâlâ reddederse deney `is_success=False` ve `outcome=failure` ile hafızaya yazılır ve rapor düğümüne geçilir. Hafıza kaydı grafta yalnız burada ve doğrulama `Passed` olduğunda yazılır; deney düğümü yazmaz. Kayıt, onaylanan spesifikasyonun `statement` metnini, `spec` alanını ve doğrulayıcının ortalama ± standart sapma özetini taşır. `Passed` olan koşu `outcome=success` ile, `instability.unstable` doğruysa `outcome=finding` ve `finding` metniyle yazılır, ikisinde de `is_success` doğrudur. Deney üç denemede de çalışmadıysa son hata `experiment_error` alanında taşınır ve doğrulayıcının mesajına girer.

`report_node` literatür, hipotez, son kod, metrik, doğrulayıcı durumu ve hafızadaki hata metinlerinden bir atölye makalesi yazar. RAG kaydının kodu ve metriği prompta girmez. Başlıklar Abstract, Introduction, Methodology, Results, Conclusion şeklindedir. Results tablosu `statistical_results` içindeki ortalama ve standart sapmadır. `instability.unstable` doğruysa işaretli modeller std değeriyle Results'a girer ve Conclusion'da limitasyon olarak yazılır. Raporun veriyi yorumlama veya kazanan seçme yetkisi yoktur. Makale İngilizce yazılır. Results ve Conclusion `statistical_decision` yönünde yazılır; cümle aynen kopyalanmak zorunda değildir ama yönü değişmez ve karar dışında yorum eklenmez. `statistical_conclusion` tablo satırı değildir. Dosya `reports/{thread_id}_paper.md` olur. Metin `paper_markdown` alanına da yazılır. Graf burada bitmez.

`consistency_checker_node` makaleyi, `statistical_results` sözlüğünü ve `statistical_decision` alanını okur. LLM çağrısından önce Python bakar: `outcome` `tie` iken olumsuzlama içermeyen bir cümlede üstünlük iddiası geçiyorsa hakem çalışmaz. İddia `superior` ve `superiority`, `more stable`, `outperform` biçimleri, `better than`, `performs better`, `is better`, `better performance` ve `the better model` gibi karşılaştırma kalıplarıdır. `to better understand` gibi karşılaştırma olmayan kullanım sayılmaz. Geri bildirim `Yön Çelişkisi: İstatistiksel fark yokken üstünlük iddia edildi` olur. Bu kapı temizse hakem sayı uyuşmazlığına, makalenin karara aykırı bir kazanan yazıp yazmadığına ve yalnız ROC-AUC övgüsüne bakar. `outcome` `winner` iken makale kazananı adlandırmıyorsa veya fark olmadığını yazıyorsa bu da tutarsızlıktır. Makale `performance` içinde `significant` olmayan bir karşılaştırma için metrik farkı iddia ediyorsa bu da tutarsızlıktır. Doğrulama `Failed` ise makale bunu gizleyemez: yazıcıya Abstract içinde `failed verification` ifadesini ve nedenini İngilizce yazması, Results'ı sayıların doğrulanmadığını söyleyen bir paragrafla açması ve hiçbir modeli kanıtlanmış üstün ilan etmemesi söylenir. Hakem LLM'den bağımsız olarak Abstract bölümünde bu ifadeyi (veya `unverified`, `not been verified`, `verification ... failed` gibi eşdeğerlerini) arar; yoksa makale yeniden yazılır, iki yeniden yazmadan sonra da yoksa `NeedsReview` olur. Kararsızlık bulgusu (`instability.unstable`) varsa hakem ayrıca LLM'siz iki şeye bakar: Abstract bulguyu anıyor mu (`high variance across splits`, `unstable`, `instability`, `large standard deviation`, `exceeds the threshold`, `sensitive to the data split` gibi kalıplar kabul edilir) ve işaretlenen her model için tablo dışında o modeli ve kararsızlığı birlikte anan bir cümle var mı. Model adı boşluk ve büyük-küçük harften bağımsız eşleşir. Eksikse makale yeniden yazılır, iki yeniden yazmadan sonra da eksikse `NeedsReview` olur. Yazıcıya özette bu ifadeyi kullanması ve `Passed` sonucunu sonuçların güvenilir olduğunun kanıtı gibi anlatmaması söylenir. İki LLM'siz kontrol daha vardır. `reliability_issue`: doğrulama `Passed` iken doğrulamadan söz eden bir cümlede `reliab*`, `robust*`, `trustworth*`, `credib*` veya `guarantee*` geçiyorsa makale geri gider; olumsuzlama yalnız güvenilirlik sözcüğünden hemen önce (en çok dört kelime) gelirse sayılır, çünkü cümledeki başka bir `no` iddiayı iptal etmez. `performance_issues`: `statistical_decision["performance"]` içinde `significant` olan her satır için makalede tablo dışında, olumsuzlama ve kararlılık sözcüğü içermeyen ve metriği (ROC-AUC, PR-AUC, F1) bir fark sözcüğüyle (`significant`, `higher`, `lower` gibi) anan bir cümle bulunmalı ve etki büyüklüğü (`effect_size_dz`, 0.006 toleransla) metinde geçmelidir. Yazıcıya `Passed` iken özette ve sonuçta doğrulamadan hiç söz etmemesi, Methodology'de tek cümleyle sızıntı ve çalıştırma hatası bulunmadığını yazması ve her anlamlı satırı Results'ta yön, düzeltilmiş p ve `dz` ile yazması söylenir. Hakem üstünlüğü kendisi seçmez. Tutarsızlık `consistency_feedback` alanına yazılır. `consistency_rounds` 2'den küçükse akış `report_node`'a döner ve makale bu eleştiriyle yeniden yazılır. Kontrol temizse `research_status` `Completed` olur. İki yeniden yazmadan sonra da tutarsızlık sürerse `NeedsReview` olur. İki durumda da graf biter.

## Durum

`AgentState` alanları `app/graph/state.py` içindedir.

| Alan | Anlamı |
| --- | --- |
| `query` | Araştırma konusu |
| `literature_context` | Makale başlığı ve özeti |
| `hypotheses` | Üç test edilebilir hipotezin `statement` metni |
| `selected_hypothesis` | Onayda seçilen hipotezin sırası (0'dan). Deney, hafıza kaydı, MLflow ve rapor yalnız bunu kullanır |
| `experiment_specs` | Aynı hipotezlerin doğrulanmış spesifikasyonları: `statement`, `models`, `dataset`, `params` |
| `approval_status` | `approved` veya `rejected` |
| `current_experiment_code` | Son çalışan Python kodu |
| `experiment_error` | Deney üç denemede de çalışmadıysa son hata metni |
| `experiment_metrics` | İlk modelin Accuracy ve F1 değeri |
| `model_results` | Bu koşunun model satırları. Bölme döngüsü varsa model başına on satır |
| `tested_models` | Yalnız bu koşuda adı geçen modeller |
| `dataset_profile` | Veri seti adı, örnek, öznitelik ve sınıf oranları |
| `statistical_results` | Model başına ortalama, standart sapma, varyans ve `statistical_conclusion` |
| `statistical_decision` | Kararlılık hükmü ve testler: `outcome`, `winner`, `metric`, `test`, `alpha`, `n_splits`, `min_adjusted_p`, `comparisons`, `performance` |
| `verification_status` | `Passed` veya `Failed` |
| `verifier_feedback` | Eleştiri metni |
| `critic_rounds` | Doğrulayıcıdan deneye dönüş sayısı |
| `critic_continue` | Bir sonraki adımın deney olması |
| `paper_markdown` | Son yazılan makale |
| `consistency_feedback` | Hakemin tutarsızlık listesi |
| `consistency_rounds` | Rapora geri dönüş sayısı |
| `consistency_continue` | Bir sonraki adımın rapor olması |
| `research_status` | İddia kontrolü temizse `Completed`, tutarsızlık sürerse `NeedsReview` |

## Kalıcılık

Checkpoint'ler `PostgresSaver` ile `DATABASE_URL` veritabanına yazılır. Deney özetlerinin gömüleri aynı Postgres'te `pgvector` koleksiyonu `experiment_memory` içindedir. İki kayıt ayrıdır: biri grafın anlık durumu, diğeri geçmiş deneylerin arama hafızasıdır.

Bir düğüm hata verirse mesaj aynı veritabanındaki `research_errors` tablosuna `thread_id` ile yazılır. `GET /research/{thread_id}` bu kaydı okur ve durumu `failed` yapar. `/start_research` sorguda model adı yoksa grafı hiç başlatmaz.
