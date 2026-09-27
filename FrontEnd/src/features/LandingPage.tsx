import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  CalendarDots,
  CaretDown,
  Check,
  CheckCircle,
  FileText,
  Heart,
  Info,
  List,
  Play,
  ShieldCheck,
  SpeakerHigh,
  Translate as TranslateIcon,
  UploadSimple,
  X,
  Pause,
  DownloadSimple,
} from "@phosphor-icons/react";
import { AudioButton, Brand } from "../components/Shared";
import { Logo } from "../components/Logo";
import { dateKey, downloadCalendar } from "../lib/calendar";
import { demoExplanation } from "../lib/demo";
import type { Language, Plan, Translate } from "../types";
import "../landing.css";

function ProductDemo({ language, t }: { language: Language; t: Translate }) {
  const [step, setStep] = useState(0);
  const [taken, setTaken] = useState(false);
  const [exported, setExported] = useState(false);
  const sample = demoExplanation(language);
  const labels = [
    t("Votre document", "الوثيقة ديالك"),
    t("En mots simples", "بكلام ساهل"),
    t("La suite, organisée", "الخطوة الجاية، منظمة"),
  ];
  const descriptions = [
    t(
      "Ajoutez une photo ou un PDF. Une ordonnance ou des résultats d’analyses suffisent pour commencer.",
      "زيد تصويرة ولا PDF. وصفة ولا نتائج التحاليل كافيين باش تبدا.",
    ),
    t(
      "Retrouvez l’essentiel en français ou en darija. Lisez l’explication ou prenez le temps de l’écouter.",
      "لقى المهم بالفرنسية ولا بالدارجة. قرا الشرح ولا خد وقتك وسمعو.",
    ),
    t(
      "Vérifiez les instructions, choisissez vos rappels et exportez votre programme dans votre calendrier.",
      "تأكد من التعليمات، ختار التذكيرات وزيد البرنامج للتقويم ديالك.",
    ),
  ];
  const icons = [UploadSimple, SpeakerHigh, CalendarDots];
  const plan: Plan = {
    demo: true,
    taken: [],
    treatments: [
      {
        id: "landing-demo",
        name: "Traitement A (exemple fictif)",
        dose: "1 unité fictive",
        instructions:
          "Démonstration uniquement, ne pas utiliser pour un traitement réel.",
        start: dateKey(),
        days: 5,
        times: ["08:00", "20:00"],
      },
    ],
  };
  function choose(index: number) {
    window.speechSynthesis?.cancel();
    setStep(index);
  }
  return (
    <div className="walkthrough">
      <div
        className="walkthrough-steps"
        role="tablist"
        aria-label={t("Découvrir les étapes", "اكتشف المراحل")}
        aria-orientation="vertical"
      >
        {labels.map((label, i) => {
          const Icon = icons[i];
          return (
            <button
              key={i}
              id={`demo-tab-${i}`}
              role="tab"
              aria-selected={step === i}
              aria-controls="demo-panel"
              tabIndex={step === i ? 0 : -1}
              className={step === i ? "selected" : ""}
              onClick={() => choose(i)}
              onKeyDown={(e) => {
                if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
                  e.preventDefault();
                  const next =
                    e.key === "Home"
                      ? 0
                      : e.key === "End"
                        ? 2
                        : (i + (e.key === "ArrowDown" ? 1 : 2)) % 3;
                  choose(next);
                  document.getElementById(`demo-tab-${next}`)?.focus();
                }
              }}
            >
              <span className="walkthrough-number">0{i + 1}</span>
              <div>
                <h3>{label}</h3>
                <p>{descriptions[i]}</p>
              </div>
              <Icon size={23} weight={step === i ? "duotone" : "regular"} />
            </button>
          );
        })}
      </div>
      <div className="demo-surface">
        <div className="demo-surface-heading">
          <span>
            <Logo />
            DarijaDoc
          </span>
          <span className="demo-label">
            {t("Exemple interactif", "مثال تفاعلي")}
          </span>
        </div>
        <div
          id="demo-panel"
          role="tabpanel"
          aria-labelledby={`demo-tab-${step}`}
          tabIndex={0}
          className="demo-panel"
        >
          <div className="demo-transition" key={step}>
            {step === 0 && (
              <div className="demo-upload">
                <div className="demo-document-icon">
                  <FileText size={48} weight="duotone" />
                </div>
                <h3>
                  {t("Tout commence par un document.", "كلشي كيبدا بوثيقة.")}
                </h3>
                <p>
                  {t(
                    "Découvrez le parcours avec notre ordonnance fictive.",
                    "اكتشف المراحل مع الوصفة التجريبية ديالنا.",
                  )}
                </p>
                <button className="landing-button" onClick={() => choose(1)}>
                  {t("Ouvrir l’exemple", "حل المثال")}
                  <ArrowRight size={18} />
                </button>
                <small>JPG · PNG · WebP · PDF</small>
              </div>
            )}
            {step === 1 && (
              <div className="demo-explanation">
                <div className="demo-result-title">
                  <span>
                    <CheckCircle size={25} weight="duotone" />
                  </span>
                  <div>
                    <h3>{t("Voici l’essentiel.", "ها المهم.")}</h3>
                    <small>
                      {t("Une explication à votre rythme", "شرح على خاطرك")}
                    </small>
                  </div>
                </div>
                <p className="demo-summary" dir="auto">
                  {sample.summary}
                </p>
                <AudioButton text={sample.summary} language={language} t={t} />
                <button className="demo-next" onClick={() => choose(2)}>
                  {t("Et pour la suite ?", "وبالنسبة للخطوة الجاية؟")}
                  <ArrowRight size={18} />
                </button>
              </div>
            )}
            {step === 2 && (
              <div className="demo-schedule">
                <div className="demo-result-title">
                  <span>
                    <CalendarDots size={25} />
                  </span>
                  <div>
                    <h3>{t("Votre journée, plus claire.", "نهارك، أوضح.")}</h3>
                    <small>
                      {t("Programme fictif · 5 jours", "برنامج خيالي · 5 أيام")}
                    </small>
                  </div>
                </div>
                <div className="demo-reminder">
                  <time>08:00</time>
                  <div>
                    <strong>{t("Traitement A", "العلاج A")}</strong>
                    <small>{t("Exemple uniquement", "غير مثال")}</small>
                  </div>
                  <button
                    aria-pressed={taken}
                    aria-label={t(
                      "Marquer la prise fictive",
                      "علم الجرعة الخيالية",
                    )}
                    onClick={() => setTaken(!taken)}
                    className={taken ? "checked" : ""}
                  >
                    <Check size={20} />
                  </button>
                </div>
                <div className="demo-reminder">
                  <time>20:00</time>
                  <div>
                    <strong>{t("Traitement A", "العلاج A")}</strong>
                    <small>{t("Exemple uniquement", "غير مثال")}</small>
                  </div>
                  <CalendarDots size={20} />
                </div>
                <button
                  className="demo-next"
                  onClick={() => {
                    downloadCalendar(plan, true);
                    setExported(true);
                  }}
                >
                  <DownloadSimple size={18} />
                  {t("Exporter cet exemple", "صدر هاد المثال")}
                </button>
                {exported && (
                  <p className="export-feedback" role="status">
                    {t(
                      "Fichier .ics téléchargé. Importez-le dans votre calendrier.",
                      "تحمل ملف .ics. زيدو للتقويم ديالك.",
                    )}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
        <div className="demo-surface-footer">
          <Info size={15} />
          {t(
            "Données fictives. Aucune recommandation médicale.",
            "معلومات خيالية. بلا توصية طبية.",
          )}
        </div>
      </div>
    </div>
  );
}

export default function LandingPage() {
  const [language, setLanguage] = useState<Language>(
    new URLSearchParams(window.location.search).get("lang") === "fr"
      ? "fr"
      : "ary",
  );
  const [menu, setMenu] = useState(false);
  const [paused, setPaused] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const t: Translate = (fr, ary) => (language === "fr" ? fr : ary);
  const app = `/app?lang=${language}`;
  useEffect(() => {
    document.documentElement.lang = language === "ary" ? "ar-MA" : "fr";
    document.documentElement.dir = language === "ary" ? "rtl" : "ltr";
    document.title =
      language === "fr"
        ? "DarijaDoc · Votre santé, en mots simples"
        : "داريجة دوك · صحتك، بكلام بسيط";
  }, [language]);
  useEffect(() => {
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenu(false);
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, []);
  useEffect(() => {
    if (
      !("IntersectionObserver" in window) ||
      matchMedia("(prefers-reduced-motion: reduce)").matches
    )
      return;
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
            observer.unobserve(entry.target);
          }
        }),
      { threshold: 0.12 },
    );
    container.current?.querySelectorAll("[data-reveal]").forEach((el) => {
      el.classList.add("reveal-ready");
      observer.observe(el);
    });
    return () => observer.disconnect();
  }, []);
  const faqs = [
    [
      t("Que peut expliquer DarijaDoc ?", "شنو يقدر يشرح داريجة دوك؟"),
      t(
        "Une photo ou un PDF d’ordonnance ou de résultats d’analyses. DarijaDoc aide à comprendre les termes et les instructions. Si le document est flou ou incomplet, vérifiez les informations avec votre professionnel de santé.",
        "تصويرة ولا PDF ديال وصفة ولا نتائج التحاليل. داريجة دوك كيساعدك تفهم الكلمات والتعليمات. إلا كانت الوثيقة ما واضحةش ولا ناقصة، تأكد مع المهني الصحي ديالك.",
      ),
    ],
    [
      t("Est-ce que cela remplace mon médecin ?", "واش كيعوض الطبيب ديالي؟"),
      t(
        "Non. DarijaDoc est une aide à la compréhension, pas un outil de diagnostic. Il peut se tromper. Votre médecin ou votre pharmacien reste votre référence pour toute décision de santé.",
        "لا. داريجة دوك مساعدة باش تفهم، ماشي أداة للتشخيص. يقدر يغلط. الطبيب ولا الصيدلي كيبقى هو المرجع لأي قرار صحي.",
      ),
    ],
    [
      t(
        "Comment fonctionne la voix en darija ?",
        "كيفاش كيخدم الصوت بالدارجة؟",
      ),
      t(
        "Vous pouvez lire les explications en darija et les écouter lorsque votre navigateur dispose d’une voix arabe compatible. La prononciation dépend de la voix installée. La saisie vocale n’est pas encore disponible dans ce prototype.",
        "تقدر تقرا الشرح بالدارجة وتسمعو إلا كان المتصفح فيه صوت عربي مناسب. النطق كيتعلق بالصوت المثبت. الإدخال بالصوت مازال ما متوفرش فهاد النسخة.",
      ),
    ],
    [
      t("Que deviennent mes documents ?", "شنو كيوقع للوثائق ديالي؟"),
      t(
        "Le fichier est envoyé au serveur lorsque vous lancez une analyse. Dans cette interface, les documents et le programme restent en mémoire pendant la session et disparaissent au rechargement. Retirez les informations personnelles inutiles avant l’envoi.",
        "الملف كيتصيفط للخادم ملي كتشغل التحليل. فهاد الواجهة، الوثائق والبرنامج كيبقاو فالذاكرة غير فالجلسة وكيمشيو ملي كتعاود تحمل الصفحة. حيد المعلومات الشخصية اللي ما محتاجاش قبل الإرسال.",
      ),
    ],
    [
      t(
        "Les rappels se synchronisent-ils avec mon calendrier ?",
        "واش التذكيرات كتتزامن مع التقويم؟",
      ),
      t(
        "Vous pouvez télécharger un fichier .ics après avoir confirmé votre programme. Importez-le dans votre calendrier et configurez ses notifications. Les modifications ne sont pas synchronisées automatiquement.",
        "تقدر تحمل ملف .ics من بعد تأكيد البرنامج. زيدو للتقويم وضبط التنبيهات ديالو. التغييرات ما كتتزامنش بوحدها.",
      ),
    ],
  ];
  return (
    <div
      ref={container}
      className={`landing ${paused ? "motion-paused" : ""}`}
      dir={language === "ary" ? "rtl" : "ltr"}
    >
      <a className="skip-link" href="#landing-main">
        {t("Aller au contenu", "سير للمحتوى")}
      </a>
      <header className="landing-header">
        <div className="landing-nav">
          <a
            href="/"
            aria-label={t("DarijaDoc, accueil", "داريجة دوك، الرئيسية")}
          >
            <Brand />
          </a>
          <nav
            id="landing-menu"
            className={menu ? "open" : ""}
            aria-label={t("Navigation", "التنقل")}
          >
            <a href="#comment" onClick={() => setMenu(false)}>
              {t("Comment ça marche", "كيفاش كيخدم")}
            </a>
            <a href="#pour-vous" onClick={() => setMenu(false)}>
              {t("Pensé pour vous", "مصاوب ليك")}
            </a>
            <a href="#questions" onClick={() => setMenu(false)}>
              {t("Vos questions", "الأسئلة ديالك")}
            </a>
          </nav>
          <div className="landing-nav-actions">
            <div className="language-switch">
              <TranslateIcon size={17} />
              <button
                aria-pressed={language === "fr"}
                onClick={() => setLanguage("fr")}
              >
                FR
              </button>
              <button
                lang="ar"
                aria-pressed={language === "ary"}
                onClick={() => setLanguage("ary")}
              >
                الدارجة
              </button>
            </div>
            <a href={app} className="landing-button nav-cta">
              {t("Ouvrir DarijaDoc", "حل داريجة دوك")}
              <ArrowUpRight size={16} />
            </a>
            <button
              className="mobile-menu-button"
              aria-expanded={menu}
              aria-controls="landing-menu"
              aria-label={t("Menu", "القائمة")}
              onClick={() => setMenu(!menu)}
            >
              {menu ? <X size={23} /> : <List size={23} />}
            </button>
          </div>
        </div>
      </header>
      <main id="landing-main">
        <section className="landing-hero landing-container">
          <div className="hero-copy">
            <span className="hero-eyebrow">
              <Heart size={17} weight="duotone" />
              {t(
                "La santé, à portée de compréhension",
                "الصحة، بكلام تقدر تفهمو",
              )}
            </span>
            <h1>
              {t("Votre santé.", "صحتك.")}
              <br />
              {t("En mots simples.", "بكلام بسيط.")}
            </h1>
            <p>
              {t(
                "Comprenez vos ordonnances et analyses en français ou en darija. Et sachez quelle question poser ensuite.",
                "فهم الوصفات والتحاليل ديالك بالفرنسية ولا بالدارجة. وعرف شنو تسول من بعد.",
              )}
            </p>
            <div className="hero-actions">
              <a className="landing-button" href={app}>
                {t("Ouvrir DarijaDoc", "حل داريجة دوك")}
                <ArrowRight size={18} />
              </a>
              <a className="landing-secondary" href="#comment">
                <Play size={16} weight="fill" />
                {t("Voir comment ça marche", "شوف كيفاش كيخدم")}
              </a>
            </div>
          </div>
          <div className="hero-image">
            <img
              src="https://img.magnific.com/photos-premium/illustration-medicale-conceptuelle-isolee-creee-ia-generative_115122-96209.jpg"
              width="1536"
              height="1024"
              fetchPriority="high"
              alt={t(
                "Illustration médicale conceptuelle.",
                "صورة توضيحية للمجال الطبي.",
              )}
            />
          </div>
        </section>
        <div className="landing-container">
          <div className="capability-strip">
            <span>
              <FileText size={21} />
              {t("Vos documents, expliqués", "وثائقك، مشروحة")}
            </span>
            <span>
              <SpeakerHigh size={21} />
              {t("À lire ou à écouter", "قرا ولا سمع")}
            </span>
            <span>
              <CalendarDots size={21} />
              {t("Votre quotidien, organisé", "نهارك، منظم")}
            </span>
            <span className="strip-language" lang="ar" dir="rtl">
              نفهموها مجموعين.
            </span>
          </div>
        </div>
        <section
          className="landing-section landing-container"
          id="comment"
          data-reveal
        >
          <div className="section-intro">
            <h2>
              {t("Moins de jargon.", "كلام أقل تعقيد.")}
              <br />
              {t("Plus de compréhension.", "وفهم أكثر.")}
            </h2>
            <p>
              {t(
                "Une aide simple, du premier mot difficile à votre programme quotidien.",
                "مساعدة ساهلة، من أول كلمة صعيبة حتى للبرنامج اليومي ديالك.",
              )}
            </p>
          </div>
          <ProductDemo language={language} t={t} />
        </section>
        <section
          className="landing-container audience-section"
          id="pour-vous"
          data-reveal
        >
          <div className="audience-heading">
            <h2>
              {t("Parce que comprendre", "حيت الفهم")}
              <br />
              {t("change la conversation.", "كيبدل المحادثة.")}
            </h2>
            <p>
              {t(
                "Pour vous. Pour vos parents. Pour les questions qu’on n’a pas toujours osé poser.",
                "ليك. لواليديك. وللأسئلة اللي ما قدرناش ديما نسولوها.",
              )}
            </p>
          </div>
          <div className="audience-grid">
            <article className="darija-feature">
              <div className="feature-top">
                <SpeakerHigh size={26} />
                <span>{t("Dans votre langue", "باللغة ديالك")}</span>
              </div>
              <div className="arabic-feature-type" lang="ar" dir="rtl">
                ماشي ضروري تفهم
                <br />
                الطب، باش تفهم صحتك.
              </div>
              <p>
                {t(
                  "Des mots du quotidien, en darija ou en français. Une explication que vous pouvez aussi écouter.",
                  "كلام ديال كل نهار، بالدارجة ولا بالفرنسية. وشرح تقدر حتى تسمعو.",
                )}
              </p>
              <AudioButton
                text={t(
                  "Votre santé mérite des mots que vous comprenez. DarijaDoc vous aide à lire vos documents, à votre rythme.",
                  "صحتك كتستاهل كلام تفهمو. داريجة دوك كيساعدك تقرا الوثائق ديالك، على خاطرك.",
                )}
                language={language}
                t={t}
                label={t("Écouter un aperçu", "سمع مثال")}
              />
            </article>
            <article className="followup-feature">
              <div className="feature-top">
                <CalendarDots size={26} />
                <span>{t("Après l’explication", "من بعد الشرح")}</span>
              </div>
              <h3>
                {t("Un peu de clarté.", "شوية ديال الوضوح.")}
                <br />
                {t("Pour la suite aussi.", "حتى للخطوة الجاية.")}
              </h3>
              <p>
                {t(
                  "Posez une question, préparez votre échange avec le pharmacien ou organisez un traitement confirmé.",
                  "سول سؤال، وجد المحادثة مع الصيدلي ولا نظم علاج تأكدتي منو.",
                )}
              </p>
              <a href={`${app}&demo=1`} className="landing-text-link">
                {t("Explorer un exemple complet", "شوف مثال كامل")}
                <ArrowUpRight size={18} />
              </a>
              <div className="feature-path" aria-hidden="true">
                <FileText size={24} />
                <span />
                <CheckCircle size={24} />
                <span />
                <CalendarDots size={24} />
              </div>
            </article>
          </div>
        </section>
        <section className="landing-container trust-section" data-reveal>
          <div className="trust-mark">
            <ShieldCheck size={42} weight="duotone" />
          </div>
          <div>
            <h2>{t("Une aide. Pas un diagnostic.", "مساعدة. ماشي تشخيص.")}</h2>
            <p>
              {t(
                "DarijaDoc vous aide à mieux comprendre, sans remplacer votre médecin. Les informations incertaines sont signalées et les instructions restent à vérifier.",
                "داريجة دوك كيساعدك تفهم مزيان، بلا ما يعوض الطبيب. المعلومات اللي ما مؤكداش كتبان، والتعليمات خاصها التأكد.",
              )}
            </p>
            <a href={`${app}&tab=accuracy`} className="landing-text-link">
              {t("Comprendre nos limites", "فهم الحدود ديالنا")}
              <ArrowRight size={17} />
            </a>
          </div>
        </section>
        <section
          className="landing-section landing-container faq-section"
          id="questions"
          data-reveal
        >
          <div>
            <h2>
              {t("Vous vous demandez", "يمكن كتسول")}
              <br />
              {t("peut-être…", "راسك…")}
            </h2>
            <p>
              {t(
                "Quelques réponses, avant de commencer.",
                "شي أجوبة، قبل ما تبدا.",
              )}
            </p>
          </div>
          <div className="faq-list">
            {faqs.map(([question, answer], i) => (
              <details key={i}>
                <summary>
                  {question}
                  <CaretDown size={19} />
                </summary>
                <p>{answer}</p>
              </details>
            ))}
          </div>
        </section>
        <section className="landing-container closing-section" data-reveal>
          <div className="closing-surface">
            <Logo animated />
            <h2>
              {t("Faisons le point, ensemble.", "نفهمو الأمور، مجموعين.")}
            </h2>
            <p>
              {t(
                "Votre prochain pas commence par une explication claire.",
                "الخطوة الجاية ديالك كتبدا بشرح واضح.",
              )}
            </p>
            <a className="landing-button" href={app}>
              {t("Ouvrir DarijaDoc", "حل داريجة دوك")}
              <ArrowRight size={18} />
            </a>
          </div>
        </section>
      </main>
      <footer className="landing-footer landing-container">
        <div className="landing-footer-top">
          <a href="/" aria-label="DarijaDoc">
            <Brand />
          </a>
          <p>
            {t(
              "Pensé pour le Maroc. À comprendre partout.",
              "مصاوب للمغرب. مفهوم فكل بلاصة.",
            )}
          </p>
          <a href="#questions">
            {t("Questions fréquentes", "الأسئلة المتكررة")}
          </a>
        </div>
        <div className="landing-footer-bottom">
          <span>
            {t(
              "Prototype de hackathon · Visuel illustratif généré par IA",
              "نسخة ديال الهاكاثون · صورة توضيحية مولدة بالذكاء الاصطناعي",
            )}
          </span>
          <button onClick={() => setPaused(!paused)} aria-pressed={paused}>
            {paused ? <Play size={13} /> : <Pause size={13} />}{" "}
            {paused
              ? t("Activer les animations", "شغل الحركة")
              : t("Réduire les animations", "نقص الحركة")}
          </button>
          <span>DarijaDoc © {new Date().getFullYear()}</span>
        </div>
      </footer>
    </div>
  );
}
