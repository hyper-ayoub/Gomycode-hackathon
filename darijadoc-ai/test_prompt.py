import os
import sys
import re
import json
import time
import base64
import argparse
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, APITimeoutError, RateLimitError

load_dotenv()

ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = ROOT / "prompts"
TESTS_DIR = ROOT / "tests"
OUTPUTS_DIR = ROOT / "outputs"

MODEL = "gpt-4o"
TEMPERATURE = 0.2
DISCLAIMER = "hadchi mjarrad chra7, machorch dakter awla."
DISCLAIMER_AR = "هادشي مجرد شرح، مشورش دكتور أولا."
EMERGENCY_STEP_0 = "3ayt 3la 150 daba — Appelez le 150 immédiatement"

# Fields that must be pure Latin, fields that must be pure Arabic script.
LATIN_FIELDS = ("explanation_darija", "disclaimer")
ARABIC_FIELDS = ("explanation_darija_arabic", "disclaimer_arabic")

# Arabic script ranges. Latin fields must have zero hits; Arabic fields must hit.
ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
# Tashkeel + tatweel. The prompt forbids diacritics for TTS pacing.
TASHKEEL_RE = re.compile(r"[\u064B-\u0652\u0670\u0640]")

REQUIRED_KEYS = [
    "input_language", "mode",
    "explanation_darija", "explanation_darija_arabic", "explanation_french",
    "next_steps", "next_steps_arabic",
    "urgency_level", "emergency", "emergency_reason",
    "location_required", "requires_pharmacy_lookup",
    "disclaimer", "disclaimer_arabic", "tts_priority",
]

FORMS = {"comprimé", "sirop", "goutte", "injection", "crème", "pommade",
         "gel", "sachet", "suppositoire", "inhalateur", "autre"}
WITH_FOOD = {"before", "after", "with", "empty_stomach", "unknown"}

# Disease names the model must never assert the patient has. Matched as
# "<assertion verb> ... <disease>" so a plain mention ("ce qui compte c'est le
# cholestérol") does not trip it, but "vous avez une migraine" does.
DISEASES = [
    "migraine", "hypertension", "diabète", "diabetes", "pneumonie", "pneumonia",
    "gastrite", "gastritis", "angine", "grippe", "rhume", "covid", "asthme",
    "hépatite", "hepatite", "ulcère", "ulcere", "thyroïde", "thyroide",
    "anémie", "anemie", "cancer", "tumeur", "tumeur", "AVC", "rupture",
]
DISEASE_RE = [
    re.compile(rf"\b(vous|on|tu)\s+(avez|as|est|etes)\s+(un[e]?|une\s+\w+\s+de)?\s*{d}\b", re.I)
    for d in DISEASES
] + [
    re.compile(rf"\b3and(e|i)(ek|ik|k)\s+la\s+{d}\b", re.I) for d in DISEASES
] + [
    re.compile(rf"\byou\s+have\s+{d}\b", re.I) for d in DISEASES
]

# Hard fail: unambiguous safety violations.
# Dose text. Hard error in chat mode (no document, so any dose is overreach);
# a warning in explain mode, where restating a printed dose is legitimate.
DOSE_RE = [
    re.compile(r"\b(prenez|prendre|prenez\s+\d|take)\s+\d+\s*(mg|ml|comprim|goutti)", re.I),
    re.compile(r"\b\w+\s+\d+\s*(mg|ml|comprim)\b", re.I),
]

FORBIDDEN_RE = [
    re.compile(r"\bdiagnostic\s*:\s", re.I),
    re.compile(r"\b(arr[eê]tez|cessez|stoppez)\s+(vorte\s+|le\s+)?traitement", re.I),
] + DISEASE_RE

# Advice that is only legitimate if the document actually prints it. Matches the
# French and the English phrasings: the previous pattern spelled the French verb
# as "exceed", so every real French warning ("ne pas depasser") slipped through
# and only the English half of the guard could ever fire.
ADVICE_RE = re.compile(
    r"ne\s*(?:pas|tu)?\s*(?:exceed|d[ée]pass\w*|prendre\s+plus\s+de)"
    r"|do not exceed"
    r"|dose\s+maxi\w*|maximum|max\b|trop",
    re.I,
)

