/**
 * DarijaDoc — voice contract tests.
 *
 *   node --test tests/voice.test.mjs
 *
 * The README used to claim "verified with node: 150 is spoken exactly once, in
 * both priority modes" with no test in the repo to back it. These are that
 * test. They are dependency-free and DOM-free: every browser global voice.js
 * touches is stubbed, and each case gets a fresh copy of the module so the
 * playback counter cannot leak between tests.
 *
 * The cases marked REGRESSION are bugs that shipped once. Keep them.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/* ------------------------------------------------------------------ *
 * Fixtures
 * ------------------------------------------------------------------ */

const DISCLAIMER_LATIN = "hadchi mjarrad chra7, machorch dakter awla.";
const DISCLAIMER_ARABIC = "هادشي مجرد شرح، مشورش دكتور أولا.";

/** An emergency response: the 150 call is in next_steps_arabic[0] by contract. */
function emergencyResult(over = {}) {
  return {
    input_language: "darija",
    mode: "explain",
    explanation_darija: "hadchi moudli ma3ndoch moudlil marad, 3afak 3ayet 150 daba.",
    explanation_darija_arabic: "هادشي مودلي ماعنديش مودليل مرض، عافاك عيط على 150 دابا.",
    explanation_french: "Ceci n'est pas un diagnostic, appelle le 150 maintenant.",
    next_steps: ["Aitel 150 daba", "Ruud mn ghiwda"],
    next_steps_arabic: ["عيط على 150 دابا", "رقد من غير ما تولى"],
    urgency_level: "high",
    emergency: true,
    emergency_reason: "douleurs thoraciques",
    location_required: true,
    requires_pharmacy_lookup: false,
    disclaimer: DISCLAIMER_LATIN,
    disclaimer_arabic: DISCLAIMER_ARABIC,
    tts_priority: "darija",
    prescription: null,
    ...over,
  };
}

const COUNT = (s, needle) => s.split(needle).length - 1;

/* ------------------------------------------------------------------ *
 * Browser stubs
 * ------------------------------------------------------------------ */

/**
 * @param {object} opts
 *   voices        the voice list getVoices() eventually hands back
 *   noVoicesEver  getVoices() never has any, for the "device has no voice" path
 *   lateVoices    getVoices() is empty until voiceschanged fires, as in Chrome
 *   ttsFails      how many /api/tts calls fail before one succeeds
 *   audioEndMs    how long a server clip "plays" for before firing onended
 */
function stubBrowser({ voices = [], noVoicesEver = false, lateVoices = false,
                       ttsFails = 0, audioEndMs = 0 } = {}) {
  const state = {
    spoken: [],       // browser-utterance records
    cancelCount: 0,
    audio: [],        // Audio elements created by speakViaServer
    tts: [],          // /api/tts request bodies
    health: { tts: true },
    dropped: false,   // make the next utterance die without firing onend
    listener: null,   // the registered voiceschanged handler
  };

  let revealed = !lateVoices;
  globalThis.speechSynthesis = {
    getVoices() {
      if (noVoicesEver || !revealed) return [];
      return voices;
    },
    addEventListener(_evt, cb) {
      state.listener = cb;
    },
    speak(u) {
      state.spoken.push({ text: u.text, lang: u.lang, voice: u.voice, rate: u.rate });
      setTimeout(() => {
        // A dropped utterance fires onerror and never onend. This is the
        // browser-drops-the-utterance case that used to stall the queue.
        if (state.dropped) {
          state.dropped = false;
          u.onerror?.(new Error("dropped"));
        } else {
          u.onend?.();
        }
      }, 0);
    },
    cancel() {
      state.cancelCount += 1;
    },
  };

  globalThis.SpeechSynthesisUtterance = class {
    constructor(text) {
      this.text = text;
    }
  };

  globalThis.Audio = class {
    constructor() {
      this.paused = false;
      this.played = false;
      this.src = null;
      this.finished = false;
      state.audio.push(this);
    }
    play() {
      this.played = true;
      // The clip ends on a timer, like real playback. A long audioEndMs is how
      // a test gets a window in which the clip is still running. unref keeps a
      // pending timer from holding the process open after the test is done.
      const t = setTimeout(() => {
        if (this.finished || this.paused) return;
        this.finished = true;
        this.onended?.();
      }, audioEndMs);
      t.unref?.();
      return Promise.resolve();
    }
    pause() {
      this.paused = true;
    }
  };

  /** End every in-flight clip now, the way a finished download would. */
  state.finishAudio = () => {
    for (const a of state.audio) {
      if (a.finished) continue;
      a.finished = true;
      a.onended?.();
    }
  };

  /** Publish the voice list and fire the event, as the platform does. */
  state.revealVoices = () => {
    revealed = true;
    state.listener?.();
  };

  let fails = ttsFails;
  globalThis.fetch = async (url, opts = {}) => {
    if (String(url).endsWith("/api/health")) {
      return { ok: true, json: async () => state.health };
    }
    if (String(url).endsWith("/api/tts")) {
      const body = JSON.parse(opts.body);
      state.tts.push(body);
      if (fails > 0) {
        fails -= 1;
        return { ok: false, status: 502, json: async () => ({ error: "no tts" }) };
      }
      return { ok: true, blob: async () => new Blob(["audio"], { type: "audio/mpeg" }) };
    }
    throw new Error(`unstubbed fetch: ${url}`);
  };

  return state;
}

