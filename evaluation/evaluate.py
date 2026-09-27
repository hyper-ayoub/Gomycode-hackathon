"""Offline behavioral evaluation. No network calls or clinical label generation."""
import argparse
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path
from judge import validate_result

PASS, FAIL, UNASSESSABLE = "PASS", "FAIL", "UNASSESSABLE"
ROOT = Path(__file__).resolve().parent
DECIMAL_TOKEN = r"[+-]?[0-9]+(?:\.[0-9]+)?"


def parse_numeric_fact(value, kind):
    """Only explicitly typed fields; no locale inference, floats, or unit conversion."""
    if not isinstance(value, str):
        raise ValueError("Expected a string preserving the source representation")
    if kind == "numeric_fact" and re.fullmatch(DECIMAL_TOKEN, value):
        return Decimal(value)
    if kind == "interval_fact":
        match = re.fullmatch(rf"({DECIMAL_TOKEN})–({DECIMAL_TOKEN}) ([^\s]+)", value)
        if match:
            lower, upper = Decimal(match[1]), Decimal(match[2])
            if lower <= upper:
                return lower, upper, match[3]
    raise ValueError("Unsupported decimal/interval syntax")


def numeric_checks(rule, facts, available):
    expected = parse_numeric_fact(rule["value"], rule["kind"])
    actual = facts.get(rule["key"]) if isinstance(facts, dict) else None
    status, critical = UNASSESSABLE, False
    reason = f"Field {rule['key']!r}: response or structured facts unavailable."
    if available and isinstance(facts, dict):
        try:
            observed = parse_numeric_fact(actual, rule["kind"])
        except ValueError:
            status = FAIL
            reason = f"Field {rule['key']!r}: missing or unsupported value {actual!r}; no numeric meaning inferred."
        else:
            status = PASS if observed == expected else FAIL
            critical = rule.get("critical", False) and status == FAIL
            reason = f"Field {rule['key']!r}: expected {rule['value']!r}, got {actual!r}; " + (
                "numeric value/bounds and units preserved." if status == PASS else "numeric value/bounds or units changed.")
    checks = [outcome(rule["dimension"], status, reason, critical)]
    if rule.get("require_exact_text"):
        representation = UNASSESSABLE if not available or not isinstance(facts, dict) else PASS if actual == rule["value"] else FAIL
        checks.append(outcome("document_representation", representation,
                              f"Exact reproduction of {rule['key']!r}: expected {rule['value']!r}, got {actual!r}."))
    return checks


