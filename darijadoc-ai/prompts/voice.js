/**
 * DarijaDoc — voice output (Member 3).
 *
 * Drop this in. It needs no build step and no dependencies.
 *
 * Why Arabic script: no phone or browser TTS engine will read Darija written in
 * Latin letters. It reads it as English gibberish. So the model sends a parallel
 * Darija-in-Arabic-script copy of every field, and we speak that.
 */

const DARIJA = "ar-MA";
const FRENCH = "fr-FR";

/* ------------------------------------------------------------------ *
 * Two speech backends
 * ------------------------------------------------------------------ */

const TTS_MODEL = "gpt-4o-mini-tts";
const TTS_VOICE = "shimmer";

/**
 * Play one rendered clip. Assigns the module-level `audio` handle so that
 * stopSpeaking() can actually interrupt it — the element used to be a local
 * const, which meant the Play/Stop button could not stop server TTS at all and
 * the clip played to the end no matter what the patient pressed.
 */
function speakViaServer(clip) {
  return new Promise((resolve) => {
    const u = new Audio();
    audio = u;
    u.src = URL.createObjectURL(clip instanceof Blob ? clip : new Blob([clip], { type: "text/plain" }));
    const done = () => {
      URL.revokeObjectURL(u.src);
      if (audio === u) audio = null;
      resolve();
    };
    u.onended = done;
    u.onerror = done; // a dropped clip must not stall the chain
    const started = u.play();
    if (started && typeof started.catch === "function") started.catch(done);
  });
}

/**
 * Ask the server to render one clip. Rejects so the caller can fall back.
 *
 * `instructions` is what carries the per-part language. The whole response goes
 * out as a single request, so a patient hears one continuous utterance rather
 * than five clips with gaps in between — but without this the server would read
 * the French passage with the same voice and rate as the Darija one, because a
 * bare string carries no language boundary.
 */
export async function fetchClip(text, { voice = TTS_VOICE, model = TTS_MODEL, instructions = null } = {}) {
  const body = { text, voice, model };
  if (instructions) body.instructions = instructions;
  const res = await fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.error || `tts ${res.status}`);
  }
  return res.blob();
}

/* ------------------------------------------------------------------ *
 * Voice discovery
 * ------------------------------------------------------------------ */

/**
 * Chrome populates getVoices() asynchronously and returns [] on the first
 * call, so a naive check reports "no Arabic voice" on a device that has one.
 * Wait for voiceschanged, then resolve for real.
 */
function loadVoices() {
  return new Promise((resolve) => {
    const immediate = speechSynthesis.getVoices();
    if (immediate && immediate.length) return resolve(immediate);

    let settled = false;
    const done = (v) => {
      if (settled) return;
      settled = true;
      resolve(v);
    };
    speechSynthesis.addEventListener("voiceschanged", () => done(speechSynthesis.getVoices()), { once: true });
    // Some platforms never fire voiceschanged. Don't hang the UI on it.
    setTimeout(() => done(speechSynthesis.getVoices()), 1200);
  });
}

function pickVoice(voices, lang) {
  if (!voices || !voices.length) return null;
  const base = lang.split("-")[0];
  return (
    voices.find((v) => v.lang === lang) ||
    voices.find((v) => v.lang && v.lang.toLowerCase().startsWith(base)) ||
    null
  );
}

/**
 * Probes what this device can actually speak.
 *
 * `server` is the one that matters: the OpenAI TTS path needs nothing from the
 * device beyond audio playback, so it is the primary path. It is probed against
 * /api/health rather than assumed, because "fetch and Audio exist" is true on
 * every browser including the ones where /api/tts is down — and a feature that
 * reports itself available and then stays silent is worse than one that says no.
 *
 * The `darija` / `french` flags only describe the browser fallback.
 */
export async function voiceSupport({ probe = true } = {}) {
  const canPlay = typeof Audio !== "undefined" && typeof URL !== "undefined";
  let server = false;
  let reason = null;

  if (canPlay && typeof fetch === "function") {
    if (probe) {
      try {
        const res = await fetch("/api/health");
        const health = await res.json();
        server = Boolean(health && health.tts);
        if (!server) reason = "server has no TTS key configured";
      } catch (e) {
        server = false;
        reason = `health probe failed: ${e.message}`;
      }
    } else {
      server = true;
    }
  } else {
    reason = "no Audio support";
  }

  if (typeof speechSynthesis === "undefined") {
    return { server, darija: false, french: false, reason: reason || "no speechSynthesis" };
  }
  const voices = await loadVoices();
  const darija = pickVoice(voices, DARIJA);
  const french = pickVoice(voices, FRENCH);
  return {
    server,
    voices,
    darija: Boolean(darija),
    french: Boolean(french),
    reason: server ? null : reason || "no Arabic voice installed and no server TTS",
  };
}

