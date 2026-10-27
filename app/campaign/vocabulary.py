from typing import Any

LANGUAGES = ("tr", "en")

MODEL_NAMES: dict[str, dict[str, str]] = {
    "tr": {
        "LinearSVC": "Doğrusal SVM",
        "SVM": "SVM (çekirdekli)",
        "RandomForest": "Random Forest",
        "ExtraTrees": "Extra Trees",
        "LogisticRegression": "Lojistik regresyon",
        "DecisionTree": "Karar ağacı",
        "GradientBoosting": "Gradient Boosting",
        "HistGradientBoosting": "Histogram Gradient Boosting",
        "XGBoost": "XGBoost",
        "LightGBM": "LightGBM",
        "CatBoost": "CatBoost",
        "KNN": "En yakın komşu (KNN)",
        "GaussianNB": "Naive Bayes",
        "MLP": "Yapay sinir ağı (MLP)",
        "AdaBoost": "AdaBoost",
        "QDA": "QDA",
        "LDA": "Doğrusal ayırtaç analizi (LDA)",
    },
    "en": {
        "LinearSVC": "Linear SVM",
        "SVM": "SVM (kernel)",
        "RandomForest": "Random forest",
        "ExtraTrees": "Extra trees",
        "LogisticRegression": "Logistic regression",
        "DecisionTree": "Decision tree",
        "GradientBoosting": "Gradient boosting",
        "HistGradientBoosting": "Histogram gradient boosting",
        "XGBoost": "XGBoost",
        "LightGBM": "LightGBM",
        "CatBoost": "CatBoost",
        "KNN": "Nearest neighbours (KNN)",
        "GaussianNB": "Naive Bayes",
        "MLP": "Neural network (MLP)",
        "AdaBoost": "AdaBoost",
        "QDA": "QDA",
        "LDA": "Linear discriminant analysis (LDA)",
    },
}

DATASET_NAMES: dict[str, dict[str, str]] = {
    "tr": {
        "breast_cancer": "Göğüs kanseri teşhisi",
        "credit_default": "Kredi kartı temerrüdü (Tayvan)",
        "customer_churn": "Telekom müşteri kaybı",
        "adult_income": "Gelir düzeyi (ABD nüfus sayımı)",
        "credit_fraud": "Kredi kartı sahteciliği",
        "tb_credit": "Kredi riski",
        "tb_california": "Kaliforniya konut fiyatları",
        "tb_electricity": "Elektrik piyasası fiyat yönü",
        "tb_magic": "Gama ışını teleskobu (MAGIC)",
        "tb_bank": "Banka pazarlama kampanyası",
        "tb_heloc": "Konut kredisi riski (HELOC)",
        "tb_house16h": "Konut fiyatları (house 16H)",
        "tb_pol": "Telekomünikasyon verisi (pol)",
        "tb_eye": "Okurken göz hareketleri",
    },
    "en": {
        "breast_cancer": "Breast cancer diagnosis",
        "credit_default": "Credit card default (Taiwan)",
        "customer_churn": "Telecom customer churn",
        "adult_income": "Income level (US census)",
        "credit_fraud": "Credit card fraud",
        "tb_credit": "Credit risk",
        "tb_california": "California house prices",
        "tb_electricity": "Electricity price direction",
        "tb_magic": "Gamma-ray telescope (MAGIC)",
        "tb_bank": "Bank marketing campaign",
        "tb_heloc": "Home equity credit risk (HELOC)",
        "tb_house16h": "House prices (house 16H)",
        "tb_pol": "Telecommunication data (pol)",
        "tb_eye": "Eye movements while reading",
    },
}

METRIC_LABELS: dict[str, dict[str, dict[str, str]]] = {
    "tr": {
        "roc_auc": {"name": "ROC-AUC", "meaning": "Modelin iki sınıfı ne kadar iyi ayırdığı (1,0 kusursuz, 0,5 yazı-tura)."},
        "pr_auc": {"name": "PR-AUC", "meaning": "Az görülen sınıfı bulma başarısı; dengesiz verilerde önemlidir."},
        "f1": {"name": "F1", "meaning": "Doğru bulma ve kaçırmama dengesi tek bir sayıda."},
    },
    "en": {
        "roc_auc": {"name": "ROC-AUC", "meaning": "How well the model separates the two classes (1.0 perfect, 0.5 coin flip)."},
        "pr_auc": {"name": "PR-AUC", "meaning": "How well the rarer class is found; matters for unbalanced data."},
        "f1": {"name": "F1", "meaning": "The balance between being right and not missing cases, in one number."},
    },
}

VERDICTS: dict[str, dict[str, Any]] = {
    "replicated": {
        "tone": "positive",
        "tr": {"label": "Doğrulandı", "meaning": "İddia, test edilen veri setlerinde tutarlı biçimde doğru çıktı."},
        "en": {"label": "Confirmed", "meaning": "The claim held consistently across the datasets that were tested."},
    },
    "contradicted": {
        "tone": "negative",
        "tr": {"label": "Çürütüldü", "meaning": "İddianın tersi doğru çıktı."},
        "en": {"label": "Refuted", "meaning": "The opposite of the claim turned out to be true."},
    },
    "inconclusive": {
        "tone": "neutral",
        "tr": {"label": "Kanıt yetersiz", "meaning": "İki yönde de net bir fark gösterilemedi; modeller yakın olabilir ya da veri azdır."},
        "en": {"label": "Not enough evidence", "meaning": "No clear difference could be shown in either direction; the models may be close or the data too small."},
    },
    "partially_replicated": {
        "tone": "warning",
        "tr": {"label": "Kısmen doğrulandı", "meaning": "İddia bazı ölçütlerde doğru, bazılarında doğrulanamadı."},
        "en": {"label": "Partly confirmed", "meaning": "The claim held on some measures but could not be confirmed on others."},
    },
    "not_testable": {
        "tone": "muted",
        "tr": {"label": "Test edilemedi", "meaning": "Yeterli sayıda veri seti bitmediği için güvenilir bir test yapılamadı."},
        "en": {"label": "Could not be tested", "meaning": "Too few datasets finished, so no reliable test was possible."},
    },
}

