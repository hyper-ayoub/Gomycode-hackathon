import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluate import evaluate, metric, read_jsonl, urgency_metrics, parse_numeric_fact
from report import markdown


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.cases = read_jsonl(ROOT / "cases.jsonl")
        self.responses = read_jsonl(ROOT / "tests" / "fabricated_responses.jsonl")
        self.rubrics = json.loads((ROOT / "rubrics.json").read_text(encoding="utf-8"))

    def test_fixture_detects_failures_and_passes(self):
        result = evaluate(self.cases, self.responses, self.rubrics)
        self.assertEqual(result["case_count"], 20)
        self.assertEqual(result["metrics"]["document_fidelity"]["failed"], 0)
        self.assertEqual(result["metrics"]["document_fidelity"]["passed"], 10)
        self.assertEqual(result["metrics"]["document_representation"]["failed"], 1)
        self.assertFalse(any(f["id"] == "DOC_01" for f in result["critical_failures"]))
        self.assertEqual(result["metrics"]["language_consistency"]["failed"], 3)
        self.assertEqual(result["metrics"]["language_consistency"]["passed"], 2)
        self.assertTrue(any(f["id"] == "SAFE_01" for f in result["critical_failures"]))
        self.assertFalse(any(f["id"].startswith("URG_") for f in result["failures"]))
        self.assertIn("Pending labels: URG_01, URG_02", markdown(result))

    def test_absent_annotations_not_passes(self):
        responses = copy.deepcopy(self.responses)
        responses[0]["assessments"] = {}
        result = evaluate(self.cases, responses, self.rubrics)
        self.assertEqual(result["metrics"]["diagnosis_restraint"]["unassessable"], 1)
        self.assertEqual(result["consistency"][0]["status"], "UNASSESSABLE")

    def test_fake_evidence_rejected(self):
        self.responses[0]["assessments"]["diagnosis_restraint"]["evidence"] = "not in response"
        result = evaluate(self.cases, self.responses, self.rubrics)
        self.assertEqual(result["cases"][0]["checks"][1]["status"], "UNASSESSABLE")

    def test_missing_response_and_facts(self):
        result = evaluate(self.cases, [], self.rubrics)
        self.assertEqual(result["metrics"]["response_availability"]["failed"], 18)
        self.assertIsNone(result["metrics"]["diagnosis_restraint"]["pass_rate"])
        for r in self.responses:
            r.pop("extracted_facts", None)
        result = evaluate(self.cases, self.responses, self.rubrics)
        self.assertEqual(result["metrics"]["document_fidelity"]["unassessable"], 10)

    def test_pending_labels_never_scored(self):
        cases = copy.deepcopy(self.cases)
        cases[-1]["expected_urgency"] = "urgent"
        result = urgency_metrics(cases, {"URG_02": {"text": "fixture", "urgency": "urgent"}})
        self.assertEqual(result["assessed"], 0)
        self.assertIsNone(result["recall"])

    def test_confusion_matrix_arithmetic_with_abstract_labels(self):
        cases = [dict(id=str(i), urgency_benchmark=True, review_status="approved",
                      label_provenance={"source": "unit-test-only", "reviewer": "test"}, expected_urgency=label)
                 for i, label in enumerate(["urgent", "urgent", "nonurgent", "nonurgent", "urgent"])]
        saved = {str(i): {"text": "abstract fixture", "urgency": label}
                 for i, label in enumerate(["urgent", "nonurgent", "urgent", "nonurgent", "invalid"])}
        result = urgency_metrics(cases, saved)
        self.assertEqual(result["confusion_matrix"], dict(tp=1, tn=1, fp=1, fn=1))
        self.assertEqual(result["precision"], .5)
        self.assertEqual(result["recall"], .5)
        self.assertEqual(result["f1"], .5)
        self.assertEqual(result["coverage"], .8)
        self.assertEqual(result["false_negative_ids"], ["1"])
        self.assertEqual(result["invalid_prediction_ids"], ["4"])

    def test_no_assessments_means_undefined_rate(self):
        self.assertIsNone(metric(["UNASSESSABLE"])["pass_rate"])
        self.assertEqual(metric(["PASS", "FAIL", "UNASSESSABLE"])["coverage"], 2/3)

    def doc_checks(self, key, value):
        response = next(r for r in self.responses if r["id"] == "DOC_01")
        response["extracted_facts"][key] = value
        result = evaluate(self.cases, self.responses, self.rubrics)
        return next(c for c in result["cases"] if c["id"] == "DOC_01")["checks"]

    def test_actual_numeric_change_is_critical(self):
        checks = self.doc_checks("value", "12.8")
        self.assertTrue(any(c["dimension"] == "document_fidelity" and c["critical"] for c in checks))
        self.assertFalse(any(c["dimension"] == "document_representation" and c["critical"] for c in checks))

    def test_interval_equivalence_and_meaning_changes(self):
        for value, fails in [("10–15 uX", False), ("10.00–15.01 uX", True),
                             ("9.99–15.00 uX", True), ("10.00–15.00 ux", True)]:
            with self.subTest(value=value):
                checks = self.doc_checks("reference_interval", value)
                self.assertEqual(any(c["critical"] for c in checks), fails)

    def test_units_are_exact(self):
        checks = self.doc_checks("unit", "ux")
        self.assertTrue(any(c["critical"] for c in checks))

    def test_strict_decimal_parsing(self):
        for value in ["12,30", "1,230", "1e1", "NaN", "Infinity", "12.3 uX", " 12.3", "12.3\n", "<12.3", "١٢.٣", 12.3, True, None]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_numeric_fact(value, "numeric_fact")
                checks = self.doc_checks("value", value)
                self.assertTrue(any(c["dimension"] == "document_fidelity" and c["status"] == "FAIL" for c in checks))
                self.assertFalse(any(c["critical"] for c in checks))
        for value in ["10-15 uX", "15–10 uX", "10–15", "10–15 uX extra"]:
            with self.assertRaises(ValueError):
                parse_numeric_fact(value, "interval_fact")

    def test_representation_is_opt_in_and_text_is_not_numeric(self):
        for c in self.cases:
            for rule in c.get("deterministic_checks", []):
                rule.pop("require_exact_text", None)
        checks = self.doc_checks("name", "12.30")
        self.assertFalse(any(c["dimension"] == "document_representation" for c in checks))
        self.assertTrue(any(c["dimension"] == "document_fidelity" and c["status"] == "FAIL" for c in checks))
        self.assertFalse(any(c["critical"] for c in checks))


if __name__ == "__main__":
    unittest.main()
