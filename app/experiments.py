import logging

from app.agents.experiment import (
    MODEL,
    PROMPT_VERSION,
    correct_classification_code,
    generate_classification_code,
)
from app.memory.rag_memory import save_experiment
from app.sandbox.e2b_runner import SandboxCodeError, run_classification
from app.tracking.mlflow_logger import (
    detect_algorithm,
    log_classification_run,
    log_failed_run,
    parse_metrics,
)

logger = logging.getLogger("axiomforge")

MAX_RETRIES = 3


def execute_experiment(
    prompt: str,
    csv_schema: str,
    existing_code: str = "",
    criticism: str = "",
    record_memory: bool = True,
) -> dict:
    if existing_code and criticism:
        source = correct_classification_code(existing_code, criticism, prompt, csv_schema)
    else:
        source = generate_classification_code(prompt, csv_schema)
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("sandbox attempt %s/%s", attempt, MAX_RETRIES)
        try:
            output = run_classification(source, csv_schema)
            metrics = parse_metrics(output)
        except SandboxCodeError as exc:
            last_error = str(exc)
            logger.error("sandbox attempt %s/%s failed:\n%s", attempt, MAX_RETRIES, last_error)
        except RuntimeError as exc:
            if "E2B_API_KEY is missing" in str(exc):
                raise
            last_error = str(exc)
            logger.error("sandbox attempt %s/%s failed:\n%s", attempt, MAX_RETRIES, last_error)
        else:
            metric_text = " ".join(f"{name}={value}" for name, value in metrics.items())
            if record_memory:
                memory_id = save_experiment(
                    hypothesis=prompt,
                    code=source,
                    metric=metric_text,
                    error_log="",
                    is_success=True,
                )
                logger.info("saved successful experiment memory_id=%s", memory_id)
            logger.info("sandbox attempt %s/%s succeeded", attempt, MAX_RETRIES)
            try:
                run_id = log_classification_run(
                    metrics,
                    prompt_version=PROMPT_VERSION,
                    algorithm=detect_algorithm(source),
                    model=MODEL,
                    attempts=attempt,
                )
            except Exception:
                logger.exception("mlflow logging failed")
                run_id = ""
            payload = {
                "code": source,
                "status": "Finished",
                "attempts": attempt,
                "mlflow_run_id": run_id,
            }
            payload.update(metrics)
            return payload
        if attempt == MAX_RETRIES:
            break
        logger.info("requesting corrected code after attempt %s", attempt)
        source = correct_classification_code(source, last_error, prompt, csv_schema)
    logger.error("sandbox failed after %s attempts", MAX_RETRIES)
    if record_memory:
        memory_id = save_experiment(
            hypothesis=prompt,
            code=source,
            metric="",
            error_log=last_error,
            is_success=False,
        )
        logger.info("saved failed experiment memory_id=%s", memory_id)
    try:
        run_id = log_failed_run(
            prompt_version=PROMPT_VERSION,
            algorithm=detect_algorithm(source),
            model=MODEL,
            attempts=MAX_RETRIES,
            error=last_error,
        )
    except Exception:
        logger.exception("mlflow logging failed")
        run_id = ""
    return {
        "code": source,
        "status": "Failed",
        "attempts": MAX_RETRIES,
        "mlflow_run_id": run_id,
    }
