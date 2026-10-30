// TasteWalk front end: builds the request, streams agent steps over SSE, renders the comparison.
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const hhmm = (t) => (t || "").slice(0, 5);
const num = (x, d = 2) => (x == null ? "–" : Number(x).toFixed(d));
// Qloo lists some names library-style: "Word (The)" -> "The Word". Also normalise odd spaces.
const pretty = (n) => String(n ?? "").replace(/^(.*) \((The|Le|La|Les)\)$/, "$2 $1");
const clean = (t) => String(t ?? "").replace(/[\u00a0\u202f]/g, " ");

const STEPS = [
  ["taste", "Taste agent: matching your favorites in Qloo"],
  ["candidates", "Taste agent: finding places people with your taste love"],
  ["plan", "Planner: choosing stops and the walking order"],
  ["critic", "Critic: explaining why each stop fits"],
  ["baseline", "Baseline: asking an LLM the same question, without Qloo"],
  ["audit", "Fact-checker: looking up the LLM's places in Qloo"],
];
const EXAMPLE_ICONS = { indie: "🎸", design: "🪴", kculture: "🎬", streetwear: "👟" };

let META = null;
let map = null;
let mapLayer = null;
let source = null;
let pins = [];

async function init() {
  META = await fetch("/api/meta").then((r) => r.json());
  if (META.fake_data) showBanner("Demo data: Qloo is mocked with fictional places (TASTEWALK_FAKE_QLOO=1).");
  else if (!META.has_qloo) showBanner("Qloo key not configured: only cached example profiles will work.");

  $("#city").innerHTML = META.cities.map((c) => `<option>${esc(c)}</option>`).join("");
  $("#examples").innerHTML = META.examples.map((e) => `
    <button type="button" class="ex-card" data-ex="${esc(e.id)}">
      <span class="ex-icon" aria-hidden="true">${EXAMPLE_ICONS[e.id] || "✨"}</span>
      <span class="ex-label">${esc(e.label)}</span>
      <span class="ex-favs">${e.input.favorites.map((f) => esc(f.name)).join(" · ")}</span>
    </button>`).join("");
  $("#examples").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-ex]");
    if (!b) return;
    history.replaceState(null, "", `?example=${b.dataset.ex}`);
    loadExample(META.examples.find((e) => e.id === b.dataset.ex).input, true);
  });
  $("#add-fav").addEventListener("click", () => addFav());
  $("#favs").addEventListener("click", (ev) => {
    if (ev.target.closest(".fav-del") && $("#favs").children.length > 1) {
      ev.target.closest(".fav").remove();
      $("#add-fav").hidden = false;
    }
  });
  $("#form").addEventListener("submit", (ev) => { ev.preventDefault(); history.replaceState(null, "", "/"); submit(); });
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showCol(t.dataset.col)));
  $("#timeline").addEventListener("mouseover", (ev) => highlight(ev.target.closest(".stop")?.dataset.i));
  $("#timeline").addEventListener("mouseleave", () => highlight(null));

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
  $("#stops").value = input.max_stops;
  document.querySelectorAll(".ex-card").forEach((c) =>
    c.classList.toggle("active", META.examples.find((e) => e.id === c.dataset.ex)?.input === input && run));
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
    max_stops: Math.min(8, Math.max(2, +$("#stops").value || 6)),
  };
}

