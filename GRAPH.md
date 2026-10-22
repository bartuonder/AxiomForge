# Araştırma grafı

LangGraph akışı `app/graph/workflow.py` içinde kurulur. Her `/start_research` yeni bir `thread_id` ve `empty_research_state` ile başlar. Checkpoint'te o kimlik için kayıt varsa yazma yapılmaz. FastAPI isteği bitse de durum durur; arayüz `GET /research/{thread_id}` ile aynı kaydı okur.

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

`literature_node` sorguyu arXiv'de aratır. En ilgili 3 makalenin başlık ve özetini `literature_context` listesine yazar.

`planner_node` literatürü ve RAG hafızasındaki başarısız deneyleri okur. Aynı hatayı tekrar etmeyen 3 hipotezi `hypotheses` listesine yazar.

`approval_gate` boş bir kapıdır. Graf burada bekler. `POST /approve_plan` kararı yazar.

`Y` ise `approval_status` `approved` olur ve akış devam eder. `N` ise `approval_status` `rejected` olur; deney, doğrulayıcı ve rapor çalışmaz.

`experiment_node` ilk hipotezi Faz 1 döngüsüne verir. Ajan `experiment-v5` ile kod yazar. Betikte yalnız `query` içinde açıkça adı geçen modeller vardır. Promptta varsayılan model yoktur. `models` sözlüğünün anahtarları bu listeyle aynıdır. Hipotez yeni model ekleyemez. Sorguda model adı yoksa deney başlamaz. Veri döngünün dışında bir kez ve sabit tohumla gelir. `make_classification` için `class_sep` en fazla 0.5'tir ve `weights` dengesizdir. Beşli döngü yalnız `train_test_split` `random_state` değerini 42, 100, 200, 300 ve 400 yapar. CSV şeması `age`, `monthly_spend`, `tenure_months`, `churn` kolonlarıdır. Çalışan kod `current_experiment_code` alanına, ilk modelin Accuracy ve F1 değerleri `experiment_metrics` alanına, satırlar `model_results` alanına, bu koşunun model adları `tested_models` alanına, veri profili `dataset_profile` alanına yazılır. Doğrulayıcıdan eleştiri gelmişse yeni kod üretmek yerine mevcut kodu o eleştiriyle düzeltir.

`verifier_node` iki kontrol yapar.

1. Betik her model için beş satır bastıysa o satırlar kullanılır. Bastıysa değil, yalnız `train_test_split` içindeki `random_state` 42, 100, 200, 300 ve 400 yapılır. Veri üretim tohumu ve model tohumu değişmez. Her model için Accuracy, F1, ROC-AUC, PR-AUC ve eğitim süresinin ortalaması, standart sapması ve varyansı NumPy ile hesaplanır. Varyans, standart sapmanın karesidir ve `{metrik}_variance` anahtarına yazılır. `statistical_conclusion` aynı sözlüğe Python tarafından yazılır. Karar ROC-AUC üzerindedir ve istatistik testine dayanır: her model çifti eşleştirilmiş bölmeler üzerinde Pitman-Morgan varyans testiyle karşılaştırılır, p değerleri Holm ile düzeltilir, alfa 0.05'tir. Bir model her rakibine karşı anlamlı biçimde düşük varyanslıysa o model daha kararlı ilan edilir. Aksi halde cümle beraberliktir ve eşdeğerlik iddia etmez. Üç bölmeden azı, tek model veya eşit olmayan seri uzunluğu `none` verir ve cümle boştur. Karar `statistical_decision` alanına da yapısal yazılır: `outcome` (`tie`, `winner`, `none`), `winner`, `metric`, `test`, `alpha`, `n_splits`, `min_adjusted_p` ve çift başına `comparisons`. `performance` alanı her çift ve ROC-AUC, PR-AUC, F1 için eşleştirilmiş farka uygulanan Nadeau-Bengio düzeltmeli t-testini taşır: `mean_difference`, `effect_size_dz`, `p_value`, `adjusted_p_value`, `significant`. Cümle İngilizcedir. ROC-AUC veya F1 standart sapması 0.05'i geçerse sonuç `Kararsız (Unstable)` sayılır.
2. Kodu veri sızıntısı için okur. Ayrılmadan önce imputation veya `fit_transform` varsa sebebiyle `Failed` döner.

İkisi de temizse `verification_status` `Passed` olur. Değilse `Failed` olur ve sebep `verifier_feedback` alanına yazılır.

`critic_continue` doğruysa ve `critic_rounds` 2'den küçükse akış `experiment_node`'a döner. İkinci düzeltmeden sonra doğrulayıcı hâlâ reddederse deney `is_success=False` ile hafızaya yazılır ve rapor düğümüne geçilir.

`report_node` literatür, hipotez, son kod, metrik, doğrulayıcı durumu ve hafızadaki hata metinlerinden bir atölye makalesi yazar. RAG kaydının kodu ve metriği prompta girmez. Başlıklar Abstract, Introduction, Methodology, Results, Conclusion şeklindedir. Results tablosu `statistical_results` içindeki ortalama ve standart sapmadır. Raporun veriyi yorumlama veya kazanan seçme yetkisi yoktur. Makale İngilizce yazılır. Results ve Conclusion `statistical_decision` yönünde yazılır; cümle aynen kopyalanmak zorunda değildir ama yönü değişmez ve karar dışında yorum eklenmez. `statistical_conclusion` tablo satırı değildir. Dosya `reports/{thread_id}_paper.md` olur. Metin `paper_markdown` alanına da yazılır. Graf burada bitmez.

`consistency_checker_node` makaleyi, `statistical_results` sözlüğünü ve `statistical_decision` alanını okur. LLM çağrısından önce Python bakar: `outcome` `tie` iken olumsuzlama içermeyen bir cümlede `superior`, `more stable`, `outperformed` veya `better` geçiyorsa hakem çalışmaz. Geri bildirim `Yön Çelişkisi: İstatistiksel fark yokken üstünlük iddia edildi` olur. Bu kapı temizse hakem sayı uyuşmazlığına, makalenin karara aykırı bir kazanan yazıp yazmadığına ve yalnız ROC-AUC övgüsüne bakar. `outcome` `winner` iken makale kazananı adlandırmıyorsa veya fark olmadığını yazıyorsa bu da tutarsızlıktır. Makale `performance` içinde `significant` olmayan bir karşılaştırma için metrik farkı iddia ediyorsa bu da tutarsızlıktır. Hakem üstünlüğü kendisi seçmez. Tutarsızlık `consistency_feedback` alanına yazılır. `consistency_rounds` 2'den küçükse akış `report_node`'a döner ve makale bu eleştiriyle yeniden yazılır. Kontrol temizse `research_status` `Completed` olur. İki yeniden yazmadan sonra da tutarsızlık sürerse `NeedsReview` olur. İki durumda da graf biter.

## Durum

`AgentState` alanları `app/graph/state.py` içindedir.

| Alan | Anlamı |
| --- | --- |
| `query` | Araştırma konusu |
| `literature_context` | Makale başlığı ve özeti |
| `hypotheses` | Üç test edilebilir hipotez |
| `approval_status` | `approved` veya `rejected` |
| `current_experiment_code` | Son çalışan Python kodu |
| `experiment_metrics` | İlk modelin Accuracy ve F1 değeri |
| `model_results` | Bu koşunun model satırları. Bölme döngüsü varsa model başına beş satır |
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
