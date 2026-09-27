import { describe, expect, it } from "vitest";
import { isExplanation, isReport } from "./api";
import { demoExplanation } from "./demo";
describe("backend response validation", () => {
  it("accepts complete explanations in both supported languages", () => {
    expect(isExplanation(demoExplanation("fr"))).toBe(true);
    expect(isExplanation(demoExplanation("ary"))).toBe(true);
  });
  it("rejects missing emergency flags instead of silently showing a safe state", () => {
    expect(isExplanation({ ...demoExplanation("fr"), emergency: null })).toBe(
      false,
    );
    expect(
      isExplanation({ ...demoExplanation("fr"), emergency: { message: "" } }),
    ).toBe(false);
  });
  it("accepts urgent responses so the interface can display the alert", () => {
    expect(
      isExplanation({
        ...demoExplanation("fr"),
        emergency: { detected: true, message: "Urgent test message" },
      }),
    ).toBe(true);
  });
  it("permits missing prescription values and rejects invalid times", () => {
    const base = demoExplanation("fr");
    expect(
      isExplanation({
        ...base,
        medicines: [{ name: "A", instructions: "Confirm details" }],
      }),
    ).toBe(true);
    expect(
      isExplanation({
        ...base,
        medicines: [{ name: "A", instructions: "", times: ["25:99"] }],
      }),
    ).toBe(false);
    expect(
      isExplanation({
        ...base,
        medicines: [{ name: "A", instructions: "", duration_days: -1 }],
      }),
    ).toBe(false);
  });
  it("rejects malformed document details", () => {
    expect(isExplanation({ ...demoExplanation("fr"), items: [null] })).toBe(
      false,
    );
    expect(isExplanation({ ...demoExplanation("fr"), next_steps: [23] })).toBe(
      false,
    );
  });
});
describe("evaluation integrity", () => {
  const valid = {
    total: 1,
    passed: 1,
    generated_at: "2026-09-27",
    cases: [
      {
        question: "Q",
        expected: "E",
        actual: "A",
        passed: true,
        category: "emergency",
      },
    ],
  };
  it("requires counts to agree with the actual test results", () => {
    expect(isReport(valid)).toBe(true);
    expect(isReport({ ...valid, total: 20 })).toBe(false);
    expect(isReport({ ...valid, passed: 0 })).toBe(false);
    expect(isReport({ ...valid, cases: [] })).toBe(false);
  });
  it("does not calculate scores from empty reports", () => {
    expect(isReport({ total: 0, passed: 0, generated_at: "", cases: [] })).toBe(
      false,
    );
    expect(isReport(null)).toBe(false);
  });
});
