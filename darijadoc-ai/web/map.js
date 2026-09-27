// DarijaDoc — map + location.
//
// Leaflet is loaded as a classic script by index.html and read off `window.L`.
// Markers are inline SVG rather than Leaflet's default PNG icons on purpose:
// the default resolves its image path by sniffing the stylesheet URL, which
// breaks the moment the CSS is served from anywhere other than the page root.
//
// Two rules this file exists to enforce:
//   1. Never call geolocation without a user gesture. See locateUser().
//   2. Never show a map that silently failed. See tileerror handling below.

const OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/* ------------------------------------------------------------------ pins */

const pin = (svg, cls) =>
  L.divIcon({
    className: `pin ${cls}`,
    html: `<svg viewBox="0 0 24 32" width="24" height="32" aria-hidden="true">${svg}</svg>`,
    iconSize: [24, 32],
    iconAnchor: [12, 32],
    popupAnchor: [0, -30],
  });

// Pharmacy: green cross on a white disc. Hospital: red cross. Distinguished by
// shape and colour, not colour alone.
const PHARMACY_SVG =
  '<circle cx="12" cy="12" r="11" fill="#fff" stroke="#0a7d3f" stroke-width="2"/>' +
  '<path d="M10 6h4v4h4v4h-4v4h-4v-4H6v-4h4z" fill="#0a7d3f"/>';
const HOSPITAL_SVG =
  '<circle cx="12" cy="12" r="11" fill="#fff" stroke="#c62828" stroke-width="2"/>' +
  '<path d="M10 6h4v4h4v4h-4v4h-4v-4H6v-4h4z" fill="#c62828"/>';
const USER_SVG =
  '<circle cx="12" cy="12" r="7" fill="#1a73e8" stroke="#fff" stroke-width="3"/>';

/* ------------------------------------------------------------------ maps */

const maps = new Map(); // container id -> Leaflet map, so a re-render reuses it

/**
 * Create or reuse a map in `container`.
 * Leaflet throws if you initialise twice on the same element, and the result
 * panel is reused for every response, so reuse is not optional here.
 */
export function getMap(container, center = [31.6295, -7.9811], zoom = 6) {
  const id = container.id;
  const existing = maps.get(id);
  if (existing) {
    if (container.isConnected) {
      existing.setView(center, zoom);
      return existing;
    }
    // The container was replaced in the DOM, so this map is orphaned: its
    // panes live in a detached element and nothing would ever be visible.
    existing.remove();
    maps.delete(id);
  }

  const map = L.map(container, { zoomControl: true, scrollWheelZoom: false })
    .setView(center, zoom);

  const tiles = L.tileLayer(OSM_TILES, {
    maxZoom: 19,
    attribution: OSM_ATTR,
  });
  tiles.on("tileerror", () => {
    // Blanking out with no explanation looks like a bug in the app. OSM tiles
    // need internet; the markers below are still correct without them.
    note(container, "Map tiles unavailable offline — markers and distances are still correct.");
  });
  tiles.addTo(map);

  maps.set(id, map);
  // A container that was display:none when the map was created has no size, so
  // Leaflet renders a grey box until invalidateSize().
  requestAnimationFrame(() => map.invalidateSize());
  return map;
}

function note(container, text) {
  let n = container.querySelector(".map-note");
  if (!n) {
    n = document.createElement("p");
    n.className = "map-note";
    container.append(n);
  }
  n.textContent = text;
}

/** Wipe markers from a previous render. */
function clearMarkers(map) {
  for (const layer of map._darijaLayers || []) map.removeLayer(layer);
  map._darijaLayers = [];
}

function addLayer(map, layer) {
  (map._darijaLayers = map._darijaLayers || []).push(layer);
  return layer;
}

/**
 * Draw the places, the patient, and optionally a destination.
 * `user` is null when the location came from the city table instead of GPS, and
 * the map says so rather than drawing a pin the patient is not at.
 *
 * Places are ranked nearest first and the nearest popup opens, because "nearest"
 * is the only reason anyone opened this.
 */
export function drawPlaces(map, { places = [], user = null, via = "gps", kind = "pharmacy" }) {
  clearMarkers(map);

  const isPharmacy = kind === "pharmacy";
  const bounds = [];

  places.forEach((p, i) => {
    const icon = pin(isPharmacy ? PHARMACY_SVG : HOSPITAL_SVG, isPharmacy ? "pin--rx" : "pin--hosp");
    const marker = L.marker([p.lat, p.lng], { icon, title: p.name, alt: p.name });
    const hours = p.hours ? `<br><small>${escapeHtml(p.hours)}</small>` : "";
    const phone = p.phone ? `<br><a href="tel:${escapeHtml(p.phone)}">${escapeHtml(p.phone)}</a>` : "";
    marker.bindPopup(
      `<b>${escapeHtml(p.name)}</b><br>${isPharmacy ? "Pharmacie" : "Hôpital / clinique"}` +
      `<br>${p.distance_m >= 1000 ? (p.distance_m / 1000).toFixed(1) + " km" : p.distance_m + " m"} away` +
      hours + phone
    );
    marker.addTo(map);
    addLayer(map, marker);
    bounds.push([p.lat, p.lng]);
    // Rank in the popup: nearest first is the whole point of the sort.
    if (i === 0) marker.openPopup();
  });

  if (user) {
    const here = L.marker([user.lat, user.lng], {
      icon: pin(USER_SVG, "pin--me"),
      title: via === "gps" ? "Your position" : "City centre (approximate)",
      alt: "Your position",
      zIndexOffset: 1000,
    }).addTo(map);
    addLayer(map, here);
    bounds.push([user.lat, user.lng]);
  }

  if (bounds.length) {
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
  }
  return map;
}

/** A straight-line "open in OSM" link, for phones where the map tiles are slow. */
export function directionsUrl(lat, lng) {
  return `https://www.openstreetmap.org/directions?to=${lat}%2C${lng}`;
}

/**
 * Last resort when the lookup service is down: search OpenStreetMap by hand.
 * It needs no key and no backend, so the patient is never simply stuck.
 */
export function browseUrl(kind) {
  const q = kind === "hospital" ? "hôpital" : "pharmacie";
  return `https://www.openstreetmap.org/search?query=${encodeURIComponent(q)}`;
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* -------------------------------------------------------------- location */

/**
 * Ask the browser where the patient is. **Call this only from a click handler.**
 *
 * Never on page load: the permission prompt has to come from the tap, and a
 * prompt on load is both bad UX and auto-denied in Safari and Firefox. On a
 * desktop browser during a demo, denial is the likely path, not the edge case,
 * so every caller needs a manual fallback ready.
 *
 * Rejects with a message meant to be shown to the patient as-is.
 */
export function locateUser({ timeout = 8000 } = {}) {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) {
      return reject(new Error("This browser cannot share your location. Pick your city below."));
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
        via: "gps",
      }),
      (err) => {
        const why = {
          1: "Location permission was refused. Pick your city below instead.",
          2: "Your location is unavailable. Pick your city below instead.",
          3: "Location lookup timed out. Pick your city below instead.",
        }[err.code] || "Could not get your location. Pick your city below instead.";
        reject(new Error(why));
      },
      { enableHighAccuracy: false, timeout, maximumAge: 60000 }
    );
  });
}
