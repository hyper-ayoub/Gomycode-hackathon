import { useState } from "react";
import {
  CalendarDots,
  Check,
  CheckCircle,
  Clock,
  DownloadSimple,
  Info,
  PencilSimple,
  Pill,
  Plus,
  ArrowRight,
  Trash,
  ArrowLeft,
  CaretRight,
  CaretLeft,
} from "@phosphor-icons/react";
import type { Explanation, Plan, Translate, Treatment } from "../types";
import { activeOn, dateKey, doseKey, downloadCalendar } from "../lib/calendar";
function draft(result: Explanation | null): Treatment[] {
  return (result?.medicines || []).map((m) => ({
    id: crypto.randomUUID(),
    name: m.name,
    dose: m.dose || "",
    instructions: m.instructions,
    times: m.times?.length ? [...m.times] : [""],
    days: m.duration_days || 0,
    start: dateKey(),
  }));
}
export function TreatmentTab({
  t,
  result,
  plan,
  setPlan,
  demo,
  startReview,
  setStartReview,
  onExplain,
}: {
  t: Translate;
  result: Explanation | null;
  plan: Plan | null;
  setPlan: (p: Plan | null) => void;
  demo: boolean;
  startReview: boolean;
  setStartReview: (v: boolean) => void;
  onExplain: () => void;
}) {
  const [editing, setEditing] = useState(startReview);
  const [rows, setRows] = useState<Treatment[]>(
    startReview ? draft(result) : plan?.treatments || [],
  );
  const [confirmed, setConfirmed] = useState(false);
  const [privateTitles, setPrivateTitles] = useState(true);
  const [notice, setNotice] = useState("");
  const [day, setDay] = useState(dateKey());
  function update(index: number, patch: Partial<Treatment>) {
    setRows(rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
    setConfirmed(false);
  }
  function save(e: React.FormEvent) {
    e.preventDefault();
    if (!confirmed || rows.length === 0) return;
    const unchanged = rows
      .filter((row) =>
        plan?.treatments.some(
          (previous) => JSON.stringify(previous) === JSON.stringify(row),
        ),
      )
      .map((row) => row.id);
    setPlan({
      treatments: rows,
      taken: (plan?.taken || []).filter((key) =>
        unchanged.some((id) => key.startsWith(`${id}/`)),
      ),
      demo: startReview ? demo : plan?.demo || false,
    });
    setEditing(false);
    setStartReview(false);
    setDay(rows[0].start);
    setNotice(
      t(
        "Votre programme est prêt. Vous pouvez maintenant l’ajouter à votre calendrier.",
        "البرنامج واجد. دابا تقدر تزيدو للتقويم.",
      ),
    );
  }
  function moveDay(delta: number) {
    const date = new Date(day + "T12:00:00");
    date.setDate(date.getDate() + delta);
    setDay(dateKey(date));
  }
  const doses = (plan?.treatments || [])
    .filter((r) => activeOn(r.start, r.days, day))
    .flatMap((r) =>
      r.times.map((time) => ({ ...r, time, key: doseKey(r.id, day, time) })),
    )
    .sort((a, b) => a.time.localeCompare(b.time));
  const taken = doses.filter((d) => plan?.taken.includes(d.key)).length;
  const next = doses.find((d) => !plan?.taken.includes(d.key));
  function toggle(key: string) {
    if (plan)
      setPlan({
        ...plan,
        taken: plan.taken.includes(key)
          ? plan.taken.filter((k) => k !== key)
          : [...plan.taken, key],
      });
  }
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">
            <CalendarDots size={17} />
            {t("Un jour à la fois", "نهار بنهار")}
          </div>
          <h1>
            {editing
              ? t("Vérifions votre programme.", "نتأكدو من البرنامج ديالك.")
              : t("Votre journée, bien organisée.", "نهارك، منظم مزيان.")}
          </h1>
          <p>
            {t(
              "Des repères simples pour suivre les instructions de votre ordonnance.",
              "برنامج ساهل باش تتبع التعليمات ديال الوصفة.",
            )}
          </p>
        </div>
        {plan && !editing && (
          <button
            className="button secondary"
            onClick={() => {
              setRows(plan.treatments);
              setEditing(true);
              setConfirmed(false);
            }}
          >
            <PencilSimple size={18} />
            {t("Modifier", "بدل")}
          </button>
        )}
      </div>
      {(plan?.demo || (editing && demo)) && (
        <div className="demo-banner">
          <Info size={19} />
          {t(
            "Programme fictif de démonstration. Ne pas utiliser pour un traitement réel.",
            "برنامج خيالي للتجربة. ما تستعملوش لعلاج حقيقي.",
          )}
        </div>
      )}
      {notice && (
        <div className="success-notice" role="status">
          <CheckCircle size={20} />
          {notice}
        </div>
      )}
      {editing ? (
        <form className="panel schedule-form" onSubmit={save}>
          <div className="review-intro">
            <Info size={22} />
            <p>
              {t(
                "Comparez chaque information avec votre ordonnance. Complétez uniquement les informations confirmées. Les horaires sont des rappels, pas de nouvelles instructions médicales.",
                "قارن كل معلومة مع الوصفة. كمل غير المعلومات المؤكدة. الأوقات غير تذكيرات، ماشي تعليمات طبية جديدة.",
              )}
            </p>
          </div>
          {rows.map((r, i) => (
            <fieldset key={r.id}>
              <legend>
                <Pill size={20} />
                {r.name}
              </legend>
              <p className="muted">{r.instructions}</p>
              <div className="form-grid">
                <label>
                  {t(
                    "Dose indiquée sur l’ordonnance",
                    "الجرعة المكتوبة فالوصفة",
                  )}
                  <input
                    required
                    value={r.dose}
                    onChange={(e) => update(i, { dose: e.target.value })}
                    placeholder={t("À confirmer", "خاص التأكيد")}
                  />
                </label>
                <label>
                  {t("Date de début", "تاريخ البداية")}
                  <input
                    type="date"
                    required
                    value={r.start}
                    onChange={(e) => update(i, { start: e.target.value })}
                  />
                </label>
                <label>
                  {t("Durée confirmée (jours)", "المدة المؤكدة (أيام)")}
                  <input
                    type="number"
                    min="1"
                    max="365"
                    required
                    value={r.days || ""}
                    onChange={(e) =>
                      update(i, { days: Number(e.target.value) })
                    }
                  />
                </label>
              </div>
              <div className="time-inputs">
                <span>{t("Heures des rappels", "أوقات التذكير")}</span>
                {r.times.map((time, j) => (
                  <div key={j}>
                    <input
                      aria-label={`${t("Rappel", "تذكير")} ${j + 1}`}
                      type="time"
                      required
                      value={time}
                      onChange={(e) =>
                        update(i, {
                          times: r.times.map((v, n) =>
                            j === n ? e.target.value : v,
                          ),
                        })
                      }
                    />
                    {r.times.length > 1 && (
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={t("Supprimer cet horaire", "حيد هاد الوقت")}
                        onClick={() =>
                          update(i, {
                            times: r.times.filter((_, n) => j !== n),
                          })
                        }
                      >
                        <Trash size={17} />
                      </button>
                    )}
                  </div>
                ))}
                {r.times.length < 8 && (
                  <button
                    type="button"
                    className="text-link"
                    onClick={() => update(i, { times: [...r.times, ""] })}
                  >
                    <Plus size={16} />
                    {t("Ajouter une heure", "زيد وقت")}
                  </button>
                )}
              </div>
              {new Set(r.times).size !== r.times.length && (
                <p className="error-text">
                  {t(
                    "Les horaires doivent être différents.",
                    "الأوقات خاصهم يكونو مختلفين.",
                  )}
                </p>
              )}
            </fieldset>
          ))}
          <label className="checkbox">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              required
            />
            <span>
              {t(
                "J’ai vérifié les doses, la durée et les horaires avec les instructions de mon ordonnance.",
                "تأكدت من الجرعات والمدة والأوقات مع تعليمات الوصفة ديالي.",
              )}
            </span>
          </label>
          <div className="result-actions">
            <button
              className="button primary"
              disabled={
                !confirmed ||
                rows.length === 0 ||
                rows.some((r) => new Set(r.times).size !== r.times.length)
              }
            >
              <Check size={18} />
              {t("Confirmer mon programme", "أكد البرنامج")}
            </button>
            <button
              type="button"
              className="button secondary"
              onClick={() => {
                setEditing(false);
                setStartReview(false);
              }}
            >
              {t("Annuler", "إلغاء")}
            </button>
          </div>
        </form>
      ) : !plan ? (
        <section className="empty-state panel">
          <span className="empty-icon">
            <CalendarDots size={42} weight="duotone" />
          </span>
          <h2>
            {t(
              "La suite commence par votre ordonnance.",
              "البداية من الوصفة ديالك.",
            )}
          </h2>
          <p>
            {t(
              "Une fois votre document expliqué, vérifiez les instructions et créez votre programme quotidien.",
              "من بعد شرح الوثيقة، تأكد من التعليمات وصاوب البرنامج اليومي.",
            )}
          </p>
          {result?.medicines.length ? (
            <button
              className="button primary"
              onClick={() => {
                setRows(draft(result));
                setEditing(true);
                setStartReview(true);
              }}
            >
              {t("Préparer mon programme", "وجد البرنامج")}
              <ArrowRight size={18} />
            </button>
          ) : (
            <button className="button primary" onClick={onExplain}>
              {t("Comprendre une ordonnance", "فهم وصفة")}
              <ArrowRight size={18} />
            </button>
          )}
          <small>
            {t(
              "Aucun traitement n’est ajouté automatiquement.",
              "حتى علاج ما كيتزاد بوحدو.",
            )}
          </small>
        </section>
      ) : (
        <div className="treatment-layout">
          <div>
            <section className="progress-card">
              <div>
                <span>
                  {t("Votre progression du jour", "التقدم ديالك اليوم")}
                </span>
                <h2>
                  {taken} <span>/ {doses.length}</span>
                </h2>
                <p>
                  {t(
                    "prises marquées comme effectuées",
                    "جرعات علمتي عليهم باللي تاخدو",
                  )}
                </p>
              </div>
              <div
                className="progress-ring"
                style={
                  {
                    "--progress": `${doses.length ? (taken / doses.length) * 100 : 0}%`,
                  } as React.CSSProperties
                }
              >
                <span>
                  {doses.length ? Math.round((taken / doses.length) * 100) : 0}
                  <small>%</small>
                </span>
              </div>
            </section>
            <section className="panel timeline-panel">
              <div className="panel-heading">
                <h2>{t("Mon programme", "البرنامج ديالي")}</h2>
                <div className="date-navigation">
                  <button
                    className="icon-button"
                    aria-label={t("Jour précédent", "النهار اللي قبل")}
                    onClick={() => moveDay(-1)}
                  >
                    <CaretLeft size={18} />
                  </button>
                  <span>
                    {new Date(day + "T12:00:00").toLocaleDateString(undefined, {
                      day: "numeric",
                      month: "short",
                    })}
                  </span>
                  <button
                    className="icon-button"
                    aria-label={t("Jour suivant", "النهار الجاي")}
                    onClick={() => moveDay(1)}
                  >
                    <CaretRight size={18} />
                  </button>
                </div>
              </div>
              <button
                className="text-link today-link"
                onClick={() => setDay(dateKey())}
              >
                {t("Revenir à aujourd’hui", "رجع لليوم")}
              </button>
              {doses.length ? (
                <div className="timeline">
                  {doses.map((d) => {
                    const done = plan.taken.includes(d.key);
                    return (
                      <div
                        key={d.key}
                        className={`dose-row ${done ? "done" : ""}`}
                      >
                        <div className="dose-time">
                          {d.time}
                          <span>{done ? <Check size={13} /> : <span />}</span>
                        </div>
                        <div className="dose-content">
                          <div className="dose-title">
                            <span className="pill-icon">
                              <Pill size={22} />
                            </span>
                            <div>
                              <h3>{d.name}</h3>
                              <p>{d.dose}</p>
                            </div>
                          </div>
                          <small>{d.instructions}</small>
                          <button
                            className={`button ${done ? "taken-button" : "secondary"}`}
                            disabled={day > dateKey()}
                            aria-pressed={done}
                            onClick={() => toggle(d.key)}
                          >
                            {done ? (
                              <CheckCircle size={18} weight="fill" />
                            ) : (
                              <Check size={18} />
                            )}{" "}
                            {done
                              ? t("Prise marquée · annuler", "تسجلات · رجع")
                              : t("Marquer comme pris", "علم باللي خديتو")}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="small-empty">
                  <CalendarDots size={30} />
                  <p>
                    {t(
                      "Aucune prise prévue pour cette date.",
                      "ما كاينة حتى جرعة مبرمجة فهاد التاريخ.",
                    )}
                  </p>
                </div>
              )}
            </section>
          </div>
          <aside>
            <section className="next-dose">
              <span className="inline">
                <Clock size={19} />
                {t(
                  "Prochaine prise non cochée",
                  "الجرعة الجاية اللي ما تسجلاتش",
                )}
              </span>
              {next ? (
                <>
                  <strong>{next.time}</strong>
                  <h3>{next.name}</h3>
                  <p>{next.dose}</p>
                </>
              ) : (
                <>
                  <strong>
                    <CheckCircle size={40} />
                  </strong>
                  <h3>{t("Tout est à jour", "كلشي محدث")}</h3>
                  <p>
                    {t(
                      "Aucune prise à cocher pour ce jour.",
                      "ما بقات حتى جرعة تسجلها لهاد النهار.",
                    )}
                  </p>
                </>
              )}
            </section>
            <section className="panel calendar-panel">
              <CalendarDots size={27} />
              <h3>{t("Gardez vos repères", "خلي البرنامج معاك")}</h3>
              <p>
                {t(
                  "Exportez le programme, puis importez-le dans votre application de calendrier.",
                  "صدر البرنامج وزيدو لتطبيق التقويم ديالك.",
                )}
              </p>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={privateTitles}
                  onChange={(e) => setPrivateTitles(e.target.checked)}
                />
                <span>
                  {t("Masquer les noms des médicaments", "خبي سميات الدوا")}
                </span>
              </label>
              <button
                className="button primary full"
                onClick={() => {
                  downloadCalendar(plan, privateTitles);
                  setNotice(
                    t(
                      "Fichier .ics téléchargé. Importez-le dans votre calendrier. Les notifications dépendent de vos réglages.",
                      "تحمل ملف .ics. زيدو للتقويم. التنبيهات على حساب الإعدادات ديالك.",
                    ),
                  );
                }}
              >
                <DownloadSimple size={18} />
                {t("Ajouter au calendrier", "زيد للتقويم")}
              </button>
              <small>
                {t(
                  "Heures locales. Export sans synchronisation automatique. Un nouvel import peut créer des doublons.",
                  "الأوقات محلية. بلا مزامنة تلقائية. استيراد جديد يقدر يكرر المواعيد.",
                )}
              </small>
            </section>
            <div className="session-note">
              <Info size={18} />
              <p>
                {t(
                  "Ce programme reste dans cette session. Exportez-le avant de fermer la page.",
                  "هاد البرنامج كيبقى غير فهاد الجلسة. صدرو قبل ما تسد الصفحة.",
                )}
              </p>
            </div>
            <button
              className="clear-button"
              onClick={() => {
                if (
                  window.confirm(
                    t(
                      "Effacer ce programme et son suivi ?",
                      "تمسح هاد البرنامج والمتابعة ديالو؟",
                    ),
                  )
                ) {
                  setPlan(null);
                  setNotice("");
                }
              }}
            >
              <Trash size={16} />
              {t("Effacer mon programme", "مسح البرنامج")}
            </button>
          </aside>
        </div>
      )}
      {editing && (
        <button className="text-link back-link" onClick={onExplain}>
          <ArrowLeft size={16} />
          {t("Revoir mon document", "راجع الوثيقة")}
        </button>
      )}
    </div>
  );
}
