import json
from pathlib import Path

from openai import OpenAI

from app.config import OPENAI_API_KEY
from app.graph.selection import primary_hypothesis
from app.graph.state import AgentState

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
    "significant false ise o metrikte anlamlı fark bulunamadığını yaz; ortalamalar farklı görünse bile fark iddia etme. "
    "Performans farkını higher veya lower ile anlat, better kullanma. "
    "Statistical decision içindeki instability alanı bir bulgudur, hata değildir. "
    "unstable true ise Results içinde flagged listesindeki her model ve metriği std değeriyle ve std_threshold ile birlikte yaz, "
    "Conclusion içinde bu modellerin sonuçlarının bölmeye duyarlı olduğunu limitasyon olarak belirt ve onlara güvenilir veya kararlı deme. "
    "unstable false ise kararsızlık iddiası kurma. "
    "Verification status Failed ise deney doğrulamadan geçmemiştir ve makale bunu gizleyemez. "
    "Abstract içinde 'failed verification' ifadesini aynen kullan ve nedenini İngilizce tek cümleyle yaz; "
    "Verifier feedback Türkçedir, onu çevirerek özetle. "
    "Results bölümünü sayıların doğrulanmadığını söyleyen kısa bir paragrafla aç. "
    "Statistical decision ve tüm sayıları yalnız doğrulanmamış gözlem olarak anlat, hiçbir modeli kanıtlanmış üstün veya kararlı ilan etme. "
    "Metrik verilmediyse sonuç olmadığını yaz ve sayı uydurma. "
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
        f"Tested models this run:\n{json.dumps(tested_models, ensure_ascii=False)}\n"
        f"Model results (rows from this run only; do not average and do not add models that are absent here):\n{json.dumps(model_results, ensure_ascii=False)}\n"
        f"Statistical results (exact Python means, standard deviations, variances, and statistical_conclusion; copy these, do not choose a winner):\n{json.dumps(statistical_results, ensure_ascii=False)}\n"
        f"Statistical decision (structured verdict from Python; the paper must not contradict it):\n{json.dumps(statistical_decision, ensure_ascii=False)}\n"
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
