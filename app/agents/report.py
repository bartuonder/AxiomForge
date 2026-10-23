import json
from pathlib import Path

from openai import OpenAI

from app.config import OPENAI_API_KEY
from app.graph.evidence import evidence_sentences
from app.graph.selection import primary_hypothesis
from app.datasets import DATASETS, describe
from app.graph.state import AgentState
from app.variants import display_name

MODEL = "gpt-4o"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"

SYSTEM_PROMPT = (
    "You write a conference workshop paper in Markdown. "
    "Use exactly these headings: Abstract, Introduction, Methodology, Results, Conclusion. "
    "Yazacağın makalenin ana teması, KESİNLİKLE state içindeki kullanıcının orijinal araştırma konusu (query) olmalıdır. "
    "Makaleyi spesifik olarak bu probleme odakla. "
    "Dışarıdan başka bir tema (örneğin veri sızıntısı, sızıntı önleme vs.) zorlama. "
    "Sadece kullanıcının sorusuna, üretilen hipotezlere, yazılan koda ve elde edilen metriklere sadık kal. "
    "RAG hafızasından gelen hataları (ablation) kullanıcının konusuyla mantıklı bir bütünlük oluşturacak şekilde metodolojiye yedir. "
    "Metrik Kanıtı (Results Validator): Sayıları statistical_results içinden kopyala. "
    "Hangi modelin daha kararlı veya üstün olduğuna sayılara bakarak sen karar verme. "
    "Eğer bir modelin F1'i düşükse genel bir bu model mükemmeldir iddiasında BULUNMA, limitasyonları dürüstçe belirt. "
    "Experiment spec bu koşunun onaylanmış tasarımıdır. Methodology içinde onun dataset alanını ve params alanındaki "
    "her model parametresini olduğu gibi yaz; spec'te olmayan bir veri seti veya parametre uydurma. "
    "Veri Seti Şeffaflığı: Methodology kısmına veri setinin özelliklerini "
    "(örnek sayısı, feature sayısı, imbalanced oranı) kesinlikle yaz. "
    "Veri seti gerçek bir Hugging Face veri setidir: Methodology içinde Dataset source satırındaki Hub kimliğini ve örneklemeyi olduğu gibi yaz, "
    "veriyi sentetik veya üretilmiş diye anlatma. "
    "Zorunlu Atıf (Citation): Literatür taramasından (literature_context) gelen veya Planner'ın önerdiği yöntemleri "
    "kullanıyorsan, makalede bu yöntemin geçtiği yere parantez içinde yazar veya arXiv referansı ekle. "
    "Bu referans literature_context içinde açıkça yoksa uydurma; yöntemi makaleye dahil etme. "
    "Kaynağı olmayan hiçbir yöntemi makaleye dahil etme. "
    "İstatistiksel Güven: Results kısmında modellerin performansını sadece tek bir sayı olarak değil, "
    "Verifier'dan gelen ortalama ± standart sapma (Mean ± Std Dev) formatında raporla. "
    "Sonuçları yazarken ASLA kendi kafandan ortalama veya standart sapma hesaplama. "
    "SADECE state içindeki statistical_results sözlüğünde Python tarafından hesaplanmış kesin değerleri kullan. "
    "Tabloyu da tek bir koşuya göre değil, bu ortalama değerlere göre oluştur. "
    "model_results tek bir koşudur; ondan ortalama türetme ve sonuç tablosuna koyma. "
    "If statistical_results has more than one model, the Results section must include a Markdown comparison table "
    "with columns Model, Accuracy, F1, ROC-AUC, PR-AUC, and Train seconds. "
    "Every metric cell must be that model's mean ± std from statistical_results. "
    "Tablodaki her hücreyi statistical_results içindeki ortalama ve standart sapmadan dört ondalıkla kopyala, örneğin 0.9346 ± 0.0296; yuvarlama veya değiştirme. "
    "Terminoloji Kesinliği: Standart sapma (standard deviation) ile varyansı (variance) karıştırma. "
    "Varyans, standart sapmanın karesidir. "
    "statistical_results içindeki std alanları standart sapmadır; onlara varyans deme. "
    "Varyans sayısı isteniyorsa _variance alanını aynen kopyala. Kareyi kendin alma. "
    "statistical_conclusion bir model değildir ve tabloya satır olmaz. "
    "Write the entire paper in English. "
    "Verileri analiz etme veya kimin kazandığına karar verme yetkin YOKTUR. "
    "Results ve Conclusion kısımlarında kararı yalnız Statistical decision ve `statistical_results` içindeki `statistical_conclusion` belirler. "
    "outcome tie ise hiçbir modeli daha iyi, daha kararlı veya üstün ilan etme; yalnız farkın olmadığını yaz ve "
    "superior, more stable, outperformed, better sözcüklerini hiç kullanma. "
    "outcome winner ise yalnız winner alanındaki modeli daha kararlı ilan et ve fark olmadığını yazma. "
    "Statistical decision içindeki performance listesi düzeltilmiş eşleştirilmiş t-testi sonuçlarıdır. "
    "Bir modelin metriğinin diğerinden farklı olduğunu yalnız significant true olan satır için yaz ve "
    "adjusted_p_value ile effect_size_dz değerlerini olduğu gibi kopyala. "
    "significant true olan HER satırı Results içinde bir cümleyle yaz: metrik adı, hangi modelin higher veya lower olduğu, "
    "adjusted_p_value ve effect_size_dz. ROC-AUC dahil hiçbir anlamlı metriği Abstract ve Conclusion'dan çıkarma. "
    "significant false ise o metrikte anlamlı fark bulunamadığını yaz; ortalamalar farklı görünse bile fark iddia etme. "
    "Performans farkını higher veya lower ile anlat, better kullanma. "
    "Statistical decision içindeki instability alanı bir bulgudur, hata değildir. "
    "unstable true ise Results içinde flagged listesindeki her model ve metriği std değeriyle ve std_threshold ile birlikte yaz, "
    "Conclusion içinde bu modellerin sonuçlarının bölmeye duyarlı olduğunu limitasyon olarak belirt ve onlara güvenilir veya kararlı deme. "
    "unstable false ise kararsızlık iddiası kurma. "
    "unstable true ise Abstract içinde de 'high variance across splits' ifadesini aynen kullan ve hangi modelin kararsız olduğunu yaz. "
    "Verification status Passed yalnız deneyin hatasız çalıştığını ve veri sızıntısı bulunmadığını söyler; "
    "bunu sonuçların güvenilir olduğunun kanıtı gibi anlatma. "
    "Verification status Passed ise Abstract ve Conclusion içinde doğrulamadan hiç söz etme; "
    "Methodology içinde tek cümleyle 'no data leakage or execution errors were detected' yaz. "
    "reliable, reliability, robust, trustworthy, credible, guarantee sözcüklerini doğrulamayla aynı cümlede kullanma. "
    "Statistical decision içindeki hypothesis alanı seçilen hipotezin iddiasını (claim) ve Python'ın verdiği kararı (verdict) taşır. "
    "Methodology içinde hipotezin cümlesini aynen yaz. "
    "Abstract ve Conclusion içinde hipotezin sonucunu verdict'e göre tam şu ifadelerle yaz: "
    "'the hypothesis was supported', 'the hypothesis was contradicted' veya 'the hypothesis was inconclusive'. "
    "verdict untested ise hipotezin bu veriyle sınanamadığını yaz. "
    "Hipotezi yeniden çerçeveleme, verdict'i değiştirme ve verdict contradicted veya inconclusive iken hipotezin desteklendiğini yazma. "
    "Evidence sentences bölümündeki her cümleyi Results içinde aynen kopyala: sırayı, sayıları ve model adlarını değiştirme, yeniden yazma. "
    "Bu cümleler hipotez kararını, anlamlı her performans farkını (p ve dz ile) ve kararsızlık bulgusunu taşır. "
    "Experiment spec içinde params doluysa deney her parametreli model için aynı bölmelerde çalışan bir kontrol grubu içerir: "
    "adı 'Model (default)' olan satır aynı modelin kütüphane varsayılan parametreleriyle çalışan halidir ve bir rakip model değildir. "
    "Methodology içinde bu kontrol grubunu ve parametrelerin etkisinin onunla karşılaştırıldığını tek cümleyle yaz. "
    "Sonuç tablosuna kontrol grubu satırlarını da 'Model (default)' adıyla koy ve hücreleri statistical_results'tan kopyala. "
    "Statistical decision içindeki parameter_effects bir parametre ayarının varsayılana göre etkisidir; "
    "her satırı Evidence sentences içindeki cümleyle yaz. significant false ise parametrelerin etkisi olduğunu iddia etme. "
    "Kontrol grubunu model karşılaştırmasında ve hipotezde yer alan bir model gibi anlatma. "
    "Verification status Failed ise deney doğrulamadan geçmemiştir ve makale bunu gizleyemez. "
    "Abstract içinde 'failed verification' ifadesini aynen kullan ve nedenini İngilizce tek cümleyle yaz; "
    "Verifier feedback Türkçedir, onu çevirerek özetle. "
    "Results bölümünü sayıların doğrulanmadığını söyleyen kısa bir paragrafla aç. "
    "Statistical decision ve tüm sayıları yalnız doğrulanmamış gözlem olarak anlat, hiçbir modeli kanıtlanmış üstün veya kararlı ilan etme. "
    "Metrik verilmediyse sonuç olmadığını yaz ve sayı uydurma. "
    "Verification status Passed ise Methodology içindeki ön işleme (ölçekleme, standardizasyon, normalizasyon, doldurma) anlatımı Final code ile aynı olmalı: "
    "yalnız eğitim bölümüne uydurulup test bölümüne uygulandığını yaz. Sorgu ön işlemenin tüm veri üzerinde veya bölmeden önce yapılmasını istese bile "
    "bunu yapılmış gibi yazma; böyle bir talimat düzeltildiyse bunu tek cümleyle belirt. "
    "Verification status Passed ise doğrulamanın başarısız olduğunu yazma. "
    "statistical_conclusion cümlesini aynen kopyalamak zorunda değilsin; kendi sözlerinle yazabilirsin ama yönünü değiştirme "
    "ve bu karar dışında yorum ekleme. "
    "Methodology bölümünde açıkça belirtmediğin ve test edilmeyen HİÇBİR modeli "
    "(önceki konuşmalardan veya RAG hafızasından gelse bile) Results veya Conclusion bölümüne dahil etme. "
    "Results ve Conclusion yalnız tested_models listesindeki modelleri adlandırabilir. "
    "Use only the supplied state. Do not invent metrics. "
    "If Claim review lists inconsistencies, rewrite the paper so those inconsistencies are gone. "
    "Replace every rejected number with the exact statistical_results value. "
    "Return only the Markdown document."
)


