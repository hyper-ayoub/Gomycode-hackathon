"""Local test UI for DarijaDoc.

Run: .venv/bin/python serve.py     ->  http://127.0.0.1:8000

Standard library only, so requirements.txt stays three lines. Every request goes
through test_prompt.ask_gpt and is scored by test_prompt.validate, so the UI
cannot drift from the harness: if the UI says PASS, the harness agrees.

Pharmacy and hospital lookup goes through the OpenStreetMap Overpass API. It is
keyless, which is the whole reason it is used here: a demo that needs a billing
account to show a map is a demo that cannot be shown. The manual city selector is
served from a static table, so the denied-geolocation path needs no third party
at all.

The API key stays in this process, read from .env, and is never sent to the
browser. Binds to 127.0.0.1 only. No auth, no rate limit, so don't expose it.
"""
import argparse
import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import test_prompt as tp

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"

# A phone photo of an ordonnance is a few MB. Anything past this is a mistake,
# not a real upload, and base64 inflates it by a third before we even parse it.
MAX_BODY = 12 * 1024 * 1024

# Overpass mirrors, tried in order. Live-tested while building this: the main
# instance and kumi.systems both 504 or time out under repeated querying, and
# private.coffee timed out every time. lz4 is the same operator as the main
# instance and answered in 4s where the main took 16s. overpass.osm.jp was tried
# and removed: it presents a certificate that is not valid for the hostname.
# A mirror list here is a guess until it is tested, so re-test it before
# trusting it.
OVERPASS = [
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OVERPASS_TIMEOUT = 25
USER_AGENT = "DarijaDoc/1.0 (local test bench; contact: repo owner)"

# Coarse city centre, used when the patient declines or loses geolocation. This
# is a static table on purpose: the manual path has to work with no network and
# no geocoder, because permission denial is the *likely* path on a desktop
# browser during a demo, not the edge case. Radius accuracy is irrelevant here,
# Overpass takes a radius around the centre either way.
CITIES = {
    "Casablanca": (33.5731, -7.5898),
    "Rabat": (34.0209, -6.8416),
    "Marrakech": (31.6295, -7.9811),
    "Fes": (34.0181, -5.0078),
    "Tanger": (35.7595, -5.8340),
    "Agadir": (30.4278, -9.5981),
    "Meknes": (33.8935, -5.5473),
    "Oujda": (34.6867, -1.9114),
    "Kenitra": (34.2610, -6.5802),
    "Tetouan": (35.5785, -5.3684),
    "Safi": (32.2994, -9.2372),
    "El Jadida": (33.2316, -8.5007),
    "Beni Mellal": (32.3373, -6.3498),
    "Nador": (35.1681, -2.9287),
    "Taza": (34.2100, -4.0100),
    "Berkane": (34.9218, -2.3200),
    "Khouribga": (32.8811, -6.9062),
    "Mohammedia": (33.6866, -7.3829),
    "Al Hoceima": (35.2517, -3.9366),
    "Ouarzazate": (30.9335, -6.9370),
    "Errachidia": (31.9314, -4.4247),
    "Essaouira": (31.5085, -9.7595),
    "Laayoune": (27.1253, -13.1625),
    "Guelmim": (28.9870, -10.0574),
    "Dakhla": (23.6848, -15.9580),
}

# Cache by rounded coordinate: a patient tapping twice in the same spot should
# not hammer a free public endpoint. Short TTL, because opening hours change.
_poi_cache = {}
_poi_cache_lock = threading.Lock()
POI_TTL = 300

# OSM tags what is physically a dental practice or a lab as amenity=hospital, so
# an unfiltered hospital search puts "Centre consultation et traitement
# dentaires" second behind the nearest real hospital. For a patient deciding
# where to go, that is a bad answer, and it cannot be fixed with an amenity
# filter because the data itself is wrong. Rank by name instead, and label it.
SPECIALIST_RE = re.compile(
    r"dentaire|dentiste|esthetique|ophtalmo|kinesitherap|psycholog|"
    r"laboratoire|analyse|analyses|centre de consultation|consultation",
    re.I,
)
GENERAL_RE = re.compile(r"hopital|hôpital|urgences|clinique|polyclinique", re.I)

# Moroccan OSM data tags a fair number of pharmacies as amenity=hospital. Served
# as-is, a pharmacy appears in the emergency list as a place to be treated.
NOT_A_HOSPITAL_RE = re.compile(r"pharmac|officine", re.I)

CTYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
}

