/* Morning Brief — hydrator
 * Reads brief.json, populates the masthead / news grid / colophon.
 * Account-specific panels (trades, cells, trade-guard, backtests) removed 2026-08.
 */

const BRIEF_URL = "brief.json";

const SECTION_ORDER = [
  ["market",         "Market",                   "M"],
  ["gold",           "Gold & Metals",            "Au"],
  ["geopolitics",    "Geopolitics",              "G"],
  ["tech_ai",        "Tech & AI · Claude · LLM", "⌬"],
  ["research",       "Research",                 "R"],
  ["consciousness",  "Consciousness & Resonance","~"],
  ["system",         "System Health",            "·"],
];

const $ = (id) => document.getElementById(id);

function fmtDateline(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { weekday: "long", year: "numeric", month: "long", day: "numeric" });
}

function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
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

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, ch => (
    { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[ch]
  ));
}

function renderCard(sectionKey, label, icon, data) {
  const tpl = $("card-template");
  const node = tpl.content.cloneNode(true);
  const art = node.querySelector(".card");
  art.dataset.section = sectionKey;

  node.querySelector(".card-icon").textContent = icon;
  node.querySelector(".card-title h2").textContent = label;

  const meta = node.querySelector(".card-meta");
  meta.textContent = (data && data.count != null) ? `${data.count} items` : "—";

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

  const src  = node.querySelector(".card-source");
  const time = node.querySelector(".card-time");
  src.textContent = (data && data.source) ? data.source : "";
  if (data && data.status) {
    const dot = document.createElement("span");
    dot.className = "card-status " + (data.status === "ok" ? "ok" : data.status === "warn" ? "warn" : "err");
    src.prepend(dot);
  }
  time.textContent = data && data.generated_at ? fmtTime(data.generated_at) : "";

  return node;
}

function renderGrid(brief) {
  const grid = $("grid");
  grid.innerHTML = "";
  const sections = brief.sections || {};
  SECTION_ORDER.forEach(([key, label, icon]) => {
    if (!sections[key] && key === "gold") return; // gold card appears once the feed lands
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
    const res = await fetch(BRIEF_URL, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const brief = await res.json();
    window.__brief = brief;
    renderGrid(brief);
    renderColophon(brief);
    renderFreshness(brief.generated_at);
    document.dispatchEvent(new CustomEvent("brief:loaded", { detail: brief }));
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
  setInterval(loadBrief, 10 * 60 * 1000); // auto-refresh every 10 minutes
});