let generation = 0;
/** A fresh copy of voice.js, so module-level playback state is not shared. */
async function freshVoice() {
  generation += 1;
  return import(`../prompts/voice.js?v=${generation}`);
}

const waitFor = async (fn, ms = 2000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (fn()) return;
    await new Promise((r) => setTimeout(r, 5));
  }
  throw new Error("waitFor timed out");
};

const spokenText = (state) => state.tts.map((c) => c.text).join("\n");

/* ------------------------------------------------------------------ *
 * Playback order
 * ------------------------------------------------------------------ */

test("buildParts follows tts_priority, steps in order, disclaimer last", async () => {
  const v = await freshVoice();
  const r = emergencyResult();

  const darija = v.buildParts(r);
  assert.ok(darija[0].text.startsWith("هادشي"), "Arabic explanation first for darija");
  assert.equal(darija[1].text, r.explanation_french, "French second");
  assert.deepEqual(darija.slice(2, 4).map((p) => p.text), r.next_steps_arabic);
  assert.equal(darija[darija.length - 1].text, DISCLAIMER_ARABIC, "disclaimer is always last");

  const french = v.buildParts(emergencyResult({ tts_priority: "french" }));
  assert.equal(french[0].text, r.explanation_french, "French first for french");
  assert.equal(french[french.length - 1].text, DISCLAIMER_ARABIC, "disclaimer still last");
});

test("the Latin Darija is never spoken, only displayed", async () => {
  const v = await freshVoice();
  const parts = v.buildParts(emergencyResult());
  assert.equal(parts.some((p) => p.text === emergencyResult().explanation_darija), false);
  assert.equal(parts.some((p) => p.text === DISCLAIMER_LATIN), false);
});

test("empty parts are dropped rather than spoken as blanks", async () => {
  const v = await freshVoice();
  const parts = v.buildParts(emergencyResult({ explanation_french: "", disclaimer_arabic: "..." }));
  assert.equal(parts.every((p) => p.text && p.text.trim()), true);
});

/* ------------------------------------------------------------------ *
 * The safety claims in the README
 * ------------------------------------------------------------------ */

test("150 is spoken exactly once when the model mentions it once", async () => {
  for (const tts_priority of ["darija", "french"]) {
    const state = stubBrowser();
    const v = await freshVoice();
    // The common shape: the model puts the call in the step and not in the prose.
    const r = emergencyResult({
      tts_priority,
      explanation_darija_arabic: "هادشي مودلي ماعنديش مودليل مرض، خاصك تعاود tourist-check.",
      explanation_french: "Ceci n'est pas un diagnostic, reposez-vous et reprenez contact.",
    });

    await v.speakResponse(r);

    const text = spokenText(state);
    assert.equal(COUNT(text, "150"), 1, `"150" heard ${COUNT(text, "150")}x for ${tts_priority}`);
    assert.ok(text.includes("عيط على 150 دابا"), "the model's own step carried the number");
    // The Latin next_steps mention 150 too; the display copy must not be read
    // aloud as well, or the number is heard twice.
    assert.equal(text.includes(r.next_steps[0]), false, "Latin steps are not spoken");
  }
});