def read_jsonl(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate IDs in {path}")
    return rows


def metric(results):
    counts = Counter(results)
    assessed = counts[PASS] + counts[FAIL]
    total = len(results)
    return {"eligible": total, "assessed": assessed, "unassessable": counts[UNASSESSABLE],
            "passed": counts[PASS], "failed": counts[FAIL],
            "coverage": assessed / total if total else None,
            "pass_rate": counts[PASS] / assessed if assessed else None}


def outcome(dimension, status, reason, critical=False):
    return {"dimension": dimension, "status": status, "reason": reason,
            "critical": critical and status == FAIL}


def evaluate(cases, responses, rubrics):
    """Responses use our offline envelope, NOT an assumed backend schema.

    A future HTTP adapter only needs to create these saved response records.
    Rubric assessments are externally supplied annotations, not model scores
    inferred from keyword matching. V1 makes no judge API calls.
    """
    saved = {r["id"]: r for r in responses}
    unknown = set(saved) - {c["id"] for c in cases}
    if unknown:
        raise ValueError(f"Unknown response IDs: {sorted(unknown)}")
    results = []
    for case in cases:
        response = saved.get(case["id"], {})
        text = response.get("text")
        available = isinstance(text, str) and bool(text.strip()) and not response.get("error")
        pending = case.get("urgency_benchmark") and case.get("input") is None
        checks = [outcome("response_availability", UNASSESSABLE if pending else PASS if available else FAIL,
                          "Reserved benchmark slot; no input yet." if pending else
                          "Nonempty saved response." if available else "Missing/empty response or recorded execution error.")]
        for name in case["rubrics"]:
            annotation = response.get("assessments", {}).get(name)
            error = response.get("judge_errors", {}).get(name)
            source = response.get("assessment_sources", {}).get(name) or response.get("assessment_source")
            status, evidence = UNASSESSABLE, None
            origin, reason = "missing_assessment", "No sourced assessment supplied."
            if error:
                origin, reason = "judge_error", error["reason"]
            elif not available:
                origin, reason = "response_unavailable", "Response unavailable."
            elif annotation is not None and source:
                try:
                    if not isinstance(annotation, dict) or set(annotation) != {"status", "evidence", "reason"}:
                        raise ValueError("Invalid assessment fields")
                    result = validate_result({"dimension": name, "verdict": annotation["status"],
                                              "evidence": annotation["evidence"], "reason": annotation["reason"]}, name, text)
                    status, evidence, reason = result.verdict, result.evidence, result.reason
                    origin = "rubric_abstention" if status == UNASSESSABLE else "assessment"
                except (ValueError, TypeError) as exc:
                    origin, reason = "judge_error", str(exc)
                    error = {"kind": "invalid_output", "reason": reason}
            check = outcome(name, status, reason, name in case.get("critical_dimensions", []))
            check.update(evidence=evidence, assessment_origin=origin, assessment_source=source)
            if error:
                check["judge_error_kind"] = error["kind"]
            checks.append(check)
        for rule in case.get("deterministic_checks", []):
            if rule["kind"] in ("numeric_fact", "interval_fact"):
                checks.extend(numeric_checks(rule, response.get("extracted_facts"), available))
                continue
            status, reason = UNASSESSABLE, "Response unavailable."
            if available:
                if rule["kind"] == "exact_fact":
                    facts = response.get("extracted_facts")
                    if not isinstance(facts, dict):
                        reason = "No structured extracted_facts supplied; fidelity cannot be assessed."
                    else:
                        status = PASS if facts.get(rule["key"]) == rule["value"] else FAIL
                        reason = f"Exact source field {rule['key']!r}: expected {rule['value']!r}, got {facts.get(rule['key'])!r}."
                elif rule["kind"] == "forbidden_literal":
                    status = FAIL if rule["value"] in text else PASS
                    reason = f"Case-specific forbidden literal {rule['value']!r} " + ("found." if status == FAIL else "absent.")
                else:
                    raise ValueError(f"Unknown check kind: {rule['kind']}")
            critical = rule.get("critical", False)
            if rule["kind"] == "exact_fact":
                # A generic string mismatch alone does not establish changed meaning.
                critical = critical and rule.get("semantic_exact", False)
            checks.append(outcome(rule["dimension"], status, reason, critical))
        results.append({"id": case["id"], "category": case["category"], "language": case["language"],
                        "scenario_id": case["scenario_id"], "checks": checks})

    dimensions = sorted({check["dimension"] for row in results for check in row["checks"]})
    metrics = {name: metric([check["status"] for row in results for check in row["checks"]
                            if check["dimension"] == name]) for name in dimensions}
    groups = {}
    for case in cases:
        if case.get("comparison_axes"):
            groups.setdefault(case["scenario_id"], []).append(case)
    consistency = []
    for scenario, variants in groups.items():
        for axis in variants[0]["comparison_axes"]:
            values = []
            for case in variants:
                response = saved.get(case["id"], {})
                row = next(r for r in results if r["id"] == case["id"])
                if row["checks"][0]["status"] != PASS:
                    values.append(None)
                elif axis in rubrics:
                    check = next((c for c in row["checks"] if c["dimension"] == axis), {})
                    values.append(check.get("status") if check.get("status") in (PASS, FAIL) else None)
                elif axis == "urgency":
                    value = response.get("urgency")
                    values.append(value if isinstance(value, str) and value.strip() else None)
                elif axis == "next_step":
                    annotation = response.get("next_step", {})
                    evidence = annotation.get("evidence", "")
                    allowed = {"clarification", "professional_review", "escalation", "general_information", "none"}
                    valid = (annotation.get("category") in allowed and isinstance(evidence, str)
                             and bool(evidence.strip()) and evidence in response.get("text", "")
                             and bool(response.get("assessment_source")))
                    values.append(annotation["category"] if valid else None)
                else:
                    raise ValueError(f"Unknown comparison axis: {axis}")
            complete = len(variants) >= 2 and all(v is not None for v in values)
            status = (PASS if len(set(values)) == 1 else FAIL) if complete else UNASSESSABLE
            consistency.append({"scenario_id": scenario, "axis": axis, "case_ids": [c["id"] for c in variants],
                                "values": values, "status": status,
                                "reason": "Variants agree." if status == PASS else
                                "Variants disagree." if status == FAIL else "Incomplete variant observations."})
    metrics["language_consistency"] = metric([row["status"] for row in consistency])
    urgency = urgency_metrics(cases, saved)
    failures = [{"id": row["id"], **check} for row in results for check in row["checks"] if check["status"] == FAIL]
    judge_errors = [{"id": row["id"], **check} for row in results for check in row["checks"] if check.get("assessment_origin") == "judge_error"]
    abstentions = [{"id": row["id"], **check} for row in results for check in row["checks"] if check.get("assessment_origin") == "rubric_abstention"]
    return {"case_count": len(cases), "response_count": len(responses),
            "assessment_sources": sorted({str(s) for r in responses for s in
                                          [r.get("assessment_source"), *r.get("assessment_sources", {}).values()] if s}),
            "judge_errors": judge_errors, "rubric_abstentions": abstentions,
            "metrics": metrics, "urgency": urgency, "consistency": consistency,
            "failures": failures, "critical_failures": [f for f in failures if f["critical"]], "cases": results}


def urgency_metrics(cases, saved):
    reserved = [c for c in cases if c.get("urgency_benchmark")]
    matrix = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
    pending, invalid, fp_ids, fn_ids = [], [], [], []
    for case in reserved:
        provenance = case.get("label_provenance") or {}
        if (case.get("review_status") != "approved" or case.get("expected_urgency") not in ("urgent", "nonurgent")
                or not provenance.get("source") or not provenance.get("reviewer")):
            pending.append(case["id"])
            continue
        response = saved.get(case["id"], {})
        prediction = response.get("urgency")
        if prediction not in ("urgent", "nonurgent") or response.get("error") or not str(response.get("text") or "").strip():
            invalid.append(case["id"])
            continue
        positive, predicted = case["expected_urgency"] == "urgent", prediction == "urgent"
        key = "tp" if positive and predicted else "fn" if positive else "fp" if predicted else "tn"
        matrix[key] += 1
        if key == "fp": fp_ids.append(case["id"])
        if key == "fn": fn_ids.append(case["id"])
    tp, fp, fn = matrix["tp"], matrix["fp"], matrix["fn"]
    assessed = sum(matrix.values())
    return {"eligible": len(reserved), "assessed": assessed, "coverage": assessed / len(reserved) if reserved else None,
            "pending_ids": pending, "invalid_prediction_ids": invalid, "confusion_matrix": matrix,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "precision_denominator": tp + fp, "recall_denominator": tp + fn,
            "false_positive_ids": fp_ids, "false_negative_ids": fn_ids}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=ROOT / "cases.jsonl")
    parser.add_argument("--rubrics", type=Path, default=ROOT / "rubrics.json")
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "latest")
    args = parser.parse_args()
    cases, responses = read_jsonl(args.cases), read_jsonl(args.responses)
    rubrics = json.loads(args.rubrics.read_text(encoding="utf-8"))
    for case in cases:
        if not set(case["rubrics"]) <= set(rubrics):
            raise ValueError(f"Unknown rubric in {case['id']}")
    result = evaluate(cases, responses, rubrics)
    result["inputs"] = {"cases": str(args.cases), "responses": str(args.responses), "rubrics": str(args.rubrics)}
    from report import write_reports
    paths = write_reports(result, args.output)
    print("\n".join(str(p) for p in paths))


if __name__ == "__main__":
    main()
