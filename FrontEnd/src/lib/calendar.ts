import type { Plan } from "../types";
export function dateKey(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
export function activeOn(start: string, days: number, day: string) {
  const delta =
    (Date.parse(day + "T00:00:00Z") - Date.parse(start + "T00:00:00Z")) /
    86400000;
  return delta >= 0 && delta < days;
}
export function doseKey(id: string, day: string, time: string) {
  return `${id}/${day}/${time}`;
}
function escape(value: string) {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/\r?\n/g, "\\n")
    .replace(/,/g, "\\,")
    .replace(/;/g, "\\;");
}
// Fold by UTF-8 byte length, not JS character count (Arabic may use multiple bytes).
function fold(line: string) {
  const encoder = new TextEncoder();
  let current = "";
  const lines: string[] = [];
  for (const char of line) {
    if (encoder.encode(current + char).length > 75) {
      lines.push(current);
      current = " ";
    }
    current += char;
  }
  lines.push(current);
  return lines.join("\r\n");
}
export function calendarContent(plan: Plan, privateTitles: boolean) {
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}/, "");
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//DarijaDoc//Treatment Calendar//FR",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
  ];
  for (const treatment of plan.treatments)
    for (const time of treatment.times) {
      lines.push(
        "BEGIN:VEVENT",
        `UID:${treatment.id}-${time.replace(":", "")}@darijadoc.local`,
        `DTSTAMP:${stamp}`,
        `DTSTART:${treatment.start.replace(/-/g, "")}T${time.replace(":", "")}00`,
        "DURATION:PT5M",
        `RRULE:FREQ=DAILY;COUNT=${treatment.days}`,
        `SUMMARY:${escape(privateTitles ? "Rappel de traitement" : treatment.name)}`,
        `DESCRIPTION:${escape(privateTitles ? "Consultez votre programme DarijaDoc." : `${treatment.dose}\n${treatment.instructions}`)}`,
        "END:VEVENT",
      );
    }
  lines.push("END:VCALENDAR");
  return lines.map(fold).join("\r\n") + "\r\n";
}
export function downloadCalendar(plan: Plan, privateTitles: boolean) {
  const url = URL.createObjectURL(
    new Blob([calendarContent(plan, privateTitles)], {
      type: "text/calendar;charset=utf-8",
    }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "darijadoc-calendrier.ics";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
