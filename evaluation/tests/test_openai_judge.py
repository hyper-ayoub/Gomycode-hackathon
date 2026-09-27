import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from judge import build_prompt
from judge_regression import run_regression, regression_markdown
from openai_judge import OpenAIJudge, request_options, create_client
from run_openai_judge import load_benchmark, collect, main


class OpenAIJudgeTests(unittest.TestCase):
    def setUp(self):
        self.examples, self.rubrics, self.requests = load_benchmark()
        self.request = self.requests[0]
        self.client = Mock()
        self.adapter = OpenAIJudge(self.client, "gpt-4.1-mini-2025-04-14", self.rubrics)

    def output(self, **overrides):
        result = dict(dimension=self.request.dimension, verdict="PASS", evidence=None, reason="No diagnosis asserted.")
        result.update(overrides)
        return json.dumps(result, ensure_ascii=False)

    def response(self, raw=None, **overrides):
        data = dict(model="gpt-4.1-mini-2025-04-14", status="completed", output=[],
                    output_text=raw if raw is not None else self.output(),
                    usage=SimpleNamespace(input_tokens=100, output_tokens=30, total_tokens=130))
        data.update(overrides)
        self.client.responses.create.return_value = SimpleNamespace(**data)

    def test_original_prompt_and_strict_schema(self):
        self.response()
        record = self.adapter.judge(self.request)
        sent = self.client.responses.create.call_args.kwargs
        self.assertEqual(sent["input"], build_prompt(self.request, self.rubrics))
        self.assertEqual(sent["temperature"], 0)
        self.assertFalse(sent["store"])
        self.assertTrue(sent["text"]["format"]["strict"])
        self.assertFalse(sent["text"]["format"]["schema"]["additionalProperties"])
        self.assertEqual(record["validation_status"], "valid")
        self.assertEqual(record["observed_verdict"], "PASS")
        self.assertEqual(record["usage"]["total_tokens"], 130)
        self.assertEqual(record["prompt_version"], "judge-v1")
        self.assertNotIn("expected_verdict", sent)

    def test_local_validator_still_rejects_bad_output(self):
        for raw in ("not JSON", self.output(evidence="fabricated evidence"),
                    self.output(dimension="language_adherence"), self.output(verdict="GOOD")):
            with self.subTest(raw=raw):
                self.response(raw)
                record = self.adapter.judge(self.request)
                self.assertEqual(record["validation_status"], "invalid_output")
                self.assertIsNone(record["observed_verdict"])
                self.assertIsNone(record["execution_error"])

    def test_null_evidence_and_abstention(self):
        self.response(self.output(verdict="UNASSESSABLE", reason="Context missing."))
        record = self.adapter.judge(self.request)
        self.assertEqual(record["validation_status"], "valid")
        self.assertEqual(record["observed_verdict"], "UNASSESSABLE")
        self.assertIsNone(record["execution_error"])

    def test_unrecognized_model_omits_sampling_parameters(self):
        options = request_options(self.request, self.rubrics, "another-model")
        self.assertNotIn("temperature", options)
        self.assertNotIn("seed", options)
        self.assertNotIn("reasoning", options)

    def test_refusal_and_truncation_not_verdicts(self):
        self.response(output=[SimpleNamespace(content=[SimpleNamespace(type="refusal")])])
        self.assertEqual(self.adapter.judge(self.request)["validation_status"], "execution_error")
        self.response(status="incomplete")
        record = self.adapter.judge(self.request)
        self.assertEqual(record["validation_status"], "execution_error")
        self.assertIsNone(record["observed_verdict"])

    def test_api_error_does_not_log_secret_or_retry(self):
        error = RuntimeError("fake-secret-value in headers or server exception")
        error.status_code = 401
        self.client.responses.create.side_effect = error
        record = self.adapter.judge(self.request)
        self.assertNotIn("fake-secret-value", json.dumps(record))
        self.assertIn("401", record["execution_error"])
        self.client.responses.create.assert_called_once()

    def test_credential_echo_discarded(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-secret-value"}):
            self.response(self.output(reason="fake-secret-value"))
            record = self.adapter.judge(self.request)
            self.assertNotIn("fake-secret-value", json.dumps(record))
            self.assertNotIn("raw_result", record)

    def test_client_environment_only_with_mock_sdk(self):
        fake_sdk = SimpleNamespace(OpenAI=Mock())
        with patch.dict(sys.modules, {"openai": fake_sdk}), patch.dict(os.environ, {"OPENAI_API_KEY": "fake-test-key"}):
            create_client()
            kwargs = fake_sdk.OpenAI.call_args.kwargs
            self.assertEqual(kwargs["api_key"], "fake-test-key")
            self.assertEqual(kwargs["max_retries"], 0)
            self.assertEqual(kwargs["base_url"], "https://api.openai.com/v1")
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            create_client()

    def test_preview_never_constructs_client(self):
        with patch("run_openai_judge.create_client", side_effect=AssertionError("No network allowed")) as factory:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                main(["--model", "gpt-4.1-mini-2025-04-14"])
            self.assertIn("preview_only_no_network", out.getvalue())
            factory.assert_not_called()

    def test_mock_benchmark_collection_report(self):
        def fake_create(**kwargs):
            dim = kwargs["text"]["format"]["schema"]["properties"]["dimension"]["enum"][0]
            return SimpleNamespace(model="mock-model", status="completed", output=[], usage=None,
                output_text=json.dumps(dict(dimension=dim, verdict="PASS", evidence=None, reason="Mock reason.")))
        self.client.responses.create.side_effect = fake_create
        with tempfile.TemporaryDirectory() as temp:
            records = collect(self.examples, self.requests, self.adapter, Path(temp) / "saved.jsonl")
        self.assertEqual(len(records), 16)
        self.assertEqual(self.client.responses.create.call_count, 16)
        for record in records:
            self.assertIn("expected_verdict", record)
            self.assertIn("model_identifier", record)
            self.assertIn("validation_status", record)
        report, _, _ = run_regression(self.examples, records, self.rubrics, source="openai:mock")
        report["provider"] = "openai"
        rendered = regression_markdown(report)
        self.assertIn("LLM judge validation against handcrafted behavioral expectations", rendered)
        self.assertIn("JV11", rendered)
        self.assertIn("Mock reason.", rendered)
        self.assertNotIn("Fabricated outputs only", rendered)


if __name__ == "__main__":
    unittest.main()
