"""Isolated OpenAI Responses adapter. Client is created only for an explicit live run."""
import os
from dataclasses import asdict

from judge import prompt_version_for, VERDICTS, build_prompt, validate_result


def result_schema(dimension):
    return {"type": "object", "additionalProperties": False,
            "properties": {"dimension": {"type": "string", "enum": [dimension]},
                           "verdict": {"type": "string", "enum": list(VERDICTS)},
                           "evidence": {"type": ["string", "null"]},
                           "reason": {"type": "string"}},
            "required": ["dimension", "verdict", "evidence", "reason"]}


def request_options(request, rubrics, model, max_output_tokens=512):
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Set --model or OPENAI_JUDGE_MODEL")
    if type(max_output_tokens) is not int or max_output_tokens < 1:
        raise ValueError("max_output_tokens must be positive")
    options = {"model": model, "input": build_prompt(request, rubrics),
               "text": {"format": {"type": "json_schema", "name": "judge_result", "strict": True,
                                   "schema": result_schema(request.dimension)}},
               "max_output_tokens": max_output_tokens, "store": False, "service_tier": "default"}
    # Documented non-reasoning model; do not assume sampling support for other models.
    if model in ("gpt-4.1-mini", "gpt-4.1-mini-2025-04-14"):
        options["temperature"] = 0
    return options


def create_client():
    key = os.environ.get("OPENAI_API_KEY")
    if not key or not key.strip():
        raise ValueError("OPENAI_API_KEY is not set in this process environment; .env is not loaded automatically")
    from openai import OpenAI
    # Pin the official endpoint rather than honoring an unrelated OPENAI_BASE_URL.
    # No automatic retry: at most one submitted request per judgment.
    return OpenAI(api_key=key, base_url="https://api.openai.com/v1", max_retries=0, timeout=60.0)


class OpenAIJudge:
    def __init__(self, client, model, rubrics, max_output_tokens=512):
        self.client, self.model, self.rubrics = client, model, rubrics
        self.max_output_tokens = max_output_tokens

    def judge(self, request):
        """Return an audit record; validate_result remains the JudgeResult boundary."""
        options = request_options(request, self.rubrics, self.model, self.max_output_tokens)
        record = {"id": f"{request.case_id}:{request.dimension}", "case_id": request.case_id,
                  "dimension": request.dimension, "observed_verdict": None, "evidence": None, "reason": None,
                  "validation_status": "execution_error", "requested_model": self.model,
                  "model_identifier": self.model, "rubric_version": request.rubric_version,
                  "prompt_version": prompt_version_for(request.rubric_version), "execution_error": None, "validation_error": None,
                  "generation_settings": {k: options[k] for k in ("max_output_tokens", "store", "service_tier", "temperature") if k in options}}
        try:
            response = self.client.responses.create(**options)
        except Exception as exc:
            # Never persist exception text, headers, or request bodies: they can contain credentials.
            status = getattr(exc, "status_code", None)
            record["execution_error"] = "OpenAI request failed" + (f" (HTTP {status})" if type(status) is int else "")
            return record
        record["model_identifier"] = response.model
        usage = getattr(response, "usage", None)
        if usage is not None:
            record["usage"] = {k: getattr(usage, k, None) for k in ("input_tokens", "output_tokens", "total_tokens")}
        if response.status != "completed":
            record["execution_error"] = "OpenAI response was not completed (including truncation); no verdict accepted"
            return record
        if any(getattr(part, "type", None) == "refusal" for item in response.output
               for part in getattr(item, "content", [])):
            record["execution_error"] = "OpenAI refused the judgment; no rubric verdict returned"
            return record
        raw = response.output_text
        # Defense in depth: never persist an accidental credential echo.
        key = os.environ.get("OPENAI_API_KEY")
        if key and key in raw:
            record["execution_error"] = "Credential-like content detected; output discarded"
            return record
        record["raw_result"] = raw
        try:
            result = validate_result(raw, request.dimension, request.candidate_response)
        except (ValueError, TypeError):
            record["validation_status"] = "invalid_output"
            record["validation_error"] = "JudgeResult schema or exact-evidence validation failed"
            return record
        record.update(observed_verdict=result.verdict, evidence=result.evidence, reason=result.reason,
                      validation_status="valid", validated_result=asdict(result))
        return record
