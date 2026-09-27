"""Render an evaluation result as JSON and Markdown."""
import argparse
import json
from pathlib import Path


def percentage(value):
    return "N/A" if value is None else f"{value:.1%}"


def markdown(result):
    lines = ["# DarijaDoc offline evaluation", "",
             "Scores describe supplied responses and annotations, not validated clinical performance.", "",
             f"Cases: {result['case_count']}. Saved responses: {result['response_count']}.",
             f"Assessment sources: {', '.join(result['assessment_sources']) or 'none'}.", "",
             "| Metric | Assessed / eligible | Coverage | Pass rate | Fail | Unassessable |",
             "|---|---:|---:|---:|---:|---:|"]
    for name, m in result["metrics"].items():
        lines.append(f"| {name} | {m['assessed']} / {m['eligible']} | {percentage(m['coverage'])} | {percentage(m['pass_rate'])} | {m['failed']} | {m['unassessable']} |")
    u = result["urgency"]
    lines += ["", "## Urgency", "", f"Assessed: {u['assessed']} / {u['eligible']}; coverage: {percentage(u['coverage'])}.",
              f"Precision: {percentage(u['precision'])} (predicted-positive denominator: {u['precision_denominator']}); "
              f"recall: {percentage(u['recall'])} (actual-positive denominator: {u['recall_denominator']}); F1: {percentage(u['f1'])}.",
              f"Confusion matrix: {u['confusion_matrix']}.",
              f"Pending labels: {', '.join(u['pending_ids']) or 'none'}.",
              f"Invalid/missing predictions: {', '.join(u['invalid_prediction_ids']) or 'none'}.",
              f"False positives: {', '.join(u['false_positive_ids']) or 'none observed'}; false negatives: {', '.join(u['false_negative_ids']) or 'none observed'}.",
              "Zero counts with zero coverage are not evidence of safety.", "", "## Cross-language consistency", ""]
    for row in result["consistency"]:
        lines.append(f"- {row['scenario_id']} / {row['axis']}: {row['status']}. {row['reason']} "
                     + "; ".join(f"{i}={v}" for i, v in zip(row['case_ids'], row['values'])))
    for heading, key in (("Critical failures", "critical_failures"), ("All failed checks", "failures"),
                         ("Judge errors (not candidate failures)", "judge_errors"), ("Rubric abstentions", "rubric_abstentions")):
        lines += ["", f"## {heading}", ""]
        lines += [f"- {f['id']} / {f['dimension']}: {f['reason']}" for f in result.get(key, [])] or ["None observed."]
    lines += ["", "Rubric rates use supplied evidence-backed assessments. Consistency measures agreement, not correctness.",
              "Document fidelity counts source fields using explicit numeric/interval rules or exact text. Document representation separately checks opted-in exact reproduction; its failures are noncritical. Other case checks count applicable assessments. No aggregate safety score is inferred.", ""]
    return "\n".join(lines)


def write_reports(result, prefix):
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path, md_path = prefix.with_suffix(".json"), prefix.with_suffix(".md")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown(result), encoding="utf-8")
    return json_path, md_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_reports(json.loads(args.result.read_text(encoding="utf-8")), args.output)
