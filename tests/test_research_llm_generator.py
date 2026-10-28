import json

import numpy as np
import pytest

from app.research import generate, llm_generator, protocol
from app.research.protocol import ExplorationView, Hypothesis, Registry

DATASETS = [f"e{index}" for index in range(6)]


def view(models):
    per_dataset = {
        dataset: {name: {"roc_auc_mean": float(values[position]), "pr_auc_mean": 0.5, "f1_mean": 0.5} for name, values in models.items()}
        for position, dataset in enumerate(DATASETS)
    }
    return ExplorationView(per_dataset, list(DATASETS))


def flat(level):
    return [level] * 6


MODELS = {"A": flat(0.70), "B": flat(0.80), "C": flat(0.75), "A__default": flat(0.65)}


def reply(*hypotheses):
    return json.dumps({"hypotheses": [{"subject": s, "other": o, "rationale": f"{s} should beat {o}"} for s, o in hypotheses]})


def propose(text, registry=None, stage="default", count=5, known=frozenset(), models=None):
    generator = llm_generator.make_generator(lambda prompt: text)
    return generator(view(models or MODELS), registry or Registry(25), stage, count, generate.DEFAULT_EFFECT, generate.DEFAULT_CONSISTENCY, known)


class TestPrompt:
    def test_it_shows_the_exploration_scores_and_nothing_else(self):
        text = llm_generator.prompt(view(MODELS), generate.model_names(view(MODELS)), "default", 3)
        for dataset in DATASETS:
            assert dataset in text
        assert "0.800" in text and "A__default" in text
        assert "at most 3 hypotheses" in text and "JSON" in text and "from the default stage" in text

    def test_it_forbids_models_that_are_not_listed_and_explains_the_controls(self):
        text = llm_generator.prompt(view(MODELS), generate.model_names(view(MODELS)), "tuned", 2)
        assert "Use only the model names listed above" in text and "ending in __default is the same model with library default parameters" in text and "from the tuned stage" in text

    def test_the_prompt_only_contains_the_datasets_of_the_view(self):
        small = ExplorationView({name: {"A": {"roc_auc_mean": 0.7}, "B": {"roc_auc_mean": 0.8}} for name in DATASETS}, DATASETS[:3])
        text = llm_generator.prompt(small, ["A", "B"], "default", 2)
        assert "e2" in text and "e3" not in text


class TestParse:
    def test_it_reads_the_list(self):
        assert llm_generator.parse(reply(("A", "B"), ("B", "C"))) == [("A", "B", "A should beat B"), ("B", "C", "B should beat C")]

    def test_it_accepts_a_fenced_block(self):
        assert llm_generator.parse("```json\n" + reply(("A", "B")) + "\n```") == [("A", "B", "A should beat B")]

    @pytest.mark.parametrize("text", ["", "no", "[]", "{}", '{"hypotheses": 3}', '{"hypotheses": [1]}', '{"hypotheses": [{"subject": "A"}]}', '{"hypotheses": [{"subject": 1, "other": 2}]}'])
    def test_anything_unusable_is_refused(self, text):
        with pytest.raises(llm_generator.GeneratorError):
            llm_generator.parse(text)

    def test_a_missing_rationale_becomes_an_empty_one(self):
        assert llm_generator.parse('{"hypotheses": [{"subject": "A", "other": "B"}]}') == [("A", "B", "")]


class TestPropose:
    def test_a_valid_proposal_becomes_a_hypothesis_with_exploration_evidence(self):
        proposals, skipped = propose(reply(("B", "A")))
        assert skipped == [] and len(proposals) == 1
        item = proposals[0]
        assert (item.subject, item.other, item.stage, item.metric, item.id) == (("B",), ("A",), "default", "roc_auc", "H1")
        assert item.evidence["median_difference"] == pytest.approx(0.10) and item.evidence["wins"] == 6 and item.evidence["datasets"] == 6
        assert item.evidence["scope"] == "exploration" and item.evidence["rationale"] == "B should beat A"
        assert item.statement == generate.statement("B", "A", "roc_auc", "default")

    def test_the_language_model_may_propose_against_the_exploration_data(self):
        proposals, _ = propose(reply(("A", "B")))
        assert proposals[0].evidence["median_difference"] == pytest.approx(-0.10) and proposals[0].evidence["wins"] == 0

    def test_unknown_models_are_skipped_with_a_reason(self):
        proposals, skipped = propose(reply(("Nope", "A"), ("B", "A")))
        assert [item.subject for item in proposals] == [("B",)]
        assert skipped == [{"statement": "Nope vs A", "reason": "unknown model"}]

    def test_a_model_against_itself_is_skipped(self):
        proposals, skipped = propose(reply(("A", "A")))
        assert proposals == [] and skipped[0]["reason"] == "a model cannot be compared with itself"

    def test_a_control_may_only_meet_its_own_model(self):
        proposals, skipped = propose(reply(("A", "A__default"), ("B", "A__default")))
        assert [item.other for item in proposals] == [("A__default",)]
        assert skipped == [{"statement": "B vs A__default", "reason": "a default control can only be compared with its own model"}]

    def test_two_controls_are_never_compared(self):
        _, skipped = propose(reply(("A__default", "B__default")), models={"A__default": flat(0.7), "B__default": flat(0.8)})
        assert skipped[0]["reason"] == "a default control can only be compared with its own model"

    def test_a_registered_claim_is_skipped(self):
        registry = Registry(25)
        registry.register(Hypothesis("H1", ("B",), ("A",), "default", "roc_auc", generate.statement("B", "A", "roc_auc", "default"), {}))
        proposals, skipped = propose(reply(("B", "A"), ("B", "C")), registry=registry)
        assert [item.other for item in proposals] == [("C",)] and skipped[0]["reason"] == generate.ALREADY_REGISTERED
        assert proposals[0].id == "H2"

    def test_a_known_claim_is_skipped(self):
        proposals, skipped = propose(reply(("B", "A")), known={(("B",), ("A",))})
        assert proposals == [] and skipped[0]["reason"] == generate.ALREADY_KNOWN

    def test_the_same_claim_twice_in_one_answer_counts_once(self):
        proposals, skipped = propose(reply(("B", "A"), ("B", "A")))
        assert len(proposals) == 1 and skipped[0]["reason"] == generate.ALREADY_REGISTERED

    def test_the_count_and_the_budget_limit_the_proposals(self):
        text = reply(("B", "A"), ("B", "C"), ("C", "A"))
        assert len(propose(text, count=2)[0]) == 2
        assert len(propose(text, registry=Registry(1))[0]) == 1

    def test_the_reply_order_is_kept(self):
        proposals, _ = propose(reply(("C", "A"), ("B", "A")))
        assert [item.subject for item in proposals] == [("C",), ("B",)]

    def test_the_ids_continue_after_the_registered_ones(self):
        registry = Registry(25)
        registry.register(Hypothesis("H1", ("X",), ("Y",), "default", "roc_auc", "x", {}))
        registry.register(Hypothesis("H2", ("X",), ("Z",), "default", "roc_auc", "y", {}))
        assert [item.id for item in propose(reply(("B", "A"), ("B", "C")), registry=registry)[0]] == ["H3", "H4"]

    def test_the_proposals_can_be_registered(self):
        registry = Registry(25)
        for item in propose(reply(("B", "A"), ("B", "C")), registry=registry)[0]:
            registry.register(item)
        assert len(registry.records) == 2


