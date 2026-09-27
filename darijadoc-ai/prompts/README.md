# DarijaDoc — AI Contract

**Status: FROZEN. Do not edit `system_prompt.txt` without telling Member 2 first.**
Any change to the prompt changes what Member 2's backend must expect.

## Files

| File | Purpose |
|---|---|
| `prompts/system_prompt.txt` | Paste into the OpenAI `system` role. Single source of truth. |
| `prompts/response_schema.json` | JSON Schema Member 2 validates every response against. |
| `prompts/voice.js` | Voice playback module for Member 3. Drop in, no build step. |
| `prompts/README.md` | This file. The contract. |
| `tests/test_inputs.json` | 112 accuracy cases with `expect_emergency` labels. |
| `tests/fixtures.json` | Ground truth for the 4 ordonnance fixtures. |
| `tests/voice.test.mjs` | Node tests for the voice contract. `node --test tests/voice.test.mjs`. |
| `test_prompt.py` | Test harness (text + vision). Also the reference validator. |
| `serve.py` | Local test UI + the places backend (pharmacies, hospitals). |
| `make_vision_fixture.py` | Generates the ordonnance fixtures used for vision tests. |
| `web/` | The local UI: `app.js`, `map.js`, `index.html`, `style.css`, `vendor/leaflet`. |

## Current score

<!-- SCORE_BLOCK -->

## Harness bugs fixed 2026-09-27

Found while re-verifying the score above. All three were in the validator, so
every earlier "verified" claim was made with the guards partly inert.

- `validate_prescription` appended to a `warnings` list it was never passed and
  that is not imported. `NameError`, which aborted the whole run instead of
  reporting a finding. It fired on exactly the two cases the guards were
  written for.
- The invented-advice guard spelled the French verb as `exceed`, so
  `ne pas depasser` never matched and only the English half could fire. Now
  `ADVICE_RE` at the top of `test_prompt.py`.
- `validate_prescription` bailed out on *any* pre-existing error, so an unrelated
  top-level failure silently skipped every prescription check.