function submit() {
  const input = readInput();
  if (!input.favorites.length) return;
  if (source) source.close();
  $("#go").disabled = true;
  $("#results").hidden = true;
  const status = {};
  renderSteps(status, true);
  $("#progress").hidden = false;
  $("#progress").scrollIntoView({ behavior: "smooth", block: "start" });

  const result = { profile: null, candidates: [], itin: null, baseline: null, audit: null };
  source = new EventSource("/api/plan?q=" + encodeURIComponent(JSON.stringify(input)));
  source.onmessage = (msg) => {
    const ev = JSON.parse(msg.data);
    if (ev.step === "error") {
      status.error = ev.message;
      finish();
    } else if (ev.step === "done") {
      result.baseline = ev.data.baseline_itinerary;
      result.audit = ev.data.baseline_audit;
      status.done = true;
      finish();
      renderResults(result);
      const proof = $("#scorecard:not([hidden])") || $("#results");
      setTimeout(() => proof.scrollIntoView({ behavior: "smooth", block: "start" }), 150);
    } else {
      status[ev.step] = ev.message;
      if (ev.step === "taste") result.profile = ev.data;
      if (ev.step === "candidates") result.candidates = ev.data || [];
      if (ev.step === "plan" || ev.step === "critic") result.itin = ev.data;
      if (ev.step === "baseline") result.baseline = ev.data;
      if (ev.step === "audit") result.audit = ev.data;
      if (ev.step === "critic" && result.itin) renderResults(result); // show Qloo side early
    }
    renderSteps(status, !status.done && !status.error);
  };
  source.onerror = () => {
    if (!source) return;
    status.error = status.error || "Connection lost. Please try again.";
    renderSteps(status, false);
    finish();
  };
  function finish() {
    if (source) source.close();
    source = null;
    $("#go").disabled = false;
  }
}

function renderSteps(status, running) {
  let activeShown = false;
  const items = STEPS.map(([key, label]) => {
    const done = status[key];
    const skipped = !done && (status.done || status.error) ;
    let cls = "pending", icon = "·";
    if (done) { cls = "done"; icon = "✓"; }
    else if (skipped) { cls = "skipped"; icon = "–"; }
    else if (running && !activeShown) { cls = "active"; icon = ""; activeShown = true; }
    const text = done || (skipped ? `${label} (skipped)` : label);
    return `<li class="${cls}"><span class="dot">${icon}</span><span>${esc(text)}</span></li>`;
  });
  if (status.error) items.push(`<li class="err"><span class="dot">!</span><span>${esc(status.error)}</span></li>`);
  $("#steps").innerHTML = items.join("");
}

function renderResults({ profile, candidates, itin, baseline, audit }) {
  if (!itin) return;
  $("#results").hidden = false;
  renderProfile(profile);
  $("#qloo-summary").innerHTML =
    `<b>${itin.stops.length} stops</b> · <b>${itin.total_km} km</b> · about ${itin.total_walk_minutes} min on foot · every stop is a Qloo place`;
  const issues = itin.check?.issues || [];
  $("#issues").innerHTML = issues.length
    ? `<div class="issues"><b>Route check:</b> ${issues.map(esc).join("; ")}</div>` : "";
  renderTimeline(itin.stops);
  renderMap(itin.stops, candidates, audit);
  renderBaseline(baseline, audit);
  renderScorecard(itin, baseline, audit);
}

function renderProfile(p) {
  if (!p) return;
  const ents = p.entities.map((e) => `<span class="chip">${esc(e.name)}</span>`).join("");
  const miss = p.unresolved.map((n) => `<span class="chip grey strike" title="Not found in Qloo">${esc(n)}</span>`).join("");
  const tags = p.top_tags.slice(0, 10).map((t) => `<span class="chip grey">${esc(t.name)}</span>`).join("");
  $("#profile").innerHTML = `
    <div class="profile-row">
      <div><span class="kicker">Your taste in Qloo</span><div class="chips">${ents}${miss}</div></div>
      ${tags ? `<div><span class="kicker muted-k">Themes your favorites share</span><div class="chips">${tags}</div></div>` : ""}
    </div>`;
}

