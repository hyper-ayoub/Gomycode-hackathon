import { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  ChatsCircle,
  FileText,
  Info,
  ArrowRight,
  Trash,
  WarningCircle,
  Microphone,
  Stop,
} from "@phosphor-icons/react";
import type { Explanation, Language, Message, Translate } from "../types";
import { AudioButton, Loader } from "../components/Shared";
import { apiError, chat, transcribe } from "../lib/api";
export function ChatTab({
  t,
  language,
  result,
  demo,
}: {
  t: Translate;
  language: Language;
  result: Explanation | null;
  demo: boolean;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "instant", block: "nearest" });
  }, [messages]);
  useEffect(
    () => () => {
      const active = recorder.current;
      if (active && active.state !== "inactive") {
        active.onstop = null;
        active.stop();
      }
      stream.current?.getTracks().forEach((track) => track.stop());
    },
    [],
  );
  async function toggleMic() {
    if (demo || busy) return;
    if (recording && recorder.current) {
      recorder.current.stop();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError(apiError(new Error("MIC_DENIED"), t, "voice"));
      return;
    }
    try {
      const next = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = next;
      const mime = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : MediaRecorder.isTypeSupported("audio/mp4")
          ? "audio/mp4"
          : "";
      const rec = new MediaRecorder(next, mime ? { mimeType: mime } : undefined);
      const chunks: Blob[] = [];
      rec.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      rec.onstop = async () => {
        next.getTracks().forEach((track) => track.stop());
        stream.current = null;
        setRecording(false);
        const blob = new Blob(chunks, { type: rec.mimeType || mime || "audio/webm" });
        if (!blob.size) return;
        setBusy(true);
        setError("");
        try {
          const text = await transcribe(blob);
          setInput((current) => (current.trim() ? `${current.trim()} ${text}` : text));
        } catch (err) {
          setError(apiError(err, t, "voice"));
        } finally {
          setBusy(false);
        }
      };
      recorder.current = rec;
      rec.start();
      setRecording(true);
      setError("");
    } catch {
      setError(apiError(new Error("MIC_DENIED"), t, "voice"));
    }
  }
  async function send(text = input) {
    if (!text.trim() || busy || recording) return;
    const next: Message[] = [
      ...messages,
      { role: "user", content: text.trim() },
    ];
    setMessages(next);
    setInput("");
    setBusy(true);
    setError("");
    try {
      if (demo) {
        setMessages([
          ...next,
          {
            role: "assistant",
            content: t(
              "Réponse de démonstration : le traitement A est fictif. Dans une vraie ordonnance, vous pouvez demander au pharmacien de vous expliquer les instructions et de confirmer les horaires. Cet exemple illustre la conversation ; il n’analyse pas votre question.",
              "جواب للتجربة: العلاج A خيالي. فالوصفة الحقيقية، تقدر تطلب من الصيدلي يشرح ليك التعليمات ويأكد ليك الأوقات. هاد المثال غير باش تشوف المحادثة، ما كيحللش السؤال ديالك.",
            ),
          },
        ]);
      } else {
        const answer = await chat(next, language, result);
        setMessages([...next, answer]);
      }
    } catch (err) {
      setMessages(messages);
      setInput(text);
      setError(apiError(err, t, "chat"));
    } finally {
      setBusy(false);
    }
  }
  const suggestions = [
    t("Expliquez plus simplement", "شرح ليا بطريقة أسهل"),
    t("Que demander au pharmacien ?", "شنو نسول الصيدلي؟"),
    t("Quelles informations vérifier ?", "شنو خاصني نتأكد منو؟"),
  ];
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">
            <ChatsCircle size={18} />
            {t("Chaque question compte", "كل سؤال مهم")}
          </div>
          <h1>{t("Parlons-en simplement.", "نهضرو ببساطة.")}</h1>
          <p>
            {t(
              "Posez vos questions, avec vos mots. En français ou en darija.",
              "سول بالكلام ديالك. بالفرنسية ولا بالدارجة.",
            )}
          </p>
        </div>
        {messages.length > 0 && (
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => setMessages([])}
          >
            <Trash size={17} />
            {t("Effacer", "مسح")}
          </button>
        )}
      </div>
      {demo && (
        <div className="demo-banner">
          <Info size={19} />
          {t(
            "Conversation de démonstration : réponses prédéfinies, sans analyse médicale.",
            "محادثة للتجربة: أجوبة موجودة من قبل، بلا تحليل طبي.",
          )}
        </div>
      )}
      <div className="chat-layout">
        <section className="panel chat-panel">
          <div className="panel-heading">
            <span className="inline">
              <span className="chat-avatar">
                <ChatsCircle size={22} weight="fill" />
              </span>
              <span>
                <h2>DarijaDoc</h2>
                <small>
                  {t("Votre aide à la compréhension", "مساعدك باش تفهم")}
                </small>
              </span>
            </span>
            <span className="subtle-tag">
              {demo ? t("Exemple", "مثال") : t("Assistant", "مساعد")}
            </span>
          </div>
          <div
            className="conversation"
            aria-live="polite"
            role="log"
            aria-label={t("Conversation", "المحادثة")}
          >
            {messages.length === 0 ? (
              <div className="chat-welcome">
                <span className="empty-icon">
                  <ChatsCircle size={38} weight="duotone" />
                </span>
                <h2>
                  {t(
                    "Qu’aimeriez-vous mieux comprendre ?",
                    "شنو بغيتي تفهم مزيان؟",
                  )}
                </h2>
                <p>
                  {t(
                    "Un mot inconnu, une instruction peu claire… Vous pouvez commencer ici.",
                    "كلمة ما فهمتيهاش ولا تعليمات ما واضحاش… بدا من هنا.",
                  )}
                </p>
                <div className="suggestions">
                  {suggestions.map((s) => (
                    <button key={s} onClick={() => send(s)}>
                      {s}
                      <ArrowRight size={16} />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m, i) => (
                <div className={`message ${m.role}`} key={i}>
                  <small>
                    {m.role === "assistant" ? "DarijaDoc" : t("Vous", "نتا")}
                  </small>
                  {m.emergency && (
                    <strong className="emergency-label">
                      <WarningCircle size={19} />
                      {t("Attention urgente", "تنبيه مستعجل")}
                    </strong>
                  )}
                  <p dir="auto">{m.content}</p>
                  {m.role === "assistant" && (
                    <AudioButton
                      text={m.content}
                      language={language}
                      t={t}
                      label={t("Écouter", "سمع")}
                    />
                  )}
                </div>
              ))
            )}
            {busy && (
              <div className="message assistant">
                <Loader
                  label={t("Préparation de la réponse…", "كنوجدو الجواب…")}
                />
              </div>
            )}
            <div ref={end} />
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <form
            className="chat-composer"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <label className="sr-only" htmlFor="message">
              {t("Votre question", "السؤال ديالك")}
            </label>
            <textarea
              id="message"
              rows={2}
              maxLength={3000}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t(
                "Écrivez votre question ici…",
                "كتب السؤال ديالك هنا…",
              )}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            {!demo && (
              <button
                type="button"
                className={`mic-button ${recording ? "recording" : ""}`}
                disabled={busy}
                onClick={toggleMic}
                aria-pressed={recording}
                aria-label={
                  recording
                    ? t("Arrêter l’enregistrement", "وقف التسجيل")
                    : t("Dicter une question", "قول السؤال")
                }
              >
                {recording ? <Stop size={18} weight="fill" /> : <Microphone size={18} />}
              </button>
            )}
            <button
              className="send-button"
              disabled={!input.trim() || busy || recording}
              aria-label={t("Envoyer la question", "صيفط السؤال")}
            >
              <ArrowUp size={22} />
            </button>
          </form>
          <div className="chat-disclaimer">
            {t(
              "DarijaDoc peut se tromper. Vérifiez les informations importantes avec un professionnel.",
              "داريجة دوك يقدر يغلط. تأكد من المعلومات المهمة مع مهني صحي.",
            )}
          </div>
        </section>
        <aside className="chat-context">
          <span className="support-icon">
            <FileText size={25} />
          </span>
          <h3>{t("Le contexte de votre échange", "السياق ديال المحادثة")}</h3>
          <p>
            {result
              ? t(
                  "L’explication de votre document accompagne vos questions.",
                  "الشرح ديال الوثيقة كيتصيفط مع الأسئلة.",
                )
              : t(
                  "Ajoutez d’abord un document dans « Comprendre » pour poser des questions à son sujet.",
                  "زيد وثيقة فـ «فهم الوثيقة» باش تسول عليها.",
                )}
          </p>
          {result && (
            <div className="context-document">
              <FileText size={20} />
              {result.document_type}
            </div>
          )}
          <div className="context-divider" />
          <Info size={21} />
          <p>
            {t(
              "Posez une question à la fois et évitez de partager des informations personnelles inutiles.",
              "سول سؤال واحد فكل مرة وما تشاركش معلومات شخصية ما محتاجاش.",
            )}
          </p>
        </aside>
      </div>
    </div>
  );
}