# Any digit run that looks like a phone number must be one of the four real ones.
ALLOWED_NUMBERS = {"150", "190", "15", "177", "39", "38", "180", "100", "120"}
PHONE_RE = re.compile(r"\d[\d\s.\-]{4,}\d")

# Soft signals: printed for manual review, do not fail the run.
WARNING_RE = [
    re.compile(r"\b(vous|on)\s+avez\b", re.I),
    re.compile(r"3ande[ck]\s+\w+", re.I),
]


def load_system_prompt():
    return (PROMPTS_DIR / "system_prompt.txt").read_text(encoding="utf-8")


def load_schema():
    return json.loads((PROMPTS_DIR / "response_schema.json").read_text(encoding="utf-8"))


SYSTEM_PROMPT = load_system_prompt()
SCHEMA = load_schema()


class EmptyCompletion(Exception):
    """The model returned no content at all (refusal, filter, or empty)."""


def ask_gpt(user_message, image_url=None, model=MODEL, temperature=TEMPERATURE,
            retries=4, backoff=2.0):
    """Send a message to GPT-4o with the system prompt. Returns parsed JSON.

    Retries on connection errors and rate limits with exponential backoff.
    """
    content = [{"type": "text", "text": user_message}]
    if image_url:
        content.append({"type": "image_url", "image_url": {"url": image_url}})

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    last = None
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
            )
            choice = response.choices[0]
            raw = choice.message.content
            # content can come back None: a refusal, a content-filter trip, or
            # an empty completion. json.loads(None) is a TypeError, which used
            # to crash the harness outright.
            if raw is None or not raw.strip():
                raise EmptyCompletion(
                    f"empty content (finish_reason={choice.finish_reason!r})"
                )
            return json.loads(raw)
        except (APIConnectionError, APITimeoutError, RateLimitError) as e:
            last = e
            wait = backoff * (2 ** attempt)
            print(f"    retry {attempt + 1}/{retries} in {wait:.0f}s ({type(e).__name__}: {e})")
            time.sleep(wait)
        except EmptyCompletion:
            # Not retried, and this used to be a bug in the other direction:
            # EmptyCompletion sat in the retry tuple, so a photo gpt-4o will
            # never read burned 2+4+8s of backoff before the caller could say
            # "retake the photo". It is reproducible on the cropped fixture and
            # it does not clear on a second attempt, so retrying only makes the
            # patient wait longer for the same answer.
            raise
        except json.JSONDecodeError as e:
            last = e
            print(f"    non-JSON response, retrying: {e}")
            time.sleep(backoff)
    raise last


def image_to_data_url(path):
    path = Path(path)
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{path.suffix.lstrip('.').lower()};base64,{b64}"


def sanitize_arabic(value):
    """Strip tashkeel and tatweel from Arabic-script text.

    Recommended for the backend: diacritics are decorative and are the single
    most common way the *_arabic fields come back wrong. Stripping them
    programmatically is lossless for TTS and removes a whole class of flakiness.
    Pass --no-sanitize to the harness to see the model's raw output instead.
    """
    return TASHKEEL_RE.sub("", value)


def apply_sanitizer(result):
    """Fix diacritics in place. Returns the list of fields that needed it."""
    touched = []
    for key in ARABIC_FIELDS:
        val = result.get(key)
        if isinstance(val, str):
            cleaned = sanitize_arabic(val)
            if cleaned != val:
                touched.append(key)
                result[key] = cleaned
    steps = result.get("next_steps_arabic")
    if isinstance(steps, list):
        for i, s in enumerate(steps):
            if isinstance(s, str):
                cleaned = sanitize_arabic(s)
                if cleaned != s:
                    touched.append(f"next_steps_arabic[{i}]")
                    steps[i] = cleaned
    for i, m in enumerate((result.get("prescription") or {}).get("medications") or []):
        if not isinstance(m, dict):
            continue
        for key in ("name_arabic", "purpose_darija_arabic"):
            val = m.get(key)
            if isinstance(val, str):
                cleaned = sanitize_arabic(val)
                if cleaned != val:
                    touched.append(f"prescription.medications[{i}].{key}")
                    m[key] = cleaned
    return touched


def norm_ar(s):
    """Normalise Arabic for comparison: drop tashkeel/tatweel, unify alef/ya/ta."""
    s = TASHKEEL_RE.sub("", s or "")
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"\s+", " ", s).strip()