`--rx-suite` also saved all four fixtures to one `outputs/rx.json`, so each run
overwrote the last and left no evidence to compare. Results now go to
`outputs/rx_<fixture>.json` with a per-fixture summary table.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# add OPENAI_API_KEY=sk-... to .env   (.env is gitignored)
```

## API call (Member 2)

```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ],
    response_format={"type": "json_object"},
    temperature=0.2,
)
result = json.loads(response.choices[0].message.content)
```

`user_content` is a list: one `{"type": "text", ...}` block, plus one
`{"type": "image_url", "image_url": {"url": ...}}` block when a document is
attached. See `test_prompt.ask_gpt`.

Retries on `APIConnectionError` / `RateLimitError` with exponential backoff are
already in `ask_gpt`. **Port that to the backend** — the harness hit real
connection errors during a full suite run and lost 10 cases without retries.

## Invariants Member 2 must enforce server-side

Do not trust the model on these. Assert them yourself after parsing:

1. `emergency == true` implies `urgency_level == "high"` **and** `location_required == true`.
2. `emergency == false` implies `location_required == false` **and** `emergency_reason is None`.
3. `next_steps` has 2–5 items.
4. `disclaimer` is exactly `hadchi mjarrad chra7, machorch dakter awla.`
5. No Arabic script in `explanation_darija`, `next_steps` or `disclaimer`.
6. Arabic script IS present in `explanation_darija_arabic`, `disclaimer_arabic`
   and every item of `next_steps_arabic`.
7. No diacritics/tatweel in any `*_arabic` field.
8. `len(next_steps) == len(next_steps_arabic)`.
9. `tts_priority` equals `"french"` iff `input_language == "french"`.
10. No phone number in the response other than 150, 190, 15, 177.
11. When `emergency == true`, `next_steps_arabic[0]` also carries the 150 call —
    that string is what the patient actually *hears*.

`test_prompt.validate()` implements all eleven. Reuse it rather than rewriting.
`test_prompt.py` also exports `run_suite()`, `ask_gpt()` and `apply_sanitizer()`.

**Member 2: call `apply_sanitizer(result)` on every response before serving it.**
The model leaks diacritics into the Arabic fields roughly one case in ten. They
are decorative, stripping them is lossless for TTS, and doing it in the backend
removes a whole class of flakiness that the prompt alone cannot close. The
harness does this by default; `--no-sanitize` shows the raw model output.

## Emergency numbers

| Number | Service |
|---|---|
| 150 | SAMU (ambulance) |
| 190 | Police |
| 15 | Pompiers (fire) |
| 177 | Gendarmerie |

On `emergency == true`, `next_steps[0]` is the 150 call and must stay at
index 0. The model reordered it once during tuning, which is why it is
asserted server-side as well.

## Model settings

- `gpt-4o` (vision + text)
- `temperature=0.2` (near-deterministic)
- `response_format={"type": "json_object"}`

## Known behaviours and limits

- **The disclaimer is Latin Darija, not Arabic script.** The original spec
  required Darija in Latin letters *and* an Arabic-script disclaimer, which
  contradicts itself and would have failed the no-Arabic-script check on every
  single response. Latin version is used. If the team wants the Arabic wording
  back, the Arabic-script check has to be dropped.
- **Reading a prescription is not prescribing.** In `explain` mode the model
  repeats doses that are printed on the document, so the patient understands
  their own prescription. It is instructed never to add, round, or infer a
  dose that is not printed there. Do not show restated doses as new advice in
  the UI — label them as "what your prescription says".
- **Unreadable photos**: the model refuses to guess and asks for a clearer
  photo, in both languages. Verified on a deliberately blurred image. Member 3
  should surface `explanation_*` as-is here; there is no document content to
  render.
- **`urgency_level` for a single asymptomatic BP of 180/100 is `medium`, not
  `high`.** Escalates only at ≥180/120, or 180/100 with a sudden/severe
  headache, blurred vision, chest pain, or breathlessness. A long-standing
  headache ("since yesterday") is `medium`. This boundary was unstable before
  the rule was pinned; it now holds 3/3. Cases t05, t16, t17 lock it in.
- **Suicidal input routes to 150.** 150 is SAMU, an ambulance line, not a
  mental-health crisis line. The prompt also asks for an extra step telling the
  patient to stay with someone and reach a human.
  **The model invented a hotline number here** — `0800 00 77 77`, on the
  suicide test case, from no source at all. It is now forbidden in the prompt
  and caught by validator check 10, and the model now emits "contact a crisis
  line near you" with no number. If you want a real crisis line in the product,
  **inject it from config after generation, not from the prompt.** Do not let
  the model write a number the app has not verified.

## Ordonnance upload contract (Member 2 and Member 3)

```
user attaches photo  ->  gpt-4o reads it  ->  explain mode + prescription object
                                        ->  requires_pharmacy_lookup decides the button
```

Mode is the routing key: **an attachment means `explain`; typing means `chat`.**
`prescription` is non-null in `explain` and null in `chat`, and
`requires_pharmacy_lookup` is true only in `explain`. A text question like
"wach kaydir l'paracétamol" is `chat`, not `explain`, so it has no prescription
object. These three are locked together and the validator enforces all of it.

Member 2 flow:

```python
result = ask_gpt(prompt, image_url=photo)     # data: or https: URL
result = apply_sanitizer(result)              # strips diacritics, incl. name_arabic
ok, errors, warnings = validate(result)       # reuse, don't reimplement
if not ok:
    return ask_for_a_better_photo(), errors
