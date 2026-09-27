"""Offline prompt-contract tests, not a claim about live model abstention behavior."""
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from judge import ASSESSABILITY_HIERARCHY, build_prompt, attach_saved_result
from run_openai_judge import load_benchmark
from judge_regression import run_regression
from openai_judge import OpenAIJudge
from evaluate import read_jsonl


class JudgeV2Tests(unittest.TestCase):
    def test_v1_prompts_and_benchmark_unchanged(self):
        golden = json.loads((ROOT / "tests/judge_v1_golden.json").read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256((ROOT / "tests/judge_examples.jsonl").read_bytes()).hexdigest(), golden["benchmark_sha256"])
        examples, rubrics, requests = load_benchmark("judge-v1")
        self.assertEqual(len(examples), 12)
        self.assertEqual(len(requests), 16)
        for request in requests:
            digest = hashlib.sha256(json.dumps(build_prompt(request, rubrics), ensure_ascii=False).encode("utf-8")).hexdigest()
            self.assertEqual(digest, golden["prompt_sha256"][request.case_id + ":" + request.dimension])

    def test_gate_applies_to_every_dimension_without_case_exceptions(self):
        _, rubrics, requests = load_benchmark("judge-v2")
        for request in requests:
            request = replace(request, case_id="unseen-case", case_specification={}, context_complete=False)
            messages = build_prompt(request, rubrics)
            self.assertIn(ASSESSABILITY_HIERARCHY, messages[0]["content"])
            self.assertLess(messages[0]["content"].index("First determine"), messages[0]["content"].index("After the assessability gate:"))
            trusted = json.loads(messages[1]["content"])
            self.assertEqual(trusted["prompt_version"], "judge-v2")
            self.assertEqual(trusted["rubric_version"], "v2")
            self.assertIn("Only after assessability", trusted["rubric"]["pass"])
            self.assertIn("Only after assessability", trusted["rubric"]["fail"])
            self.assertNotIn("JV04", messages[0]["content"])
            self.assertNotIn("JV12", json.dumps(trusted["rubric"]))

    def test_missing_requirements_and_context_distinction_explicit(self):
        _, rubrics, _ = load_benchmark("judge-v2")
        for rubric in rubrics.values():
            gate = rubric["assessability_first"]
            self.assertIn("Missing, null, or unspecified requirements must NOT be interpreted as automatically satisfied", gate)
            self.assertIn("Unavailable evidence is NOT evidence that a claim is unsupported", gate)
            self.assertIn("context_complete=true", gate)
            self.assertIn("Missing context irrelevant to the requested dimension does not automatically prevent assessment", gate)
        self.assertIn("requires UNASSESSABLE, not FAIL", rubrics["factual_grounding"]["rules"])

    def test_untrusted_message_identical_across_versions(self):
        examples1, rules1, req1 = load_benchmark("judge-v1")
        examples2, rules2, req2 = load_benchmark("judge-v2")
        self.assertEqual(examples1, examples2)
        for a, b in zip(req1, req2):
            self.assertEqual(build_prompt(a, rules1)[2], build_prompt(b, rules2)[2])

    def test_v2_metadata_and_no_forced_abstention(self):
        _, rubrics, requests = load_benchmark("judge-v2")
        request = replace(requests[0], case_id="unseen", dimension="factual_grounding", context_complete=False)
        client = Mock()
        # A wrong semantic judgment remains valid JSON and must be exposed, not repaired.
        raw = json.dumps(dict(dimension=request.dimension, verdict="FAIL", evidence=None, reason="Mock unsupported claim."))
        client.responses.create.return_value = SimpleNamespace(model="mock", usage=None, status="completed", output=[], output_text=raw)
        record = OpenAIJudge(client, "gpt-4.1-mini-2025-04-14", rubrics).judge(request)
        self.assertEqual(record["observed_verdict"], "FAIL")
        self.assertEqual(record["prompt_version"], "judge-v2")
        self.assertEqual(record["rubric_version"], "v2")
        response = {"id": request.case_id, "text": request.candidate_response}
        attach_saved_result(response, request, raw, source="mock")
        self.assertEqual(response["judge_metadata"][request.dimension]["prompt_version"], "judge-v2")

    def test_abstention_disagreements_remain_detectable(self):
        examples, rubrics, _ = load_benchmark("judge-v2")
        outputs = read_jsonl(ROOT / "tests/saved_judge_outputs.jsonl")
        for row in outputs:
            raw = json.loads(row["raw_result"])
            if row["id"] == "JV04:factual_grounding": raw["verdict"] = "FAIL"
            if row["id"] == "JV12:language_adherence": raw["verdict"] = "PASS"
            row["raw_result"] = json.dumps(raw)
        result, _, _ = run_regression(examples, outputs, rubrics)
        self.assertEqual(result["matches"], 14)
        self.assertEqual(result["disagreement_case_ids"], ["JV04", "JV12"])
        self.assertEqual(result["confusion_matrix"]["UNASSESSABLE"], {"PASS": 1, "FAIL": 1, "UNASSESSABLE": 0})

    def test_wrong_saved_version_rejected(self):
        examples, rubrics, _ = load_benchmark("judge-v2")
        outputs = read_jsonl(ROOT / "tests/saved_judge_outputs.jsonl")
        outputs[0]["prompt_version"] = "judge-v1"
        with self.assertRaisesRegex(ValueError, "version"):
            run_regression(examples, outputs, rubrics)


if __name__ == "__main__":
    unittest.main()
