import logging

from openai import AuthenticationError, OpenAI, PermissionDeniedError, RateLimitError

from app.config import OPENAI_API_KEY

logger = logging.getLogger("axiomforge")

CHECK_MODEL = "gpt-4o"
CHECK_TIMEOUT_SECONDS = 10.0


class OpenAIUnavailable(RuntimeError):
    pass


def check_openai_access(client: OpenAI | None = None) -> None:
    if client is None:
        if not OPENAI_API_KEY:
            return
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=CHECK_TIMEOUT_SECONDS, max_retries=0)
    try:
        client.chat.completions.create(model=CHECK_MODEL, max_tokens=1, messages=[{"role": "user", "content": "ping"}])
    except RateLimitError as exc:
        if getattr(exc, "code", None) == "insufficient_quota" or "insufficient_quota" in str(exc):
            raise OpenAIUnavailable("the OpenAI quota is exhausted; add credit before starting a research") from exc
    except (AuthenticationError, PermissionDeniedError) as exc:
        raise OpenAIUnavailable("the OpenAI key was rejected; check OPENAI_API_KEY") from exc
    except Exception:
        logger.warning("the OpenAI access check could not be completed; the research starts anyway", exc_info=True)
