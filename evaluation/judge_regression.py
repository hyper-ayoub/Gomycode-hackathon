"""Run judge regression against saved outputs; never invokes a provider."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path

from evaluate import evaluate, read_jsonl
from judge import JudgeRequest, VERDICTS, attach_saved_result, build_prompt, prompt_version_for
from report import percentage, write_reports

ROOT = Path(__file__).resolve().parent


def run_regression(examples, outputs, rubrics, source="fabricated_saved_judge_output"):
    saved = {row["id"]: row for row in outputs}
    expected_ids = {f"{e['id']}:{dim}" for e in examples for dim in e["expected"]}
    if len(saved) != len(outputs) or set(saved) - expected_ids:
        raise ValueError("Duplicate or unknown saved judge output IDs")
    matrix = {v: {w: 0 for w in VERDICTS} for v in VERDICTS}
    rows, traces, cases, responses = [], [], [], []
    for example in examples:
        response = {"id": example["id"], "text": example["candidate_response"]}
        for dim, expected in example["expected"].items():
            if expected not in VERDICTS:
                raise ValueError("Invalid expected verdict")
            request = JudgeRequest(case_id=example["id"], dimension=dim, rubric_version=rubrics[dim]["version"],
                                   **{k: example[k] for k in ("case_specification", "context_complete", "input", "document_facts", "candidate_response")})
            key = f"{example['id']}:{dim}"
            output = saved.get(key)
            if output and (output.get("rubric_version", request.rubric_version) != request.rubric_version or
                           output.get("prompt_version", prompt_version_for(request.rubric_version)) != prompt_version_for(request.rubric_version)):
                raise ValueError("Saved output version does not match selected rubrics")
            error = "Saved output missing" if output is None else output.get("execution_error")
            raw = output.get("raw_result") if output else None
            result = attach_saved_result(response, request, raw, source=source,
                                         execution_error=error)
            observed = result.verdict if result else None
            error_info = response.get("judge_errors", {}).get(dim)
            rows.append({"id": key, "case_id": example["id"], "dimension": dim, "expected": expected,
                         "observed": observed, "agrees": observed == expected if result else None,
                         "error": error_info, "evidence": result.evidence if result else None,
                         "reason": result.reason if result else None})
            if result:
                matrix[expected][observed] += 1
            traces.append({"id": key, "request": asdict(request), "messages": build_prompt(request, rubrics),
                           "saved_output": output, "validated_result": asdict(result) if result else None,
                           "assessment": response.get("assessments", {}).get(dim), "error": error_info})
        cases.append({"id": example["id"], "scenario_id": example["id"], "category": "judge_validation",
                      "language": example["case_specification"].get("output_language"),
                      "input": example["input"], "rubrics": list(example["expected"]),
                      "critical_dimensions": ["diagnosis_restraint", "factual_grounding"]})
        responses.append(response)
    valid = sum(r["observed"] is not None for r in rows)
    matches = sum(r["agrees"] is True for r in rows)
    result = {"example_count": len(examples), "judgment_count": len(rows), "valid_outputs": valid,
              "coverage": valid / len(rows) if rows else None, "matches": matches,
              "agreement": matches / valid if valid else None,
              "matches_over_all_expected": matches / len(rows) if rows else None,
              "confusion_matrix": matrix,
              "invalid_output_count": sum(r["error"] is not None and r["error"]["kind"] == "invalid_output" for r in rows),
              "execution_error_count": sum(r["error"] is not None and r["error"]["kind"] == "execution_error" for r in rows),
              "disagreement_case_ids": sorted({r["case_id"] for r in rows if r["agrees"] is False}), "judgments": rows}
    candidate_report = evaluate(cases, responses, rubrics)
    for trace in traces:
        trace["final_case_report"] = next(c for c in candidate_report["cases"] if c["id"] == trace["request"]["case_id"])
    return result, candidate_report, traces


def regression_markdown(result):
    live = result.get("provider") == "openai"
    title = "LLM judge validation against handcrafted behavioral expectations" if live else "Saved judge regression"
    description = "OpenAI judge outputs compared with handcrafted expectations; not medical accuracy." if live else "Fabricated outputs only; this does not measure a real judge or clinical performance."
    lines = [f"# {title}", "", description, "",
             f"Examples: {result['example_count']}; judgments: {result['judgment_count']}.",
             f"Valid outputs: {result['valid_outputs']}; coverage: {percentage(result['coverage'])}.",
             f"Agreement among valid outputs: {result['matches']} / {result['valid_outputs']} ({percentage(result['agreement'])}).",
             f"Matches / all expected judgments: {percentage(result['matches_over_all_expected'])}.",
             f"Invalid outputs: {result['invalid_output_count']}; execution/missing-output errors: {result['execution_error_count']}.",
             f"Disagreement case IDs: {', '.join(result['disagreement_case_ids']) or 'none'}.", "",
             "Rows = expected; columns = observed. Invalid outputs/errors are excluded, not classified as UNASSESSABLE.", "",
             "| Expected | PASS | FAIL | UNASSESSABLE |", "|---|---:|---:|---:|"]
    for verdict, counts in result["confusion_matrix"].items():
        lines.append(f"| {verdict} | {counts['PASS']} | {counts['FAIL']} | {counts['UNASSESSABLE']} |")
    lines += ["", "## Errors and disagreements", ""]
    lines += [f"- {r['id']}: expected {r['expected']}, observed {r['observed']}; {r['error'] or 'verdict disagreement'}"
              for r in result["judgments"] if r["error"] or r["agrees"] is False] or ["None."]
    for row in result["judgments"]:
        if row["agrees"] is False:
            lines += [f"- {row['id']} evidence: {json.dumps(row.get('evidence'), ensure_ascii=False)}",
                      f"  Reason: {row.get('reason')}"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=Path, default=ROOT / "tests/judge_examples.jsonl")
    parser.add_argument("--outputs", type=Path, required=True)
    parser.add_argument("--judge-version", choices=("judge-v1", "judge-v2"), default="judge-v1")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/judge_regression")
    args = parser.parse_args()
    rubric_file = "rubrics.json" if args.judge_version == "judge-v1" else "rubrics_v2.json"
    rubrics = json.loads((ROOT / rubric_file).read_text(encoding="utf-8"))
    result, candidate_report, traces = run_regression(read_jsonl(args.examples), read_jsonl(args.outputs), rubrics)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(regression_markdown(result), encoding="utf-8")
    write_reports(candidate_report, str(args.output) + "_candidates")
    Path(str(args.output) + "_trace.json").write_text(json.dumps(traces, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(regression_markdown(result))


if __name__ == "__main__":
    main()
