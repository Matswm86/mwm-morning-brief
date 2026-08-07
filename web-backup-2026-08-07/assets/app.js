/* Morning Brief — hydrator
 * Reads brief.json, populates the masthead / hero / section cards.
 */

const BRIEF_URL = "brief.json";

const SECTION_ORDER = [
  ["market",         "Market",                   "M"],
  ["geopolitics",    "Geopolitics",              "G"],
  ["tech_ai",        "Tech & AI · Claude · LLM", "⌬"],
  ["research",       "Research",                 "R"],
  ["consciousness",  "Consciousness & Resonance","~"],
  ["system",         "System Health",            "·"],
];

const $ = (id) => document.getElementById(id);

// Display name per Market-Detector strategy_code — mirrors strategy.py
// NAME_BY_CODE. Code 3 was "LiqSweep iFVG"; LiqSweep was parked 2026-06-22 and
// the funded fleet now runs PDHR, so the detector's legacy code 3 surfaces PDHR.
const STRAT_NAME_BY_CODE = {
  0: "Stand down",
  1: "ORB · full",
  2: "ORB · reduced",
  3: "PDHR MNQ",
  4: "No trade",
};
const stratName = (code, fallback) =>
  STRAT_NAME_BY_CODE[code] || fallback || "—";

function fmtDateline(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const opts = { weekday: "long", year: "numeric", month: "long", day: "numeric" };
  return d.toLocaleDateString("en-GB", opts);
}

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function ageMinutes(iso) {
  if (!iso) return null;
  return Math.round((Date.now() - new Date(iso).getTime()) / 60000);
}

function renderFreshness(generatedAt) {
  const el = $("freshness");
  const m = ageMinutes(generatedAt);
  if (m === null) { el.textContent = "no data"; el.className = "pill error"; return; }
  let label, cls;
  if (m < 120) { label = `fresh · ${m}m`; cls = "fresh"; }
  else if (m < 1440) { label = `${Math.floor(m/60)}h old`; cls = "stale"; }
  else { label = `${Math.floor(m/1440)}d old`; cls = "error"; }
  el.textContent = label;
  el.className = "pill " + cls;
}

function renderHero(brief) {
  const r = brief.regime || {};
  const s = brief.strategy || {};
  const tier = (r.tier || "-").toUpperCase();
  const tierValid = ["A","B","C"].includes(tier);

  const card = $("tier-card");
  card.dataset.tier = tierValid ? tier : "";
  $("tier-letter").textContent = tierValid ? tier : "—";
  $("tier-caption").textContent = r.tier_caption || (tierValid ? "active" : "awaiting open");

  $("regime-session").textContent = r.session_label || "ORB session";

  $("strategy-name").textContent = s.name || "Stand down";
  $("strategy-sub").textContent  = s.subtitle || "no trade";
  $("strategy-why").textContent  = s.why || "No regime signal yet. Dashboard updates on the next ORB fire.";

  const n = Number.isFinite(s.contracts) ? s.contracts : 0;
  $("contract-num").textContent = n;
  $("contract-sym").textContent = s.symbol || "MNQ";
  $("contract-sub").textContent = n === 0 ? "stand down" : (n === 1 ? "single" : "ladder");

  $("strat-code").textContent  = r.strategy_code != null ? String(r.strategy_code) : "—";
  $("vol-state").textContent   = r.volatility || "—";
  $("dir-bias").textContent    = r.direction || "—";
  $("signal-age").textContent  = r.generated_at ? fmtTime(r.generated_at) : "—";

  renderSessionPair(r);
  renderAccuracy(r.calibration);
}

function renderSessionPair(regime) {
  const container = $("hero-session-pair");
  if (!container) return;
  const sessions = (regime && regime.sessions) || {};
  const keys = ["LDN", "NY"].filter(k => sessions[k]);
  if (keys.length === 0) {
    container.hidden = true;
    container.innerHTML = "";
    return;
  }
  container.hidden = false;

  let latestKey = null;
  let latestTs = 0;
  keys.forEach(k => {
    const t = Date.parse(sessions[k].generated_at || "");
    if (Number.isFinite(t) && t > latestTs) { latestTs = t; latestKey = k; }
  });

  container.innerHTML = "";
  keys.forEach(k => {
    const s = sessions[k];
    const tier = (s.tier || "-").toUpperCase();
    const tierValid = ["A", "B", "C"].includes(tier);
    const tile = document.createElement("article");
    tile.className = "session-tile" + (k === latestKey ? " session-tile-latest" : "");
    tile.dataset.session = k;
    if (tierValid) tile.dataset.tier = tier;

    const regimeLabel = s.regime || s.tier_caption || "—";
    const strat = stratName(s.strategy_code, s.strategy_label || s.strategy);
    const ts = s.generated_at ? fmtTime(s.generated_at) : "—";

    tile.innerHTML = `
      <div class="session-tile-head">
        <span class="session-tile-name">${escapeHtml(k)}</span>
        <span class="session-tile-tier">${tierValid ? tier : "—"}</span>
      </div>
      <div class="session-tile-regime">${escapeHtml(regimeLabel)}</div>
      <div class="session-tile-strategy">${escapeHtml(strat)}</div>
      <div class="session-tile-time">${escapeHtml(ts)}</div>
    `;
    container.appendChild(tile);
  });
}

