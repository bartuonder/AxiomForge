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
    r"\b(?:superior(?:ity)?|more\s+stable|outperform(?:s|ed|ing)?)\b"
    r"|\bbetter\s+than\b"
    r"|\b(?:perform\w*|is|are|was|were|be|proves?|proved|appears?|seems?|remains?|yields?|achieves?)"
    r"\s+(?:\w+ly\s+)?better\b"
    r"|\bbetter\s+(?:performance|results?|accuracy|stability|generali[sz]ation|predictive\s+\w+)\b"
    r"|\bthe\s+better\s+(?:model|classifier|performer|choice)\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(r"\b(?:no|not|neither|nor|none|never|cannot|without)\b|n't", re.IGNORECASE)
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n")
_HEADING = re.compile(r"^#{1,6}[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_FAILED_VERIFICATION = re.compile(
    r"\bfailed\s+(?:the\s+)?(?:\w+\s+)?verification\b"
    r"|\bverification\b[^.\n]{0,80}?\b(?:failed|was\s+rejected|did\s+not\s+pass)\b"
    r"|\bdid\s+not\s+pass\s+(?:the\s+)?(?:\w+\s+)?verification\b"
    r"|\bunverified\b|\bnot\s+(?:been\s+)?verified\b|\bcould\s+not\s+be\s+verified\b|\bfailed\s+to\s+verify\b",
    re.IGNORECASE,
)
DIRECTION_CONFLICT ="Yön Çelişkisi: İstatistiksel fark yokken üstünlük iddia edildi"
_INSTABILITY_TERMS = re.compile(
    r"\bunstab\w*|\binstabilit\w*|\bhigh(?:er)?\s+(?:variance|variability)\b"
    r"|\b(?:large|high|substantial)\s+(?:standard\s+deviation|std|spread)\b"
    r"|\bexceed\w*\s+(?:the\s+)?(?:\w+\s+){0,3}threshold\b"
    r"|\bsensitiv\w*\s+to\s+(?:the\s+)?(?:data\s+|train\w*\s+)?split",
    re.IGNORECASE,
)
INSTABILITY_ABSTRACT_NOTICE = (
    "Kararsızlık bulgusu var ama makalenin özeti (Abstract) bunu yazmıyor. "
    "Özet 'high variance across splits' ifadesini ve hangi modelin kararsız olduğunu içermeli."
)
INSTABILITY_MODEL_NOTICE = (
    "Kararsızlık bulgusunda {model} işaretlendi ama makale bu modelin bölmeye duyarlılığını "
    "tablo dışında bir cümlede açıklamıyor."
)
_VERIFICATION_WORD = re.compile(r"\bverif\w*", re.IGNORECASE)
_RELIABILITY_TERMS = re.compile(
    r"\breliab\w*|\btrustworth\w*|\bcredib\w*|\brobust\w*|\bguarantee\w*",
    re.IGNORECASE,
)
_NEGATED_RELIABILITY = re.compile(
    r"(?:\b(?:no|not|never|cannot|without|neither|nor)\b|n't)"
    r"(?:\W+\w+){0,4}?\W+(?:reliab\w*|trustworth\w*|credib\w*|robust\w*|guarantee\w*)",
    re.IGNORECASE,
)
_METRIC_NAMES = {"roc_auc": "ROC-AUC", "pr_auc": "PR-AUC", "f1": "F1"}
_METRIC_LABELS = {
    "roc_auc": re.compile(r"\bROC[- _]?AUC\b", re.IGNORECASE),
    "pr_auc": re.compile(r"\bPR[- _]?AUC\b|\baverage\s+precision\b", re.IGNORECASE),
    "f1": re.compile(r"\bF1\b", re.IGNORECASE),
}
_DIFFERENCE_TERMS = re.compile(
    r"\bsignific\w*|\bhigher\b|\blower\b|\bdiffer\w*|\bexceed\w*|\bgreater\b|\blarger\b|\bbetter\b|\boutperform\w*",
    re.IGNORECASE,
)
_STABILITY_TERMS = re.compile(r"\bstabil\w*|\bvarianc\w*|\bvariab\w*", re.IGNORECASE)
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
EFFECT_SIZE_TOLERANCE = 0.006
PERFORMANCE_OMISSION_NOTICE = (
    "{metric} için {a} ile {b} arasında anlamlı bir fark var (significant true) ama makale bunu "
    "tablo dışında bir cümlede yazmıyor. Results içinde yönü (higher veya lower), adjusted_p_value ve "
    "effect_size_dz ile birlikte yaz; Abstract ve Conclusion bu metriği dışarıda bırakmasın."
)
EFFECT_SIZE_NOTICE = "{metric} karşılaştırmasının etki büyüklüğü (effect_size_dz = {value}) makalede yok."
RELIABILITY_NOTICE = (
    "Doğrulama Passed ama makale bunu sonuçların güvenilir olduğunun kanıtı gibi anlatıyor "
    "('reliability', 'robust' gibi sözcüklerle). Passed yalnız deneyin hatasız çalıştığını "
    "ve veri sızıntısı bulunmadığını söyler."
)
VERIFICATION_NOTICE = (
    "Doğrulama Failed olduğu halde makalenin özeti (Abstract) bunu açıkça yazmıyor. "
    "Özet 'failed verification' ifadesini ve nedenini içermeli."
)
CONSISTENCY_PROMPT = (
    "Sen acımasız bir akademik hakemsin. "
    "1) Makaledeki sayılarla JSON'daki sayılar arasında uyuşmazlık var mı? "
    "2) Kararlılık hükmünü sen verme. statistical_decision hükümdür: "
    "outcome tie ise makale hiçbir modeli daha kararlı veya üstün ilan edemez, "
    "outcome winner ise makale yalnız winner alanındaki modeli daha kararlı ilan edebilir. "
    "Makale bu hükümle çelişen bir kazanan yazıyorsa bunu issues'a ekle. "
    "Makalenin cümleyi kendi sözleriyle yazması tutarsızlık değildir. "
    "3) PR-AUC eksik bırakılıp sadece ROC-AUC mi övülmüş? "
    "4) Makale bir metrikte modeller arasında fark olduğunu, statistical_decision.performance içinde "
    "significant true olmayan bir karşılaştırma için mi iddia ediyor? Öyleyse issues'a ekle. "
    "5) statistical_decision.instability.unstable true ise makale flagged listesindeki modelleri ve metrikleri "
    "yüksek sapmalı olarak raporlamalı ve onları güvenilir veya kararlı diye anlatmamalıdır. "
    "Raporlamıyorsa veya öyle anlatıyorsa issues'a ekle. unstable false iken makale kararsızlık iddia ediyorsa onu da ekle. "
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
    for sentence in _SENTENCE_BREAK.split(paper):
        if _SUPERIORITY.search(sentence) and not _NEGATION.search(sentence):
            return DIRECTION_CONFLICT
    return ""


def abstract_of(paper: str) -> str:
    headings = list(_HEADING.finditer(paper))
    for position, heading in enumerate(headings):
        if heading.group(1).strip().rstrip(":").lower() == "abstract":
            end = headings[position + 1].start() if position + 1 < len(headings) else len(paper)
            return paper[heading.end():end]
    return paper


def verification_issue(paper: str, verification_status: str) -> str:
    if verification_status != "Failed":
        return ""
    return "" if _FAILED_VERIFICATION.search(abstract_of(paper)) else VERIFICATION_NOTICE


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _prose_sentences(paper: str) -> list[str]:
    return [
        sentence
        for line in paper.splitlines()
        if not line.lstrip().startswith("|")
        for sentence in _SENTENCE_BREAK.split(line)
        if sentence.strip()
    ]


def reliability_issue(paper: str, verification_status: str) -> str:
    if verification_status != "Passed":
        return ""
    for sentence in _prose_sentences(paper):
        if (
            _VERIFICATION_WORD.search(sentence)
            and _RELIABILITY_TERMS.search(sentence)
            and not _NEGATED_RELIABILITY.search(sentence)
        ):
            return RELIABILITY_NOTICE
    return ""


def performance_issues(paper: str, performance: list[dict] | None) -> list[str]:
    significant = [item for item in performance or [] if item.get("significant")]
    if not significant:
        return []
    prose = _prose_sentences(paper)
    numbers = [float(match.group()) for sentence in prose for match in _NUMBER.finditer(sentence)]
    issues: list[str] = []
    for item in significant:
        key = str(item.get("metric", ""))
        pattern = _METRIC_LABELS.get(key)
        if pattern is None:
            continue
        metric = _METRIC_NAMES[key]
        reported = any(
            pattern.search(sentence)
            and _DIFFERENCE_TERMS.search(sentence)
            and not _STABILITY_TERMS.search(sentence)
            and not _NEGATION.search(sentence)
            for sentence in prose
        )
        if not reported:
            issues.append(PERFORMANCE_OMISSION_NOTICE.format(metric=metric, a=item["a"], b=item["b"]))
            continue
        effect = abs(float(item.get("effect_size_dz", 0.0)))
        if effect and not any(abs(number - effect) <= EFFECT_SIZE_TOLERANCE for number in numbers):
            issues.append(EFFECT_SIZE_NOTICE.format(metric=metric, value=f"{effect:.2f}"))
    return issues


def instability_issues(paper: str, instability: dict | None) -> list[str]:
    if not instability or not instability.get("unstable"):
        return []
    issues: list[str] = []
    if not _INSTABILITY_TERMS.search(abstract_of(paper)):
        issues.append(INSTABILITY_ABSTRACT_NOTICE)
    prose = _prose_sentences(paper)
    for model in dict.fromkeys(str(item["model"]) for item in instability.get("flagged", [])):
        squashed = _squash(model)
        if not any(squashed in _squash(sentence) and _INSTABILITY_TERMS.search(sentence) for sentence in prose):
            issues.append(INSTABILITY_MODEL_NOTICE.format(model=model))
    return issues


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
