// DarijaDoc local test bench.
//
// Imports the real prompts/voice.js so the browser runs the same file the CLI
// project ships, rather than a re-implementation that can drift from it.

import { speakResponse, stopSpeaking, isSpeaking, voiceSupport, styleEmergencyStep }
  from "/voice.js";
import { getMap, drawPlaces, locateUser, directionsUrl, browseUrl } from "/map.js";

const $ = (s) => document.querySelector(s);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
};

let samples = [];
let cities = [];
let current = null;      // last result object, for playback
let pendingImage = null; // { dataUrl, displayUrl, filename }
let lastPhotoCheck = null; // image stats, so the confirm gate can use them

/* ------------------------------------------------------------------ theme */

const THEME_KEY = "darijadoc.theme";
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  localStorage.setItem(THEME_KEY, t);
}
setTheme(
  localStorage.getItem(THEME_KEY) ||
  (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
);
$("#themeBtn").addEventListener("click", () =>
  setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark")
);

/* ------------------------------------------------------------------ toast */

let toastTimer;
function toast(msg, bad = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.toggle("bad", bad);
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), bad ? 6500 : 3000);
}

/* -------------------------------------------------------------------- net */

async function post(path, payload) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

async function boot() {
  try {
    const h = await (await fetch("/api/health")).json();
    if (!h.api_key) {
      $("#modelBadge").textContent = "no API key";
      $("#modelBadge").classList.add("bad");
      return;
    }
    $("#modelBadge").textContent = h.model;

    samples = await (await fetch("/api/samples")).json();
    $("#sampleCount").textContent = `${samples.length}`;
    const chips = $("#sampleChips");
    samples.forEach((s) => {
      const b = el("button", "chip");
      b.append(el("em", null, s.id));
      b.append(document.createTextNode(s.input));
      b.title = `${s.id} · ${s.category} · expect_emergency=${s.expect_emergency}`;
      // The labelled cases are the ones worth eyeballing first.
      if (s.expect_emergency === true) b.classList.add("is-red");
      b.addEventListener("click", () => {
        $("#q").value = s.input;
        ask(s.id);
      });
      chips.append(b);
    });

    await loadCities();

    const fx = await (await fetch("/api/fixtures")).json();
    $("#fixtureCount").textContent = `${fx.length}`;
    const fchips = $("#fixtureChips");
    fx.forEach((f) => {
      const b = el("button", "chip");
      b.append(el("em", null, f.name.replace("prescription_", "")));
      b.append(document.createTextNode(f.unreadable ? "unreadable" : "readable"));
      b.title = f.note;
      b.addEventListener("click", () => pickFixture(f));
      fchips.append(b);
    });

    // Server TTS (OpenAI) is the primary path, so a device with no Arabic
    // system voice is still fine. Only disable if we have neither.
    const v = await voiceSupport();
    if (!v.server && !v.darija) {
      // An error state, not a silent degrade: a patient who can neither read nor
      // hear Darija has been left with nothing.
      $("#voiceNote").textContent = `no speech available — ${v.reason}`;
      $("#voiceNote").dataset.unavailable = "1";
      $("#speakBtn").disabled = true;
    } else {
      $("#voiceNote").textContent = v.server
        ? (v.darija ? "server + system voice" : "server voice (OpenAI)")
        : "system voice only";
    }
  } catch (e) {
    console.error("boot failed", e);
    toast(`startup failed: ${e.message}`, true);
  }
}

/* ------------------------------------------------------------------- tabs */

document.querySelectorAll(".tab").forEach((t) =>
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => {
      x.classList.toggle("is-on", x === t);
      x.setAttribute("aria-selected", String(x === t));
    });
    document.querySelectorAll(".tabpane").forEach((p) =>
      p.classList.toggle("is-on", p.dataset.pane === t.dataset.tab)
    );
  })
);

/* -------------------------------------------------------------- ask flow */

