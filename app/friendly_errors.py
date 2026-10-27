import re
from typing import Any

from openai import APIConnectionError, AuthenticationError, PermissionDeniedError, RateLimitError

from app.agents.campaign_planner import CampaignUnsupported
from app.agents.experiment import QueryNamesTooFewModels
from app.sandbox.e2b_runner import SandboxCodeError

MAX_MESSAGE_LENGTH = 2000
_TAG = re.compile(r"^\[(?P<code>[a-z0-9_]+)\]\s*(?P<detail>.*)$", re.DOTALL)
_MESSAGE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"insufficient_quota|exceeded your current quota|quota is exhausted", re.IGNORECASE), "openai_quota"),
    (re.compile(r"key was rejected|Incorrect API key|invalid_api_key", re.IGNORECASE), "openai_key"),
    (re.compile(r"OPENAI_API_KEY is missing"), "openai_missing_key"),
    (re.compile(r"E2B_API_KEY is missing"), "e2b_missing_key"),
    (re.compile(r"arxiv paper not found"), "arxiv_not_found"),
    (re.compile(r"arxiv request failed"), "arxiv_unavailable"),
    (re.compile(r"arxiv returned no|arxiv query is empty|no arxiv identifier"), "no_sources"),
    (re.compile(r"campaign planner returned no valid campaign|campaign planner did not return candidates"), "planner_invalid"),
    (re.compile(r"returned invalid JSON|returned an unusable answer|returned an empty|did not return an object"), "ai_format"),
    (re.compile(r"reported no progress for .* worker may have stopped"), "stale_worker"),
    (re.compile(r"^campaign cancelled"), "campaign_cancelled"),
    (re.compile(r"^campaign failed"), "campaign_failed"),
    (re.compile(r"campaign report is missing"), "report_missing"),
]