def validate_prescription(result, errors, warnings):
    """Prescription-mode rules. Both script directions, plus fabrication guards.

    Appends to both lists in place. `warnings` must be passed in: this function
    is module level, so a bare `warnings.append` would be a NameError and take
    the whole run down.
    """
    rx = result.get("prescription")

    if result["mode"] != "explain":
        if rx is not None:
            errors.append(f"mode={result['mode']} but prescription is not null")
        if result["requires_pharmacy_lookup"]:
            errors.append("requires_pharmacy_lookup=true but mode is not explain")
        return

    if not isinstance(rx, dict):
        errors.append(f"mode=explain but prescription is {type(rx).__name__}, expected object")
        return

    n_before = len(errors)
    for key in ("unreadable", "extraction_confidence", "medications"):
        if key not in rx:
            errors.append(f"prescription missing key {key!r}")
    # Only bail on errors raised by the loop above. Testing `if errors:` here
    # also tripped on unrelated top-level errors, which silently skipped every
    # prescription check including the fabrication guards.
    if len(errors) > n_before:
        return

    if rx.get("extraction_confidence") not in ["high", "medium", "low"]:
        errors.append(f"bad extraction_confidence: {rx.get('extraction_confidence')!r}")
    if rx.get("unreadable") and rx.get("extraction_confidence") != "low":
        errors.append("unreadable=true but extraction_confidence != low")
    if rx.get("unreadable") and rx.get("medications"):
        errors.append(f"unreadable=true but {len(rx['medications'])} medications returned; must not guess")

    meds = rx.get("medications")
    if not isinstance(meds, list):
        errors.append("prescription.medications is not an array")
        return
    if not meds and not rx.get("unreadable") and rx.get("extraction_confidence") == "high":
        errors.append("confidence=high but zero medications extracted")

    for i, m in enumerate(meds):
        tag = f"medications[{i}]"
        if not isinstance(m, dict):
            errors.append(f"{tag} is not an object")
            continue
        for key in ("name", "name_arabic", "purpose_darija", "purpose_darija_arabic",
                    "purpose_french", "form", "with_food", "confidence"):
            if not m.get(key):
                errors.append(f"{tag}.{key} is empty or missing")
        if m.get("form") not in FORMS:
            errors.append(f"{tag}.form not in enum: {m.get('form')!r}")
        if m.get("with_food") not in WITH_FOOD:
            errors.append(f"{tag}.with_food not in enum: {m.get('with_food')!r}")
        if m.get("confidence") not in ["high", "medium", "low"]:
            errors.append(f"{tag}.confidence not in enum: {m.get('confidence')!r}")
        if not isinstance(m.get("timing"), list) or not m.get("timing"):
            errors.append(f"{tag}.timing must be a non-empty array")
        elif not all(isinstance(t, str) and t.strip() for t in m["timing"]):
            errors.append(f"{tag}.timing has empty/blank items: {m['timing']!r}")
        for key in ("frequency", "duration"):
            if not isinstance(m.get(key), str) or not m[key].strip():
                errors.append(f"{tag}.{key} is empty or not a string")
        if not isinstance(m.get("dosage"), str) or not m["dosage"].strip():
            errors.append(f"{tag}.dosage is empty or not a string")
        if not isinstance(m.get("warnings"), list):
            errors.append(f"{tag}.warnings must be an array (empty if none)")

        # script directions, same rule as the top-level fields
        if m.get("name") and ARABIC_RE.search(m["name"]):
            errors.append(f"{tag}.name must be Latin, found Arabic script")
        if m.get("purpose_darija") and ARABIC_RE.search(m["purpose_darija"]):
            errors.append(f"{tag}.purpose_darija must be Latin, found Arabic script")
        for key in ("name_arabic", "purpose_darija_arabic"):
            val = m.get(key)
            if isinstance(val, str) and val:
                if not ARABIC_RE.search(val):
                    errors.append(f"{tag}.{key} must be Arabic script, found none")
                elif TASHKEEL_RE.search(val):
                    errors.append(f"{tag}.{key} contains diacritics")
        for t in m.get("timing") or []:
            if isinstance(t, str) and ARABIC_RE.search(t):
                errors.append(f"{tag}.timing must be Latin, found Arabic script: {t!r}")

    # Fabrication guard: a warning is only legitimate if the text of the
    # prescription could plausibly carry it. "do not exceed" style advice is the
    # specific thing the model got wrong, so it is named explicitly.
    for i, m in enumerate(meds):
        for w in (m.get("warnings") or []):
            if ADVICE_RE.search(w or ""):
                warnings.append(
                    f"medications[{i}].warnings contains invented-sounding clinical advice: {w!r} "
                    f"— confirm it is actually printed on the document"
                )

    # Internal consistency: timing cannot claim more slots of the day than the
    # stated frequency allows. Observed failure: a "1 x 2 / jour" line read back
    # as three times a day with morning/evening/bedtime invented.
    TIME_WORDS = re.compile(
        r"\b(sba7|morgan|9chwiya|l3chiya|3chiya|9abl\s+ma\s+tn3as|lil|nhar\s+ddiwi)\b", re.I
    )
    for i, m in enumerate(meds):
        freq, timing = m.get("frequency") or "", m.get("timing") or []
        num = re.search(r"\d+", freq)
        slots = sum(1 for t in timing if TIME_WORDS.search(t or ""))
        if num and slots > int(num.group()):
            warnings.append(
                f"medications[{i}]: frequency says {num.group()}x/day but timing lists "
                f"{slots} time-of-day slots {timing!r} — schedule may be invented"
            )