function renderScorecard(itin, baseline, audit) {
  const el = $("#scorecard");
  if (!baseline || !audit) { el.hidden = true; return; }
  const n = itin.stops.length;
  const withHours = itin.stops.filter((s) => s.place.hours).length;
  const t = audit.total;
  const llmPlaces = [
    `<b>${audit.found}</b> located in Qloo`,
    audit.in_osm ? `<b>${audit.in_osm}</b> exist on OpenStreetMap but not in Qloo` : "",
    audit.nowhere ? `<b class="bad">${audit.nowhere}</b> found in neither` : "",
  ].filter(Boolean).join(" · ");
  const unknownHours = audit.found - audit.hours_checked;
  const llmHours = !audit.found ? "Can't be checked: no stop is in Qloo"
    : !audit.hours_checked ? `Unknown: Qloo has no hours for the ${audit.found} located`
    : `${audit.hours_checked} checked${audit.closed ? `, <b class="bad">${audit.closed} closed</b> at the planned time` : ", none closed"}${unknownHours > 0 ? ` · ${unknownHours} unknown` : ""}`;
  const llmWalk = audit.found >= 2 && audit.walk_km > 0
    ? `Only between the located stops: ${audit.walk_km} km${audit.longest_leg_min > 25 ? `, one leg ${audit.longest_leg_min} min` : ""}`
    : "Can't be estimated: too few stops can be located";
  const rows = [
    ["The places", `<b class="good">${n} Qloo places</b>, each with a Qloo ID, address and coordinates`, llmPlaces],
    ["Opening hours", `Checked for ${withHours} of ${n} at the planned time`, llmHours],
    ["Walking", `<b>${itin.total_km} km</b> (estimated: straight line x 1.3)`, llmWalk],
    ["Why each stop", "Qloo says which of your favorites drove each pick", "The LLM's own words"],
  ];
  const head = audit.nowhere
    ? `The AI-only plan named <span class="bad">${audit.nowhere} of ${t}</span> places we couldn't find in Qloo or OpenStreetMap. Every TasteWalk stop is a real Qloo place.`
    : `Qloo could check <span class="bad">${audit.found} of ${t}</span> AI-only stops, and <span class="good">${n} of ${n}</span> TasteWalk stops.`;
  el.hidden = false;
  el.innerHTML = `
    <div class="sc-head">
      <span class="kicker">The proof</span>
      <h2>${head}</h2>
    </div>
    <table class="sc">
      <thead><tr><th></th><th class="q">With Qloo</th><th class="l">LLM only</th></tr></thead>
      <tbody>${rows.map(([k, q, l]) => `<tr><th scope="row">${k}</th><td class="q">${q}</td><td class="l">${l}</td></tr>`).join("")}</tbody>
    </table>
    <p class="fine">We look up each AI-named place in Qloo, then in OpenStreetMap. "Found in neither" doesn't prove a place is made up (both have gaps); it means nobody can confirm it, its hours or the walk before you go. Branches of chains are marked unclear and not judged.</p>`;
}

function renderTimeline(stops) {
  $("#timeline").innerHTML = stops.map((s, i) => {
    const p = s.place;
    const leg = i ? `<li class="leg">🚶 ${s.walk_minutes_from_prev} min walk</li>` : "";
    const because = s.because_of.map((t) => `<span class="chip">♥ ${esc(t)}</span>`).join(" ");
    const name = pretty(p.name);
    const vibe = (p.vibe || []).slice(0, 4).map((t) => `<span class="chip grey">${esc(t)}</span>`).join(" ");
    const where = [p.neighborhood, p.address].filter(Boolean).map(esc).join(" · ");
    const aff = p.affinity != null
      ? `<span class="aff" title="Qloo affinity: how strongly people with your taste favor this place"><i style="width:${Math.round(p.affinity * 100)}%"></i></span><span class="aff-n">${num(p.affinity)}</span>` : "";
    return `${leg}<li class="stop" data-i="${i}">
      <span class="num">${i + 1}</span>
      <div class="stop-body">
        <div class="stop-meta"><span class="time">${hhmm(s.arrive)}–${hhmm(s.leave)}</span> · ${esc(p.category || "Place")} ${aff}</div>
        <div class="stop-head">
          <div>
            <h3>${esc(name)}</h3>
            ${where ? `<div class="stop-meta">${where}</div>` : ""}
            ${p.description ? `<p class="desc">${esc(p.description)}</p>` : ""}
          </div>
          ${p.image_url ? `<img class="thumb" src="${esc(p.image_url)}" alt="${esc(name)}" loading="lazy" onerror="this.remove()">` : ""}
        </div>
        ${s.why_it_fits ? `<div class="why"><b>Why it fits you</b>${esc(clean(s.why_it_fits))}</div>` : ""}
        ${because || vibe ? `<div class="chips">${because} ${vibe}</div>` : ""}
        <div class="qid" title="Qloo entity ID ${esc(p.qloo_id)}">✓ Qloo place · ${esc(p.qloo_id.slice(0, 8))}…</div>
      </div></li>`;
  }).join("");
}

