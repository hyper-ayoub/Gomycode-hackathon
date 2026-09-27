import { describe, expect, it } from "vitest";
import { activeOn, calendarContent, doseKey } from "./calendar";
import type { Plan } from "../types";
const plan: Plan = {
  demo: false,
  taken: [],
  treatments: [
    {
      id: "test-1",
      name: "Private medicine, A; B",
      instructions: "Line one\nLine two",
      dose: "Confirmed dose",
      start: "2026-09-27",
      days: 5,
      times: ["08:00", "20:00"],
    },
  ],
};
describe("calendar export", () => {
  it("exports one bounded recurrence per reminder using local times", () => {
    const data = calendarContent(plan, false);
    expect(data.match(/BEGIN:VEVENT/g)).toHaveLength(2);
    expect(data).toContain("DTSTART:20260927T080000\r\n");
    expect(data).toContain("DTSTART:20260927T200000\r\n");
    expect(data.match(/RRULE:FREQ=DAILY;COUNT=5/g)).toHaveLength(2);
    expect(data).toContain("DURATION:PT5M");
    expect(data.endsWith("END:VCALENDAR\r\n")).toBe(true);
  });
  it("removes medication names, doses and instructions in private mode", () => {
    const data = calendarContent(plan, true);
    expect(data).toContain("SUMMARY:Rappel de traitement");
    expect(data).not.toContain("Private medicine");
    expect(data).not.toContain("Confirmed dose");
    expect(data).not.toContain("Line one");
  });
  it("escapes values that would otherwise corrupt calendar fields", () => {
    const data = calendarContent(plan, false);
    expect(data).toContain("SUMMARY:Private medicine\\, A\\; B");
    expect(data).toContain("DESCRIPTION:Confirmed dose\\nLine one\\nLine two");
  });
  it("folds long Arabic lines at 75 UTF-8 bytes without losing text", () => {
    const name = "علاج تجريبي ".repeat(30);
    const data = calendarContent(
      { ...plan, treatments: [{ ...plan.treatments[0], name }] },
      false,
    );
    for (const line of data.split("\r\n"))
      expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(75);
    expect(data.replace(/\r\n /g, "")).toContain(`SUMMARY:${name}`);
  });
});
describe("daily tracking", () => {
  it("includes the first and final day, excludes dates outside treatment", () => {
    expect(activeOn("2026-09-27", 5, "2026-09-26")).toBe(false);
    expect(activeOn("2026-09-27", 5, "2026-09-27")).toBe(true);
    expect(activeOn("2026-09-27", 5, "2026-10-01")).toBe(true);
    expect(activeOn("2026-09-27", 5, "2026-10-02")).toBe(false);
  });
  it("handles dates spanning DST without drifting", () => {
    expect(activeOn("2026-03-28", 3, "2026-03-30")).toBe(true);
    expect(activeOn("2026-03-28", 3, "2026-03-31")).toBe(false);
  });
  it("keeps marks separate between days and reminder times", () => {
    expect(doseKey("a", "2026-09-27", "08:00")).not.toBe(
      doseKey("a", "2026-09-28", "08:00"),
    );
    expect(doseKey("a", "2026-09-27", "08:00")).not.toBe(
      doseKey("a", "2026-09-27", "20:00"),
    );
  });
});