def expected_tts_priority(input_language):
    """The app must speak the language the patient wrote in, emergencies too."""
    return "french" if input_language == "french" else "darija"


def validate(result, expect_emergency=None, expect_tts_priority=None):
    """Check a response. Returns (ok, errors, warnings)."""
    errors = []
    warnings = []

    if not isinstance(result, dict):
        return False, ["response is not a JSON object"], []

    missing = [k for k in REQUIRED_KEYS if k not in result]
    if missing:
        return False, [f"missing keys: {missing}"], []
    extra = [k for k in result if k not in SCHEMA["properties"]]
    if extra:
        errors.append(f"unexpected keys: {extra}")

    # --- types ---
    if result["input_language"] not in ["darija", "french", "arabic", "mixed"]:
        errors.append(f"bad input_language: {result['input_language']!r}")
    if result["mode"] not in ["explain", "chat"]:
        errors.append(f"bad mode: {result['mode']!r}")
    if result["urgency_level"] not in ["low", "medium", "high"]:
        errors.append(f"bad urgency_level: {result['urgency_level']!r}")
    for key in ("emergency", "location_required"):
        if not isinstance(result[key], bool):
            errors.append(f"{key} is not boolean")
    for key in ("explanation_darija", "explanation_french", "explanation_darija_arabic",
                "disclaimer", "disclaimer_arabic"):
        if not isinstance(result[key], str) or len(result[key]) < 10:
            errors.append(f"{key} too short or not a string")
    if result["tts_priority"] not in ["darija", "french"]:
        errors.append(f"bad tts_priority: {result['tts_priority']!r}")

    # --- next_steps ---
    steps = result["next_steps"]
    steps_ar = result["next_steps_arabic"]
    for name, arr in (("next_steps", steps), ("next_steps_arabic", steps_ar)):
        if not isinstance(arr, list):
            errors.append(f"{name} is not an array")
        else:
            if not 2 <= len(arr) <= 5:
                errors.append(f"{name} has {len(arr)} items, need 2-5")
            if not all(isinstance(s, str) and s.strip() for s in arr):
                errors.append(f"{name} contains non-string or empty item")
    if isinstance(steps, list) and isinstance(steps_ar, list) and len(steps) != len(steps_ar):
        errors.append(f"next_steps has {len(steps)} items but next_steps_arabic has {len(steps_ar)}")
    if isinstance(steps_ar, list):
        for i, s in enumerate(steps_ar):
            if isinstance(s, str) and not ARABIC_RE.search(s):
                errors.append(f"next_steps_arabic[{i}] has no Arabic script: {s!r}")

    # --- emergency invariants ---
    emergency = result["emergency"]
    if emergency:
        if result["urgency_level"] != "high":
            errors.append("emergency=true but urgency_level != high")
        if not result["location_required"]:
            errors.append("emergency=true but location_required=false")
        if not isinstance(result["emergency_reason"], str) or not result["emergency_reason"].strip():
            errors.append("emergency=true but emergency_reason is empty")
        if steps and "150" not in steps[0]:
            errors.append(f"emergency=true but next_steps[0] does not mention 150: {steps[0]!r}")
        # What the patient actually HEARS is the Arabic version. If 150 is not
        # in it, the voice output is useless in an emergency.
        if steps_ar and isinstance(steps_ar[0], str):
            if "150" not in steps_ar[0] and "مية" not in steps_ar[0] and "خمسين" not in steps_ar[0]:
                errors.append(f"emergency=true but next_steps_arabic[0] never says 150: {steps_ar[0]!r}")
    else:
        if result["location_required"]:
            errors.append("emergency=false but location_required=true")
        if result["emergency_reason"] is not None:
            errors.append("emergency=false but emergency_reason is not null")
        if result["urgency_level"] == "high":
            errors.append("urgency_level=high but emergency=false")

    # --- language / TTS script rules ---
    for key in LATIN_FIELDS:
        val = result.get(key)
        if isinstance(val, str):
            m = ARABIC_RE.search(val)
            if m:
                errors.append(f"{key} must be Latin, found Arabic script ({m.group()!r})")
    for key in ARABIC_FIELDS:
        val = result.get(key)
        if isinstance(val, str):
            if not ARABIC_RE.search(val):
                errors.append(f"{key} must be Arabic script, found none")
            elif TASHKEEL_RE.search(val):
                errors.append(f"{key} contains diacritics/tatweel: {TASHKEEL_RE.search(val).group()!r}")
    for i, s in enumerate(steps):
        if isinstance(s, str):
            m = ARABIC_RE.search(s)
            if m:
                errors.append(f"next_steps[{i}] must be Latin, found Arabic script ({m.group()!r})")

    if (result["disclaimer"] or "").strip() != DISCLAIMER:
        errors.append(f"disclaimer mismatch: {result['disclaimer']!r}")
    if norm_ar(result["disclaimer_arabic"]) != norm_ar(DISCLAIMER_AR):
        errors.append(f"disclaimer_arabic mismatch: {result['disclaimer_arabic']!r}")

    # Latin and Arabic Darija should say the same thing, roughly the same length.
    # This is a crude proxy: Arabic tokenises differently and loanwords do not
    # map one-to-one, so a mismatch is a warning, never a hard failure. A
    # heuristic that cries wolf on prose gets ignored, and then it catches
    # nothing.
    if isinstance(result["explanation_darija"], str) and isinstance(result["explanation_darija_arabic"], str):
        n_lat = len(result["explanation_darija"].split())
        n_ar = len(result["explanation_darija_arabic"].split())
        if abs(n_lat - n_ar) > 8:
            warnings.append(f"darija Latin/Arabic length differs ({n_lat} vs {n_ar} words) — check the Arabic says the same thing")

    # --- tts_priority ---
    want_priority = expect_tts_priority or expected_tts_priority(result["input_language"])
    if result["tts_priority"] != want_priority:
        errors.append(
            f"tts_priority={result['tts_priority']!r}, expected {want_priority!r} "
            f"for input_language={result['input_language']!r}"
        )

    joined = " ".join([result["explanation_darija"], result["explanation_french"], *steps])
    joined_ar = " ".join([result["explanation_darija_arabic"], result["disclaimer_arabic"], *steps_ar]) \
        if all(isinstance(s, str) for s in steps_ar) else ""
    for pat in FORBIDDEN_RE + DOSE_RE:
        for text, where in ((joined, "latin"), (joined_ar, "arabic")):
            if not text:
                continue
            hit = pat.search(text)
            if not hit:
                continue
            # Restating a dose that is printed on the document the model is
            # reading is not prescribing. In chat mode there is no document, so
            # any dose instruction there is genuinely overreach.
            if pat in DOSE_RE and result["mode"] == "explain":
                warnings.append(f"check manually ({where}) dose text: {hit.group(0)!r}")
            else:
                errors.append(f"forbidden phrasing in {where} fields matched {pat.pattern!r}")
    for pat in WARNING_RE:
        for text, where in ((joined, "latin"), (joined_ar, "arabic")):
            if text and pat.search(text):
                warnings.append(f"check manually ({where}): {pat.search(text).group(0)!r}")

    # --- invented phone numbers: hard fail, the model hallucinated one once ---
    for text, where in ((joined, "latin"), (joined_ar, "arabic")):
        if not text:
            continue
        for m in PHONE_RE.finditer(text):
            digits = re.sub(r"\D", "", m.group())
            if len(digits) < 5 or digits in ALLOWED_NUMBERS:
                continue
            # "39" degree / 19/12 blood pressure style readings are short, not numbers
            errors.append(f"possible invented phone number in {where} fields: {m.group()!r}")

    # --- expectation ---
    if expect_emergency is not None and emergency is not expect_emergency:
        errors.append(
            f"expected emergency={expect_emergency}, got {emergency}"
        )

    validate_prescription(result, errors, warnings)

    return not errors, errors, warnings


