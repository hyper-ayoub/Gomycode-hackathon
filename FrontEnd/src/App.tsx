import { useEffect, useState } from "react";
import type { Explanation, Language, Plan, Tab, Translate } from "./types";
import { Shell } from "./components/Shell";
import { ExplainTab } from "./features/ExplainTab";
import { TreatmentTab } from "./features/TreatmentTab";
import { ChatTab } from "./features/ChatTab";
import { AccuracyTab } from "./features/AccuracyTab";
import { demoExplanation } from "./lib/demo";
export default function App() {
  const [tab, setTab] = useState<Tab>("explain");
  const [language, setLanguage] = useState<Language>("fr");
  const [result, setResult] = useState<Explanation | null>(null);
  const [demo, setDemo] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [review, setReview] = useState(false);
  const t: Translate = (fr, ary) => (language === "fr" ? fr : ary);
  function navigate(next: Tab) {
    window.speechSynthesis?.cancel();
    setTab(next);
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  useEffect(() => {
    document.documentElement.lang = language === "ary" ? "ar-MA" : "fr";
    document.documentElement.dir = language === "ary" ? "rtl" : "ltr";
    if (demo && result) setResult(demoExplanation(language));
  }, [language]);
  return (
    <Shell
      tab={tab}
      setTab={navigate}
      language={language}
      setLanguage={setLanguage}
      t={t}
    >
      <div hidden={tab !== "explain"}>
        <ExplainTab
          language={language}
          t={t}
          result={result}
          setResult={setResult}
          demo={demo}
          setDemo={setDemo}
          onSchedule={() => {
            setReview(true);
            navigate("treatment");
          }}
          onChat={() => navigate("chat")}
        />
      </div>
      {tab === "treatment" && (
        <TreatmentTab
          t={t}
          result={result}
          plan={plan}
          setPlan={setPlan}
          demo={demo}
          startReview={review}
          setStartReview={setReview}
          onExplain={() => navigate("explain")}
        />
      )}
      <div hidden={tab !== "chat"}>
        <ChatTab
          key={result ? `${demo}:${result.summary}` : "no-document"}
          t={t}
          language={language}
          result={result}
          demo={demo}
        />
      </div>
      {tab === "accuracy" && <AccuracyTab t={t} />}
    </Shell>
  );
}