$("#askBtn").addEventListener("click", () => ask());
$("#q").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
});

async function ask(id) {
  const text = $("#q").value.trim();
  if (!text) return toast("type something first", true);

  const btn = $("#askBtn");
  btn.classList.add("busy");
  btn.disabled = true;
  stopSpeaking();
  showWorking("asking…");

  const t0 = performance.now();
  try {
    const data = await post("/api/ask", { text, id, sanitize: $("#sanitize").checked });
    if (!data.ok) return showError(data);
    render(data, Math.round(performance.now() - t0));
  } catch (e) {
    showError({ error: e.message });
  } finally {
    btn.classList.remove("busy");
    btn.disabled = false;
  }
}

/* ----------------------------------------------------------- photo flow */

const drop = $("#drop");
const fileInput = $("#file");

drop.addEventListener("click", () => fileInput.click());
drop.addEventListener("dragover", (e) => {
  e.preventDefault();
  drop.classList.add("over");
});
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  const f = e.dataTransfer.files[0];
  if (f) takeFile(f);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) takeFile(fileInput.files[0]);
});

function takeFile(file) {
  if (!file.type.startsWith("image/")) return toast("that is not an image", true);
  const reader = new FileReader();
  reader.onload = () => setImage(reader.result, file.name);
  reader.onerror = () => toast("could not read that file", true);
  reader.readAsDataURL(file);
}

// A fixture is served by this app, but gpt-4o cannot reach 127.0.0.1, so the
// bytes have to be inlined before they go to the API.
async function pickFixture(f) {
  $("#fileName").textContent = f.name;
  try {
    const blob = await (await fetch(f.url)).blob();
    const reader = new FileReader();
    reader.onload = () => setImage(reader.result, f.name, f.url);
    reader.onerror = () => toast("could not load that fixture", true);
    reader.readAsDataURL(blob);
  } catch (e) {
    toast(`could not load ${f.name}: ${e.message}`, true);
  }
}

function setImage(dataUrl, filename, displayUrl) {
  pendingImage = { dataUrl, displayUrl: displayUrl || dataUrl, filename };
  $("#fileName").textContent = filename;
  $("#rxBtn").disabled = false;
  inspectPhoto(dataUrl);
}

/* --------------------------------------------------------- photo quality */

// Thresholds measured on the project's own fixtures, downscaled to the 256px
// thumbnail this measures, not guessed:
//
//                       luma sd    long edge
//   readable fixtures   6.9-10.7   1180
//   blurred fixture     3.4        1180
//   blank page (control) 0.0       1180
//
// 5.0 sits between the blurred page and the worst readable one, with margin on
// both sides. A low-res check is separate because a blurry 400px phone photo and
// a sharp 4000px one are different problems with different advice.
//
// This cannot tell "out of focus" from "mostly blank page": both are low in
// detail. So it does not claim the photo is blurry. It says there is little
// detail to read and tells the patient to check their paper copy, which is the
// advice that is right in both cases.
const QUALITY = { minSd: 5.0, flatSd: 1.5, minLongEdge: 1000, darkMean: 70 };

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("could not decode that image"));
    img.src = src;
  });
}