STATIC = {
    "/": (WEB / "index.html", "text/html; charset=utf-8"),
    "/index.html": (WEB / "index.html", "text/html; charset=utf-8"),
    "/style.css": (WEB / "style.css", "text/css; charset=utf-8"),
    "/app.js": (WEB / "app.js", "text/javascript; charset=utf-8"),
    "/map.js": (WEB / "map.js", "text/javascript; charset=utf-8"),
    # Served straight out of prompts/, so the browser runs the real file.
    "/voice.js": (ROOT / "prompts" / "voice.js", "text/javascript; charset=utf-8"),
}

STATIC_DIRS = {
    "outputs": ROOT / "outputs",
    # Leaflet is vendored rather than pulled from a CDN: a demo on hotel wifi
    # that silently loses its map is worse than a slightly stale leaflet.js.
    "vendor": WEB / "vendor",
}


def haversine(lat1, lng1, lat2, lng2):
    """Metres between two points. Good enough to sort a list of nearby places."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def overpass(query):
    """Run an Overpass QL query, trying each mirror. Returns (elements, mirror).

    Raises the last error if every mirror fails, so the caller can tell the
    patient the lookup is unavailable rather than showing an empty map that
    looks like "there are no pharmacies here".
    """
    last = None
    for base in OVERPASS:
        try:
            req = urllib.request.Request(
                base, data=query.encode("utf-8"),
                headers={"User-Agent": USER_AGENT, "Content-Type": "text/plain; charset=utf-8"},
            )
            with urllib.request.urlopen(req, timeout=OVERPASS_TIMEOUT) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return payload.get("elements", []), base
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            last = e
            print(f"  overpass mirror failed ({base}): {type(e).__name__}: {e}", file=sys.stderr)
    raise last if last else RuntimeError("no Overpass mirror available")


class Handler(BaseHTTPRequestHandler):
    server_version = "DarijaDoc"

    # ---------- plumbing ----------

    def log_message(self, fmt, *args):
        # Keep the terminal readable: the harness already prints its own detail.
        sys.stderr.write("  %s\n" % (fmt % args))

    def _send(self, code, body=b"", ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # Local-only tool: never let a stale bundle survive a code change.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None, "bad Content-Length"
        if n <= 0:
            return None, "empty body"
        if n > MAX_BODY:
            return None, f"upload too large ({n / 1048576:.1f} MB, limit {MAX_BODY // 1048576} MB)"
        try:
            return json.loads(self.rfile.read(n)), None
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return None, f"bad JSON: {e}"

    def _static(self, path):
        if path in STATIC:
            f, ctype = STATIC[path]
            if not f.is_file():
                return self._send(404, "not found", "text/plain; charset=utf-8")
            return self._send(200, f.read_bytes(), ctype)

        # Serve the generated fixtures so the UI can show the real photo, and the
        # vendored leaflet the map needs.
        for d, base in STATIC_DIRS.items():
            if path.startswith(f"/{d}/"):
                rel = urllib.parse.unquote(path[len(d) + 2:])
                f = (base / rel).resolve()
                # Path traversal guard: the resolved file must stay under base.
                if not f.is_file() or base.resolve() not in f.parents:
                    return self._send(404, "not found", "text/plain; charset=utf-8")
                ctype = CTYPES.get(f.suffix.lower(), "application/octet-stream")
                return self._send(200, f.read_bytes(), ctype)

        return self._send(404, "not found", "text/plain; charset=utf-8")

    # ---------- routes ----------

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/api/health":
            return self._json({
                "ok": True,
                "api_key": bool(os.getenv("OPENAI_API_KEY")),
                "model": tp.MODEL,
                "samples": len(json.loads((tp.TESTS_DIR / "test_inputs.json").read_text("utf-8"))),
                # voice.js probes this to decide whether the Play button is
                # honest. It must not be a guess: a Play button that lights up
                # and then says nothing is the failure mode we are avoiding.
                "tts": bool(os.getenv("OPENAI_API_KEY")),
                "places": True,
            })

        if path == "/api/cities":
            return self._json([{"name": n, "lat": c[0], "lng": c[1]} for n, c in CITIES.items()])

        if path == "/api/samples":
            tests = json.loads((tp.TESTS_DIR / "test_inputs.json").read_text("utf-8"))
            return self._json([
                {"id": t["id"], "input": t["input"], "category": t.get("category", "?"),
                 "expect_emergency": t.get("expect_emergency")}
                for t in tests
            ])

        if path == "/api/fixtures":
            fixtures = json.loads((tp.TESTS_DIR / "fixtures.json").read_text("utf-8"))
            return self._json([
                {"name": n, "url": "/outputs/" + Path(t["image"]).name,
                 "note": t.get("note", ""), "unreadable": t.get("unreadable")}
                for n, t in fixtures.items()
            ])

        return self._static(path)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        data, err = self._body()
        if err:
            return self._json({"ok": False, "error": err}, 400)

        try:
            if path == "/api/ask":
                return self._json(self._ask(data))
            if path == "/api/rx":
                return self._json(self._rx(data))
            if path == "/api/tts":
                return self._tts(data)
            if path == "/api/pharmacies":
                out = self._pois(data, ("pharmacy",), 3000, 25)
                return self._json(out, 200 if out.get("ok") else 502)
            if path == "/api/hospitals":
                # amenity=hospital only, never "clinic". OSM tags diagnostic labs
                # and dental practices as clinics, so a clinic-inclusive query
                # put "Laboratoire de Biologie Medicale" at 686m ahead of the
                # nearest real hospital at 2.2km. For the emergency map that is
                # the worst possible answer: a lab cannot treat anyone.
                #
                # 10km, not 20: Overpass cost climbs steeply with radius and a
                # 20km search took over two minutes, which is useless to someone
                # waiting on an ambulance decision.
                out = self._pois(
                    data, ("hospital",), 10000, 15, drop_re=NOT_A_HOSPITAL_RE)
                return self._json(out, 200 if out.get("ok") else 502)
        except Exception as e:  # never take the server down on one bad request
            return self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)

        return self._json({"ok": False, "error": "unknown route"}, 404)

    # ---------- places: pharmacies and hospitals ----------

    def _pois(self, data, amenities, radius, limit, drop_re=None):
        """Nearby places from OpenStreetMap, by coordinates or by city name.

        Deliberately no geolocation on the server: the coordinates come from the
        browser (granted) or from the static city table (declined), never from
        this process asking for anything.

        `drop_re` exists because amenity=hospital is not a reliable promise: a
        Casablanca pharmacy is tagged as a hospital in the live OSM data, and it
        was served as the 4th nearest hospital. Filtered on the name, not hidden.
        """
        lat, lng, via = self._origin(data)
        if lat is None:
            return {"ok": False, "error": "send lat/lng, or a city name from /api/cities"}

        kinds = "|".join(amenities)
        key = (kinds, round(lat, 3), round(lng, 3))
        now = time.time()
        with _poi_cache_lock:
            hit = _poi_cache.get(key)
            if hit and now - hit["at"] < POI_TTL:
                return {"ok": True, "via": hit["via"], "origin": hit["origin"],
                        "places": hit["places"], "cached": True}

        where = (f"around:{radius},{lat:.5f},{lng:.5f}")
        query = (
            f"[out:json][timeout:20];("
            + "".join(
                f'nwr["amenity"="{a}"]({where});' for a in amenities
            )
            # Ask for more than we need: drop_re removes some, and truncating at
            # the final count would leave the list short.
            + f");out center {limit * 3};"
        )
        try:
            elements, mirror = overpass(query)
        except Exception as e:
            # Overpass is a free public service and it does go down. An empty map
            # would read as "there is no pharmacy here", which on an emergency map
            # is a dangerous lie, so this is reported as a failure with a way out.
            print(f"  places lookup failed: {type(e).__name__}: {e}", file=sys.stderr)
            return {
                "ok": False,
                "kind": "places_unavailable",
                "error": "The map service is not answering right now. "
                         "Open OpenStreetMap below to search by hand.",
                "detail": f"{type(e).__name__}: {e}",
                "origin": {"lat": lat, "lng": lng, "via": via},
                "places": [],
            }

        places = []
        dropped = 0
        for el in elements:
            tags = el.get("tags") or {}
            if drop_re and drop_re.search(" ".join(str(v) for v in tags.values())):
                dropped += 1
                continue
            plat = el.get("lat") or (el.get("center") or {}).get("lat")
            plng = el.get("lon") or (el.get("center") or {}).get("lon")
            if plat is None or plng is None:
                continue
            name = tags.get("name") or tags.get("name:fr") or tags.get("name:ar")
            named = bool(name and name.strip())
            if not named:
                # Never invent a reassuring name for a node the mapper left blank.
                # Defaulting to "Pharmacie" put an unnamed node at the top of the
                # emergency list, which is precisely the wrong thing to do.
                name = {"pharmacy": "Pharmacie (sans nom)"}.get(tags.get("amenity"),
                                                               "Établissement de santé (sans nom)")
            specialist = bool(SPECIALIST_RE.search(name)) and not GENERAL_RE.search(name)
            places.append({
                "name": name,
                "name_ar": tags.get("name:ar") or "",
                "kind": tags.get("amenity"),
                "named": named,
                # A specialist facility is still shown, never hidden: dropping it
                # would be a lie about what is nearby. It is ranked below the
                # places that can actually treat an emergency, and so is a place
                # we cannot even name.
                "specialist": specialist or not named,
                "lat": plat,
                "lng": plng,
                "distance_m": int(haversine(lat, lng, plat, plng)),
                "phone": tags.get("phone") or tags.get("contact:phone") or "",
                "hours": tags.get("opening_hours") or "",
                "always_open": tags.get("opening_hours") in ("24/7", "always"),
            })
        # Nearest named general facility first; specialists and unnamed nodes
        # after, each still by distance.
        places.sort(key=lambda p: (p["specialist"], p["distance_m"]))

        origin = {"lat": lat, "lng": lng, "via": via}
        with _poi_cache_lock:
            _poi_cache[key] = {"at": now, "via": via, "origin": origin, "places": places}

        return {
            "ok": True,
            "origin": origin,
            "places": places[:limit],
            "source": "OpenStreetMap via Overpass",
            "mirror": mirror,
            "dropped_wrongly_tagged": dropped,
            # An empty list is a real answer in a village with no mapped
            # pharmacy. The UI has to say so rather than looking broken.
            "empty_reason": None if places else
                "No pharmacy mapped within this radius. Try a bigger town, or ask "
                "someone locally — this is a coverage gap in the map data, not proof "
                "there is no pharmacy.",
        }

    @staticmethod
    def _origin(data):
        """Coordinates from lat/lng, or a city name from the static table.

        The city branch is a lookup in a dict, not a geocoder call. That keeps
        the denied-permission path working with no third party and no key.
        """
        try:
            lat = data.get("lat")
            lng = data.get("lng")
            if lat is not None and lng is not None:
                lat, lng = float(lat), float(lng)
                if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                    return None, None, None
                # Morocco, with slack: a patient abroad may still want a map.
                return lat, lng, "gps"
        except (TypeError, ValueError):
            pass

        name = (data.get("city") or "").strip().lower()
        if not name:
            return None, None, None
        for city, (clat, clng) in CITIES.items():
            if city.lower() == name:
                return clat, clng, "city"
        return None, None, None

    # ---------- speech ----------

    def _tts(self, data):
        """OpenAI TTS, because no browser ships an Arabic voice.

        The whole point of the *_arabic fields is that no phone or desktop TTS
        engine will read Darija written in Latin letters, it reads it as English
        gibberish. Chrome on Linux typically has zero ar-* voices, so
        speechSynthesis cannot do this job at all here. OpenAI renders the same
        Arabic script properly, so the server speaks and the browser just plays.

        One mp3 per call, not one per field: the queue order still comes from
        voice.js, so the emergency call stays step 1 and a single failure cannot
        leave a half-finished queue talking.

        `instructions` is how a single clip still switches language per section.
        A bare string carries no language boundary, so without it the French
        passage gets read with the Darija voice at the Darija rate.
        """
        text = (data.get("text") or "").strip()
        if not text:
            return self._json({"ok": False, "error": "nothing to say"}, 400)
        if len(text) > 2000:
            return self._json({"ok": False, "error": "too long to speak"}, 400)

        instructions = (data.get("instructions") or "").strip() or None
        if instructions and len(instructions) > 1000:
            instructions = instructions[:1000]

        from openai import OpenAI
        kwargs = {
            "model": data.get("model") or "gpt-4o-mini-tts",
            "voice": data.get("voice") or "shimmer",
            "input": text,
        }
        if instructions:
            kwargs["instructions"] = instructions
        try:
            r = OpenAI(api_key=os.getenv("OPENAI_API_KEY")).audio.speech.create(**kwargs)
            audio = r.read()
        except TypeError:
            # An older SDK that does not know the parameter. Losing the language
            # hint is bad; failing the request would be worse.
            kwargs.pop("instructions", None)
            try:
                r = OpenAI(api_key=os.getenv("OPENAI_API_KEY")).audio.speech.create(**kwargs)
                audio = r.read()
            except Exception as e:
                return self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 502)
        except Exception as e:
            return self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 502)

        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(audio)

    # ---------- the two model calls ----------

    def _score(self, result, truth=None, expect_emergency=None):
        """Run the harness validators. Same code path as the CLI."""
        ok, errors, warnings = tp.validate(result, expect_emergency=expect_emergency)
        if truth is not None:
            t_errors, t_warnings = tp.check_against_truth(result, truth)
            errors += t_errors
            warnings += t_warnings
            ok = ok and not t_errors
        return {"pass": ok, "errors": errors, "warnings": warnings}

    def _expectation(self, test_id):
        """Pull the labelled expectation for a test case, so clicking a chip in
        the UI is scored exactly like running that id through the CLI."""
        if not test_id:
            return None
        for t in json.loads((tp.TESTS_DIR / "test_inputs.json").read_text("utf-8")):
            if t["id"] == test_id:
                return t.get("expect_emergency")
        return None

    def _ask(self, data):
        text = (data.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "type something first"}
        if len(text) > 4000:
            return {"ok": False, "error": "too long (4000 char limit)"}

        expect = self._expectation(data.get("id"))
        result = tp.ask_gpt(text)
        touched = tp.apply_sanitizer(result) if data.get("sanitize", True) else []

        return {
            "ok": True,
            "result": result,
            "sanitized": touched,
            "labelled": data.get("id") or None,
            "check": self._score(result, expect_emergency=expect),
        }

    def _rx(self, data):
        image = data.get("image") or ""
        stem = (data.get("filename") or "").strip()
        stem = Path(stem).stem if stem else ""

        if image.startswith("data:"):
            url = image
        elif image.startswith(("http://", "https://")):
            url = image
        else:
            return {"ok": False, "error": "no image attached"}

        if len(url) > MAX_BODY:
            return {"ok": False, "error": "image too large"}

        fixtures = json.loads((tp.TESTS_DIR / "fixtures.json").read_text("utf-8"))
        truth = fixtures.get(stem)

        # The prompt the harness uses for the ordonnance flow, so the UI and the
        # CLI exercise the model identically.
        prompt = data.get("prompt") or (
            "Hadchi ordonnance. Sharhha liya, chno kayn fiha, w kifach nakhodha."
        )

        try:
            result = tp.ask_gpt(prompt, image_url=url)
        except tp.EmptyCompletion as e:
            # The harness's own note: this must not surface as an error, it has
            # to ask for a retake. gpt-4o does it on some real photos.
            return {"ok": False, "kind": "empty_completion",
                    "error": "The model returned no content for this photo.",
                    "advice": "Retake it: flat, well lit, whole page in frame.",
                    "detail": str(e)}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

        touched = tp.apply_sanitizer(result)

        return {
            "ok": True,
            "result": result,
            "sanitized": touched,
            "check": self._score(result, truth),
            "truth_found": truth is not None,
            "photo": image if image.startswith("data:") else url,
        }


def main():
    ap = argparse.ArgumentParser(description="Local DarijaDoc test UI")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set. Add it to .env")

    if args.host not in ("127.0.0.1", "localhost"):
        sys.exit(f"refusing to bind {args.host}: this holds your API key and has no auth")

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"  DarijaDoc  {url}   (model {tp.MODEL})")
    print("  Ctrl-C to stop\n")
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
        srv.server_close()


if __name__ == "__main__":
    main()