/* ------------------------------------------------------------------ *
 * Playback
 * ------------------------------------------------------------------ */

let speaking = false;
let audio = null;

// A counter, not a boolean. A boolean cannot tell "the user pressed stop" from
// "a newer response started and reset the flag", so a superseded response could
// resume talking over the current one.
let playToken = 0;

export function buildParts(result) {
  const parts = [];
  const ar = { text: result.explanation_darija_arabic, lang: DARIJA };
  const fr = { text: result.explanation_french, lang: FRENCH };

  if (result.tts_priority === "french") parts.push(fr, ar);
  else parts.push(ar, fr);

  (result.next_steps_arabic || []).forEach((s) => parts.push({ text: s, lang: DARIJA }));
  parts.push({ text: result.disclaimer_arabic, lang: DARIJA });
  return parts.filter((p) => p.text);
}

/** Tell the renderer which section is which language, in order. */
function buildInstructions(parts) {
  const seq = parts
    .map((p, i) => `${i + 1}. ${p.lang === FRENCH ? "French" : "Darija written in Arabic script"}`)
    .join(" ");
  return (
    `Read the text in order, switching language per section: ${seq}. ` +
    "Speak slowly and calmly, as if reassuring an elderly patient. " +
    "Do not read the section numbers, and do not add anything that is not in the text."
  );
}

/**
 * Play the response: server TTS first, browser speech as the fallback.
 *
 * The order still comes from buildParts, so the 150 call stays step 1 and the
 * disclaimer stays last.
 */
export async function speakResponse(result, { rate = 0.9, prefer = "server" } = {}) {
  stopSpeaking();
  const token = playToken;
  const cancelled = () => token !== playToken;
  speaking = true;

  const parts = buildParts(result);
  const text = parts.map((p) => p.text).join(". ");

  if (prefer === "server" && text) {
    try {
      const clip = await fetchClip(text, { instructions: buildInstructions(parts) });
      if (cancelled()) return;
      await speakViaServer(clip);
      if (cancelled()) return;
      speaking = false;
      return;
    } catch (e) {
      // No credits, no network, model unavailable: fall through to the browser
      // rather than leaving the patient with silence.
      if (cancelled()) return;
      console.warn("server TTS failed, using browser voice:", e.message);
    }
  }

  const voices = await loadVoices();
  for (const part of parts) {
    if (cancelled()) break;
    await speakOne(part, voices, rate);
  }
  if (!cancelled()) speaking = false;
}

function speakOne(part, voices, rate) {
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(part.text);
    const voice = pickVoice(voices, part.lang);
    if (voice) u.voice = voice;
    // Set lang regardless: if voice is null, the tag is still better than the
    // browser default, which may not be Arabic at all.
    u.lang = part.lang;
    u.rate = rate; // slower for elderly patients
    u.pitch = 1.0;
    // onend alone is not enough. If an utterance is dropped (no voice for the
    // tag, tab backgrounded, user switched apps) onend never fires and the
    // chain stalls with no audio and no error. onerror keeps it moving.
    u.onend = resolve;
    u.onerror = resolve;
    speechSynthesis.speak(u);
  });
}

export function stopSpeaking() {
  playToken++;
  speaking = false;
  if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
  if (audio) {
    audio.pause();
    audio = null;
  }
}

export function isSpeaking() {
  return speaking;
}

/** Highlight step 1 as the urgent one in the UI. Visual only, never spoken. */
export function styleEmergencyStep(stepEl) {
  if (!stepEl) return;
  stepEl.classList.add("step--urgent");
  stepEl.setAttribute("role", "alert");
}

/* ------------------------------------------------------------------ *
 * Usage
 * ------------------------------------------------------------------ */

/*
const support = await voiceSupport();
if (!support.server && !support.darija) {
  // No way to speak at all. Show the text large, and treat this as an error
  // state rather than a silent degrade: a patient who cannot read Darija and
  // cannot hear it has been left with nothing.
  console.warn("no speech available:", support.reason);
}
button.addEventListener("click", () => {
  if (isSpeaking()) return stopSpeaking();
  speakResponse(result);
});

// On mobile, speech must be started from a user gesture, or iOS blocks it.
// Call stopSpeaking on unmount too: audio that survives a route change keeps
// talking over the next page.
*/

// iOS: audio left running after navigation is a real problem.
if (typeof window !== "undefined") {
  window.addEventListener("pagehide", stopSpeaking);
}
