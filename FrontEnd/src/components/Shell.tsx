import {
  FileText,
  CalendarDots,
  ChatsCircle,
  ChartBar,
  ArrowUpRight,
  Heart,
  Translate as TranslateIcon,
  ShieldCheck,
} from "@phosphor-icons/react";
import type { Language, Tab, Translate } from "../types";
import { Brand } from "./Shared";
export function Shell({
  tab,
  setTab,
  language,
  setLanguage,
  t,
  children,
}: {
  tab: Tab;
  setTab: (tab: Tab) => void;
  language: Language;
  setLanguage: (l: Language) => void;
  t: Translate;
  children: React.ReactNode;
}) {
  const links = [
    {
      id: "explain" as const,
      icon: FileText,
      label: t("Comprendre", "فهم الوثيقة"),
      sub: t("Ordonnances & analyses", "الوصفات والتحاليل"),
    },
    {
      id: "treatment" as const,
      icon: CalendarDots,
      label: t("Mon traitement", "العلاج ديالي"),
      sub: t("Mon programme quotidien", "البرنامج اليومي"),
    },
    {
      id: "chat" as const,
      icon: ChatsCircle,
      label: t("Mes questions", "الأسئلة ديالي"),
      sub: t("En parler simplement", "نهضرو ببساطة"),
    },
    {
      id: "accuracy" as const,
      icon: ChartBar,
      label: t("Notre fiabilité", "الموثوقية"),
      sub: t("En toute transparence", "بكل شفافية"),
    },
  ];
  return (
    <div
      className="app-shell"
      dir={language === "ary" ? "rtl" : "ltr"}
      lang={language === "ary" ? "ar-MA" : "fr"}
    >
      <a className="skip-link" href="#main">
        {t("Aller au contenu", "سير للمحتوى")}
      </a>
      <aside className="sidebar">
        <Brand />
        <div className="nav-label">
          {t("Votre espace santé", "الفضاء الصحي ديالك")}
        </div>
        <nav aria-label={t("Navigation principale", "التنقل الرئيسي")}>
          {links.map(({ id, icon: Icon, label, sub }) => (
            <button
              key={id}
              className={`nav-item ${tab === id ? "active" : ""}`}
              onClick={() => setTab(id)}
              aria-current={tab === id ? "page" : undefined}
            >
              <Icon size={23} weight={tab === id ? "fill" : "regular"} />
              <span>
                {label}
                <small>{sub}</small>
              </span>
              {tab === id && <span className="nav-active-mark" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <Heart size={22} />
            <strong>
              {t("Un peu plus de clarté.", "شوية ديال الوضوح.")}
              <br />
              {t("Un peu moins d’inquiétude.", "شوية أقل ديال القلق.")}
            </strong>
            <p>
              {t(
                "Votre santé mérite des mots que vous comprenez.",
                "صحتك كتستاهل كلام تفهمو.",
              )}
            </p>
          </div>
          <a
            href="https://www.google.com/maps/search/pharmacie/"
            target="_blank"
            rel="noreferrer"
            className="sidebar-pharmacy"
          >
            {t("Une pharmacie près de moi", "صيدلية قريبة ليا")}
            <ArrowUpRight size={16} />
          </a>
          <div className="made-in">
            {t("Pensé pour le Maroc", "مصاوب للمغرب")}
            <span className="morocco-mark">✳</span>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            <span>{t("Mon espace", "الفضاء ديالي")}</span>
            <span>/</span>
            <strong>{links.find((l) => l.id === tab)?.label}</strong>
          </div>
          <div className="topbar-actions">
            <span className="prototype-label">
              {t("Prototype", "نسخة تجريبية")}
            </span>
            <div className="language-switch" aria-label={t("Langue", "اللغة")}>
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
          </div>
        </header>
        <main id="main" tabIndex={-1}>
          {children}
        </main>
        <footer className="footer">
          <span>
            <ShieldCheck size={17} />
            {t(
              "Pour mieux comprendre. Votre professionnel de santé reste votre référence.",
              "باش تفهم مزيان. المهني الصحي ديالك كيبقى هو المرجع.",
            )}
          </span>
          <span>
            DarijaDoc <span className="footer-dot">·</span>{" "}
            {t("Fait avec attention", "مصاوب بعناية")}
          </span>
        </footer>
      </div>
    </div>
  );
}
