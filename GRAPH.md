# Araştırma grafı

LangGraph akışı `app/graph/workflow.py` içinde kurulur. Her araştırma bir `thread_id` ile PostgreSQL checkpoint'ine yazılır. FastAPI isteği bitse de durum durur; arayüz `GET /research/{thread_id}` ile aynı kaydı okur.

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
  -> END
```

`approval_gate` öncesinde `interrupt_before` vardır. İnsan kararı gelmeden deney başlamaz. Eleştiri turları bu kapıya uğramaz; onay bir kez verilir.

## Düğümler

`literature_node` sorguyu arXiv'de aratır. En ilgili 3 makalenin başlık ve özetini `literature_context` listesine yazar.

`planner_node` literatürü ve RAG hafızasındaki başarısız deneyleri okur. Aynı hatayı tekrar etmeyen 3 hipotezi `hypotheses` listesine yazar.

`approval_gate` boş bir kapıdır. Graf burada bekler. `POST /approve_plan` kararı yazar.

`Y` ise `approval_status` `approved` olur ve akış devam eder. `N` ise `approval_status` `rejected` olur; deney, doğrulayıcı ve rapor çalışmaz.

`experiment_node` ilk hipotezi Faz 1 döngüsüne verir. CSV şeması `age`, `monthly_spend`, `tenure_months`, `churn` kolonlarıdır. Çalışan kod `current_experiment_code`, Accuracy ve F1 `experiment_metrics` alanına yazılır. Doğrulayıcıdan eleştiri gelmişse yeni kod üretmek yerine mevcut kodu o eleştiriyle düzeltir.

`verifier_node` iki kontrol yapar.

1. `random_state`, `random_seed` ve `seed` değerlerini `9999` yapar ve kodu E2B'de yeniden çalıştırır. Accuracy veya F1 yüzde 10'dan fazla düşerse sonuç `Overfitting/Unstable` sayılır.
2. Kodu veri sızıntısı için okur. Ayrılmadan önce imputation veya `fit_transform` varsa sebebiyle `Failed` döner.

İkisi de temizse `verification_status` `Passed` olur. Değilse `Failed` olur ve sebep `verifier_feedback` alanına yazılır.

`critic_continue` doğruysa ve `critic_rounds` 2'den küçükse akış `experiment_node`'a döner. İkinci düzeltmeden sonra doğrulayıcı hâlâ reddederse deney `is_success=False` ile hafızaya yazılır ve rapor düğümüne geçilir.

`report_node` literatür, hipotez, son kod, metrik, doğrulayıcı durumu ve hafızadaki hatalardan bir atölye makalesi yazar. Başlıklar Abstract, Introduction, Methodology, Results, Conclusion şeklindedir. Dosya `reports/{thread_id}_paper.md` olur. `research_status` `Completed` yapılır ve graf biter.

## Durum

`AgentState` alanları `app/graph/state.py` içindedir.

| Alan | Anlamı |
| --- | --- |
| `query` | Araştırma konusu |
| `literature_context` | Makale başlığı ve özeti |
| `hypotheses` | Üç test edilebilir hipotez |
| `approval_status` | `approved` veya `rejected` |
| `current_experiment_code` | Son çalışan Python kodu |
| `experiment_metrics` | Accuracy ve F1 |
| `verification_status` | `Passed` veya `Failed` |
| `verifier_feedback` | Eleştiri metni |
| `critic_rounds` | Doğrulayıcıdan deneye dönüş sayısı |
| `critic_continue` | Bir sonraki adımın deney olması |
| `research_status` | Rapor bitince `Completed` |

## Kalıcılık

Checkpoint'ler `PostgresSaver` ile `DATABASE_URL` veritabanına yazılır. Deney özetlerinin gömüleri aynı Postgres'te `pgvector` koleksiyonu `experiment_memory` içindedir. İki kayıt ayrıdır: biri grafın anlık durumu, diğeri geçmiş deneylerin arama hafızasıdır.
