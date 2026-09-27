import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from judge import JudgeRequest, validate_result, build_prompt, attach_saved_result, SYSTEM_PROMPT
from judge_regression import run_regression
from evaluate import evaluate, read_jsonl


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.rubrics = json.loads((ROOT / "rubrics.json").read_text(encoding="utf-8"))
        self.examples = read_jsonl(ROOT / "tests/judge_examples.jsonl")
        self.outputs = read_jsonl(ROOT / "tests/saved_judge_outputs.jsonl")
        self.request = JudgeRequest("TEST", "diagnosis_restraint", "v1", {}, True, "input", [], "No diagnosis asserted.")
        self.raw = dict(dimension="diagnosis_restraint", verdict="PASS", evidence=None, reason="No diagnosis asserted.")

    def test_valid_and_nullable_results(self):
        for verdict in ("PASS", "FAIL", "UNASSESSABLE"):
            for evidence in (None, "No diagnosis"):
                raw = dict(self.raw, verdict=verdict, evidence=evidence)
                result = validate_result(json.dumps(raw), self.request.dimension, self.request.candidate_response)
                self.assertEqual(result.verdict, verdict)
                self.assertEqual(result.evidence, evidence)

    def test_malformed_results(self):
        invalid = ["not json", "```json\n{}\n```", "[]", "null", {},
                   dict(self.raw, extra=True), {k:v for k,v in self.raw.items() if k != "evidence"},
                   dict(self.raw, verdict="pass"), dict(self.raw, verdict=1),
                   dict(self.raw, dimension="factual_grounding"), dict(self.raw, reason="  "),
                   dict(self.raw, reason=None), dict(self.raw, evidence=""),
                   '{"dimension":"diagnosis_restraint","verdict":"FAIL","verdict":"PASS","evidence":null,"reason":"x"}']
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_result(raw, self.request.dimension, self.request.candidate_response)

    def test_nonverbatim_evidence(self):
        for evidence in ("Invented quotation", "no diagnosis", "No  diagnosis", 123):
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                validate_result(dict(self.raw, evidence=evidence), self.request.dimension, self.request.candidate_response)

    def test_injection_is_only_in_untrusted_message(self):
        for id in ("JV11", "JV12"):
            example = next(e for e in self.examples if e["id"] == id)
            request = JudgeRequest(case_id=id, dimension=next(iter(example["expected"])), rubric_version="v1",
                                   **{k:example[k] for k in ("case_specification", "context_complete", "input", "document_facts", "candidate_response")})
            messages = build_prompt(request, self.rubrics)
            self.assertEqual(messages[0]["content"], SYSTEM_PROMPT)
            self.assertEqual([m["role"] for m in messages], ["system", "developer", "user"])
            self.assertNotIn(example["candidate_response"], messages[1]["content"])
            self.assertEqual(json.loads(messages[2]["content"])["candidate_response"], example["candidate_response"])
            self.assertNotIn("expected", messages[1]["content"])

    def test_unknown_dimension_and_version_rejected(self):
        with self.assertRaises(ValueError):
            JudgeRequest("TEST", "urgency", "v1", {}, True, "", [], "")
        altered = copy.deepcopy(self.rubrics)
        altered["diagnosis_restraint"]["version"] = "v2"
        with self.assertRaises(ValueError):
            build_prompt(self.request, altered)

    def evaluate_attached(self, raw=None, execution_error=None):
        response = dict(id="TEST", text=self.request.candidate_response)
        attach_saved_result(response, self.request, raw, source="test", execution_error=execution_error)
        cases = [dict(id="TEST", scenario_id="TEST", category="test", language="fr", rubrics=["diagnosis_restraint"])]
        return evaluate(cases, [response], self.rubrics), response

    def test_execution_error_not_candidate_failure(self):
        result, _ = self.evaluate_attached(execution_error="mock timeout")
        self.assertEqual(result["failures"], [])
        self.assertEqual(len(result["judge_errors"]), 1)
        self.assertEqual(result["rubric_abstentions"], [])
        self.assertEqual(result["metrics"]["diagnosis_restraint"]["assessed"], 0)

    def test_abstention_is_not_execution_error(self):
        raw = dict(self.raw, verdict="UNASSESSABLE", reason="Evaluation attachment missing.")
        result, _ = self.evaluate_attached(raw)
        self.assertEqual(result["judge_errors"], [])
        self.assertEqual(result["rubric_abstentions"][0]["reason"], raw["reason"])
        self.assertEqual(result["failures"], [])

    def test_invalid_output_not_candidate_failure(self):
        result, _ = self.evaluate_attached(dict(self.raw, evidence="fabricated"))
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["judge_errors"][0]["judge_error_kind"], "invalid_output")

    def test_null_evidence_pass_and_omission_fail_integrate(self):
        for verdict in ("PASS", "FAIL"):
            result, response = self.evaluate_attached(dict(self.raw, verdict=verdict))
            self.assertEqual(result["cases"][0]["checks"][1]["status"], verdict)
            self.assertEqual(result["judge_errors"], [])
            with self.assertRaises(ValueError):
                attach_saved_result(response, self.request, self.raw, source="second judge")

    def test_saved_regression(self):
        result, _, traces = run_regression(self.examples, self.outputs, self.rubrics)
        self.assertEqual(result["example_count"], 12)
        self.assertEqual(result["judgment_count"], 16)
        self.assertEqual(result["agreement"], 1)
        self.assertEqual(result["invalid_output_count"], 0)
        self.assertEqual(result["confusion_matrix"]["UNASSESSABLE"]["UNASSESSABLE"], 2)
        self.assertEqual(next(t for t in traces if t["id"] == "JV11:diagnosis_restraint")["validated_result"]["verdict"], "FAIL")

    def test_stress_regression(self):
        outputs = read_jsonl(ROOT / "tests/saved_judge_outputs_stress.jsonl")
        result, _, _ = run_regression(self.examples, outputs, self.rubrics)
        self.assertEqual(result["invalid_output_count"], 1)
        self.assertEqual(result["execution_error_count"], 1)
        self.assertEqual(result["disagreement_case_ids"], ["JV03"])
        self.assertEqual(result["valid_outputs"], 14)
        self.assertEqual(result["matches"], 13)
        self.assertEqual(result["confusion_matrix"]["FAIL"]["PASS"], 1)

    def test_missing_output_not_abstention_in_matrix(self):
        result, _, _ = run_regression(self.examples, [], self.rubrics)
        self.assertEqual(result["execution_error_count"], 16)
        self.assertIsNone(result["agreement"])
        self.assertEqual(sum(sum(r.values()) for r in result["confusion_matrix"].values()), 0)


if __name__ == "__main__":
    unittest.main()
