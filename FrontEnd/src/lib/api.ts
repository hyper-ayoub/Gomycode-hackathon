import type { AccuracyReport, Explanation, Language, Message } from "../types";
export const API_URL = (
  import.meta.env.VITE_API_URL || "http://localhost:8000"
).replace(/\/$/, "");
async function request(path: string, options?: RequestInit) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    signal: AbortSignal.timeout(60000),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
export function isExplanation(value: unknown): value is Explanation {
  if (!value || typeof value !== "object") return false;
  const v = value as Explanation;
  return (
    typeof v.summary === "string" &&
    typeof v.document_type === "string" &&
    Array.isArray(v.items) &&
    v.items.every(
      (i) => typeof i?.title === "string" && typeof i?.detail === "string",
    ) &&
    Array.isArray(v.next_steps) &&
    v.next_steps.every((i) => typeof i === "string") &&
    Array.isArray(v.uncertainties) &&
    v.uncertainties.every((i) => typeof i === "string") &&
    typeof v.emergency?.detected === "boolean" &&
    typeof v.emergency?.message === "string" &&
    Array.isArray(v.medicines) &&
    v.medicines.every(
      (m) =>
        typeof m?.name === "string" &&
        typeof m?.instructions === "string" &&
        (m.dose === undefined || typeof m.dose === "string") &&
        (m.times === undefined ||
          (Array.isArray(m.times) &&
            m.times.every(
              (t) =>
                typeof t === "string" && /^([01]\d|2[0-3]):[0-5]\d$/.test(t),
            ))) &&
        (m.duration_days === undefined ||
          (Number.isInteger(m.duration_days) && m.duration_days > 0)),
    )
  );
}
export async function explain(
  file: File,
  language: Language,
): Promise<Explanation> {
  const form = new FormData();
  form.append("file", file);
  form.append("language", language);
  const result = await request("/explain", { method: "POST", body: form });
  if (!isExplanation(result)) throw new Error("INVALID_RESPONSE");
  return result;
}
export async function chat(
  messages: Message[],
  language: Language,
  context: Explanation | null,
): Promise<Message> {
  const result = await request("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages: messages.map(({ role, content }) => ({ role, content })),
      language,
      context,
    }),
  });
  if (
    typeof result?.reply !== "string" ||
    typeof result?.emergency?.detected !== "boolean" ||
    typeof result?.emergency?.message !== "string"
  )
    throw new Error("INVALID_RESPONSE");
  return {
    role: "assistant",
    content: result.emergency.detected
      ? `${result.emergency.message}\n\n${result.reply}`
      : result.reply,
    emergency: result.emergency.detected,
  };
}
export function isReport(value: unknown): value is AccuracyReport {
  if (!value || typeof value !== "object") return false;
  const v = value as AccuracyReport;
  return (
    Number.isInteger(v.total) &&
    v.total > 0 &&
    Number.isInteger(v.passed) &&
    v.passed >= 0 &&
    v.passed <= v.total &&
    typeof v.generated_at === "string" &&
    Array.isArray(v.cases) &&
    v.cases.length === v.total &&
    v.cases.every(
      (c) =>
        typeof c?.question === "string" &&
        typeof c?.expected === "string" &&
        typeof c?.actual === "string" &&
        typeof c?.passed === "boolean" &&
        typeof c?.category === "string",
    ) &&
    v.cases.filter((c) => c.passed).length === v.passed
  );
}