STATUS_LABELS: dict[str, dict[str, str]] = {
    "tr": {
        "queued": "Sırada",
        "running": "Çalışıyor",
        "completed": "Tamamlandı",
        "needs_review": "İnceleme gerekli",
        "failed": "Başarısız",
    },
    "en": {
        "queued": "Queued",
        "running": "Running",
        "completed": "Completed",
        "needs_review": "Needs review",
        "failed": "Failed",
    },
}

GLOSSARY: dict[str, dict[str, dict[str, str]]] = {
    "tr": {
        "campaign": {"term": "Kampanya", "explanation": "Bir iddianın tek bir deneyle değil, birçok veri setinde toplu olarak sınanması."},
        "claim": {"term": "İddia", "explanation": "Sınanan cümle; örneğin 'ağaç tabanlı modeller sinir ağlarından daha iyidir'."},
        "dataset": {"term": "Veri seti", "explanation": "Modellerin denendiği gerçek bir veri tablosu. Ne kadar çok veri setinde aynı sonuç çıkarsa iddia o kadar güvenilirdir."},
        "verdict": {"term": "Karar", "explanation": "İddianın sonucu: doğrulandı, çürütüldü, kanıt yetersiz, kısmen doğrulandı ya da test edilemedi."},
        "roc_auc": {"term": "ROC-AUC", "explanation": "Modelin iki sınıfı ayırma başarısı; 1,0 kusursuz, 0,5 rastgele tahmin demektir."},
        "pr_auc": {"term": "PR-AUC", "explanation": "Az görülen sınıfı bulma başarısı; dengesiz verilerde ROC-AUC'yi tamamlar."},
        "f1": {"term": "F1", "explanation": "Doğru bulma ve kaçırmama dengesini tek sayıda gösteren ölçüt."},
        "tuned": {"term": "Ayarlı", "explanation": "Modelin ayarları (hiperparametreler) rastgele aramayla optimize edildi. Ayarsız model, kütüphanenin varsayılan ayarlarıyla çalışır."},
        "wilcoxon": {"term": "Wilcoxon testi", "explanation": "İki modelin veri setleri üzerindeki farkının şans eseri olup olmadığını denetleyen istatistik testi."},
        "holm": {"term": "Holm düzeltmesi", "explanation": "Aynı anda birçok karşılaştırma yapılınca şans eseri 'anlamlı' sonuç çıkma riskini azaltan düzeltme."},
        "sandbox": {"term": "Sandbox", "explanation": "Deneylerin güvenli, yalıtılmış bir uzak bilgisayarda çalıştırılması."},
        "evidence": {"term": "Kanıt kaydı", "explanation": "Rapordaki her sayının dayandığı kayıt; [E1], [E2] gibi numaralanır."},
        "confidence": {"term": "Güven", "explanation": "Sonucun ne kadar sağlam olduğu: kaç veri setinde ve kaç ölçütte aynı yönde çıktığına bakılır."},
    },
    "en": {
        "campaign": {"term": "Campaign", "explanation": "Testing a claim in bulk across many datasets instead of one single experiment."},
        "claim": {"term": "Claim", "explanation": "The sentence under test, for example 'tree-based models beat neural networks'."},
        "dataset": {"term": "Dataset", "explanation": "A real data table the models were tried on. The more datasets show the same result, the more reliable the claim."},
        "verdict": {"term": "Verdict", "explanation": "The outcome of the claim: confirmed, refuted, not enough evidence, partly confirmed or could not be tested."},
        "roc_auc": {"term": "ROC-AUC", "explanation": "How well a model separates the two classes; 1.0 is perfect and 0.5 is random guessing."},
        "pr_auc": {"term": "PR-AUC", "explanation": "How well the rarer class is found; it complements ROC-AUC on unbalanced data."},
        "f1": {"term": "F1", "explanation": "A measure that combines being right and not missing cases in one number."},
        "tuned": {"term": "Tuned", "explanation": "The model's settings (hyperparameters) were optimised by random search. An untuned model uses the library defaults."},
        "wilcoxon": {"term": "Wilcoxon test", "explanation": "A statistical test that checks whether the difference between two models across datasets could be chance."},
        "holm": {"term": "Holm correction", "explanation": "A correction that lowers the risk of a chance 'significant' result when many comparisons are made at once."},
        "sandbox": {"term": "Sandbox", "explanation": "Running the experiments on a safe, isolated remote computer."},
        "evidence": {"term": "Evidence record", "explanation": "The record behind each number in the report; they are numbered [E1], [E2] and so on."},
        "confidence": {"term": "Confidence", "explanation": "How solid the result is: it looks at how many datasets and measures agree on the direction."},
    },
}


def pretty_model(key: str, language: str) -> str:
    return MODEL_NAMES[language].get(key, key)


def pretty_dataset(key: str, language: str) -> str:
    return DATASET_NAMES[language].get(key, key)