def write_workshop_paper(state: AgentState, past_experiments: list[dict], run_id: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _brief(state, past_experiments, run_id)},
        ],
    )
    markdown = _markdown_only(response.choices[0].message.content or "")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{run_id}_paper.md"
    path.write_text(markdown, encoding="utf-8")
    return str(path)


def _brief(state: AgentState, past_experiments: list[dict], run_id: str) -> str:
    hypotheses = [primary_hypothesis(state)[0]] if state.get("hypotheses") else []
    experiment_spec = primary_hypothesis(state)[1] or {}
    literature = state.get("literature_context") or []
    metrics = state.get("experiment_metrics") or {}
    model_results = state.get("model_results") or []
    dataset_profile = state.get("dataset_profile") or {}
    statistical_results = state.get("statistical_results") or {}
    statistical_decision = state.get("statistical_decision") or {}
    evidence = "\n".join(f"- {sentence}" for sentence in evidence_sentences(statistical_decision))
    failures = [
        {"error_log": item.get("error_log", "")}
        for item in past_experiments
        if item.get("is_success") is False
    ]
    tested_models = list(state.get("tested_models") or [])
    if not tested_models:
        for item in model_results:
            name = str(item.get("model", ""))
            if name and name not in tested_models:
                tested_models.append(name)
    tested_models = [display_name(name) for name in tested_models]
    model_results = [{**item, "model": display_name(str(item.get("model", "")))} for item in model_results]
    statistical_results = {display_name(str(name)): value for name, value in statistical_results.items()}
    return (
        f"Run id: {run_id}\n"
        f"Query: {state.get('query', '')}\n"
        f"Verification status: {state.get('verification_status', '')}\n"
        f"Verifier feedback: {state.get('verifier_feedback', '')}\n"
        f"Hypotheses:\n{json.dumps(hypotheses, ensure_ascii=False)}\n"
        f"Experiment spec (the approved design that was run):\n{json.dumps(experiment_spec, ensure_ascii=False)}\n"
        f"Literature:\n{json.dumps(literature, ensure_ascii=False)}\n"
        f"Metrics: {json.dumps(metrics, ensure_ascii=False)}\n"
        f"Dataset profile:\n{json.dumps(dataset_profile, ensure_ascii=False)}\n"
        f"Dataset source: {describe(str(experiment_spec['dataset'])) if experiment_spec.get('dataset') in DATASETS else 'not recorded'}\n"
        f"Tested models this run:\n{json.dumps(tested_models, ensure_ascii=False)}\n"
        f"Model results (rows from this run only; do not average and do not add models that are absent here):\n{json.dumps(model_results, ensure_ascii=False)}\n"
        f"Statistical results (exact Python means, standard deviations, variances, and statistical_conclusion; copy these, do not choose a winner):\n{json.dumps(statistical_results, ensure_ascii=False)}\n"
        f"Statistical decision (structured verdict from Python; the paper must not contradict it):\n{json.dumps(statistical_decision, ensure_ascii=False)}\n"
        f"Evidence sentences (written by Python from the statistical decision; copy each one word for word into Results, in this order):\n{evidence}\n"
        f"Final code:\n{state.get('current_experiment_code', '')}\n"
        f"RAG memory failures:\n{json.dumps(failures, ensure_ascii=False)}\n"
        f"Claim review:\n{state.get('consistency_feedback', '')}\n"
        f"Previous paper:\n{state.get('paper_markdown', '')}"
    )


def _markdown_only(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if not text:
        raise RuntimeError("report agent returned empty markdown")
    return text + "\n"