async function inspectPhoto(dataUrl) {
  const box = $("#quality");
  box.hidden = true;
  lastPhotoCheck = null;
  let img;
  try {
    img = await loadImage(dataUrl);
  } catch (e) {
    return; // let the server be the judge; the browser just could not decode it
  }

  const w = 256;
  const c = document.createElement("canvas");
  c.width = w;
  c.height = Math.max(1, Math.round((w * img.height) / img.width));
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, c.width, c.height);

  let sum = 0, sumSq = 0, n = 0;
  const px = ctx.getImageData(0, 0, c.width, c.height).data;
  for (let i = 0; i < px.length; i += 4) {
    const y = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2];
    sum += y;
    sumSq += y * y;
    n += 1;
  }
  const mean = sum / n;
  const sd = Math.sqrt(Math.max(0, sumSq / n - mean * mean));
  const longEdge = Math.max(img.width, img.height);

  lastPhotoCheck = { mean, sd, longEdge, width: img.width, height: img.height };

  const issues = [];
  if (sd < QUALITY.flatSd) {
    issues.push("this looks blank, or the lens was covered — there is nothing to read");
  } else if (sd < QUALITY.minSd) {
    issues.push("there is very little detail to read (out of focus, too far away, or too much glare)");
  }
  if (mean < QUALITY.darkMean) {
    issues.push("the photo is very dark, so small print will not be legible");
  }
  if (longEdge < QUALITY.minLongEdge) {
    issues.push(`only ${img.width}×${img.height}px — a phone photo of the whole page is usually 2000px+`);
  }
  if (!issues.length) return;

  box.innerHTML = "";
  const head = el("p", "quality-head", "This photo may be hard to read:");
  box.append(head);
  const ul = el("ul", "quality-list");
  issues.forEach((i) => ul.append(el("li", null, i)));
  box.append(ul);
  box.append(el("p", "quality-foot",
    "You can still send it. If the extraction below does not match your paper " +
    "prescription, do not act on it — send a clearer photo."));

  const row = el("div", "quality-actions");
  const retry = el("button", "btn", "Choose another photo");
  retry.addEventListener("click", () => fileInput.click());
  const send = el("button", "btn ghost", "Send it anyway");
  send.addEventListener("click", () => {
    box.hidden = true;
    lastPhotoCheck = { ...lastPhotoCheck, waived: true };
  });
  row.append(send, retry);
  box.append(row);
  box.hidden = false;
}

$("#rxBtn").addEventListener("click", async () => {
  if (!pendingImage) return;
  const btn = $("#rxBtn");
  btn.classList.add("busy");
  btn.disabled = true;
  stopSpeaking();
  showWorking("reading the photo…");

  const t0 = performance.now();
  try {
    const data = await post("/api/rx", {
      image: pendingImage.dataUrl,
      filename: pendingImage.filename,
    });
    if (!data.ok) return showError(data);
    data.photo = pendingImage.displayUrl;
    render(data, Math.round(performance.now() - t0));
  } catch (e) {
    showError({ error: e.message });
  } finally {
    btn.classList.remove("busy");
    btn.disabled = false;
  }
});

/* ------------------------------------------- places: pharmacy / hospital */

// The manual city path is not a fallback for later. On a desktop browser during
// a demo, permission denial is the *likely* outcome, so it is built and wired
// from the first commit and both paths are exercised in the same code.
async function loadCities() {
  try {
    cities = await (await fetch("/api/cities")).json();
  } catch (e) {
    cities = [];
    console.warn("city list unavailable", e);
  }
}

