import { useEffect, useState } from "react";
import {
  ChartBar,
  ShieldCheck,
  Clock,
  CheckCircle,
  XCircle,
  ArrowClockwise,
  CaretDown,
  Info,
} from "@phosphor-icons/react";
import type { AccuracyReport, Translate } from "../types";
import { isReport } from "../lib/api";
export function AccuracyTab({ t }: { t: Translate }) {
  const [report, setReport] = useState<AccuracyReport | null>(null);
  const [state, setState] = useState<
    "loading" | "missing" | "invalid" | "ready"
  >("loading");
  async function load() {
    setState("loading");
    try {
      const r = await fetch("/accuracy_report.json", { cache: "no-store" });
      if (
        !r.ok ||
        !r.headers.get("content-type")?.includes("application/json")
      ) {
        setState("missing");
        return;
      }
      const data = await r.json();
      if (!isReport(data)) {
        setState("invalid");
        return;
      }
      setReport(data);
      setState("ready");
    } catch {
      setState("missing");
    }
  }
  useEffect(() => {
    void load();
  }, []);
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">
            <ShieldCheck size={18} />
            {t("La confiance se construit", "الثقة كتبنى")}
          </div>
          <h1>{t("En toute transparence.", "بكل شفافية.")}</h1>
          <p>
            {t(
              "Comment nous testons DarijaDoc, et ce que ces résultats signifient.",
              "كيفاش كنجربو داريجة دوك، وشنو كتعني هاد النتائج.",
            )}
          </p>
        </div>
        <button
          className="button secondary"
          disabled={state === "loading"}
          onClick={load}
        >
          <ArrowClockwise size={18} />
          {t("Actualiser", "حدث")}
        </button>
      </div>
      <div className="evaluation-note">
        <Info size={21} />
        <p>
          {t(
            "Évaluation du prototype sur un jeu de tests. Ces résultats ne constituent pas une validation clinique ni une garantie de fiabilité médicale.",
            "تقييم النسخة التجريبية بأسئلة اختبار. النتائج ماشي مصادقة طبية وماشي ضمان للموثوقية الطبية.",
          )}
        </p>
      </div>
      {state !== "ready" ? (
        <section className="panel empty-state">
          <span className="empty-icon">
            <ChartBar size={41} weight="duotone" />
          </span>
          <span className="subtle-tag">
            <Clock size={14} />
            {t("Évaluation du prototype", "تقييم النسخة التجريبية")}
          </span>
          <h2>
            {state === "loading"
              ? t("Chargement du rapport…", "كنحملو التقرير…")
              : state === "invalid"
                ? t("Le rapport doit être vérifié.", "خاص مراجعة التقرير.")
                : t(
                    "Des résultats vérifiés, bientôt ici.",
                    "نتائج متحقق منها، قريبا هنا.",
                  )}
          </h2>
          <p>
            {state === "invalid"
              ? t(
                  "Le fichier fourni est incomplet ou incohérent. Aucun score n’est affiché.",
                  "الملف ناقص ولا ما متناسقش. ما غاديش نعرضو حتى نقطة.",
                )
              : t(
                  "Le rapport de tests n’a pas encore été publié. Nous afficherons les scores uniquement après une évaluation réelle.",
                  "تقرير الاختبارات مازال ما تنشرش. غادي نعرضو النقط من بعد تقييم حقيقي.",
                )}
          </p>
        </section>
      ) : (
        report && (
          <>
            <div className="report-summary">
              <div>
                <span>{t("Tests réussis", "اختبارات ناجحة")}</span>
                <strong>
                  {Math.round((report.passed / report.total) * 100)}
                  <small>%</small>
                </strong>
                <p>
                  {report.passed} / {report.total}{" "}
                  {t("cas de test", "حالات اختبار")}
                </p>
              </div>
              <div>
                <span>{t("Rapport généré le", "تاريخ التقرير")}</span>
                <h3>{report.generated_at}</h3>
                <p>
                  {t(
                    "Consultez les réponses, pas seulement le score.",
                    "شوف الأجوبة، ماشي غير النقطة.",
                  )}
                </p>
              </div>
            </div>
            <section className="panel test-cases">
              <h2>{t("Les cas de test", "حالات الاختبار")}</h2>
              {report.cases.map((c, i) => (
                <details key={i}>
                  <summary>
                    {c.passed ? (
                      <CheckCircle size={21} className="green" />
                    ) : (
                      <XCircle size={21} className="red" />
                    )}
                    <span>
                      {c.question}
                      <small>
                        {c.category} ·{" "}
                        {c.passed
                          ? t("Réussi", "ناجح")
                          : t("À améliorer", "خاص يتحسن")}
                      </small>
                    </span>
                    <CaretDown size={18} />
                  </summary>
                  <div>
                    <h4>{t("Réponse attendue", "الجواب المنتظر")}</h4>
                    <p>{c.expected}</p>
                    <h4>{t("Réponse obtenue", "الجواب اللي جا")}</h4>
                    <p>{c.actual}</p>
                  </div>
                </details>
              ))}
            </section>
          </>
        )
      )}
      <section className="evaluation-principles">
        <h2>{t("Ce que nous voulons vérifier", "شنو بغينا نختابرو")}</h2>
        <div>
          <span>01</span>
          <div>
            <h3>{t("La compréhension", "الفهم")}</h3>
            <p>
              {t(
                "Des explications fidèles au document, accessibles en français et en darija.",
                "شرح كيحترم الوثيقة وواضح بالفرنسية والدارجة.",
              )}
            </p>
          </div>
        </div>
        <div>
          <span>02</span>
          <div>
            <h3>{t("La prudence", "الحذر")}</h3>
            <p>
              {t(
                "Les incertitudes sont signalées. Une information manquante ne doit pas être inventée.",
                "المعلومات اللي ما مؤكداش خاصها تبان. المعلومات الناقصة ما خاصهاش تتخترع.",
              )}
            </p>
          </div>
        </div>
        <div>
          <span>03</span>
          <div>
            <h3>{t("Les situations urgentes", "الحالات المستعجلة")}</h3>
            <p>
              {t(
                "Tester si les situations urgentes déclenchent une alerte et une orientation adaptée.",
                "نتأكدو واش الحالات المستعجلة كتطلق تنبيه وتوجيه مناسب.",
              )}
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