```

Member 3 flow, for `requires_pharmacy_lookup == true`:

- Render the pharmacy button. **Never call `geolocation` on load.** The browser
  permission prompt must come from the tap. A prompt on page load is both bad
  UX and auto-denied in Safari and Firefox.
- On tap, `navigator.geolocation.getCurrentPosition` with a short timeout.
- Granted: pass lat/lng to the pharmacy lookup.
- Denied or timed out: fall back to a manual city selector. This path must be
  built and tested from day one, not added later — on a desktop browser during
  a demo, permission denial is the *likely* path, not the edge case.

`location_required` and `requires_pharmacy_lookup` are independent flags:
`location_required` is true only in an emergency (show the hospital map);
`requires_pharmacy_lookup` means "offer the pharmacy button". Both can be true
at once, which is not a contradiction.

`form` enum: `comprimé, sirop, goutte, injection, crème, pommade, gel, sachet,
suppositoire, inhalateur, autre`. `sachet`, `pommade` and `gel` were added
because the model used them and the original enum had no place to put them.

## Pharmacy and hospital lookup (implemented)

Both flags now have a real implementation, in `serve.py` plus `web/map.js` and
`web/app.js`. Data comes from **OpenStreetMap through the Overpass API**: no API
key, no billing, real pharmacy and hospital coverage for Morocco. A demo that
needs a cloud account to show a map is a demo that cannot be shown.

```bash
curl -X POST localhost:8000/api/pharmacies -d '{"city":"Casablanca"}'
curl -X POST localhost:8000/api/hospitals  -d '{"lat":33.5731,"lng":-7.5898}'
curl localhost:8000/api/cities          # the manual-path city list
```

- **Never geolocate on load.** `locateUser()` in `web/map.js` is the only place
  `getCurrentPosition` is called, and only from a click handler. The doc comment
  there says why; do not "helpfully" call it earlier.
- **The manual path is the primary path.** `GET /api/cities` returns 25 Moroccan
  cities with coordinates, and a city name is resolved from that static table in
  `serve.py` — not from a geocoder call. So the denied-permission path needs no
  third party at all, which is what makes it testable and demo-proof. Distances
  from a city centre are labelled as approximate in the UI, because they are.
- **Map failures are never silent.** Overpass is free and it does go down. A
  blank map reads as "there is no pharmacy here", which on an emergency map is a
  dangerous lie, so a failed lookup returns `kind: "places_unavailable"` and the
  UI shows a search link to OpenStreetMap instead. Leaflet tiles fail
  independently of the lookup, and a `tileerror` says so.
- Leaflet is **vendored** in `web/vendor/leaflet/`, not loaded from a CDN, so the
  map still works on bad wifi. Markers are inline SVG rather than Leaflet's
  default PNGs, because the default resolves its image path by sniffing the
  stylesheet URL and breaks the moment the CSS is not served from the page root.

### The map data is wrong in specific, measured ways

Every one of these was observed in live Casablanca data, not predicted:

1. **`amenity=clinic` includes labs and dentists.** A clinic-inclusive hospital
   query returned "Laboratoire de Biologie Medicale Casa Analyses" at 686 m,
   ahead of the nearest real hospital at 2.2 km. The hospitals endpoint queries
   `amenity=hospital` only.
2. **A pharmacy is tagged `amenity=hospital`.** Moroccan OSM data does this, and
   it was served as the 4th nearest *hospital*. Filtered by name
   (`NOT_A_HOSPITAL_RE`) — shown nowhere rather than shown wrongly.
3. **A dental centre is tagged `amenity=hospital`.** It cannot be filtered by
   tag, because the tag itself is wrong. It is ranked *below* the general
   hospitals by `SPECIALIST_RE` and labelled in the list. Never hidden: dropping
   a real nearby place would be a different lie.
4. **Unnamed nodes defaulted to the name "Pharmacie"** and sorted to the top of
   the emergency list. An unnamed place is now labelled as unnamed and ranked
   last. Inventing a reassuring name for a blank node is the exact failure this
   project keeps hitting in the model.
5. **Overpass mirrors are unreliable.** Measured while building this: the main
   instance and `kumi.systems` both 504 or time out under repeated querying,
   `private.coffee` timed out every time, and `overpass.osm.jp` presents a
   certificate that is not valid for its hostname. `lz4.overpass-api.de` answered
   in 4.4 s where the main took 16.3 s. **The mirror list in `serve.py` is a
   guess until you re-test it.**

The general lesson is the same one as the Arabic font fixture: measure the data
before blaming it, and before shipping a rank order built on it.

## Ordonnance extraction: what actually works

Verified against 4 fixtures generated by `make_vision_fixture.py` (4 medicines,
one with a trailing non-numbered line; one Arabic-script page; one blurred; one
cropped). These are synthetic renders, not photographs — see the caveat at the
end.

Works well:

- Medication list, order, and drug names read correctly. `apres chaque repas`
  maps to `with_food: "after"`. Purposes are sensible (toux, diarrhée, douleur).
- `unreadable` / `extraction_confidence: "low"` with an empty array and a
  request for a better photo, on a genuinely illegible page — when the model
  does take that branch.
- Never inventing a duration, once told not to carry it from the line above.

**One of the fixtures was itself wrong.** `prescription_partial` was generated
with `blur=2.4`, which washed the surviving text out: in the date band
(y 143–178) *no pixel was darker than 128* — min 181, sd 12.6, against min 72 /
sd 30.7 on the sharp page. The ground truth asserted `12/03/2026` from a band
that carries no readable strokes, and the model duly returned `12/10/2023` and
was failed for it. The fixture's job is the *crop* (Aer must not appear), not
blur robustness, so the blur is back at the default 0.6 and the date now reads
correctly. `prescription_blurry` covers blur. Lesson, same as the Arabic-font
one below: measure the fixture before blaming the model.

**Three real problems. Do not ship the extraction UI without reading this.**

1. **`confidence` is not trustworthy. It is the most important finding here.**
   On the Arabic-script fixture the model returned `confidence: "high"` while
   reporting a duration of `3 yyam` for a page that says `5 أيام`, and reading
   `مرتين` (twice) as three times a day. Prompt instructions to be more
   conservative on Arabic pages reduced invented schedules in some runs and not
   others. Treat `confidence` as decorative: never use it to hide the photo or
   to skip a confirmation step. **Member 3 must always show the source photo
   beside the extraction.**

   Still reproducing after the fixture and validator fixes: the Arabic page
   says `5 أيام` for Doliprane and the model returned `3 yyam` on **3 of 3**
   runs, always at `confidence: "high"`. It is caught as a warning, not an
   error, so the fixture scores PASS — a clean 4/4 does **not** mean the
   extraction is right.
2. **A fully illegible photo produced three confident invented medications.**
   The blurred fixture has 5x less edge content and 3x less contrast than the
   sharp one, and the response was `unreadable: false, confidence: "high"` with
   Paracétamol, Amoxicilline and Ibuprofène — none of which appear on the page.
   Those are the three most common French drugs, i.e. filled in from priors. The
   prompt's anti-fabrication rules did not prevent this. If a production photo
   is too dark, too small or too compressed, expect a confident wrong answer
   rather than a refusal.

   This one did **not** reproduce in 3/3 recent runs — `unreadable: true` with
   zero medications every time. Still treat it as a live risk, not a fixed bug.
3. **Schedule granularity gets invented.** A line reading "1 x 2 / jour" with no
   times of day comes back as a morning/evening/bedtime schedule. The validator
   now warns when `timing` lists more time-of-day slots than `frequency` allows,
   but that only catches the internal contradiction, not a consistently
   over-detailed reading. Note this guard was dead until 2026-09-27 (see
   **Harness bugs fixed**); it has fired only once since.

Mitigation, in priority order: always show the photo; make the patient confirm
they can read the name and dose on their own paper copy before acting; and treat
a low-res or low-light upload as a product-level problem to solve with a
pre-upload quality check, not with prompt wording.

**All three are now implemented in the local UI**, because the first one alone
was not enough — problem 2 above is a confident wrong answer, and a photo pinned
beside it does not stop anyone acting on it.

1. The source photo is pinned beside the extraction and never collapsed
   (`web/app.js`, `renderExtraction`).
2. The extraction is headed **"What your prescription says"** with the caption
   "This is what the document says, not new advice from us. Check every line
   against your paper copy." Restated doses are no longer presented as
   something the app decided.
3. A **confirm-before-acting gate**: with a readable prescription, the next
   steps and the Play button stay dimmed and disabled until the patient ticks
   *"I can read the name and the dose on my own paper copy"*. **Never gated in
   an emergency** — a patient in trouble must not be stopped by a checkbox.
4. A **pre-upload quality check** runs on every picked file, in the browser,
   before the photo is sent. Thresholds were measured on this project's own
   fixtures downscaled to the 256px thumbnail the check samples:

   | | luma sd | long edge |
   |---|---|---|
   | readable fixtures | 6.9 – 10.7 | 1180 |
   | blurred fixture | 3.4 | 1180 |
   | blank page (control) | 0.0 | 1180 |

   `sd < 5.0` warns, `sd < 1.5` says the lens was probably covered,
   `mean < 70` says too dark, `long edge < 1000` says low resolution. The
   patient can always send it anyway.

   It deliberately does **not** claim the photo is blurry: a low-detail image
   could be out of focus, too far away, or just a mostly-blank page, and the
   browser cannot tell those apart. It says there is little detail to read and
   tells them to check the paper — which is right in all three cases. Same
   reasoning as the `confidence` warning: do not assert more than you measured.

**API note for Member 2:** `gpt-4o` reproducibly returns `content: null` with
`finish_reason: "stop"` for some images (seen on the cropped fixture, on all 4
retries). `ask_gpt` raises `EmptyCompletion`; the vision and prescription paths
report it as a failure instead of crashing. **The backend needs the same guard**,
and it should answer "retake the photo" rather than surfacing an error. Real
patient photos — screenshots, dark images, partial captures — will hit this.

`EmptyCompletion` is **not retried**, and that is a change. It used to sit in the
retry tuple, so a photo the model will never read burned 2+4+8s of backoff before
the caller could say "retake the photo" — fourteen seconds of spinner for the
patient to get the answer they were always going to get. It does not clear on a
second attempt, so retrying only makes them wait longer.

**Caveat on the Arabic finding:** the first run of the Arabic fixture reported
the page unreadable, and that turned out to be a bug in *my fixture*, not a
model limitation — the font in use has zero Arabic glyphs, so the text rendered
as empty boxes. After switching to an Arabic-capable font, the Arabic page read
correctly. Lesson: verify your fixture before blaming the model, and never
hardcode a font path in a generator.

## Voice Output Contract (Member 3)

Use `prompts/voice.js`. It is a complete, dependency-free module:
`voiceSupport()`, `speakResponse(result)`, `stopSpeaking()`, `isSpeaking()`,
`buildParts(result)`, `styleEmergencyStep(el)`, plus the server path
`speakViaServer(blob)`, `fetchClip(text, {instructions})`.

### Two backends, server first

**The primary path is not `speechSynthesis`.** No browser ships a Darija voice:
Chrome on Linux typically has zero `ar-*` voices, so the fallback cannot do the
job at all on the machine this was built on. The server renders the
Arabic-script fields with OpenAI TTS (`POST /api/tts`, `gpt-4o-mini-tts`,
voice `shimmer`) and the browser just plays an mp3. `speechSynthesis` is the
fallback for when the server has no key, no credit, or no network.

```js
import { speakResponse, stopSpeaking, isSpeaking, voiceSupport } from "./voice.js";

