from typing import Any, TypedDict


class AgentState(TypedDict):
    query: str
    literature_context: list[str]
    hypotheses: list[str]
    experiment_specs: list[dict[str, Any]]
    approval_status: str
    current_experiment_code: str
    experiment_error: str
    experiment_metrics: dict[str, float]
    model_results: list[dict[str, str | float]]
    tested_models: list[str]
    dataset_profile: dict[str, str | float]
    statistical_results: dict[str, dict[str, float] | str]
    statistical_decision: dict[str, Any]
    verification_status: str
    verifier_feedback: str
    critic_rounds: int
    critic_continue: bool
    paper_markdown: str
    consistency_feedback: str
    consistency_rounds: int
    consistency_continue: bool
    research_status: str