function renderAccuracy(cal) {
  if (!cal || cal.status !== "ok" || !cal.n) {
    $("accuracy-n").textContent = "no data yet";
    $("acc-direction").textContent = "—";
    $("acc-strategy").textContent = "—";
    $("acc-sim").textContent = "—";
    return;
  }
  $("accuracy-n").textContent = `n=${cal.n} past predictions`;

  const dir = cal.direction || {};
  const strat = cal.strategy || {};
  const sim = cal.simulation || {};

  const dCell = $("acc-direction").parentElement;
  const sCell = $("acc-strategy").parentElement;

  $("acc-direction").textContent = dir.caption || "—";
  dCell.className = "accuracy-cell " + (dir.usable ? "usable" : (dir.lift < 0 ? "underperf" : "baseline"));

  $("acc-strategy").textContent = strat.caption || "—";
  sCell.className = "accuracy-cell " + (strat.usable ? "usable" : (strat.lift < 0 ? "underperf" : "baseline"));

  if (sim.avg_r != null && sim.n_trades) {
    const sign = sim.avg_r >= 0 ? "+" : "";
    $("acc-sim").textContent = `${sign}${sim.avg_r.toFixed(2)}R/tr · ${sim.n_trades} sim trades`;
  } else {
    $("acc-sim").textContent = "—";
  }
}

function renderCard(sectionKey, label, icon, data) {
  const tpl = $("card-template");
  const node = tpl.content.cloneNode(true);
  const art = node.querySelector(".card");
  art.dataset.section = sectionKey;

  node.querySelector(".card-icon").textContent = icon;
  node.querySelector(".card-title h2").textContent = label;

  const meta = node.querySelector(".card-meta");
  if (data && data.count != null) meta.textContent = `${data.count} items`;
  else meta.textContent = "—";

  const lede = node.querySelector(".card-lede");
  if (data && data.lede) lede.textContent = data.lede;
  else lede.remove();

  const ul = node.querySelector(".card-bullets");
  const items = (data && Array.isArray(data.bullets)) ? data.bullets : [];
  if (items.length === 0) {
    art.classList.add("empty");
  } else {
    items.slice(0, 6).forEach(b => {
      const li = document.createElement("li");
      if (typeof b === "string") {
        li.innerHTML = b;
      } else if (b && typeof b === "object") {
        const parts = [];
        if (b.headline) parts.push(`<strong>${escapeHtml(b.headline)}</strong>`);
        if (b.body)     parts.push(escapeHtml(b.body));
        let html = parts.join(" — ");
        if (b.url) html += ` <a href="${b.url}" target="_blank" rel="noopener">↗</a>`;
        li.innerHTML = html;
      }
      ul.appendChild(li);
    });
  }

  const foot = node.querySelector(".card-foot");
  const src  = node.querySelector(".card-source");
  const time = node.querySelector(".card-time");
  if (data && data.source) src.textContent = data.source;
  else src.textContent = "";
  if (data && data.status) {
    const dot = document.createElement("span");
    dot.className = "card-status " + (data.status === "ok" ? "ok" : data.status === "warn" ? "warn" : "err");
    src.prepend(dot);
  }
  time.textContent = data && data.generated_at ? fmtTime(data.generated_at) : "";

  return node;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, ch => (
    { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[ch]
  ));
}

function renderGrid(brief) {
  const grid = $("grid");
  grid.innerHTML = "";
  const sections = brief.sections || {};
  SECTION_ORDER.forEach(([key, label, icon]) => {
    grid.appendChild(renderCard(key, label, icon, sections[key]));
  });
}

function renderColophon(brief) {
  $("schema-tag").textContent = brief.schema || "morning_brief.v1";
  const n = Object.keys(brief.sections || {}).length;
  $("source-count").textContent = `${n} sections`;
  $("generated-at").textContent = "generated " + fmtTime(brief.generated_at);
  $("dateline").textContent = fmtDateline(brief.generated_at);
}

async function loadBrief() {
  const btn = $("refresh");
  btn.classList.add("spinning");
  try {
    const res = await fetch(BRIEF_URL + "?t=" + Date.now(), { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const brief = await res.json();
    renderHero(brief);
    renderGrid(brief);
    renderColophon(brief);
    renderFreshness(brief.generated_at);
  } catch (e) {
    $("freshness").textContent = "load failed";
    $("freshness").className = "pill error";
    console.error("brief load failed:", e);
    const grid = $("grid");
    grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)">
      <p>Could not load <code>brief.json</code>.</p>
      <p style="font-size:13px;margin-top:8px">${escapeHtml(e.message)}</p>
    </div>`;
  } finally {
    setTimeout(() => btn.classList.remove("spinning"), 400);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadBrief();
  $("refresh").addEventListener("click", loadBrief);
  // auto-refresh every 10 minutes while tab is open
  setInterval(loadBrief, 10 * 60 * 1000);
});