TEXTS: dict[str, dict[str, tuple[str, str, str]]] = {
    "tr": {
        "planner_refused": (
            "Sorunuzdan test edilebilir bir iddia çıkarılamadı",
            "Sistem, sorunuzda ya da bulunan makalede iki modeli karşılaştıran bir iddia bulamadı.",
            "Sorunuza iki model adı ve bir karşılaştırma yazın; örneğin 'Random forest, sinir ağından daha iyidir'. Ya da bir arXiv bağlantısı ekleyin.",
        ),
        "too_few_models": (
            "Sorunuzda yeterli model adı yok",
            "Bir karşılaştırma için en az iki model adı gerekir.",
            "Sorunuza iki model adı ekleyin; örneğin 'RandomForest ve SVM'.",
        ),
        "openai_quota": (
            "OpenAI kredisi bitmiş",
            "Yapay zekâ servisi kredi bittiği için isteği kabul etmedi. Hiçbir deney başlatılmadı.",
            "OpenAI hesabınıza kredi ekleyin, sonra yeniden deneyin.",
        ),
        "openai_busy": (
            "Yapay zekâ servisi şu an yoğun",
            "Servis kısa süreliğine istek sayısını sınırladı.",
            "Birkaç dakika bekleyip yeniden deneyin.",
        ),
        "openai_key": (
            "OpenAI anahtarı kabul edilmedi",
            "Yapay zekâ servisi, ayarlardaki anahtarı geçersiz saydı.",
            "OPENAI_API_KEY ayarını denetleyin.",
        ),
        "openai_network": (
            "Yapay zekâ servisine ulaşılamadı",
            "İnternet bağlantısı ya da servis geçici olarak kullanılamıyor.",
            "Bağlantınızı denetleyip yeniden deneyin.",
        ),
        "openai_missing_key": (
            "OpenAI anahtarı ayarlanmamış",
            "Sistem yapay zekâ servisini kullanmak için bir anahtara ihtiyaç duyuyor.",
            "OPENAI_API_KEY ayarını ekleyip sunucuyu yeniden başlatın.",
        ),
        "e2b_missing_key": (
            "Deney ortamı anahtarı ayarlanmamış",
            "Deneyler uzak bir ortamda (E2B) çalışır ve bunun için bir anahtar gerekir.",
            "E2B_API_KEY ayarını ekleyip sunucuyu yeniden başlatın.",
        ),
        "sandbox_error": (
            "Deney çalışırken hata verdi",
            "Uzak ortamdaki kod beklenmedik bir hatayla durdu.",
            "Yeniden deneyin. Sorun sürerse teknik ayrıntıyı geliştiriciye iletin.",
        ),
        "arxiv_not_found": (
            "Belirtilen arXiv makalesi bulunamadı",
            "Yazdığınız kimlik ya da bağlantıyla eşleşen bir makale yok.",
            "Kimliği denetleyin; örneğin 'arXiv:2207.08815'.",
        ),
        "arxiv_unavailable": (
            "arXiv'e ulaşılamadı",
            "Makale servisi şu an yanıt vermiyor.",
            "Birkaç dakika sonra yeniden deneyin ya da iddiayı doğrudan sorunuza yazın.",
        ),
        "no_sources": (
            "İlgili makale bulunamadı",
            "Sorunuzla ilgili yeterince uygun bir makale çıkmadı.",
            "Sorunuzu model adlarıyla daha net yazın ya da bir arXiv bağlantısı ekleyin.",
        ),
        "planner_invalid": (
            "Uygun bir deney planı üretilemedi",
            "Yapay zekâ üç denemede de çalıştırılabilir bir plan çıkaramadı.",
            "Sorunuzu daha sade yazıp yeniden deneyin; iki model ve bir karşılaştırma yeterlidir.",
        ),
        "ai_format": (
            "Yapay zekâ beklenen biçimde yanıt vermedi",
            "Servisin cevabı okunamadı.",
            "Yeniden deneyin. Sorun sürerse teknik ayrıntıyı geliştiriciye iletin.",
        ),
        "stale_worker": (
            "İşlem uzun süredir ilerlemiyor",
            "Arka planda çalışan sürecin durmuş olabileceği düşünülüyor.",
            "Birkaç dakika sonra sayfayı yenileyin; değişmezse işlemi yeniden başlatın.",
        ),
        "campaign_failed": (
            "Kampanya tamamlanamadı",
            "Deneyler bir hata nedeniyle sonuç üretemeden durdu.",
            "Yeniden deneyin. Sorun sürerse teknik ayrıntıyı geliştiriciye iletin.",
        ),
        "campaign_cancelled": (
            "Kampanya iptal edildi",
            "Kampanya siz durdurduğunuz için sonuç üretmeden sona erdi.",
            "İsterseniz kampanyayı aynı ayarlarla yeniden başlatabilirsiniz.",
        ),
        "report_missing": (
            "Rapor bulunamadı",
            "Kampanya bitti ama raporu kaydedilmemiş görünüyor.",
            "Kampanyayı yeniden çalıştırın.",
        ),
        "unknown": (
            "Beklenmeyen bir hata oluştu",
            "İşlem tamamlanamadı.",
            "Yeniden deneyin. Sorun sürerse teknik ayrıntıyı geliştiriciye iletin.",
        ),
    },
    "en": {
        "planner_refused": (
            "No testable claim could be taken from your question",
            "The system found no claim that compares two models in your question or in the paper it found.",
            "Write two model names and a comparison, for example 'random forests beat neural networks'. Or add an arXiv link.",
        ),
        "too_few_models": (
            "Your question names too few models",
            "A comparison needs at least two model names.",
            "Add two model names to your question, for example 'RandomForest and SVM'.",
        ),
        "openai_quota": (
            "The OpenAI credit has run out",
            "The AI service refused the request because the credit is used up. Nothing was started.",
            "Add credit to your OpenAI account and try again.",
        ),
        "openai_busy": (
            "The AI service is busy",
            "The service briefly limited the number of requests.",
            "Wait a few minutes and try again.",
        ),
        "openai_key": (
            "The OpenAI key was not accepted",
            "The AI service rejected the key in the settings.",
            "Check the OPENAI_API_KEY setting.",
        ),
        "openai_network": (
            "The AI service could not be reached",
            "The connection or the service is temporarily unavailable.",
            "Check your connection and try again.",
        ),
        "openai_missing_key": (
            "The OpenAI key is not set",
            "The system needs a key to use the AI service.",
            "Add the OPENAI_API_KEY setting and restart the server.",
        ),
        "e2b_missing_key": (
            "The experiment environment key is not set",
            "Experiments run in a remote environment (E2B) which needs a key.",
            "Add the E2B_API_KEY setting and restart the server.",
        ),
        "sandbox_error": (
            "The experiment stopped with an error",
            "The code in the remote environment stopped unexpectedly.",
            "Try again. If it keeps happening, pass the technical detail to the developer.",
        ),
        "arxiv_not_found": (
            "The arXiv paper was not found",
            "No paper matches the identifier or link you wrote.",
            "Check the identifier, for example 'arXiv:2207.08815'.",
        ),
        "arxiv_unavailable": (
            "arXiv could not be reached",
            "The paper service is not answering right now.",
            "Try again in a few minutes or write the claim directly in your question.",
        ),
        "no_sources": (
            "No relevant paper was found",
            "No paper matched your question well enough.",
            "Name the models more clearly or add an arXiv link.",
        ),
        "planner_invalid": (
            "No usable experiment plan could be made",
            "The AI could not produce a runnable plan in three tries.",
            "Write your question more simply; two models and a comparison are enough.",
        ),
        "ai_format": (
            "The AI did not answer in the expected format",
            "The reply of the service could not be read.",
            "Try again. If it keeps happening, pass the technical detail to the developer.",
        ),
        "stale_worker": (
            "The job has not moved for a long time",
            "The background process may have stopped.",
            "Refresh the page in a few minutes; if nothing changes, start the job again.",
        ),
        "campaign_failed": (
            "The campaign could not be completed",
            "The experiments stopped with an error before giving a result.",
            "Try again. If it keeps happening, pass the technical detail to the developer.",
        ),
        "campaign_cancelled": (
            "The campaign was cancelled",
            "The campaign ended without a result because you stopped it.",
            "You can start it again with the same settings if you like.",
        ),
        "report_missing": (
            "The report was not found",
            "The campaign finished but its report does not seem to have been saved.",
            "Run the campaign again.",
        ),
        "unknown": (
            "An unexpected error occurred",
            "The job could not be completed.",
            "Try again. If it keeps happening, pass the technical detail to the developer.",
        ),
    },
}
CODES = tuple(TEXTS["tr"])