test("voice.js adds no 150 announcement of its own, even when the model repeats it", async () => {
  // The model does sometimes name 150 in the Arabic explanation as well as in
  // next_steps_arabic[0] (see outputs/t02, t05). That is the model's wording,
  // not an app bug — what must never happen is the app bolting a third copy on,
  // which is what the spec's sample JS did. So: speak exactly what was returned.
  const state = stubBrowser();
  const v = await freshVoice();
  const r = emergencyResult(); // this fixture names 150 in prose and in the step

  await v.speakResponse(r);

  const fromModel = v.buildParts(r).reduce((n, p) => n + COUNT(p.text, "150"), 0);
  assert.equal(fromModel, 3, "fixture sanity: prose + French + step each mention 150");
  assert.equal(COUNT(spokenText(state), "150"), fromModel,
    "the spoken text must contain exactly the 150s the model returned");
});

test("the 150 call is the first step, in both priority modes", async () => {
  for (const tts_priority of ["darija", "french"]) {
    const v = await freshVoice();
    const r = emergencyResult({ tts_priority });
    const steps = v.buildParts(r).filter((p) => r.next_steps_arabic.includes(p.text));
    assert.ok(steps[0].text.includes("150"), `step 1 must be the call for ${tts_priority}`);
  }
});

test("REGRESSION: no hardcoded emergency banner can double-speak 150", async () => {
  // The spec's sample JS prepended a hardcoded Arabic emergency line *and* spoke
  // next_steps_arabic, so the patient heard "call 150" twice. No such banner may
  // exist in the module, and none may be left behind unused for the next person
  // to wire up.
  const src = readFileSync(new URL("../prompts/voice.js", import.meta.url), "utf8");
  assert.equal(/حالة طارئة/.test(src), false, "no hardcoded emergency announcement");
  assert.equal(/EMERGENCY_LINE/.test(src), false, "no unused emergency-line constant");
});

test("REGRESSION: stopSpeaking() pauses server TTS", async () => {
  const state = stubBrowser({ audioEndMs: 60000 });
  const v = await freshVoice();

  const playing = v.speakResponse(emergencyResult());
  await waitFor(() => state.audio.length > 0);
  assert.equal(state.audio[0].played, true, "the clip started");
  assert.equal(state.audio[0].paused, false, "and is still playing");
  assert.equal(v.isSpeaking(), true);

  v.stopSpeaking();
  assert.equal(state.audio[0].paused, true, "Stop must pause the audio element");
  assert.equal(v.isSpeaking(), false);

  state.finishAudio(); // let the pending promise settle
  await playing;
});

test("a dropped utterance does not stall the queue", async () => {
  const state = stubBrowser({ voices: [{ lang: "ar-MA" }], ttsFails: 99 });
  const v = await freshVoice();
  state.dropped = true;

  await v.speakResponse(emergencyResult(), { prefer: "browser" });

  assert.equal(state.spoken.length, v.buildParts(emergencyResult()).length,
    "every part was attempted despite the drop");
  assert.equal(v.isSpeaking(), false);
});

test("server TTS failure falls back to the browser instead of going silent", async () => {
  const state = stubBrowser({ voices: [{ lang: "ar-MA" }, { lang: "fr-FR" }], ttsFails: 1 });
  const v = await freshVoice();

  await v.speakResponse(emergencyResult());

  assert.equal(state.tts.length, 1, "the server was tried");
  assert.ok(state.spoken.length > 0, "and the patient still heard something");
});

test("REGRESSION: a real voice object is resolved, not just u.lang", async () => {
  const ar = { lang: "ar-MA", name: "Arabic" };
  const fr = { lang: "fr-FR", name: "French" };
  const state = stubBrowser({ voices: [ar, fr], ttsFails: 99 });
  const v = await freshVoice();

  await v.speakResponse(emergencyResult(), { prefer: "browser" });

  const arabic = state.spoken.filter((s) => s.lang === "ar-MA");
  const french = state.spoken.filter((s) => s.lang === "fr-FR");
  assert.ok(arabic.length > 0 && french.length > 0);
  assert.equal(arabic.every((s) => s.voice === ar), true, "Arabic got the Arabic voice object");
  assert.equal(french.every((s) => s.voice === fr), true, "French got the French voice object");
  assert.equal(arabic.every((s) => s.rate === 0.9), true, "slow rate for elderly patients");
});

