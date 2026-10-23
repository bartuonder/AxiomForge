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
_HYPOTHESIS_WORD = re.compile(r"\bhypothes\w*", re.IGNORECASE)
_INTENT = re.compile(
    r"\bto\s+(?:determine|investigate|examine|assess|evaluate|compare|test|see)\b|\bwhether\b|\bwhich\s+(?:model|one|classifier)\b",
    re.IGNORECASE,
)
_CLAUSE_BREAK = re.compile(r"[;,]|\b(?:while|whereas|but|although|though|however)\b", re.IGNORECASE)
_GENERIC_PERFORMANCE = re.compile(r"\bperform\w*|\bpredictive\b", re.IGNORECASE)
_STABILITY_TERMS = re.compile(r"\bstabil\w*|\bvarianc\w*|\bvariab\w*", re.IGNORECASE)
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
EFFECT_SIZE_TOLERANCE = 0.006
PERFORMANCE_OMISSION_NOTICE = (
    "{metric} için {a} ile {b} arasında anlamlı bir fark var (significant true) ama makale bunu "
    "tablo dışında bir cümlede yazmıyor. Results içinde yönü (higher veya lower), adjusted_p_value ve "
    "effect_size_dz ile birlikte yaz; Abstract ve Conclusion bu metriği dışarıda bırakmasın."
)
EFFECT_SIZE_NOTICE = "{metric} karşılaştırmasının etki büyüklüğü (effect_size_dz = {value}) makalede yok."
_VERDICT_WORDS = {
    "supported": re.compile(r"(?<!not\s)(?<!un)\bsupported\b", re.IGNORECASE),
    "contradicted": re.compile(r"\bcontradict\w*", re.IGNORECASE),
    "inconclusive": re.compile(r"\binconclusive\b", re.IGNORECASE),
}
HYPOTHESIS_MISSING_NOTICE = (
    "Hipotezin kararı {verdict} ama makalenin {section} bölümü bunu 'the hypothesis was {verdict}' "
    "ifadesiyle yazmıyor."
)
HYPOTHESIS_REVERSED_NOTICE = (
    "Hipotezin kararı {verdict} ama makalenin {section} bölümü hipotezin desteklendiğini yazıyor."
)
_TABLE_COLUMNS = {
    "accuracy": "accuracy",
    "f1": "f1",
    "f1score": "f1",
    "rocauc": "roc_auc",
    "prauc": "pr_auc",
    "trainseconds": "train_seconds",
    "trainingseconds": "train_seconds",
    "traintime": "train_seconds",
    "trainingtime": "train_seconds",
}
_TABLE_LABELS = {
    "accuracy": "Accuracy",
    "f1": "F1",
    "roc_auc": "ROC-AUC",
    "pr_auc": "PR-AUC",
    "train_seconds": "Train seconds",
}
_NUMBER_TEXT = r"\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
_CELL = re.compile(rf"(-?{_NUMBER_TEXT})\s*(?:±|\+/-|\+-)\s*({_NUMBER_TEXT})")
_SEPARATOR_CELL = re.compile(r":?-{2,}:?")
_HEADER_DECORATION = re.compile(r"\([^)]*\)|\b(?:mean|std|sd|dev|deviation)\b|±|\+/-", re.IGNORECASE)
TABLE_MISSING_NOTICE = (
    "Makalede sonuç tablosu yok. Results içine Model, Accuracy, F1, ROC-AUC, PR-AUC ve Train seconds "
    "sütunlu bir Markdown tablosu koy ve her modelin ortalama ± standart sapmasını statistical_results'tan kopyala."
)
TABLE_COLUMN_NOTICE = "Sonuç tablosunda {metric} sütunu yok."
TABLE_ROW_NOTICE = "Sonuç tablosunda {model} satırı yok."
TABLE_CELL_NOTICE = (
    "Sonuç tablosunda {model} için {metric} hücresi '{found}' ama doğrulanmış değer {expected}."
)
_CLAIM_TERMS = re.compile(
    r"\bhigher\b|\blower\b|\bbetter\b|\bworse\b|\boutperform\w*|\bsuperior\b|\bgreater\b|\blarger\b|\bexceed\w*|\bimprov\w*",
    re.IGNORECASE,
)
UNSUPPORTED_DIFFERENCE_NOTICE = (
    '{metric} için {a} ile {b} arasındaki fark anlamlı değil (significant false) ama makale bir üstünlük '
    'iddia ediyor: "{clause}". Bu karşılaştırma için yalnızca "No significant difference" cümlesini kullan.'
)
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


def _significant_metric_labels(statistical_decision: dict) -> list[re.Pattern[str]]:
    significant = {
        str(item.get("metric"))
        for item in statistical_decision.get("performance") or []
        if item.get("significant")
    }
    labels = [pattern for key, pattern in _METRIC_LABELS.items() if key in significant]
    return labels + [_GENERIC_PERFORMANCE] if labels else labels


def _is_excused(text: str, labels: list[re.Pattern[str]]) -> bool:
    return not _STABILITY_TERMS.search(text) and any(label.search(text) for label in labels)


