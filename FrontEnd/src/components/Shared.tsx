import { useEffect, useState } from "react";
import {
  WarningCircle,
  SpeakerHigh,
  Stop,
  CircleNotch,
  ArrowUpRight,
  FirstAidKit,
} from "@phosphor-icons/react";
import type { Language, Translate } from "../types";
export function Brand({ small = false }: { small?: boolean }) {
  return (
    <div className={`brand ${small ? "small" : ""}`}>
      <span className="brand-icon">
        <FirstAidKit size={26} weight="fill" />
      </span>
      <span>
        Darija<span className="brand-light">Doc</span>
        <small>صحتك، بكلام بسيط</small>
      </span>
    </div>
  );
}
export function Emergency({ message, t }: { message: string; t: Translate }) {
  return (
    <div className="emergency" role="alert">
      <WarningCircle size={26} weight="fill" />
      <div>
        <strong>
          {t(
            "Une attention immédiate peut être nécessaire",
            "يمكن تحتاج مساعدة دابا",
          )}
        </strong>
        <p>
          {message ||
            t(
              "Contactez un professionnel de santé sans attendre.",
              "تاصل بشي مهني صحي بلا ما تسنى.",
            )}
        </p>
      </div>
    </div>
  );
}
export function Loader({ label }: { label: string }) {
  return (
    <span className="inline">
      <CircleNotch className="spin" size={20} />
      {label}
    </span>
  );
}
export function AudioButton({
  text,
  language,
  t,
  label,
}: {
  text: string;
  language: Language;
  t: Translate;
  label?: string;
}) {
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setPlaying(false);
    window.speechSynthesis?.getVoices();
    return () => {
      window.speechSynthesis?.cancel();
    };
  }, [text, language]);
  function play() {
    if (!("speechSynthesis" in window)) {
      setError(
        t(
          "La lecture audio n’est pas disponible dans ce navigateur.",
          "الصوت ما متوفرش فهاد المتصفح.",
        ),
      );
      return;
    }
    if (playing && window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
      setPlaying(false);
      return;
    }
    const voices = speechSynthesis.getVoices();
    const prefix = language === "fr" ? "fr" : "ar";
    const voice =
      voices.find(
        (v) => v.lang.toLowerCase() === (language === "fr" ? "fr-fr" : "ar-ma"),
      ) || voices.find((v) => v.lang.startsWith(prefix));
    if (!voice) {
      setError(
        t(
          "Aucune voix compatible installée. Le texte reste disponible.",
          "ما كاينش صوت مناسب مثبت. تقدر تقرا النص.",
        ),
      );
      return;
    }
    setError("");
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = 0.9;
    utterance.onend = () => setPlaying(false);
    utterance.onerror = () => {
      setPlaying(false);
      setError(t("Lecture audio interrompue.", "توقف الصوت."));
    };
    setPlaying(true);
    speechSynthesis.speak(utterance);
  }
  return (
    <div>
      <button className="audio-button" onClick={play}>
        {playing ? <Stop size={18} weight="fill" /> : <SpeakerHigh size={20} />}{" "}
        {playing
          ? t("Arrêter", "وقف")
          : label || t("Écouter l’explication", "سمع الشرح")}
        {playing && (
          <span className="audio-bars" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
          </span>
        )}
      </button>
      {language === "ary" && (
        <small className="audio-note">
          {t(
            "Prononciation selon la voix arabe disponible.",
            "النطق على حساب الصوت العربي المتوفر.",
          )}
        </small>
      )}
      {error && (
        <small role="status" className="error-text">
          {error}
        </small>
      )}
    </div>
  );
}
export function PharmacyLink({ t }: { t: Translate }) {
  return (
    <a
      className="text-link"
      href="https://www.google.com/maps/search/pharmacie/"
      target="_blank"
      rel="noreferrer"
    >
      {t("Trouver une pharmacie", "قلب على صيدلية")}
      <ArrowUpRight size={17} />
    </a>
  );
}