function renderMap(stops, candidates, audit) {
  if (!window.L) { $("#map").textContent = "Map unavailable."; return; }
  if (!map) {
    map = L.map("map", { scrollWheelZoom: false });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
  }
  if (mapLayer) mapLayer.remove();
  mapLayer = L.layerGroup().addTo(map);
  const chosen = new Set(stops.map((s) => s.place.qloo_id));
  const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
  candidates.filter((c) => !chosen.has(c.qloo_id)).forEach((c) =>
    L.circleMarker([c.lat, c.lon], { radius: 4, color: "#8a8178", weight: 1, fillOpacity: .35 })
      .bindTooltip(`${esc(c.name)} (Qloo match, not on route)`).addTo(mapLayer));
  const pts = stops.map((s) => [s.place.lat, s.place.lon]);
  L.polyline(pts, { color: accent, weight: 4, opacity: .85, dashArray: "6 8" }).addTo(mapLayer);

  const llmPts = (audit?.stops || []).filter((c) => c.found && c.lat != null && c.lon != null);
  llmPts.forEach((c) => {
    const icon = L.divIcon({ className: "", html: `<div class="pin llm">AI</div>`, iconSize: [26, 26], iconAnchor: [13, 13] });
    L.marker([c.lat, c.lon], { icon }).bindTooltip(`LLM only: ${esc(c.qloo_name)}`).addTo(mapLayer);
  });

  pins = stops.map((s, i) => {
    const icon = L.divIcon({ className: "", html: `<div class="pin" data-i="${i}">${i + 1}</div>`, iconSize: [30, 30], iconAnchor: [15, 15] });
    return L.marker([s.place.lat, s.place.lon], { icon }).bindTooltip(esc(pretty(s.place.name)))
      .on("click", () => document.querySelector(`.stop[data-i="${i}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" }))
      .on("mouseover", () => highlight(String(i))).on("mouseout", () => highlight(null))
      .addTo(mapLayer);
  });
  if (pts.length) map.fitBounds(pts, { padding: [30, 30] });
  setTimeout(() => map.invalidateSize(), 50);
}

function highlight(i) {
  document.querySelectorAll(".pin[data-i]").forEach((p) => p.classList.toggle("hot", p.dataset.i === i));
  document.querySelectorAll(".stop[data-i]").forEach((s) => s.classList.toggle("hot", s.dataset.i === i));
}

function renderBaseline(b, audit) {
  if (!b) {
    $("#baseline").innerHTML = `<li class="empty">${META.has_llm ? "The LLM-only plan is unavailable right now (provider limit). The Qloo plan is complete; the examples above always include it." : "No LLM configured, so there is no baseline to compare."}</li>`;
    return;
  }
  const checks = audit?.stops || [];
  $("#baseline").innerHTML = b.stops.map((s, i) => {
    const c = checks[i];
    let badges = "";
    if (c) {
      if (c.found && c.ambiguous) badges = `<span class="badge" title="Several branches in Qloo">◐ Chain: branch unclear</span>`;
      else if (c.found) badges = `<span class="badge ok" title="${esc(c.qloo_name)}${c.address ? " · " + esc(c.address) : ""}">✓ Located in Qloo</span>`;
      else if (c.in_osm) badges = `<span class="badge">🗺 On OpenStreetMap, not in Qloo</span>`;
      else if (c.in_osm === false) badges = `<span class="badge no">✗ Not found in Qloo or OpenStreetMap</span>`;
      else badges = `<span class="badge">? Not in Qloo</span>`;
      if (c.open === false) badges += `<span class="badge no">✗ Closed at this time</span>`;
      if (c.walk_minutes_from_prev != null) badges += `<span class="badge ${c.walk_minutes_from_prev > 25 ? "no" : ""}">🚶 ${c.walk_minutes_from_prev} min from previous</span>`;
    }
    return `<li>
      <div class="stop-meta">${esc(s.time || "")}${s.category ? " · " + esc(s.category) : ""}</div>
      <h3>${esc(s.name)}</h3>
      ${badges ? `<div class="badges">${badges}</div>` : ""}
      ${s.why ? `<div class="llm-why">${esc(s.why)}</div>` : ""}
    </li>`;
  }).join("");
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