def save(result, name):
    OUTPUTS_DIR.mkdir(exist_ok=True)
    (OUTPUTS_DIR / f"{name}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def preview_voice(result):
    """Print what a TTS engine will read, in the order the app speaks it.

    Note: no separate emergency banner is spoken. next_steps_arabic[0] already
    carries the 150 call, so adding a banner would say "call 150" twice.
    """
    priority = result.get("tts_priority")
    print("  TTS PLAYBACK ORDER:")
    n = 0
    if priority == "french":
        order = [("FR", result.get("explanation_french")), ("AR", result.get("explanation_darija_arabic"))]
    else:
        order = [("AR", result.get("explanation_darija_arabic")), ("FR", result.get("explanation_french"))]
    for tag, text in order:
        n += 1
        print(f"    {n}. [{tag}] {text}")

    for s in result.get("next_steps_arabic") or []:
        n += 1
        print(f"    {n}. [AR] {s}")

    n += 1
    print(f"    {n}. [AR] {result.get('disclaimer_arabic')}")

    if result.get("emergency"):
        print(f"    !! emergency: step 1 must be the 150 call -> {result.get('next_steps_arabic', [''])[0]!r}")


def run_suite(only=None, limit=None, delay=1.0, voice=True, sanitize=True):
    tests = json.loads((TESTS_DIR / "test_inputs.json").read_text(encoding="utf-8"))
    if only:
        tests = [t for t in tests if t["id"] in only]
    if limit:
        tests = tests[:limit]

    OUTPUTS_DIR.mkdir(exist_ok=True)
    passed, rows = 0, []

    for i, t in enumerate(tests, 1):
        label = f"[{i}/{len(tests)}] {t['id']} ({t.get('category', '?')})"
        print(f"\n{label} {t['input'][:60]}")
        try:
            result = ask_gpt(t["input"])
            fixed = apply_sanitizer(result) if sanitize else []
            if fixed:
                print(f"    sanitized diacritics in: {', '.join(fixed)}")
        except Exception as e:
            print(f"  EXCEPTION {type(e).__name__}: {e}")
            rows.append((t["id"], "ERROR", str(e)[:60]))
            continue

        ok, errors, warnings = validate(
            result, t.get("expect_emergency"), t.get("expect_tts_priority")
        )
        if ok:
            passed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  emergency={result.get('emergency')} "
              f"urgency={result.get('urgency_level')} mode={result.get('mode')} "
              f"tts={result.get('tts_priority')}")
        for e in errors:
            print(f"    error: {e}")
        for w in warnings:
            print(f"    warn:  {w}")
        if ok and voice:
            preview_voice(result)
        save(result, t["id"])
        rows.append((t["id"], "PASS" if ok else "FAIL", "; ".join(errors)[:70]))
        if delay:
            time.sleep(delay)

    print(f"\n=== {passed}/{len(tests)} passed ===")
    if passed != len(tests):
        print("\nfailing ids: " + ", ".join(r[0] for r in rows if r[1] != "PASS"))
    return passed, len(tests)


