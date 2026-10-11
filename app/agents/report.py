import json
from pathlib import Path

from openai import OpenAI

from app.config import OPENAI_API_KEY
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
    "If model_results lists more than one model, the Results section must include a Markdown comparison table "
    "with columns Model, Accuracy, F1, and Train seconds. Use only the supplied numbers. "
    "Use only the supplied state and memory. Do not invent metrics. "
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
    hypotheses = state.get("hypotheses") or []
    literature = state.get("literature_context") or []
    metrics = state.get("experiment_metrics") or {}
    model_results = state.get("model_results") or []
    failures = [item for item in past_experiments if item.get("is_success") is False]
    return (
        f"Run id: {run_id}\n"
        f"Query: {state.get('query', '')}\n"
        f"Verification status: {state.get('verification_status', '')}\n"
        f"Verifier feedback: {state.get('verifier_feedback', '')}\n"
        f"Hypotheses:\n{json.dumps(hypotheses, ensure_ascii=False)}\n"
        f"Literature:\n{json.dumps(literature, ensure_ascii=False)}\n"
        f"Metrics: {json.dumps(metrics, ensure_ascii=False)}\n"
        f"Model results:\n{json.dumps(model_results, ensure_ascii=False)}\n"
        f"Final code:\n{state.get('current_experiment_code', '')}\n"
        f"RAG memory failures:\n{json.dumps(failures, ensure_ascii=False)}"
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