const km = (m) => (m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${m} m`);

function link(href, text) {
  const a = document.createElement("a");
  a.href = href;
  a.textContent = text;
  a.target = "_blank";
  a.rel = "noopener";
  return a;
}

function makePlacesBlock(kind) {
  const isHospital = kind === "hospital";
  const wrap = el("div", `places places--${kind}`);

  const head = el("div", "places-head");
  head.append(el("b", null, isHospital ? "Nearest hospital" : "Find a pharmacy"));
  head.append(el("span", "dim tiny", "OpenStreetMap · no account needed"));
  wrap.append(head);

  if (isHospital) {
    wrap.append(el("p", "dim tiny",
      "150 is the ambulance. Use this only if you can travel there yourself."));
  }

  const actions = el("div", "places-actions");
  const locate = el("button", "btn primary",
    isHospital ? "Show me where I am" : "Use my location");
  const selWrap = el("label", "citysel");
  selWrap.append(el("span", "dim tiny", "or pick your city"));
  const sel = el("select");
  sel.append(new Option("Choose a city…", ""));
  cities.forEach((c) => sel.append(new Option(c.name, c.name)));
  selWrap.append(sel);
  actions.append(locate, selWrap);
  wrap.append(actions);

  const status = el("p", "places-status", "Nothing looked up yet.");
  wrap.append(status);

  const map = el("div", "map");
  map.id = `map-${kind}`;
  map.hidden = true;
  wrap.append(map);

  const list = el("ol", "place-list");
  wrap.append(list);

  async function run(origin) {
    const endpoint = isHospital ? "/api/hospitals" : "/api/pharmacies";
    status.textContent = origin.via === "gps" ? "looking nearby…" : `looking in ${origin.name}…`;
    status.classList.remove("bad");
    list.innerHTML = "";
    map.hidden = true;

    const offerBrowse = () => {
      list.innerHTML = "";
      const li = el("li");
      li.append(link(browseUrl(kind), isHospital
        ? "Search OpenStreetMap for a hospital"
        : "Search OpenStreetMap for a pharmacy"));
      list.append(li);
    };

    let data;
    try {
      data = await post(endpoint, origin.via === "city"
        ? { city: origin.name }
        : { lat: origin.lat, lng: origin.lng });
    } catch (e) {
      status.textContent = `Lookup failed: ${e.message}`;
      status.classList.add("bad");
      offerBrowse();
      return;
    }
    if (!data.ok) {
      status.textContent = data.error || "Lookup failed.";
      status.classList.add("bad");
      if (data.detail) console.warn("places lookup", data.detail);
      offerBrowse();
      return;
    }

    const here = { lat: data.origin.lat, lng: data.origin.lng };
    const approx = data.origin.via === "city";
    status.textContent = approx
      ? `Nearest to the centre of ${sel.value}. Use "my location" for exact distances.`
      : `Nearest to you · ${data.places.length} found within ${isHospital ? "10" : "3"} km.`;

    if (!data.places.length) {
      status.textContent = data.empty_reason || "Nothing mapped nearby.";
      map.hidden = false;
      drawPlaces(getMap(map, [here.lat, here.lng], 12), { places: [], user: here, via: "city", kind });
      return;
    }

    map.hidden = false;
    drawPlaces(getMap(map, [here.lat, here.lng], isHospital ? 12 : 14),
      { places: data.places, user: here, via: data.origin.via, kind });

    data.places.forEach((p) => {
      const li = el("li");
      const name = el("b", null, p.name);
      li.append(name, el("span", "dim tiny", ` · ${km(p.distance_m)}`));
      // OSM mislabels some specialists as amenity=hospital. Say so, rather than
      // let a dental practice look like somewhere to be treated.
      if (p.specialist) {
        li.append(el("div", "place-warn", "Specialist practice — not an emergency service."));
      }
      if (p.always_open) li.append(el("span", "tag tag--ok", "24/7"));
      if (p.hours) li.append(el("div", "dim tiny", p.hours));
      if (p.phone) {
        const tel = link(`tel:${p.phone}`, p.phone);
        tel.className = "place-phone";
        li.append(tel);
      }
      li.append(link(directionsUrl(p.lat, p.lng), "Open in OpenStreetMap"));
      list.append(li);
    });
  }

  // The ONLY place getCurrentPosition is ever called from. A prompt on page load
  // is bad UX and is auto-denied in Safari and Firefox.
  locate.addEventListener("click", async () => {
    locate.disabled = true;
    status.textContent = "asking your browser for your location…";
    try {
      const here = await locateUser();
      await run(here);
    } catch (e) {
      // The message is already written for the patient.
      status.textContent = e.message;
      status.classList.add("bad");
      sel.focus();
    } finally {
      locate.disabled = false;
    }
  });

  sel.addEventListener("change", () => {
    if (!sel.value) return;
    const c = cities.find((x) => x.name === sel.value);
    if (c) run({ lat: c.lat, lng: c.lng, via: "city", name: c.name });
  });

  return wrap;
}

/**
 * Two independent flags, and the doc is explicit that both can be true at once:
 * `location_required` means "you need a hospital", `requires_pharmacy_lookup`
 * means "offer the pharmacy button". So they get their own blocks rather than one
 * merged widget.
 */
function renderPlaces(r) {
  const box = $("#places");
  box.innerHTML = "";
  const kinds = [];
  if (r.location_required) kinds.push("hospital");
  if (r.requires_pharmacy_lookup) kinds.push("pharmacy");
  box.hidden = kinds.length === 0;
  kinds.forEach((k) => box.append(makePlacesBlock(k)));
}

/* --------------------------------------------------------------- render */

function showWorking(msg) {
  $("#empty").hidden = true;
  $("#out").hidden = false;
  $("#prose").innerHTML = "";
  $("#steps").innerHTML = "";
  $("#extract").innerHTML = "";
  $("#split").hidden = true;
  $("#emergency").hidden = true;
  $("#sanitized").hidden = true;
  $("#notes").hidden = true;
  $("#quality").hidden = true;
  $("#places").hidden = true;
  $("#places").innerHTML = "";
  $("#confirm").hidden = true;
  unlockActing();
  $("#verdictDot").className = "dot";
  $("#verdictText").textContent = msg;
  $("#verdictMs").textContent = "";
  $("#raw").textContent = "";
}

// This is the one function that must never fail, because it is what reports a
// failure. A throw here hides the real error behind a bare "failed", which is
// exactly what happened once already. Keep it to textContent and toast only.
function showError(d) {
  showWorking("failed");
  const msg = d.error || "something went wrong";
  try {
    const notes = $("#notes");
    notes.innerHTML = "";
    const head = document.createElement("li");
    head.className = "err";
    head.textContent = msg;
    notes.append(head);
    if (d.advice) {
      const a = document.createElement("li");
      a.textContent = d.advice;
      notes.append(a);
    }
    if (d.detail) {
      const t = document.createElement("li");
      t.textContent = `detail: ${d.detail}`;
      notes.append(t);
    }
    notes.hidden = false;
    $("#verdictDot").className = "dot no";
  } catch (_) {
    // Last resort: the toast is built once at startup and cannot depend on this.
    toast(msg, true);
  }
}

// Surface anything that escapes, instead of leaving a half-rendered page.
window.addEventListener("error", (e) => {
  console.error("uncaught", e.error || e.message);
  toast(`JS error: ${e.message}`, true);
});
window.addEventListener("unhandledrejection", (e) => {
  console.error("unhandled rejection", e.reason);
  toast(`JS error: ${e.reason && e.reason.message ? e.reason.message : e.reason}`, true);
});

function render(data, ms) {
  const r = data.result;
  current = r;

  $("#empty").hidden = true;
  $("#out").hidden = false;
  $("#verdictDot").className = `dot ${data.check.pass ? "ok" : "no"}`;
  $("#verdictText").textContent = data.check.pass
    ? `PASS${data.labelled ? ` · ${data.labelled}` : ""}`
    : `FAIL${data.labelled ? ` · ${data.labelled}` : ""}`;
  $("#verdictMs").textContent = `${ms} ms`;

  const notes = $("#notes");
  notes.innerHTML = "";
  data.check.errors.forEach((e) => notes.append(el("li", "err", e)));
  data.check.warnings.forEach((w) => notes.append(el("li", null, `warn: ${w}`)));
  notes.hidden = notes.children.length === 0;

  const s = $("#sanitized");
  if (data.sanitized && data.sanitized.length) {
    s.textContent = `diacritics stripped from: ${data.sanitized.join(", ")}`;
    s.hidden = false;
  } else {
    s.hidden = true;
  }

  // emergency
  const em = $("#emergency");
  if (r.emergency) {
    $("#emergencyReason").textContent = r.emergency_reason || "";
    em.hidden = false;
  } else {
    em.hidden = true;
  }

  // pills
  const pills = $("#pills");
  pills.innerHTML = "";
  const add = (label, value, cls) => {
    const p = el("span", `pill ${cls || ""}`);
    p.append(document.createTextNode(label + " "));
    p.append(el("b", null, String(value)));
    pills.append(p);
  };
  add("mode", r.mode);
  add("urgency", r.urgency_level, r.urgency_level);
  add("lang", r.input_language);
  add("speak", r.tts_priority);
  if (r.requires_pharmacy_lookup) add("pharmacy lookup", "yes");
  if (r.prescription) {
    add("confidence", r.prescription.extraction_confidence,
        "conf-" + r.prescription.extraction_confidence);
  }

  // photo + extraction
  const rx = r.prescription;
  if (data.photo) {
    $("#split").hidden = false;
    $("#photoImg").src = data.photo;
    renderExtraction(rx);
  } else {
    $("#split").hidden = true;
  }

  renderConfirm(r, rx);
  renderPlaces(r);
  renderProse(r);
  renderSteps(r);

  $("#disclaimer").textContent = r.disclaimer || "";
  $("#raw").textContent = JSON.stringify(r, null, 2);
}

/* ------------------------------------------------- confirm before acting */

// The extraction is a best guess from a photograph, and the harness has caught
// it confidently inventing three drugs off a blurred page. The mitigation the
// doc ranks above prompt wording is the patient checking their own paper copy,
// so the next steps and the audio stay locked until they say they have.
//
// Never gated in an emergency. A patient in trouble must never be stopped by a
// checkbox.
function renderConfirm(r, rx) {
  const box = $("#confirm");
  const meds = (rx && rx.medications) || [];
  const needsGate = Boolean(rx) && !rx.unreadable && meds.length > 0 && !r.emergency;

  if (!needsGate) {
    box.hidden = true;
    box.innerHTML = "";
    unlockActing();
    return;
  }

  box.innerHTML = "";
  const label = el("label", "confirm-check");
  const cb = el("input");
  cb.type = "checkbox";
  const set = () => (cb.checked ? unlockActing() : lockActing());
  cb.addEventListener("change", set);
  label.append(cb, el("span", null,
    "I can read the name and the dose on my own paper copy"));
  box.append(label);
  box.append(el("p", "dim tiny",
    "This was read from a photo, so it can be wrong. Check it against the paper " +
    "before you take anything."));
  box.hidden = false;
  set();
}

function lockActing() {
  $("#steps").classList.add("is-gated");
  $("#speakBtn").disabled = true;
  $("#speakBtn").title = "Confirm the prescription against your paper copy first";
}

function unlockActing() {
  $("#steps").classList.remove("is-gated");
  const v = $("#voiceNote").dataset.unavailable === "1";
  $("#speakBtn").disabled = v;
  $("#speakBtn").title = "";
}

function renderExtraction(rx) {
  const box = $("#extract");
  box.innerHTML = "";
  if (!rx) {
    box.append(el("p", "dim", "no prescription object"));
    return;
  }

  box.append(el("h3", null, "What your prescription says"));
  box.append(el("p", "dim tiny rx-caption",
    "Read off your photo. This is what the document says, not new advice from us. " +
    "Check every line against your paper copy."));

  const head = el("div", "rx-head");
  const add = (k, v) => {
    if (v == null || v === "") return;
    const s = el("span");
    s.append(document.createTextNode(k + " "));
    s.append(el("b", null, String(v)));
    head.append(s);
  };
  add("doctor", rx.doctor_name);
  add("date", rx.date);
  add("confidence", rx.extraction_confidence);
  box.append(head);

  if (rx.unreadable) {
    box.append(el("div", "unreadable",
      "Page judged unreadable — no medication was guessed, which is the correct answer here."));
  }

  const meds = rx.medications || [];
  if (!meds.length) return;

  const list = el("div", "meds");
  meds.forEach((m) => {
    const c = el("div", "med");

    const top = el("div", "med-top");
    top.append(el("span", "med-name", m.name));
    if (m.name_arabic) top.append(el("span", "med-ar", m.name_arabic));
    if (m.dosage) top.append(el("span", "med-dose", m.dosage));
    c.append(top);

    const purpose = m.purpose_darija_arabic || m.purpose_darija || m.purpose_french;
    if (purpose) c.append(el("div", "med-purpose", purpose));

    const meta = el("div", "med-meta");
    const tag = (txt, cls) => meta.append(el("span", `tag ${cls || ""}`, txt));
    if (m.frequency) tag(m.frequency);
    if (m.duration && m.duration !== "unknown") tag(m.duration);
    if (m.with_food && m.with_food !== "unknown") tag(m.with_food);
    if (m.confidence) tag(`confidence ${m.confidence}`, `conf-${m.confidence}`);
    (m.warnings || []).forEach((w) => tag(w, "warn"));
    c.append(meta);

    if ((m.timing || []).length) {
      c.append(el("div", "dim tiny", `timing: ${m.timing.join(" · ")}`));
    }
    list.append(c);
  });
  box.append(list);
}

function renderProse(r) {
  const box = $("#prose");
  box.innerHTML = "";

  // Darija in Arabic script is shown and spoken first. French stays underneath.
  const spoken = [
    ["explanation_darija_arabic", "Darija (Arabic script)"],
    ["explanation_french", "Français"],
  ];

  spoken.forEach(([key, label], i) => {
    if (!r[key]) return;
    const n = el("div", `say ${key.endsWith("_arabic") ? "ar" : ""}`);
    if (i === 0) n.classList.add("first");
    n.append(el("div", "who", label + (i === 0 ? " · spoken first" : "")));
    n.append(el("div", "txt", r[key]));
    box.append(n);
  });

  if (r.explanation_darija) {
    const n = el("div", "say");
    n.append(el("div", "who", "Darija (Latin) · not spoken, shown for you"));
    n.append(el("div", "txt", r.explanation_darija));
    box.append(n);
  }
}

function renderSteps(r) {
  const box = $("#steps");
  box.innerHTML = "";
  const steps = r.next_steps_arabic || [];
  const lat = r.next_steps || [];
  if (!steps.length && !lat.length) return;

  box.append(el("h3", null, "What to do next"));
  const ol = el("ol", "step-list");
  const n = Math.max(steps.length, lat.length);
  for (let i = 0; i < n; i++) {
    const li = el("li");
    const wrap = el("div");
    if (steps[i]) wrap.append(el("div", "txt ar", steps[i]));
    if (lat[i]) wrap.append(el("div", null, lat[i]));
    li.append(wrap);
    // Step 1 is the urgent one in an emergency; voice.js owns that styling.
    if (r.emergency && i === 0) styleEmergencyStep(li);
    ol.append(li);
  }
  box.append(ol);
}

/* ------------------------------------------------------------------ voice */

// speakResponse hands back a stop function, not a promise, so poll isSpeaking()
// to keep the button label honest.
let voicePoll;
$("#speakBtn").addEventListener("click", () => {
  if (!current) return;
  if (isSpeaking()) {
    stopSpeaking();
    return;
  }
  speakResponse(current);
  $("#speakBtn").textContent = "⏹ Stop";
  clearInterval(voicePoll);
  voicePoll = setInterval(() => {
    if (!isSpeaking()) {
      clearInterval(voicePoll);
      $("#speakBtn").textContent = "🔊 Play";
    }
  }, 250);
});

// Never leave audio playing over a new result or a closed tab.
window.addEventListener("pagehide", stopSpeaking);

$("#q").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.metaKey && !e.ctrlKey) {
    e.preventDefault();
    ask();
  }
});

boot();