def _from_message(message: str) -> str | None:
    for pattern, code in _MESSAGE_RULES:
        if pattern.search(message):
            return code
    return None


def classify(exc: BaseException) -> str | None:
    if isinstance(exc, CampaignUnsupported):
        return "planner_refused"
    if isinstance(exc, QueryNamesTooFewModels):
        return "too_few_models"
    if isinstance(exc, RateLimitError):
        return "openai_quota" if getattr(exc, "code", None) == "insufficient_quota" or "insufficient_quota" in str(exc) else "openai_busy"
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        return "openai_key"
    if isinstance(exc, APIConnectionError):
        return "openai_network"
    if isinstance(exc, SandboxCodeError):
        return "sandbox_error"
    return _from_message(str(exc))


def tag_error(exc: BaseException) -> str:
    text = str(exc) or type(exc).__name__
    code = None if _TAG.match(text) else classify(exc)
    return (f"[{code}] {text}" if code else text)[:MAX_MESSAGE_LENGTH]


describe = tag_error


def explain_error(message: str | None, language: str = "tr") -> dict[str, Any] | None:
    if not message:
        return None
    language = language if language in TEXTS else "tr"
    tagged = _TAG.match(message)
    if tagged and tagged.group("code") in TEXTS["tr"]:
        code, technical = tagged.group("code"), tagged.group("detail").strip()
    else:
        code, technical = _from_message(message) or "unknown", message
    title, text, hint = TEXTS[language][code]
    return {"code": code, "title": title, "message": text, "hint": hint, "technical": technical}