class TestFailure:
    def test_an_unusable_answer_falls_back_to_the_rules_and_says_so(self):
        generator = llm_generator.make_generator(lambda prompt: "I cannot help")
        proposals, skipped = generator(view(MODELS), Registry(25), "default", 5, generate.DEFAULT_EFFECT, generate.DEFAULT_CONSISTENCY, frozenset())
        assert proposals and skipped[0]["reason"].startswith("the language model answer was not usable")
        rules, _ = generate.propose(view(MODELS), Registry(25), "default", 5)
        assert [item.digest() for item in proposals] == [item.digest() for item in rules]

    def test_a_failing_call_falls_back_too(self):
        def complete(prompt):
            raise RuntimeError("quota")

        proposals, skipped = llm_generator.make_generator(complete)(view(MODELS), Registry(25), "default", 5, generate.DEFAULT_EFFECT, generate.DEFAULT_CONSISTENCY, frozenset())
        assert proposals and "quota" in skipped[0]["reason"]

    def test_an_answer_with_no_valid_proposal_does_not_fall_back(self):
        proposals, skipped = propose(reply(("Nope", "Nada")))
        assert proposals == [] and len(skipped) == 1


class TestTheProtocolDoesNotDependOnTheGenerator:
    def test_the_signature_is_the_one_of_the_rule_generator(self):
        import inspect

        assert list(inspect.signature(llm_generator.make_generator(lambda p: "")).parameters) == list(inspect.signature(generate.propose).parameters)

    def test_the_prompt_is_built_from_the_exploration_view_only(self, monkeypatch):
        seen = []
        generator = llm_generator.make_generator(lambda prompt: seen.append(prompt) or reply(("B", "A")))
        full = {f"d{index}": {"A": {"roc_auc_mean": 0.7}, "B": {"roc_auc_mean": 0.8}} for index in range(16)}
        explore = [f"d{index}" for index in range(6)]
        generator(ExplorationView(full, explore), Registry(25), "default", 3, 0.01, 5 / 6, frozenset())
        assert all(f"d{index}" in seen[0] for index in range(6)) and not any(f"d{index}" in seen[0] for index in range(6, 16))

    def test_even_an_adversarial_generator_cannot_inflate_the_error_in_a_null_world(self):
        rng = np.random.default_rng(0)
        names = [f"M{index}" for index in range(8)]
        confirmed = 0
        for _ in range(150):
            scores = {name: rng.normal(0, 0.014, 16) for name in names}
            base = rng.normal(0.8, 0.07, 16)
            results = {f"d{row:02d}": {name: {"roc_auc_mean": float(base[row] + scores[name][row])} for name in names} for row in range(16)}
            explore, confirm = protocol.split_pool(list(results), 6, 0)
            registry = Registry(protocol.max_hypotheses(10))
            exploration = ExplorationView(results, explore)
            best = sorted(((np.median([exploration.per_dataset[d][a]["roc_auc_mean"] - exploration.per_dataset[d][b]["roc_auc_mean"] for d in explore]), a, b) for a in names for b in names if a != b), reverse=True)[:8]
            text = reply(*[(a, b) for _, a, b in best])
            proposals, _ = llm_generator.make_generator(lambda prompt, text=text: text)(exploration, registry, "default", 8, 0.0, 0.0, frozenset())
            for item in proposals:
                registry.register(item)
            outcome = protocol.confirm(registry, {"default": {d: results[d] for d in confirm}})
            confirmed += int(any(item["status"] == "confirmed" for item in outcome))
        assert confirmed / 150 <= 0.10