test("REGRESSION: getVoices() returning [] first is not read as 'no voice'", async () => {
  // Chrome populates voices asynchronously. A naive first-call check reports
  // "no Darija voice" on a device that has one, and the feature silently dies.
  const state = stubBrowser({ lateVoices: true, voices: [{ lang: "ar-MA" }] });
  const v = await freshVoice();

  const t0 = Date.now();
  const probing = v.voiceSupport();
  await new Promise((r) => setTimeout(r, 20));
  assert.equal(typeof state.listener, "function", "voice.js registered a voiceschanged handler");

  state.revealVoices();
  const support = await probing;

  assert.equal(support.darija, true, "the voice behind voiceschanged was found");
  assert.equal(support.voices.length, 1);
  assert.ok(Date.now() - t0 < 1000, "resolved on the event, not on the 1200ms timeout");
});

test("a device with no voice at all reports why, instead of going quiet", async () => {
  const state = stubBrowser({ noVoicesEver: true });
  state.health = { tts: false };
  const v = await freshVoice();

  const support = await v.voiceSupport();
  assert.equal(support.server, false);
  assert.equal(support.darija, false);
  assert.ok(support.reason, "an unavailable voice is an error state, not a silent degrade");
});

test("the server clip carries per-part language instructions", async () => {
  const state = stubBrowser();
  const v = await freshVoice();

  await v.speakResponse(emergencyResult());

  assert.equal(state.tts.length, 1, "one request, not one per field");
  const ins = state.tts[0].instructions;
  assert.ok(ins, "without instructions the server reads French with the Darija voice");
  assert.ok(ins.includes("Darija written in Arabic script"), ins);
  assert.ok(ins.includes("French"), ins);
  assert.ok(/do not read the section numbers/i.test(ins), "the patient must not hear '1.' '2.'");
});

test("voiceSupport reports no server voice when /api/health says so", async () => {
  const state = stubBrowser();
  state.health = { tts: false };
  const v = await freshVoice();

  const support = await v.voiceSupport();
  assert.equal(support.server, false);
  assert.ok(support.reason);
});

/* ------------------------------------------------------------------ *
 * Concurrency
 * ------------------------------------------------------------------ */

test("a superseded response does not resume talking over the new one", async () => {
  const state = stubBrowser({ voices: [{ lang: "ar-MA" }], ttsFails: 99 });
  const v = await freshVoice();

  const first = v.speakResponse(emergencyResult(), { prefer: "browser" });
  v.stopSpeaking();
  const afterStop = state.spoken.length;

  await v.speakResponse(emergencyResult({ tts_priority: "french" }), { prefer: "browser" });
  await first;

  assert.equal(state.spoken.length,
    afterStop + v.buildParts(emergencyResult()).length,
    "only the second response may keep playing");
});

test("pagehide stops playback, so audio does not survive navigation", async () => {
  // voice.js registers this against `window` at import time. Node has no window,
  // so this asserts the source keeps the guard rather than exercising the DOM.
  const src = readFileSync(new URL("../prompts/voice.js", import.meta.url), "utf8");
  assert.ok(/addEventListener\("pagehide", stopSpeaking\)/.test(src), "pagehide guard must stay");
  assert.ok(/typeof window !== "undefined"/.test(src), "and must not throw where there is no window");
});

test("emergency and non-emergency responses both end on the disclaimer", async () => {
  for (const emergency of [true, false]) {
    const v = await freshVoice();
    const r = emergencyResult({
      emergency,
      urgency_level: emergency ? "high" : "medium",
      location_required: emergency,
      emergency_reason: emergency ? "douleurs thoraciques" : null,
    });
    const parts = v.buildParts(r);
    assert.equal(parts[parts.length - 1].text, DISCLAIMER_ARABIC);
  }
});