const support = await voiceSupport();
if (!support.server && !support.darija) {
  // No way to speak at all. A patient who can neither read nor hear Darija has
  // been left with nothing, so this is an error state, not a silent degrade.
  console.error("no speech available:", support.reason);
}

speakerBtn.addEventListener("click", () => {
  if (isSpeaking()) return stopSpeaking();
  speakResponse(result); // rate 0.9 by default, for elderly patients
});
```

`voiceSupport()` probes `GET /api/health` for a `tts` flag rather than assuming
`fetch` and `Audio` exist. Every browser has those two, including the ones where
`/api/tts` is down, and a Play button that lights up and then says nothing is
worse than one that reports itself unavailable.

### Per-part language on a single request

One mp3 per response, not one per field: the patient hears one continuous
utterance instead of five clips with gaps, it is one round trip, and a single
failure cannot leave a half-finished queue talking. A bare string carries no
language boundary though, so without help the French passage gets read with the
Darija voice at the Darija rate. `speakResponse` therefore sends `instructions`
to the TTS model naming which section is which language. `serve.py` passes them
through and falls back to an unparameterised call on an SDK that does not know
the field — losing the hint is bad, failing the request would be worse.

### Rules the module already implements, do not re-implement

- Playback order follows `tts_priority`; `ar-MA` for Darija, `fr-FR` for French.
- `next_steps_arabic` is spoken in order, and `disclaimer_arabic` is always last.
- The app adds **no** announcement of its own. `next_steps_arabic[0]` already
  carries the 150 call, so the app must **not** prepend a separate emergency
  banner. Highlighting that step in the UI (`styleEmergencyStep`) is visual
  only, never spoken.
- The disclaimer is always spoken. It is not skippable.
- `speechSynthesis.cancel()` on stop, and on `pagehide`, or a queue survives
  navigation and keeps talking over the next page.
- Start playback from a user gesture, or iOS blocks it.

**On "the 150 call is heard exactly once":** the app's own contribution is
exactly zero, and `tests/voice.test.mjs` asserts that by counting the 150s the
model returned against the 150s actually spoken. The model itself sometimes
names 150 in the Arabic explanation *as well as* in the first step — measured on
`outputs/t02` and `t05` — so a patient can hear it twice. That is the model's
wording, not an app bug, and the fix if it bothers you is prompt wording, not
`voice.js`. Do not "solve" it by silently dropping text from the response.

### Run the voice tests

```bash
node --test tests/voice.test.mjs
```

18 cases, no dependencies, no DOM: every browser global is stubbed and each case
gets a fresh copy of the module so playback state cannot leak between them. The
README used to assert "verified with node" with nothing in the repo to back it.

Six things the naive implementation gets wrong, all now covered by a test:

1. **`getVoices()` returns `[]` on first call in Chrome.** A naive
   `voices.find(v => v.lang === "ar-MA")` reports "no Darija voice" on a device
   that has one, and the feature silently dies. Wait for `voiceschanged`, with
   a timeout, before deciding.
2. **`onend` alone stalls the queue.** If an utterance is dropped — no voice for
   the tag, tab backgrounded, app switched — `onend` never fires and playback
   stops mid-response with no audio and no error. `voice.js` advances on
   `onerror` too.
3. **Setting only `u.lang` lets the browser pick any default voice.** On a device
   with no Arabic voice that is often a non-Arabic one, which reads Darija as
   nonsense. Resolve a real `SpeechSynthesisVoice` and assign it; still set
   `lang` as the fallback.
4. **Stop could not stop server TTS.** `speakViaServer` built its `Audio`
   element as a local `const`, so the module-level handle that `stopSpeaking()`
   checks was always `null` and the clip played to the end no matter what the
   patient pressed. This is the whole point of the primary path, and it was
   broken in it.
5. **A boolean cannot tell "the user pressed stop" from "a newer response reset
   the flag".** A superseded response could resume talking over the current one.
   The cancel flag is a monotonic counter now.
6. **The hardcoded emergency banner was still in the file as dead code**
   (`EMERGENCY_LINE_AR`, unused). It was one careless edit away from
   double-speaking 150, which is the exact bug the spec's sample JS had. Removed,
   and a test greps the source to keep it out.

On a device with no Arabic voice installed **and** no server TTS, this feature has
no fallback worth the name — the patient cannot read the text either.
`voiceSupport()` returns `reason` for that case; treat it as a real error state,
not a silent degrade. The server path exists precisely so this state should be
rare.

## Test corrections made during tuning

Three of the original 15 cases were wrong and were changed. All three are
annotated in `tests/test_inputs.json` with a `note` field.

- **t05** `tla3 liya damm f ras 18/10` — spec expected `emergency: true`. An
  asymptomatic 180/100 is stage-2 hypertension, not a hypertensive emergency.
  Flipped to `false` / medium.
- **t17** — first draft was a headache "since yesterday" with BP 180/100. That
  is same-day evaluation, not an ambulance. Rewritten as a sudden severe
  headache with vision change.
- **t20** — first draft used `mrga3 men l3malt`, which is ambiguous Darija
  (means "came back"); the model read it as vomiting. Rewritten unambiguously.

Seven cases were added (t16–t22): the hypertension boundary, Arabic-script
input, French input, child unresponsive, mixed low-risk, and stable chronic.

## Local test UI

```bash
.venv/bin/python serve.py          # opens http://127.0.0.1:8000
```

Two tabs: **Ask** (type like a patient, or click any of the 112 test cases) and
**Ordonnance photo** (drop a real phone photo, or click a generated fixture).
Each response shows the harness verdict — PASS/FAIL, the errors, the warnings —
so the validators are visible instead of only on the terminal.

Standard library only, so `requirements.txt` stays three lines. Every request goes
through `test_prompt.ask_gpt` and is scored by `test_prompt.validate`, and
clicking a labelled test case applies its `expect_emergency`, so **the UI cannot
disagree with the CLI**. It also serves the real `prompts/voice.js` and the real
vendored `leaflet.js` to the browser, so the Play button and the map exercise the
shipped files rather than copies.

Some deliberate choices:

- The source photo is pinned beside the extraction, never collapsed. See
  problem 1 above for why.
- Playback order is `tts_priority`, and the Latin Darija is shown but never
  spoken — no engine reads Darija in Latin letters.
- An empty completion from the API is reported as "retake the photo", not as an
  error, because that is what the patient needs to hear.
- The pharmacy and hospital lookups are **not** auto-run. They render a button,
  and the browser is asked for a location only when the patient taps it. An
  emergency response gets the hospital block as well, for the same reason.
- A pharmacy that is closed, missing from OSM, or unreachable because Overpass is
  down must never look like "there is none". The empty and failed states both say
  what actually happened and offer a search link.
- The API key stays in the server process and is never sent to the browser. The
  server binds to 127.0.0.1 only and refuses any other host, because it has no
  auth. Do not expose it.

## Quick commands

```bash
# Full suite (112 cases), with TTS playback preview
.venv/bin/python test_prompt.py

