"""ONLY the handcrafted judge-validation benchmark. Defaults to a no-network preview."""
import argparse
import json
import os
from pathlib import Path

from evaluate import read_jsonl
from judge import JudgeRequest
from judge_regression import run_regression, regression_markdown
from openai_judge import OpenAIJudge, create_client, request_options

ROOT = Path(__file__).resolve().parent


def load_benchmark(judge_version="judge-v1"):
    # Deliberately no --cases/--responses override: never load cases.jsonl or urgency slots.
    examples = read_jsonl(ROOT / "tests/judge_examples.jsonl")
    files = {"judge-v1": "rubrics.json", "judge-v2": "rubrics_v2.json"}
    if judge_version not in files:
        raise ValueError("Unsupported judge version")
    rubrics = json.loads((ROOT / files[judge_version]).read_text(encoding="utf-8"))
    if len(examples) != 12 or sum(len(e["expected"]) for e in examples) != 16:
        raise ValueError("This command requires the approved 12-example, 16-judgment benchmark")
    requests = []
    for example in examples:
        for dim in example["expected"]:
            requests.append(JudgeRequest(case_id=example["id"], dimension=dim, rubric_version=rubrics[dim]["version"],
                            **{k: example[k] for k in ("case_specification", "context_complete", "input", "document_facts", "candidate_response")}))
    return examples, rubrics, requests


def collect(examples, requests, adapter, path):
    expected = {f"{e['id']}:{d}": v for e in examples for d, v in e["expected"].items()}
    outputs = []
    with path.open("x", encoding="utf-8") as stream:
        for request in requests:
            record = adapter.judge(request)
            record["expected_verdict"] = expected[record["id"]]
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            outputs.append(record)
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=os.environ.get("OPENAI_JUDGE_MODEL"))
    parser.add_argument("--judge-version", choices=("judge-v1", "judge-v2"), default="judge-v1")
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/openai_judge_validation")
    parser.add_argument("--execute", action="store_true", help="Explicitly enable 16 billable requests")
    args = parser.parse_args(argv)
    if not args.model:
        parser.error("Set --model or OPENAI_JUDGE_MODEL")
    examples, rubrics, requests = load_benchmark(args.judge_version)
    options = [request_options(r, rubrics, args.model, args.max_output_tokens) for r in requests]
    preview = {"mode": "execute" if args.execute else "preview_only_no_network",
               "model": args.model, "examples": len(examples), "judgments": len(requests),
               "prompt_version": args.judge_version, "temperature": options[0].get("temperature", "omitted"),
               "structured_output": "strict json_schema + local JudgeResult validation",
               "max_output_tokens_per_request": args.max_output_tokens,
               "max_total_output_tokens": len(requests) * args.max_output_tokens,
               "serialized_request_characters": sum(len(json.dumps(o, ensure_ascii=False)) for o in options),
               "automatic_retries": 0, "timeout_seconds": 60}
    print(json.dumps(preview, indent=2))
    if not args.execute:
        return
    paths = [Path(str(args.output) + suffix) for suffix in (".jsonl", ".json", ".md")]
    if any(path.exists() for path in paths):
        parser.error("Output exists; choose a fresh --output prefix to preserve the earlier run")
    try:
        client = create_client()
    except (ValueError, ImportError):
        parser.error("Requires the OpenAI SDK and OPENAI_API_KEY in the process environment; no key is printed or loaded from .env")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        outputs = collect(examples, requests, OpenAIJudge(client, args.model, rubrics, args.max_output_tokens), paths[0])
    finally:
        client.close()
    result, _, _ = run_regression(examples, outputs, rubrics, source=f"openai:{args.model}:{args.judge_version}")
    result.update(provider="openai", title="LLM judge validation against handcrafted behavioral expectations",
                  configuration=preview, records=outputs)
    paths[1].write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths[2].write_text(regression_markdown(result), encoding="utf-8")
    print(regression_markdown(result))


if __name__ == "__main__":
    main()
