import logging

from app.agents.experiment import (
    MODEL,
    PROMPT_VERSION,
    correct_classification_code,
    generate_classification_code,
)
from app.sandbox.e2b_runner import SandboxCodeError, run_classification
from app.tracking.mlflow_logger import (
    detect_algorithm,
    log_classification_run,
    log_failed_run,
    parse_metrics,
)

logger = logging.getLogger("axiomforge")

MAX_RETRIES = 3


def execute_experiment(prompt: str, csv_schema: str) -> dict:
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
            run_id = log_classification_run(
                metrics,
                prompt_version=PROMPT_VERSION,
                algorithm=detect_algorithm(source),
                model=MODEL,
                attempts=attempt,
            )
            logger.info("sandbox attempt %s/%s succeeded run_id=%s", attempt, MAX_RETRIES, run_id)
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
    run_id = log_failed_run(
        prompt_version=PROMPT_VERSION,
        algorithm=detect_algorithm(source),
        model=MODEL,
        attempts=MAX_RETRIES,
        error=last_error,
    )
    logger.error("sandbox failed after %s attempts run_id=%s", MAX_RETRIES, run_id)
    return {
        "code": source,
        "status": "Failed",
        "attempts": MAX_RETRIES,
        "mlflow_run_id": run_id,
    }
