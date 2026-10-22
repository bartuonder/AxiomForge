import logging

from app.agents.experiment import (
    MODEL,
    PROMPT_VERSION,
    QueryNamesNoModel,
    correct_classification_code,
    generate_classification_code,
    models_dict_error,
    requested_models,
    split_contract_error,
)
from app.agents.spec import spec_code_error
from app.memory.rag_memory import save_experiment
from app.sandbox.e2b_runner import SandboxCodeError, run_classification
from app.tracking.mlflow_logger import (
    detect_algorithm,
    log_failed_run,
    log_model_comparison,
    parse_dataset_profile,
    parse_model_results,
)

logger = logging.getLogger("axiomforge")

MAX_RETRIES = 3


def execute_experiment(
    prompt: str,
    csv_schema: str,
    existing_code: str = "",
    criticism: str = "",
    record_memory: bool = True,
    track_run: bool = True,
    models: list[dict] | None = None,
    spec: dict | None = None,
) -> dict:
    allowed = list(models) if models is not None else requested_models(prompt)
    if not allowed:
        raise QueryNamesNoModel()
    logger.info("allowed_models=%s", [item["key"] for item in allowed])
    logger.info("experiment spec=%s", spec)
    if existing_code and criticism:
        source = correct_classification_code(existing_code, criticism, prompt, csv_schema, allowed, spec)
    else:
        source = generate_classification_code(prompt, csv_schema, allowed, spec)
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("sandbox attempt %s/%s", attempt, MAX_RETRIES)
        contract_error = models_dict_error(source, allowed)
        if not contract_error and spec:
            contract_error = spec_code_error(source, spec, allowed)
        if not contract_error:
            contract_error = split_contract_error(source)
        if contract_error:
            last_error = contract_error
            logger.error("sandbox attempt %s/%s failed:\n%s", attempt, MAX_RETRIES, last_error)
            if attempt == MAX_RETRIES:
                break
            logger.info("requesting corrected code after attempt %s", attempt)
            source = correct_classification_code(source, last_error, prompt, csv_schema, allowed, spec)
            continue
        try:
            output = run_classification(source, csv_schema)
            dataset_profile = parse_dataset_profile(output)
            model_results = parse_model_results(output)
            metrics = {
                "accuracy": float(model_results[0]["accuracy"]),
                "f1": float(model_results[0]["f1"]),
            }
        except SandboxCodeError as exc:
            last_error = str(exc)
            logger.error("sandbox attempt %s/%s failed:\n%s", attempt, MAX_RETRIES, last_error)
        except RuntimeError as exc:
            if "E2B_API_KEY is missing" in str(exc):
                raise
            last_error = str(exc)
            logger.error("sandbox attempt %s/%s failed:\n%s", attempt, MAX_RETRIES, last_error)
        else:
            printed: list[str] = []
            for item in model_results:
                name = str(item["model"])
                if name not in printed:
                    printed.append(name)
            allowed_names = [str(item["key"]) for item in allowed]
            if printed != allowed_names:
                last_error = "Printed model names must be exactly " + ", ".join(allowed_names) + "."
                logger.error("sandbox attempt %s/%s failed:\n%s", attempt, MAX_RETRIES, last_error)
            else:
                metric_text = " ".join(
                    (
                        f"{item['model']} accuracy={item['accuracy']} f1={item['f1']} "
                        f"roc_auc={item['roc_auc']} pr_auc={item['pr_auc']} "
                        f"train_seconds={item['train_seconds']} "
                        f"tn={item['tn']} fp={item['fp']} fn={item['fn']} tp={item['tp']}"
                    )
                    for item in model_results
                )
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
                run_id = ""
                if track_run:
                    try:
                        run_id = log_model_comparison(
                            model_results,
                            prompt_version=PROMPT_VERSION,
                            algorithm=detect_algorithm(source),
                            model=MODEL,
                            attempts=attempt,
                            dataset=dataset_profile,
                        )
                    except Exception:
                        logger.exception("mlflow logging failed")
                payload = {
                    "code": source,
                    "status": "Finished",
                    "attempts": attempt,
                    "mlflow_run_id": run_id,
                    "model_results": model_results,
                    "dataset_profile": dataset_profile,
                }
                payload.update(metrics)
                return payload
        if attempt == MAX_RETRIES:
            break
        logger.info("requesting corrected code after attempt %s", attempt)
        source = correct_classification_code(source, last_error, prompt, csv_schema, allowed, spec)
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
    run_id = ""
    if track_run:
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
    return {
        "code": source,
        "status": "Failed",
        "attempts": MAX_RETRIES,
        "mlflow_run_id": run_id,
        "error": last_error,
    }
