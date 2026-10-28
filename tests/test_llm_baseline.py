import json

import pytest

from app.campaign.benchmark import CASES
from app.campaign.hard_benchmark import near_cases
from tools import llm_baseline as baseline

REFERENCE = {case["id"]: "inconclusive" for case in near_cases()} | {"N9": "contradicted", "N10": "partially_replicated", "N11": "replicated", "N12": "contradicted"}


def answer(verdict, confidence=0.9):
    return json.dumps({"verdict": verdict, "confidence": confidence})


def oracle(query):
    for case in CASES:
        if case["query"] == query:
            return answer("true" if case["expected"] == "replicated" else "false")
    return answer("unclear")


class TestParse:
    @pytest.mark.parametrize("text,expected", [
        (answer("true"), "replicated"),
        (answer("false"), "contradicted"),
        (answer("unclear"), "inconclusive"),
        (answer("TRUE"), "replicated"),
        ('```json\n{"verdict": "false", "confidence": 0.7}\n```', "contradicted"),
    ])
    def test_the_answers_map_to_the_verdict_words_of_the_system(self, text, expected):
        assert baseline.parse(text) == expected

    @pytest.mark.parametrize("text", ["", "I do not know", "{}", '{"verdict": "maybe"}', "[1]", '{"verdict": 3}'])
    def test_anything_else_is_invalid(self, text):
        assert baseline.parse(text) == "invalid"


class TestCases:
    def test_the_known_claims_keep_their_expected_verdict(self):
        known = [case for case in baseline.cases(REFERENCE) if case["kind"] == "known"]
        assert len(known) == 10 and {case["reference"] for case in known} == {"replicated", "contradicted"}
        assert known[0]["query"] == CASES[0]["query"]

    def test_the_near_claims_take_the_data_based_verdict_as_reference(self):
        near = [case for case in baseline.cases(REFERENCE) if case["kind"] == "near"]
        assert len(near) == 14 and sum(1 for case in near if case["reference"] == "inconclusive") == 10
        assert next(case for case in near if case["id"] == "N11")["reference"] == "replicated"

    def test_a_missing_reference_is_refused(self):
        with pytest.raises(ValueError, match="N1"):
            baseline.cases({})


class TestPrompt:
    def test_it_asks_about_the_claim_without_offering_any_data(self):
        text = baseline.prompt("Random forests outperform a single decision tree on tabular classification data.")
        assert "Random forests outperform a single decision tree" in text
        assert "without" in text.lower() and "json" in text.lower() and "true" in text and "false" in text and "unclear" in text


