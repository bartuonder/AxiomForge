import json
import re

from openai import OpenAI

from app.config import OPENAI_API_KEY

MODEL = "gpt-4o"
_NO_DIFFERENCE = re.compile(
    r"no (?:statistically )?significant difference|indistinguishable|\(Tie\)|neither model",
    re.IGNORECASE,
)
_SUPERIORITY = re.compile(
    r"\b(?:superior|more stable|outperformed|better)\b",
    re.IGNORECASE,
)
DIRECTION_CONFLICT = "Yön Çelişkisi: İstatistiksel fark yokken üstünlük iddia edildi"
CONSISTENCY_PROMPT = (
    "Sen acımasız bir akademik hakemsin. "
    "1) Makaledeki sayılarla JSON'daki sayılar arasında uyuşmazlık var mı? "
    "2) Kararlılık hükmünü sen verme. statistical_decision hükümdür: "
    "outcome tie ise makale hiçbir modeli daha kararlı veya üstün ilan edemez, "
    "outcome winner ise makale yalnız winner alanındaki modeli daha kararlı ilan edebilir. "
    "Makale bu hükümle çelişen bir kazanan yazıyorsa bunu issues'a ekle. "
    "Makalenin cümleyi kendi sözleriyle yazması tutarsızlık değildir. "
    "3) PR-AUC eksik bırakılıp sadece ROC-AUC mi övülmüş? "
    "Tüm tutarsızlıkları listele. "
    "issues listesine yalnız somut tutarsızlıkları yaz. "
    "Bir kontrol temizse onu issues listesine koyma. "
    "Makale tutarlıysa consistent true olsun ve issues boş liste olsun. "
    'Return only JSON: {"consistent": true, "issues": []}.'
)


def judge_consistency(
    paper: str,
    statistical_results: dict,
    statistical_decision: dict,
) -> tuple[bool, list[str]]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": CONSISTENCY_PROMPT},
            {
                "role": "user",
                "content": (
                    "statistical_results:\n"
                    f"{json.dumps(statistical_results, ensure_ascii=False)}\n\n"
                    "statistical_decision:\n"
                    f"{json.dumps(statistical_decision, ensure_ascii=False)}\n\n"
                    f"Paper:\n{paper}"
                ),
            },
        ],
    )
    content = response.choices[0].message.content or ""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("consistency checker returned invalid JSON") from exc
    if not isinstance(payload, dict):
        return False, ["Hakem geçerli bir karar döndürmedi."]
    raw_issues = payload.get("issues") or []
    if isinstance(raw_issues, str):
        issues = [raw_issues.strip()] if raw_issues.strip() else []
    elif isinstance(raw_issues, list):
        issues = [str(item).strip() for item in raw_issues if str(item).strip()]
    else:
        issues = [str(raw_issues).strip()] if str(raw_issues).strip() else []
    consistent = bool(payload.get("consistent")) and not issues
    if not consistent and not issues:
        issues = ["Hakem makaleyi tutarsız buldu ama madde yazmadı."]
    return consistent, issues


def direction_conflict(paper: str, statistical_decision: dict) -> str:
    if statistical_decision.get("outcome") != "tie":
        return ""
    if _SUPERIORITY.search(paper):
        return DIRECTION_CONFLICT
    return ""


def conclusion_issues(paper: str, statistical_decision: dict) -> list[str]:
    if statistical_decision.get("outcome") != "winner":
        return []
    winner = str(statistical_decision.get("winner", ""))
    issues: list[str] = []
    if winner and winner not in paper:
        issues.append(f"Makale {winner} modelini doğrulayıcının daha kararlı bulduğu model olarak adlandırmıyor.")
    if _NO_DIFFERENCE.search(paper):
        issues.append(f"Makale doğrulayıcı {winner} modelini daha kararlı bulduğu halde fark olmadığını yazıyor.")
    return issues
