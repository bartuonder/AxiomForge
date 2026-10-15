import json
import re

from openai import OpenAI

from app.config import OPENAI_API_KEY
from app.graph.verifier import TIE_CONCLUSION

MODEL = "gpt-4o"
_WINNER_SENTENCE = re.compile(
    r"\S+ modeli istatistiksel olarak anlamlı bir şekilde daha kararlıdır"
)
_TIE_MARKS = ("farksızdır (Tie)", "üstünlük kuramamıştır")
_SUPERIORITY = re.compile(
    r"\b(?:superior|more stable|outperformed|better)\b",
    re.IGNORECASE,
)
DIRECTION_CONFLICT = "Yön Çelişkisi: İstatistiksel fark yokken üstünlük iddia edildi"
CONSISTENCY_PROMPT = (
    "Sen acımasız bir akademik hakemsin. "
    "1) Makaledeki sayılarla JSON'daki sayılar arasında uyuşmazlık var mı? "
    "2) Kararlılık hükmünü sen verme. statistical_conclusion cümlesi hükümdür. "
    "Makale bu cümleyle çelişen bir kazanan yazıyorsa bunu issues'a ekle. "
    "3) PR-AUC eksik bırakılıp sadece ROC-AUC mi övülmüş? "
    "Tüm tutarsızlıkları listele. "
    "issues listesine yalnız somut tutarsızlıkları yaz. "
    "Bir kontrol temizse onu issues listesine koyma. "
    "Makale tutarlıysa consistent true olsun ve issues boş liste olsun. "
    'Return only JSON: {"consistent": true, "issues": []}.'
)


def judge_consistency(paper: str, statistical_results: dict) -> tuple[bool, list[str]]:
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


def direction_conflict(paper: str, statistical_results: dict) -> str:
    conclusion = statistical_results.get("statistical_conclusion", "")
    if not isinstance(conclusion, str):
        return ""
    if not any(mark in conclusion for mark in _TIE_MARKS):
        return ""
    if _SUPERIORITY.search(paper):
        return DIRECTION_CONFLICT
    return ""


def conclusion_issues(paper: str, statistical_results: dict) -> list[str]:
    conclusion = statistical_results.get("statistical_conclusion", "")
    if not isinstance(conclusion, str) or not conclusion:
        return []
    issues: list[str] = []
    if conclusion not in paper:
        issues.append("Makale statistical_conclusion cümlesini aynen kullanmıyor.")
    winners = _WINNER_SENTENCE.findall(paper)
    if conclusion == TIE_CONCLUSION and winners:
        issues.append("Makale beraberlik kararına rağmen bir modeli daha kararlı ilan ediyor.")
    if conclusion != TIE_CONCLUSION:
        if TIE_CONCLUSION in paper:
            issues.append("Makale kazanan kararına rağmen beraberlik yazıyor.")
        if any(sentence != conclusion for sentence in winners):
            issues.append("Makale Python kararından farklı bir modeli daha kararlı ilan ediyor.")
    return issues