class TestEvaluate:
    def run(self, complete, repeats=1):
        return baseline.evaluate(baseline.cases(REFERENCE), complete, repeats)

    def test_an_oracle_for_the_known_claims_scores_all_ten_there(self):
        result = self.run(oracle)
        assert result["known"]["correct"] == 10 and result["known"]["total"] == 10 and result["known"]["accuracy"] == 1.0

    def test_an_answerer_that_is_always_unclear_never_asserts_anything(self):
        result = self.run(lambda query: answer("unclear"))
        assert result["near"]["decisive"] == 0 and result["near"]["false_certainty"] == 0 and result["near"]["agree"] == 10
        assert result["known"]["correct"] == 0

    def test_an_answerer_that_always_says_true_is_inconsistent_on_every_pair(self):
        result = self.run(lambda query: answer("true"))
        assert result["near"]["decisive"] == 14 and result["near"]["false_certainty"] == 10
        assert result["near"]["both_true_pairs"] == 7 and result["near"]["pairs"] == 7

    def test_a_pair_with_only_one_direction_called_true_is_not_a_both_true_pair(self):
        by_query = {case["query"]: case["id"] for case in near_cases()}
        result = self.run(lambda query: answer("true") if by_query.get(query) in {"N1", "N3", "N5"} else answer("unclear"))
        assert result["near"]["both_true_pairs"] == 0 and result["near"]["decisive"] == 3

    def test_false_certainty_counts_decisive_answers_where_the_data_was_inconclusive(self):
        by_query = {case["query"]: case["id"] for case in near_cases()}

        def complete(query):
            return answer("true") if by_query.get(query) in {"N1", "N2", "N11"} else answer("unclear")

        result = self.run(complete)
        assert result["near"]["decisive"] == 3 and result["near"]["false_certainty"] == 2

    def test_the_agreement_counts_the_same_verdict_as_the_data(self):
        reference_text = {case["query"]: REFERENCE[case["id"]] for case in near_cases()}

        def complete(query):
            verdict = reference_text.get(query)
            return answer({"replicated": "true", "contradicted": "false"}.get(verdict, "unclear")) if verdict else oracle(query)

        result = self.run(complete)
        assert result["near"]["agree"] == 13 and result["near"]["decisive"] == 3

    def test_repeats_multiply_the_samples(self):
        calls = []
        self.run(lambda query: calls.append(query) or answer("unclear"), repeats=3)
        assert len(calls) == 24 * 3
        assert self.run(lambda query: answer("unclear"), repeats=3)["known"]["total"] == 30

    def test_invalid_answers_are_counted_and_never_correct(self):
        result = self.run(lambda query: "no idea")
        assert result["invalid"] == 24 and result["known"]["correct"] == 0

    def test_a_failing_call_counts_as_invalid(self):
        def complete(query):
            raise RuntimeError("quota")

        assert self.run(complete)["invalid"] == 24

    def test_the_result_is_plain_json(self):
        json.dumps(self.run(oracle))


class TestSystemNumbers:
    def test_the_system_row_is_taken_from_the_stored_campaign(self, monkeypatch):
        monkeypatch.setattr(baseline.store, "load_analysis", lambda campaign: {"claims": [{"id": case["id"], "verdict": case["expected"]} for case in CASES]})
        assert baseline.system_known("benchmark-default") == {"correct": 10, "total": 10, "accuracy": 1.0}

    def test_a_wrong_system_verdict_is_not_counted(self, monkeypatch):
        claims = [{"id": case["id"], "verdict": "inconclusive"} for case in CASES]
        monkeypatch.setattr(baseline.store, "load_analysis", lambda campaign: {"claims": claims})
        assert baseline.system_known("benchmark-default")["correct"] == 0

    def test_a_missing_campaign_is_refused(self, monkeypatch):
        monkeypatch.setattr(baseline.store, "load_analysis", lambda campaign: None)
        with pytest.raises(ValueError, match="no stored analysis"):
            baseline.system_known("nope")

    def test_the_reference_comes_from_the_near_campaign(self, monkeypatch):
        monkeypatch.setattr(baseline.store, "load_analysis", lambda campaign: {"claims": [{"id": "N1", "verdict": "inconclusive"}]})
        assert baseline.reference_from("near-default") == {"N1": "inconclusive"}


class TestCommandLine:
    def test_it_prints_a_comparison_and_writes_the_file(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(baseline, "reference_from", lambda campaign: REFERENCE)
        monkeypatch.setattr(baseline, "system_known", lambda campaign: {"correct": 10, "total": 10, "accuracy": 1.0})
        monkeypatch.setattr(baseline, "make_complete", lambda model: oracle)
        target = tmp_path / "out.json"
        assert baseline.main(["--repeats", "2", "--out", str(target)]) == 0
        output = capsys.readouterr().out
        assert "known claims" in output and "false certainty" in output.lower()
        saved = json.loads(target.read_text(encoding="utf-8"))
        assert saved["repeats"] == 2 and saved["model"] == baseline.DEFAULT_MODEL and saved["llm"]["known"]["total"] == 20 and saved["system"]["known"]["correct"] == 10

    def test_a_bad_repeat_count_is_refused(self, capsys):
        assert baseline.main(["--repeats", "0"]) == 2