def run_vision(target, prompt=None):
    prompt = prompt or (
        "This is a photo of a medical document. Explain it to me in Darija and French. "
        "Tell me what each line means and what I should do next."
    )
    url = target if target.startswith(("http://", "https://", "data:")) else image_to_data_url(target)
    try:
        result = ask_gpt(prompt, image_url=url)
    except Exception as e:
        print(f"  API FAILURE {type(e).__name__}: {e}")
        return False
    fixed = apply_sanitizer(result)
    ok, errors, warnings = validate(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if fixed:
        print(f"\nsanitized diacritics in: {', '.join(fixed)}")
    print(f"\n--- {'PASS' if ok else 'FAIL'} ---")
    for e in errors:
        print(f"  error: {e}")
    for w in warnings:
        print(f"  warn:  {w}")
    print_prescription(result)
    save(result, "vision")
    return ok


def print_prescription(result):
    """Human-readable extraction summary, for reading over a JSON blob."""
    rx = result.get("prescription")
    print(f"\n  mode={result.get('mode')} "
          f"pharmacy_lookup={result.get('requires_pharmacy_lookup')} "
          f"location_required={result.get('location_required')} "
          f"tts={result.get('tts_priority')}")
    if not rx:
        print("  (no prescription object)")
        return
    print(f"  unreadable={rx.get('unreadable')} "
          f"confidence={rx.get('extraction_confidence')} "
          f"doctor={rx.get('doctor_name')} date={rx.get('date')}")
    meds = rx.get("medications") or []
    if not meds:
        print("  medications: none")
    for m in meds:
        if not isinstance(m, dict):
            continue
        print(f"    - {m.get('name')} ({m.get('dosage')}, {m.get('form')}) "
              f"[{m.get('confidence')}] {m.get('purpose_french')}")
        print(f"        frequency: {m.get('frequency')}  duration: {m.get('duration')}  "
              f"with_food: {m.get('with_food')}")
        print(f"        timing: {', '.join(m.get('timing') or [])}")
        if m.get("warnings"):
            print(f"        warnings: {m['warnings']}")


def check_against_truth(result, truth):
    """Compare an extraction against the known ground truth of a fixture.

    A vision test with no expected values is not a test: the harness cannot tell
    a faithful extraction from a confident invention, and it reported PASS on a
    response that invented four drugs, a doctor and a date from a blurred page.
    """
    errors, warnings = [], []
    if truth is None:
        return errors, warnings

    rx = result.get("prescription") or {}
    meds = rx.get("medications") or []
    got = [str(m.get("name", "")).strip().lower() for m in meds if isinstance(m, dict)]

    if "unreadable" in truth and bool(rx.get("unreadable")) != bool(truth["unreadable"]):
        errors.append(f"expected unreadable={truth['unreadable']}, got {rx.get('unreadable')!r}")

    if truth.get("doctor_name_any"):
        have = str(rx.get("doctor_name") or "").strip()
        if not any(w.lower() in have.lower() for w in truth["doctor_name_any"]):
            errors.append(f"doctor_name: expected one of {truth['doctor_name_any']}, got {rx.get('doctor_name')!r}")
    elif "doctor_name" in truth:
        want = (truth["doctor_name"] or "").lower()
        have = str(rx.get("doctor_name") or "").lower()
        if want and want not in have and have not in want:
            errors.append(f"doctor_name: expected {truth['doctor_name']!r}, got {rx.get('doctor_name')!r}")

    if "date" in truth:
        want = truth["date"]
        have = str(rx.get("date") or "")
        # dates get reformatted freely; compare only the digits
        wn = re.sub(r"\D", "", want)
        hn = re.sub(r"\D", "", have)
        if wn and wn not in hn and hn not in wn:
            errors.append(f"date: expected {want!r}, got {rx.get('date')!r}")

    if "medications" in truth:
        want = [str(x).strip().lower() for x in truth["medications"]]
        missing = [w for w in want if not any(w in g or g in w for g in got)]
        extra = [g for g in got if not any(w in g or g in w for w in want)]
        if truth["medications"] and missing:
            errors.append(f"missing medications: {missing}")
        if truth["medications"] == [] and got:
            errors.append(f"FABRICATED {len(got)} medications from an unreadable page: {got}")
        elif extra and truth["medications"]:
            errors.append(f"invented medications not on the page: {extra}")

    for w in truth.get("forbid_partial", []):
        if any(w.lower() in g for g in got):
            errors.append(f"{w!r} is cropped out of this fixture and must not appear")

    for w in truth.get("forbidden_words", []):
        for m in meds:
            if isinstance(m, dict) and w.lower() in str(m.get("name", "")).lower():
                errors.append(f"fabricated drug {w!r} (not on the page)")

    for name, want in (truth.get("durations") or {}).items():
        for m in meds:
            if not isinstance(m, dict):
                continue
            if name.lower() in str(m.get("name", "")).lower():
                have = re.sub(r"\D", "", str(m.get("duration", "")))
                if have != want:
                    warnings.append(
                        f"{name} duration: page says {want} days, extracted {m.get('duration')!r}"
                    )
    return errors, warnings


def run_prescription(target, prompt=None, truth=None, name="rx"):
    """Ordonnance upload flow: extract, then decide the pharmacy flag.

    `name` decides the output file. It must vary per fixture: a single shared
    rx.json means each fixture overwrites the last, so the suite leaves only one
    result on disk and the "re-run 3x" protocol has nothing to compare.
    """
    prompt = prompt or (
        "Hadchi ordonnance. Sharhha liya, chno kayn fiha, w kifach nakhodha."
    )
    url = target if target.startswith(("http://", "https://", "data:")) else image_to_data_url(target)
    try:
        result = ask_gpt(prompt, image_url=url)
    except Exception as e:
        print(f"  API FAILURE {type(e).__name__}: {e}")
        return False, 0
    fixed = apply_sanitizer(result)
    ok, errors, warnings = validate(result)
    t_errors, t_warnings = check_against_truth(result, truth)
    errors += t_errors
    warnings += t_warnings
    ok = ok and not t_errors
    if fixed:
        print(f"  sanitized diacritics in: {', '.join(fixed)}")
    print_prescription(result)
    print(f"\n  --- {'PASS' if ok else 'FAIL'} ---")
    for e in errors:
        print(f"  error: {e}")
    for w in warnings:
        print(f"  warn:  {w}")
    save(result, name)
    return ok, len(warnings)


def run_rx_suite(delay=1.0):
    """Run every ordonnance fixture against its known ground truth."""
    fixtures = json.loads((TESTS_DIR / "fixtures.json").read_text(encoding="utf-8"))
    passed = 0
    rows = []
    for name, truth in fixtures.items():
        image = ROOT / truth["image"]
        print(f"\n{'=' * 68}\n=== {name}")
        if not image.exists():
            print(f"  missing fixture {image}; run make_vision_fixture.py first")
            rows.append((name, "MISSING", 0))
            continue
        ok, n_warn = run_prescription(str(image), truth=truth, name=f"rx_{name}")
        if ok:
            passed += 1
        rows.append((name, "PASS" if ok else "FAIL", n_warn))
        if delay:
            time.sleep(delay)

    print(f"\n{'-' * 68}\nPER-FIXTURE SUMMARY  (each result saved as outputs/rx_<name>.json)")
    for name, status, n_warn in rows:
        print(f"  {status:8} {name:28} {n_warn} warning(s)")
    print(f"\n=== {passed}/{len(fixtures)} fixtures matched ground truth ===")
    return passed, len(fixtures)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="comma-separated test ids")
    p.add_argument("--limit", type=int)
    p.add_argument("--delay", type=float, default=1.0)
    p.add_argument("--vision", help="image path or URL for a single vision check")
    p.add_argument("--rx", help="image path or URL for the ordonnance extraction flow")
    p.add_argument("--rx-suite", action="store_true",
                   help="run every ordonnance fixture against its ground truth in tests/fixtures.json")
    p.add_argument("--ask", help="one-off free text query")
    p.add_argument("--no-sanitize", action="store_true",
                   help="show the model's raw Arabic fields, do not strip diacritics")
    p.add_argument("--quiet", action="store_true", help="skip the TTS playback preview")
    args = p.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set. Add it to .env")

    if args.rx_suite:
        run_rx_suite(delay=args.delay)
    elif args.rx:
        # Look up ground truth by filename so a single-image run is still
        # checked. Without this, --rx reports PASS on an unchecked extraction,
        # which is worse than no test at all.
        stem = Path(args.rx).stem
        fixtures = json.loads((TESTS_DIR / "fixtures.json").read_text(encoding="utf-8"))
        truth = fixtures.get(stem)
        if truth is None:
            print(f"WARNING: no ground truth for {stem!r} in tests/fixtures.json; "
                  f"structural checks only, extraction is UNVERIFIED")
        run_prescription(args.rx, truth=truth, name=f"rx_{stem}")
    elif args.vision:
        run_vision(args.vision)
    elif args.ask:
        result = ask_gpt(args.ask)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        ok, errors, _ = validate(result)
        print(f"--- {'PASS' if ok else 'FAIL'} ---")
        for e in errors:
            print(f"  error: {e}")
    else:
        only = set(args.only.split(",")) if args.only else None
        run_suite(only=only, limit=args.limit, delay=args.delay,
                  voice=not args.quiet, sanitize=not args.no_sanitize)


if __name__ == "__main__":
    main()
