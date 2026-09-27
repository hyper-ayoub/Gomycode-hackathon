import type {
  AccuracyReport,
  Explanation,
  Language,
  Message,
  Translate,
} from "../types";
export const API_URL = (
  import.meta.env.VITE_API_URL || "http://localhost:8000"
).replace(/\/$/, "");
export interface Facility {
  name: string;
  facility_type: string;
  lat: number;
  lon: number;
  distance_km: number;
  address?: string | null;
}
async function request(path: string, options?: RequestInit, timeoutMs = 60000) {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (err) {
    if (
      err instanceof DOMException &&
      (err.name === "TimeoutError" || err.name === "AbortError")
    ) {
      throw new Error("TIMEOUT");
    }
    throw new Error("NETWORK");
  }
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      detail = "";
    }
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return response.json();
}
const API_COPY: Record<string, [string, string]> = {
  TIMEOUT: [
    "Le serveur a mis trop de temps à répondre. Réessayez.",
    "الخادم طال بزاف باش يجاوب. عاود جرب.",
  ],
  NETWORK: [
    "Le serveur est injoignable. Vérifiez qu’il est démarré, puis réessayez.",
    "الخادم ما كيجاوبش. تأكد بلي خدام وعاود جرب.",
  ],
  UNREADABLE: [
    "Le document est trop difficile à lire. Reprenez une photo plus nette, avec toute la page.",
    "الوثيقة ما بايناش مزيان. عاود تصويرة واضحة والصفحة كاملة.",
  ],
  UNSUPPORTED_TYPE: [
    "Choisissez une image JPG, PNG, WebP ou un fichier PDF.",
    "ختار تصويرة JPG ولا PNG ولا WebP ولا ملف PDF.",
  ],
  TOO_LARGE: [
    "Le fichier dépasse 10 Mo. Choisissez un fichier plus léger.",
    "الملف فات 10 Mo. ختار ملف أصغر.",
  ],
  EMPTY: [
    "Le fichier envoyé est vide. Choisissez un autre document.",
    "الملف اللي تصيفط خاوي. ختار وثيقة أخرى.",
  ],
  NOT_CONFIGURED: [
    "Le serveur n’a pas encore de clé OpenAI. Ajoutez OPENAI_API_KEY dans Backend/.env, puis redémarrez l’API.",
    "الخادم ما فيهش مفتاح OpenAI. زيد OPENAI_API_KEY فـ Backend/.env وعاد خدم الـ API.",
  ],
  INVALID_RESPONSE: [
    "La réponse du serveur est incomplète. Réessayez.",
    "جواب الخادم ناقص. عاود جرب.",
  ],
  UPSTREAM: [
    "Le service d’analyse n’a pas répondu. Réessayez dans un instant.",
    "خدمة التحليل ما جاوباتش. عاود من بعد شوية.",
  ],
  MIC_DENIED: [
    "Le micro n’est pas disponible. Vous pouvez écrire votre question.",
    "الميكرو ما متوفرش. تقدر تكتب السؤال ديالك.",
  ],
};
const API_FALLBACK: Record<string, [string, string]> = {
  explain: [
    "L’analyse n’a pas abouti. Vérifiez que le serveur est disponible puis réessayez. Votre fichier est conservé ici.",
    "ما قدرناش نكملو التحليل. تأكد من الخادم وعاود جرب. الملف باقي هنا.",
  ],
  chat: [
    "La réponse n’est pas disponible. Vérifiez le serveur puis renvoyez votre question.",
    "الجواب ما متوفرش. تأكد من الخادم وعاود صيفط السؤال.",
  ],
  voice: [
    "La transcription n’a pas abouti. Vous pouvez écrire votre question.",
    "ما قدرناش نكتبوا الكلام. تقدر تكتب السؤال ديالك.",
  ],
  places: [
    "Les pharmacies proches ne sont pas disponibles pour le moment.",
    "الصيدليات القريبة ما متوفراش دابا.",
  ],
};
export function apiError(
  err: unknown,
  t: Translate,
  fallback: keyof typeof API_FALLBACK,
) {
  const raw = err instanceof Error ? err.message : "";
  const code = raw.startsWith("NOT_CONFIGURED") ? "NOT_CONFIGURED" : raw;
  const copy = API_COPY[code] || API_FALLBACK[fallback];
  return t(copy[0], copy[1]);
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
  const result = await request("/explain", { method: "POST", body: form }, 120000);
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
export async function transcribe(blob: Blob): Promise<string> {
  const type = blob.type || "audio/webm";
  const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
  const form = new FormData();
  form.append("file", new File([blob], `question.${ext}`, { type }));
  const result = await request("/voice/transcribe", { method: "POST", body: form }, 90000);
  if (typeof result?.text !== "string" || !result.text.trim()) {
    throw new Error("INVALID_RESPONSE");
  }
  return result.text.trim();
}
export async function nearbyPharmacies(lat: number, lon: number): Promise<Facility[]> {
  const params = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
    radius_km: "5",
    facility_type: "pharmacy",
    limit: "6",
  });
  const result = await request(`/location/nearby?${params}`);
  if (!Array.isArray(result?.results)) throw new Error("INVALID_RESPONSE");
  return result.results.filter(
    (place: Facility) =>
      typeof place?.name === "string" &&
      typeof place.lat === "number" &&
      typeof place.lon === "number" &&
      typeof place.distance_km === "number",
  );
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