# Same, without the preview. Use -u so the log streams instead of buffering.
.venv/bin/python -u test_prompt.py --quiet

# Raw model output, no diacritic stripping
.venv/bin/python test_prompt.py --no-sanitize

# Skip the playback preview
.venv/bin/python test_prompt.py --quiet

# One case
.venv/bin/python test_prompt.py --only t07

# One-off query
.venv/bin/python test_prompt.py --ask "3bandi wja3 f 9lb"

# Ordonnance extraction, all four fixtures, checked against ground truth
# (saves outputs/rx_<fixture>.json per fixture and prints a summary table)
.venv/bin/python make_vision_fixture.py
.venv/bin/python test_prompt.py --rx-suite

# One fixture, still ground-truth checked by filename
.venv/bin/python test_prompt.py --rx outputs/prescription_blurry.png

# Generic vision check
.venv/bin/python test_prompt.py --vision outputs/prescription_fixture.png

# Voice contract. No API key needed, no network, ~3s.
node --test tests/voice.test.mjs

# Local UI
.venv/bin/python serve.py          # opens http://127.0.0.1:8000

# Places, without opening the UI
curl localhost:8000/api/cities
curl -X POST localhost:8000/api/pharmacies -d '{"city":"Casablanca"}'
curl -X POST localhost:8000/api/hospitals  -d '{"lat":33.5731,"lng":-7.5898}'

