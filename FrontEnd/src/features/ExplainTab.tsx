import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle,
  FileText,
  Flask,
  UploadSimple,
  LockKey,
  SpeakerHigh,
  CalendarDots,
  X,
  Info,
  Camera,
  WarningCircle,
  ArrowCounterClockwise,
} from "@phosphor-icons/react";
import type { Explanation, Language, Translate } from "../types";
import {
  AudioButton,
  Emergency,
  Loader,
  PharmacyLink,
} from "../components/Shared";
import { explain } from "../lib/api";
import { demoExplanation } from "../lib/demo";
export function ExplainTab({
  language,
  t,
  result,
  setResult,
  demo,
  setDemo,
  onSchedule,
  onChat,
}: {
  language: Language;
  t: Translate;
  result: Explanation | null;
  setResult: (r: Explanation | null) => void;
  demo: boolean;
  setDemo: (v: boolean) => void;
  onSchedule: () => void;
  onChat: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [responseLanguage, setResponseLanguage] = useState<Language>(language);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const camera = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  function select(next?: File) {
    if (!next || busy) return;
    if (
      !["image/jpeg", "image/png", "image/webp", "application/pdf"].includes(
        next.type,
      )
    ) {
      setError(
        t(
          "Choisissez une image JPG, PNG, WebP ou un fichier PDF.",
          "ختار تصويرة JPG ولا PNG ولا WebP ولا ملف PDF.",
        ),
      );
      return;
    }
    if (next.size > 10 * 1024 * 1024) {
      setError(
        t(
          "Le fichier dépasse 10 Mo. Choisissez un fichier plus léger.",
          "الملف فات 10 Mo. ختار ملف أصغر.",
        ),
      );
      return;
    }
    setFile(next);
    setResult(null);
    setDemo(false);
    setError("");
  }
  async function submit() {
    if (!file || busy) return;
    setError("");
    setBusy(true);
    try {
      setResult(await explain(file, language));
      setResponseLanguage(language);
      setDemo(false);
    } catch {
      setError(
        t(
          "L’analyse n’a pas abouti. Vérifiez que le serveur est disponible puis réessayez. Votre fichier est conservé ici.",
          "ما قدرناش نكملو التحليل. تأكد من الخادم وعاود جرب. الملف باقي هنا.",
        ),
      );
    } finally {
      setBusy(false);
    }
  }
  function sample() {
    if (busy) return;
    setFile(null);
    setError("");
    setDemo(true);
    setResult(demoExplanation(language));
  }
  return (
    <div className="page explain-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">
            <span className="status-dot" />
            {t("À votre rythme, dans votre langue", "على خاطرك، وباللغة ديالك")}
          </div>
          <h1>
            {result
              ? t(
                  "Les mots compliqués, en plus simple.",
                  "الكلام الصعيب، بطريقة ساهلة.",
                )
              : t(
                  "Comprendre, c’est déjà avancer.",
                  "ملي كتفهم، كتزيد خطوة لقدام.",
                )}
          </h1>
          <p>
            {t(
              "Une ordonnance, une analyse ? Faisons le point, ensemble.",
              "عندك وصفة ولا تحاليل؟ نفهموهم مجموعين.",
            )}
          </p>
        </div>
        <span className="heading-icon">
          <FileText size={29} />
        </span>
      </div>
      <div className="steps" aria-label={t("Les étapes", "المراحل")}>
        <span className={result ? "complete" : "current"}>
          <b>{result ? <Check size={14} /> : "1"}</b>
          {t("Ajouter un document", "زيد وثيقة")}
        </span>
        <div />
        <span className={result ? "current" : ""}>
          <b>2</b>
          {t("Comprendre l’essentiel", "فهم المهم")}
        </span>
        <div />
        <span>
          <b>3</b>
          {t("Organiser la suite", "نظم الخطوة الجاية")}
        </span>
      </div>
      {result?.emergency.detected && (
        <Emergency message={result.emergency.message} t={t} />
      )}
      {demo && result && (
        <div className="demo-banner">
          <Info size={19} />
          <span>
            {t(
              "Vous explorez un exemple fictif. Ce n’est pas une prescription médicale.",
              "كتشوف مثال خيالي. هادي ماشي وصفة طبية.",
            )}
          </span>
          <button
            onClick={() => {
              setResult(null);
              setDemo(false);
            }}
            aria-label={t("Fermer l’exemple", "سد المثال")}
          >
            <X size={18} />
          </button>
        </div>
      )}
      <div className={`explain-layout ${result ? "has-result" : ""}`}>
        <section className="document-panel panel">
          <div className="panel-heading">
            <span className="inline">
              <FileText size={21} />
              <h2>{t("Votre document", "الوثيقة ديالك")}</h2>
            </span>
            <span className="subtle-tag">
              {t("Photo ou PDF", "تصويرة ولا PDF")}
            </span>
          </div>
          {result && demo ? (
            <div className="sample-paper">
              <span className="paper-mark">
                <FileText size={27} />
              </span>
              <span className="sample-stamp">
                {t("Exemple fictif", "مثال خيالي")}
              </span>
              <h3>{t("Ordonnance de démonstration", "وصفة للتجربة")}</h3>
              <div className="paper-divider" />
              <p>{t("Traitement A", "العلاج A")}</p>
              <small>
                {t(
                  "1 unité fictive · matin et soir",
                  "وحدة خيالية · الصباح والعشية",
                )}
              </small>
              <small>
                {t("Durée de l’exemple : 5 jours", "مدة المثال: 5 أيام")}
              </small>
              <div className="paper-divider" />
              <p className="paper-warning">
                {t(
                  "Ce document ne doit pas être utilisé pour prendre un médicament.",
                  "هاد الوثيقة ما خاصهاش تستعمل باش تاخد شي دوا.",
                )}
              </p>
            </div>
          ) : file ? (
            <div className="file-preview">
              {file.type === "application/pdf" ? (
                <object
                  data={preview}
                  type="application/pdf"
                  aria-label={t("Aperçu du PDF", "معاينة PDF")}
                >
                  <p>
                    {t("Aperçu indisponible.", "المعاينة ما متوفراش.")}{" "}
                    <a href={preview} target="_blank" rel="noreferrer">
                      {t("Ouvrir le PDF", "حل PDF")}
                    </a>
                  </p>
                </object>
              ) : (
                <img
                  src={preview}
                  alt={t(
                    "Document sélectionné pour analyse",
                    "الوثيقة المختارة للتحليل",
                  )}
                />
              )}
              <div className="file-details">
                <FileText size={20} />
                <span>
                  {file.name}
                  <small>{(file.size / 1024 / 1024).toFixed(1)} Mo</small>
                </span>
                <button
                  className="icon-button"
                  disabled={busy}
                  onClick={() => {
                    setFile(null);
                    setResult(null);
                    setError("");
                  }}
                  aria-label={t("Retirer le document", "حيد الوثيقة")}
                >
                  <X size={19} />
                </button>
              </div>
            </div>
          ) : (
            <div
              className={`upload-zone ${drag ? "dragging" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDrag(true);
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDrag(false);
                select(e.dataTransfer.files[0]);
              }}
            >
              <div className="upload-art" aria-hidden="true">
                <FileText size={38} weight="duotone" />
                <span>
                  <UploadSimple size={17} />
                </span>
              </div>
              <h3>{t("Déposez votre document ici", "حط الوثيقة ديالك هنا")}</h3>
              <p>
                {t(
                  "Une photo suffit pour y voir plus clair.",
                  "تصويرة كافية باش تفهم مزيان.",
                )}
              </p>
              <button
                className="button primary"
                onClick={() => input.current?.click()}
              >
                <UploadSimple size={19} />
                {t("Choisir un document", "ختار وثيقة")}
              </button>
              <small>
                {t(
                  "JPG, PNG, WebP ou PDF · 10 Mo maximum",
                  "JPG، PNG، WebP ولا PDF · حتى 10 Mo",
                )}
              </small>
              <button
                className="camera-link"
                onClick={() => camera.current?.click()}
              >
                <Camera size={17} />
                {t("Prendre une photo", "خد تصويرة")}
              </button>
            </div>
          )}
          <input
            ref={input}
            className="sr-only"
            type="file"
            accept="image/jpeg,image/png,image/webp,application/pdf"
            onChange={(e) => {
              select(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          <input
            ref={camera}
            className="sr-only"
            type="file"
            accept="image/*"
            capture="environment"
            onChange={(e) => {
              select(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          {file && !result && (
            <button
              className="button primary full"
              disabled={busy}
              onClick={submit}
            >
              {busy ? (
                <Loader label={t("Analyse en cours…", "التحليل جاري…")} />
              ) : (
                <>
                  {t("Expliquer mon document", "شرح ليا الوثيقة")}
                  <ArrowRight size={18} />
                </>
              )}
            </button>
          )}
          {result && (
            <button
              className="button secondary full"
              onClick={() => {
                setResult(null);
                setDemo(false);
                setFile(null);
              }}
            >
              <ArrowCounterClockwise size={17} />
              {t("Ajouter un autre document", "زيد وثيقة أخرى")}
            </button>
          )}
          {error && (
            <div className="form-error" role="alert">
              <WarningCircle size={20} />
              <p>{error}</p>
            </div>
          )}
          <div className="privacy-note">
            <LockKey size={17} />
            <p>
              {t(
                "Le document est envoyé pour analyse uniquement lorsque vous le demandez. Évitez les informations personnelles inutiles.",
                "الوثيقة كتتصيفط للتحليل غير ملي كتطلب. حيد المعلومات الشخصية اللي ما محتاجاش.",
              )}
            </p>
          </div>
          {!result && (
            <div className="sample-row">
              <div className="sample-file">
                <FileText size={22} />
              </div>
              <div>
                <strong>
                  {t("Juste envie de découvrir ?", "بغيتي غير تجرب؟")}
                </strong>
                <small>
                  {t(
                    "Explorez une ordonnance fictive.",
                    "شوف مثال ديال وصفة خيالية.",
                  )}
                </small>
              </div>
              <button onClick={sample} className="text-link">
                {t("Essayer", "جرب")}
                <ArrowUpRight size={18} />
              </button>
            </div>
          )}
        </section>
        {result ? (
          <section className="result-panel panel" aria-live="polite">
            <div className="panel-heading">
              <span className="inline">
                <CheckCircle size={23} className="green" />
                <h2>{t("Votre explication", "الشرح ديالك")}</h2>
              </span>
              <span className="subtle-tag">{result.document_type}</span>
            </div>
            <AudioButton
              text={[
                result.summary,
                ...result.items.map((i) => `${i.title}. ${i.detail}`),
                ...result.next_steps,
                ...result.uncertainties,
              ].join("\n")}
              language={demo ? language : responseLanguage}
              t={t}
            />
            {!demo && language !== responseLanguage && (
              <p className="muted">
                {t(
                  "Cette explication reste dans la langue choisie lors de l’analyse. Relancez l’analyse pour changer sa langue.",
                  "هاد الشرح باقي باللغة اللي تختارت وقت التحليل. عاود التحليل باش تبدل اللغة.",
                )}
              </p>
            )}
            <h3>{t("En quelques mots", "بكلام قليل")}</h3>
            <p className="summary-text" dir="auto">
              {result.summary}
            </p>
            <div className="explanation-items">
              {result.items.map((item, i) => (
                <div key={i}>
                  <span className="item-number">{i + 1}</span>
                  <div>
                    <h3>{item.title}</h3>
                    <p>{item.detail}</p>
                  </div>
                </div>
              ))}
            </div>
            {result.uncertainties.length > 0 && (
              <div className="uncertainty">
                <Info size={21} />
                <div>
                  <strong>{t("À vérifier", "خاص تتأكد")}</strong>
                  {result.uncertainties.map((u, i) => (
                    <p key={i}>{u}</p>
                  ))}
                </div>
              </div>
            )}
            <h3>{t("Et maintenant ?", "ودابا؟")}</h3>
            <ul className="next-steps">
              {result.next_steps.map((s, i) => (
                <li key={i}>
                  <CheckCircle size={18} />
                  {s}
                </li>
              ))}
            </ul>
            <div className="result-actions">
              {result.medicines.length > 0 && (
                <button className="button primary" onClick={onSchedule}>
                  <CalendarDots size={19} />
                  {t("Créer mon programme", "صاوب البرنامج")}
                </button>
              )}
              <button className="button secondary" onClick={onChat}>
                {t("Poser une question", "سول سؤال")}
                <ArrowRight size={17} />
              </button>
            </div>
            <PharmacyLink t={t} />
          </section>
        ) : (
          <aside className="explain-aside">
            <section className="language-card">
              <div className="inline">
                <span className="small-icon">
                  <SpeakerHigh size={20} />
                </span>
                <span>{t("On parle votre langue", "كنهضرو بلغتك")}</span>
              </div>
              <div className="darija-display" lang="ar" dir="rtl">
                صحتك،
                <br />
                بكلام بسيط.
              </div>
              <p>
                {t(
                  "Moins de jargon. Plus de clarté. En français ou en darija, à lire ou à écouter.",
                  "كلام مفهوم بلا تعقيد. بالفرنسية ولا بالدارجة، قرا ولا سمع.",
                )}
              </p>
              <AudioButton
                text={t(
                  "Bienvenue sur DarijaDoc. Comprenez vos documents de santé, à votre rythme et dans votre langue.",
                  "مرحبا بيك فداريجة دوك. فهم الوثائق الصحية ديالك، على خاطرك وباللغة ديالك.",
                )}
                language={language}
                t={t}
                label={t("Écouter un aperçu", "سمع مثال")}
              />
            </section>
            <section className="photo-tips">
              <h3>{t("Pour une lecture plus juste", "باش نقراو مزيان")}</h3>
              <p>
                <Check size={17} />
                {t("Toute la page dans le cadre", "الصفحة كاملة فالتصويرة")}
              </p>
              <p>
                <Check size={17} />
                {t("Une bonne lumière, sans reflet", "ضو مزيان بلا انعكاس")}
              </p>
              <p>
                <Check size={17} />
                {t("Un texte net et bien lisible", "كلام واضح وساهل يتقرا")}
              </p>
            </section>
          </aside>
        )}
      </div>
      {!result && (
        <div className="supported-documents">
          <div>
            <span className="support-icon">
              <FileText size={23} />
            </span>
            <div>
              <h3>{t("Ordonnances", "الوصفات")}</h3>
              <p>
                {t(
                  "Comprendre les mots et les instructions.",
                  "فهم الكلمات والتعليمات.",
                )}
              </p>
            </div>
          </div>
          <div>
            <span className="support-icon lavender">
              <Flask size={23} />
            </span>
            <div>
              <h3>{t("Résultats d’analyses", "نتائج التحاليل")}</h3>
              <p>
                {t(
                  "Mettre des mots simples sur vos résultats.",
                  "نتائجك بكلام واضح.",
                )}
              </p>
            </div>
          </div>
          <div className="support-disclaimer">
            <Info size={20} />
            <p>
              {t(
                "Une aide pour comprendre, jamais un diagnostic.",
                "مساعدة باش تفهم، ماشي تشخيص.",
              )}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
