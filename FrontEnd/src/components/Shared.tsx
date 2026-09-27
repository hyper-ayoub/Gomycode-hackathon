import { useState, useEffect } from "react";
import {
  WarningCircle,
  SpeakerHigh,
  Stop,
  CircleNotch,
  ArrowUpRight,
} from "@phosphor-icons/react";
import type { Language, Translate } from "../types";
import { apiError, nearbyPharmacies, type Facility } from "../lib/api";
import { Logo } from "./Logo";
export function Brand({ small = false }: { small?: boolean }) {
  return (
    <div className={`brand ${small ? "small" : ""}`}>
      <Logo />
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
const MAPS_FALLBACK = "https://www.google.com/maps/search/pharmacie/";
function mapsLink(place: Facility) {
  return `https://www.google.com/maps/search/?api=1&query=${place.lat},${place.lon}`;
}
export function PharmacyLink({
  t,
  variant = "link",
}: {
  t: Translate;
  variant?: "link" | "sidebar";
}) {
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">(
    "idle",
  );
  const [places, setPlaces] = useState<Facility[]>([]);
  const [notice, setNotice] = useState("");
  const label =
    variant === "sidebar"
      ? t("Une pharmacie près de moi", "صيدلية قريبة ليا")
      : t("Trouver une pharmacie", "قلب على صيدلية");
  function find() {
    if (status === "loading") return;
    setNotice("");
    if (!navigator.geolocation) {
      window.open(MAPS_FALLBACK, "_blank", "noopener");
      return;
    }
    setStatus("loading");
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const results = await nearbyPharmacies(
            position.coords.latitude,
            position.coords.longitude,
          );
          setPlaces(results);
          setStatus("ready");
          if (results.length === 0) {
            setNotice(
              t(
                "Aucune pharmacie trouvée dans les 5 km. La carte reste disponible.",
                "ما لقيناش صيدلية فـ 5 كم. الخريطة باقية متاحة.",
              ),
            );
          }
        } catch (err) {
          setPlaces([]);
          setStatus("error");
          setNotice(apiError(err, t, "places"));
        }
      },
      () => {
        setStatus("error");
        setNotice(
          t(
            "La position n’est pas disponible. Ouvrez la carte pour chercher une pharmacie.",
            "الموقع ما متوفرش. حل الخريطة باش تقلب على صيدلية.",
          ),
        );
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 },
    );
  }
  return (
    <div className={variant === "sidebar" ? "sidebar-pharmacy-block" : "nearby-block"}>
      <button
        type="button"
        className={variant === "sidebar" ? "sidebar-pharmacy" : "text-link"}
        onClick={find}
        disabled={status === "loading"}
      >
        {status === "loading" ? t("Recherche…", "كنقلبو…") : label}
        <ArrowUpRight size={variant === "sidebar" ? 16 : 17} />
      </button>
      {places.length > 0 && (
        <ul className="nearby-list">
          {places.map((place) => (
            <li key={`${place.lat},${place.lon},${place.name}`}>
              <a href={mapsLink(place)} target="_blank" rel="noreferrer">
                <span>{place.name}</span>
                <small>{place.distance_km.toFixed(1)} km</small>
              </a>
            </li>
          ))}
        </ul>
      )}
      {notice && <p className="nearby-status">{notice}</p>}
      {status === "error" && (
        <a
          className="nearby-status"
          href={MAPS_FALLBACK}
          target="_blank"
          rel="noreferrer"
        >
          {t("Ouvrir la carte", "حل الخريطة")}
        </a>
      )}
    </div>
  );
}
