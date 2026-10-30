// TasteWalk front end: builds the request, streams agent steps over SSE, renders the comparison.
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const hhmm = (t) => (t || "").slice(0, 5);

const STEPS = [
  ["taste", "Taste agent: matching your favorites in Qloo"],
  ["candidates", "Taste agent: finding places that match your taste"],
  ["plan", "Planner: choosing stops and the walking order"],
  ["critic", "Critic: explaining why each stop fits"],
  ["baseline", "Baseline: asking an LLM without Qloo"],
];

let META = null;
let map = null;
let mapLayer = null;
let source = null;

async function init() {
  META = await fetch("/api/meta").then((r) => r.json());
  if (META.fake_data) showBanner("Demo data: Qloo is mocked with fictional places (TASTEWALK_FAKE_QLOO=1).");
  else if (!META.has_qloo) showBanner("Qloo key not configured: only cached example profiles will work.");

  $("#city").innerHTML = META.cities.map((c) => `<option>${esc(c)}</option>`).join("");
  $("#examples").innerHTML = META.examples
    .map((e) => `<button type="button" class="chip-btn" data-ex="${esc(e.id)}">${esc(e.label)}</button>`)
    .join("");
  $("#examples").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-ex]");
    if (b) loadExample(META.examples.find((e) => e.id === b.dataset.ex).input, true);
  });
  $("#add-fav").addEventListener("click", () => addFav());
  $("#favs").addEventListener("click", (ev) => {
    if (ev.target.closest(".fav-del") && $("#favs").children.length > 1) ev.target.closest(".fav").remove();
  });
  $("#form").addEventListener("submit", (ev) => { ev.preventDefault(); submit(); });
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showCol(t.dataset.col)));

  // Shareable demo links: /?example=indie runs that profile right away.
  const exId = new URLSearchParams(location.search).get("example");
  const ex = META.examples.find((e) => e.id === exId);
  loadExample((ex || META.examples[0]).input, !!ex);
}

function showBanner(text) { const b = $("#banner"); b.textContent = text; b.hidden = false; }

function addFav(name = "", type = "urn:entity:artist") {
  const row = $("#fav-row").content.firstElementChild.cloneNode(true);
  const sel = $(".fav-type", row);
  sel.innerHTML = META.types.map((t) => `<option value="${esc(t.value)}">${esc(t.label)}</option>`).join("");
  sel.value = type;
  $(".fav-name", row).value = name;
  $("#favs").append(row);
  if ($("#favs").children.length >= 8) $("#add-fav").hidden = true;
}

function loadExample(input, run) {
  $("#favs").innerHTML = "";
  $("#add-fav").hidden = false;
  input.favorites.forEach((f) => addFav(f.name, f.type));
  $("#start").value = hhmm(input.start_time);
  if (run) submit();
}

function readInput() {
  const favorites = [...document.querySelectorAll(".fav")]
    .map((r) => ({ name: $(".fav-name", r).value.trim(), type: $(".fav-type", r).value }))
    .filter((f) => f.name);
  return {
    city: $("#city").value,
    favorites,
    start_time: $("#start").value || "10:00",
    max_stops: Math.min(8, Math.max(2, +$("#stops").value || 5)),
  };
}

function submit() {
  const input = readInput();
  if (!input.favorites.length) return;
  if (source) source.close();
  $("#go").disabled = true;
  $("#results").hidden = true;
  renderSteps({});
  $("#progress").hidden = false;
  $("#progress").scrollIntoView({ behavior: "smooth", block: "start" });

  const status = {};
  const result = { profile: null, candidates: [], itin: null, baseline: null };
  source = new EventSource("/api/plan?q=" + encodeURIComponent(JSON.stringify(input)));
  source.onmessage = (msg) => {
    const ev = JSON.parse(msg.data);
    if (ev.step === "error") {
      status.error = ev.message;
      finish();
    } else if (ev.step === "done") {
      result.baseline = ev.data.baseline_itinerary;
      finish();
      renderResults(result);
    } else {
      status[ev.step] = ev.message;
      if (ev.step === "taste") result.profile = ev.data;
      if (ev.step === "candidates") result.candidates = ev.data || [];
      if (ev.step === "plan" || ev.step === "critic") result.itin = ev.data;
      if (ev.step === "baseline") result.baseline = ev.data;
      if (ev.step === "critic" && result.itin) renderResults(result); // show Qloo side early
    }
    renderSteps(status, !META.has_llm);
  };
  source.onerror = () => {
    if (!source) return;
    status.error = status.error || "Connection lost. Please try again.";
    renderSteps(status);
    finish();
  };
  function finish() {
    if (source) source.close();
    source = null;
    $("#go").disabled = false;
  }
}

function renderSteps(status, noLlm) {
  const items = STEPS.map(([key, label]) => {
    const done = status[key];
    const skipped = key === "baseline" && noLlm && status.critic;
    const cls = done ? "done" : "pending";
    const icon = done ? "✓" : skipped ? "–" : "·";
    const text = done || (skipped ? "Baseline skipped: no LLM configured" : label);
    return `<li class="${cls}"><span class="dot">${icon}</span><span>${esc(text)}</span></li>`;
  });
  if (status.error) items.push(`<li class="err"><span class="dot">!</span><span>${esc(status.error)}</span></li>`);
  $("#steps").innerHTML = items.join("");
}

