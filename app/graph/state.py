from typing import TypedDict


class AgentState(TypedDict):
    query: str
    literature_context: list[str]
    hypotheses: list[str]
    approval_status: str
    current_experiment_code: str
    experiment_metrics: dict[str, float]
    model_results: list[dict[str, str | float]]
    dataset_profile: dict[str, str | float]
    verification_status: str
    verifier_feedback: str
    critic_rounds: int
    critic_continue: bool
    research_status: str