def direction_conflict(paper: str, statistical_decision: dict) -> str:
    if statistical_decision.get("outcome") != "tie":
        return ""
    labels = _significant_metric_labels(statistical_decision)
    for sentence in _SENTENCE_BREAK.split(paper):
        if not _SUPERIORITY.search(sentence) or _NEGATION.search(sentence):
            continue
        if _HYPOTHESIS_WORD.search(sentence) or _INTENT.search(sentence):
            continue
        if _is_excused(sentence, labels):
            continue
        clauses = [
            clause
            for clause in _CLAUSE_BREAK.split(sentence)
            if _SUPERIORITY.search(clause) and not _NEGATION.search(clause)
        ]
        offending = next((clause for clause in clauses if not _is_excused(clause, labels)), None)
        if offending is None:
            continue
        return f'{DIRECTION_CONFLICT}: "{offending.strip()[:200]}"'
    return ""


def section_of(paper: str, title: str) -> str:
    headings = list(_HEADING.finditer(paper))
    for position, heading in enumerate(headings):
        if heading.group(1).strip().rstrip(":").lower() == title.lower():
            end = headings[position + 1].start() if position + 1 < len(headings) else len(paper)
            return paper[heading.end():end]
    return paper


def abstract_of(paper: str) -> str:
    return section_of(paper, "abstract")


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


def hypothesis_issues(paper: str, hypothesis: dict | None) -> list[str]:
    verdict = str((hypothesis or {}).get("verdict", ""))
    expected = _VERDICT_WORDS.get(verdict)
    if expected is None:
        return []
    issues: list[str] = []
    for title in ("Abstract", "Conclusion"):
        section = section_of(paper, title)
        if not expected.search(section):
            issues.append(HYPOTHESIS_MISSING_NOTICE.format(verdict=verdict, section=title))
        elif verdict != "supported" and _VERDICT_WORDS["supported"].search(section):
            issues.append(HYPOTHESIS_REVERSED_NOTICE.format(verdict=verdict, section=title))
    return issues


def _column_key(header: str) -> str | None:
    return _TABLE_COLUMNS.get(_squash(_HEADER_DECORATION.sub("", header)))


def _markdown_tables(paper: str) -> list[list[list[str]]]:
    blocks: list[list[str]] = []
    block: list[str] = []
    for line in paper.splitlines() + [""]:
        if line.lstrip().startswith("|"):
            block.append(line)
        elif block:
            blocks.append(block)
            block = []
    tables: list[list[list[str]]] = []
    for lines in blocks:
        rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
        rows = [row for row in rows if not all(_SEPARATOR_CELL.fullmatch(cell) or not cell for cell in row)]
        if rows:
            tables.append(rows)
    return tables


def _written_value_matches(text: str, expected: float) -> bool:
    try:
        value = float(text)
    except ValueError:
        return False
    if "e" in text.lower():
        return abs(value - expected) <= 1e-9 + 0.005 * abs(expected)
    decimals = len(text.split(".")[1]) if "." in text else 0
    return abs(value - expected) <= 0.5 * 10 ** -decimals + 1e-9


def table_issues(paper: str, statistical_results: dict | None) -> list[str]:
    records = {
        name: record
        for name, record in (statistical_results or {}).items()
        if isinstance(record, dict)
    }
    if not records:
        return []
    chosen = None
    for rows in _markdown_tables(paper):
        columns = {
            index: key
            for index, cell in enumerate(rows[0])
            if (key := _column_key(cell)) is not None
        }
        if columns:
            chosen = (rows, columns)
            break
    if chosen is None:
        return [TABLE_MISSING_NOTICE]
    rows, columns = chosen
    issues = [
        TABLE_COLUMN_NOTICE.format(metric=label)
        for key, label in _TABLE_LABELS.items()
        if key not in columns.values()
    ]
    for model, record in records.items():
        row = next((item for item in rows[1:] if item and _squash(item[0]) == _squash(model)), None)
        if row is None:
            issues.append(TABLE_ROW_NOTICE.format(model=model))
            continue
        for index, metric in columns.items():
            mean, std = float(record[f"{metric}_mean"]), float(record[f"{metric}_std"])
            cell = row[index] if index < len(row) else ""
            found = _CELL.search(cell)
            if found and _written_value_matches(found.group(1), mean) and _written_value_matches(found.group(2), std):
                continue
            issues.append(
                TABLE_CELL_NOTICE.format(
                    model=model,
                    metric=_TABLE_LABELS[metric],
                    found=cell or "boş",
                    expected=f"{mean:.4f} ± {std:.4f}",
                )
            )
    return issues


def unsupported_difference_issues(paper: str, performance: list[dict] | None) -> list[str]:
    rows = [item for item in performance or [] if not item.get("significant")]
    if not rows:
        return []
    prose = _prose_sentences(paper)
    issues: list[str] = []
    for item in rows:
        key = str(item.get("metric", ""))
        label = _METRIC_LABELS.get(key)
        if label is None:
            continue
        first, second = _squash(str(item["a"])), _squash(str(item["b"]))
        offending = None
        for sentence in prose:
            if _HYPOTHESIS_WORD.search(sentence) or _INTENT.search(sentence):
                continue
            for clause in _CLAUSE_BREAK.split(sentence):
                squashed = _squash(clause)
                if (
                    label.search(clause)
                    and first in squashed
                    and second in squashed
                    and _CLAIM_TERMS.search(clause)
                    and not _NEGATION.search(clause)
                    and not _STABILITY_TERMS.search(clause)
                ):
                    offending = clause.strip()
                    break
            if offending:
                break
        if offending:
            issues.append(
                UNSUPPORTED_DIFFERENCE_NOTICE.format(
                    metric=_METRIC_NAMES[key], a=item["a"], b=item["b"], clause=offending[:200]
                )
            )
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