function renderResults({ profile, candidates, itin, baseline }) {
  if (!itin) return;
  $("#results").hidden = false;
  renderProfile(profile);
  const walk = itin.total_walk_minutes;
  $("#qloo-summary").textContent =
    `${itin.stops.length} stops · ${itin.total_km} km · about ${walk} min of walking · every stop comes from Qloo`;
  const issues = itin.check?.issues || [];
  $("#issues").innerHTML = issues.length
    ? `<div class="issues"><b>Route check:</b> ${issues.map(esc).join("; ")}</div>` : "";
  renderTimeline(itin.stops);
  renderMap(itin.stops, candidates);
  renderBaseline(baseline);
}

function renderProfile(p) {
  if (!p) return;
  const ents = p.entities.map((e) => `<span class="chip">${esc(e.name)}</span>`).join("");
  const miss = p.unresolved.map((n) => `<span class="chip grey strike" title="Not found in Qloo">${esc(n)}</span>`).join("");
  const tags = p.top_tags.slice(0, 10).map((t) => `<span class="chip grey">${esc(t.name)}</span>`).join("");
  $("#profile").innerHTML = `
    <h2>Your taste profile</h2>
    <div class="chips">${ents}${miss}</div>
    ${tags ? `<p class="muted" style="margin:10px 0 0">Shared themes Qloo found</p><div class="chips">${tags}</div>` : ""}`;
}

function renderTimeline(stops) {
  $("#timeline").innerHTML = stops.map((s, i) => {
    const p = s.place;
    const leg = i ? `<li class="leg">${s.walk_minutes_from_prev} min walk</li>` : "";
    const because = s.because_of.map((t) => `<span class="chip">♥ ${esc(t)}</span>`).join(" ");
    const vibe = (p.vibe || []).slice(0, 4).map((t) => `<span class="chip grey">${esc(t)}</span>`).join(" ");
    const aff = p.affinity != null ? ` · affinity ${p.affinity.toFixed(2)}` : "";
    const where = [p.neighborhood, p.address].filter(Boolean).map(esc).join(" · ");
    return `${leg}<li class="stop">
      <span class="num">${i + 1}</span>
      <div class="stop-body">
        <div class="stop-meta">${hhmm(s.arrive)}–${hhmm(s.leave)} · ${esc(p.category || "Place")}${aff}</div>
        <div class="stop-head">
          <div>
            <h3>${esc(p.name)}</h3>
            ${where ? `<div class="stop-meta">${where}</div>` : ""}
            ${p.description ? `<p class="desc">${esc(p.description)}</p>` : ""}
          </div>
          ${p.image_url ? `<img class="thumb" src="${esc(p.image_url)}" alt="" loading="lazy" onerror="this.remove()">` : ""}
        </div>
        ${s.why_it_fits ? `<div class="why"><b>Why it fits you</b>${esc(s.why_it_fits)}</div>` : ""}
        ${because || vibe ? `<div class="chips">${because} ${vibe}</div>` : ""}
        <div class="qid">Qloo ID ${esc(p.qloo_id)}</div>
      </div></li>`;
  }).join("");
}

function renderMap(stops, candidates) {
  if (!window.L) { $("#map").textContent = "Map unavailable."; return; }
  if (!map) {
    map = L.map("map", { scrollWheelZoom: false });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
  }
  if (mapLayer) mapLayer.remove();
  mapLayer = L.layerGroup().addTo(map);
  const chosen = new Set(stops.map((s) => s.place.qloo_id));
  const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
  candidates.filter((c) => !chosen.has(c.qloo_id)).forEach((c) =>
    L.circleMarker([c.lat, c.lon], { radius: 4, color: "#888", weight: 1, fillOpacity: .4 })
      .bindTooltip(`${esc(c.name)} (Qloo match, not on route)`).addTo(mapLayer));
  const pts = stops.map((s) => [s.place.lat, s.place.lon]);
  L.polyline(pts, { color: accent, weight: 4, opacity: .8, dashArray: "6 8" }).addTo(mapLayer);
  stops.forEach((s, i) => {
    const icon = L.divIcon({ className: "", html: `<div class="pin">${i + 1}</div>`, iconSize: [28, 28], iconAnchor: [14, 14] });
    L.marker([s.place.lat, s.place.lon], { icon }).bindTooltip(esc(s.place.name)).addTo(mapLayer);
  });
  if (pts.length) map.fitBounds(pts, { padding: [30, 30] });
  setTimeout(() => map.invalidateSize(), 50);
}

function renderBaseline(b) {
  if (!b) {
    $("#baseline").innerHTML = `<li class="empty">${META.has_llm ? "Waiting for the LLM-only plan…" : "No LLM configured, so there is no baseline to compare."}</li>`;
    return;
  }
  $("#baseline").innerHTML = b.stops.map((s) => `<li>
      <div class="stop-meta">${esc(s.time || "")}${s.category ? " · " + esc(s.category) : ""}</div>
      <h3>${esc(s.name)}<span class="unverified">unverified</span></h3>
      ${s.why ? `<div class="muted">${esc(s.why)}</div>` : ""}
    </li>`).join("");
}

function showCol(col) {
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.col === col);
    t.setAttribute("aria-selected", t.dataset.col === col);
  });
  document.querySelectorAll(".col").forEach((c) => c.classList.toggle("active", c.dataset.col === col));
  if (col === "qloo" && map) setTimeout(() => map.invalidateSize(), 50);
}

init();