# Count / reset
ls outputs/*.json | wc -l
rm -f outputs/*.json
```

Re-running a case overwrites `outputs/<id>.json`. Read those files when judging
tone or phrasing; the pass/fail only covers structure and safety rules.

## Change protocol

1. Change **one** thing in `system_prompt.txt`. Do not rewrite.
2. Re-run the full suite.
3. Re-run the changed boundary cases 3x — one green run is not proof, the
   hypertension cases were green sometimes and then flipped.
4. Re-run with `--no-sanitize` to see the model's raw Arabic, not the cleaned copy.
5. Re-run the readable and blurred vision fixtures.
6. Run `node --test tests/voice.test.mjs` if you touched playback order, the
   emergency announcement, or the voice module at all. It is free and instant.
7. If you touched the places code, re-read **The map data is wrong in specific,
   measured ways** above before trusting a rank order, and re-test the Overpass
   mirrors rather than assuming the list still works.
8. Bump the score in this file and tell Member 2 and Member 3.

## Deviations from the original TTS spec, and why

The TTS spec said to *replace* `system_prompt.txt` with a shorter version. That
version was a regression against work already verified here, so the new fields
were added to the tuned prompt instead. Concretely, the replacement would have:

- restored an Arabic-script `disclaimer` while the field is for Latin text, and
  made `disclaimer` and `disclaimer_arabic` the same string, leaving no Latin
  disclaimer for the display side;
- dropped the blood-pressure rule (t05/t16/t17 go back to unstable), the
  "unresponsive person" rule (t20), the `next_steps` 2–5 bound, the "150 must be
  index 0" rule that fixed a real safety bug, the "never infer an unprinted dose"
  rule, the "don't guess at unreadable images" rule, and the suicide
  stay-with-someone step;
- dropped `minItems`/`maxItems` from `next_steps` in the schema;
- made `next_steps[0]` Arabic-only, breaking the Latin display contract.

Two behavioural changes were made deliberately, against the spec:

- **`tts_priority` follows the input language in emergencies too.** The spec
  said emergency always means Darija, justified as "reach the patient in their
  language" — which argues the opposite. A French-only patient who is choking
  gains nothing from hearing Darija. Validator check 9 enforces this.
- **`timing`, `frequency` and `duration` are Latin only.** The spec's timing
  table translated "matin" to "ف الصباح" in Arabic script while its `frequency`
  example was Latin ("3 مرات ف النهار"), and `timing` had no script rule at
  all. All three are now Latin Darija, consistent with the rest of the Latin
  fields. There is no `timing_arabic`; the voice reads
  `explanation_darija_arabic` and `next_steps_arabic`, not each medication row.
  If Member 3 wants to speak an individual medication, that field has to be
  added, not transliterated client-side.
- **No worked example of a prescription is in the prompt.** The spec's sample
  output was a full invented ordonnance, including a `warnings` entry
  ("do not exceed 3 g/day") that appears on no prescription and a hardcoded
  date. Feeding GPT a filled-in example of a fabricated prescription is close to
  the worst possible way to teach it not to fabricate one. The prompt describes
  the fields and the honesty rules instead.
- **No separate emergency announcement is spoken.** The spec's JS prepends a
  hardcoded Arabic emergency line *and* speaks `next_steps_arabic`, whose first
  item is already the 150 call, so the patient hears "call 150" twice. Verified
  with `node`: 150 is spoken exactly once, in both priority modes.
