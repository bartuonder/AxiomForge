from app.memory.rag_memory import save_experiment, search_past_experiments


def main() -> None:
    failure_id = save_experiment(
        hypothesis="Using a missing target column lowers tabular classification accuracy.",
        code="y = data['missing_target']",
        metric="accuracy=0.0",
        error_log="KeyError: missing_target",
        is_success=False,
    )
    success_id = save_experiment(
        hypothesis="A random forest on age, spend, and tenure predicts customer churn.",
        code="RandomForestClassifier().fit(X_train, y_train)",
        metric="accuracy=0.81 f1=0.77",
        error_log="",
        is_success=True,
    )
    failure_hits = search_past_experiments("failed experiment because the target column was missing", k=3)
    success_hits = search_past_experiments("successful random forest churn model", k=3)
    print("saved_failure", failure_id)
    print("saved_success", success_id)
    print("failure_search")
    for item in failure_hits:
        print(item["is_success"], item["hypothesis"], item["metric"])
    print("success_search")
    for item in success_hits:
        print(item["is_success"], item["hypothesis"], item["metric"])
    if not failure_hits or not success_hits:
        raise SystemExit("search returned no experiments")


if __name__ == "__main__":
    main()
