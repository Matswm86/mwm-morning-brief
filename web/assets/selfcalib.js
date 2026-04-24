/*! Self-calibration progress bar
 *  6-segment horizontal loading bar tracking % toward "selvkalibrerende
 *  forsknings- og handelsorganisme" — a self-calibrating research-and-trading
 *  organism with Claude as the disposable cognition substrate.
 *  Reads /selfcalib.json. Recomputes aggregate on every render.
 */
(function () {
  const $ = (id) => document.getElementById(id);

  const BADGE_CLASS = {
    live:    "sc-badge-live",
    thin:    "sc-badge-thin",
    shadow:  "sc-badge-shadow",
    manual:  "sc-badge-manual",
    "ad-hoc":  "sc-badge-adhoc",
    partial: "sc-badge-partial",
  };

  function pulseIfFresh(iso, days) {
    if (!iso) return false;
    const then = Date.parse(iso);
    if (isNaN(then)) return false;
    const ageDays = (Date.now() - then) / 86_400_000;
    return ageDays <= (days || 7);
  }

  function renderSegment(dim, totalWeight) {
    const seg = document.createElement("div");
    seg.className = "sc-seg";
    seg.style.flexGrow = String(dim.weight);
    seg.setAttribute("data-id", dim.id);
    seg.setAttribute("data-pct", String(dim.pct));
    if (pulseIfFresh(dim.last_shipped, 7)) seg.classList.add("sc-pulse");

    const fill = document.createElement("div");
    fill.className = "sc-seg-fill";
    fill.style.width = Math.max(0, Math.min(100, dim.pct)) + "%";

    const empty = document.createElement("div");
    empty.className = "sc-seg-empty";

    const foot = document.createElement("div");
    foot.className = "sc-seg-foot";
    const id = document.createElement("span");
    id.className = "sc-seg-id";
    id.textContent = dim.id;
    const pct = document.createElement("span");
    pct.className = "sc-seg-pct";
    pct.textContent = dim.pct + "%";
    foot.appendChild(id);
    foot.appendChild(pct);

    seg.appendChild(fill);
    seg.appendChild(empty);
    seg.appendChild(foot);

    const tip = renderTooltip(dim);
    seg.appendChild(tip);
    return seg;
  }

  function renderTooltip(dim) {
    const tip = document.createElement("div");
    tip.className = "sc-tip";

    const head = document.createElement("div");
    head.className = "sc-tip-head";
    const label = document.createElement("span");
    label.className = "sc-tip-label";
    label.textContent = dim.label;
    const badge = document.createElement("span");
    badge.className = "sc-tip-badge " + (BADGE_CLASS[dim.status_badge] || "");
    badge.textContent = dim.status_badge || "—";
    head.appendChild(label);
    head.appendChild(badge);

    const stat = document.createElement("div");
    stat.className = "sc-tip-stat";
    stat.innerHTML =
      `<span>${dim.pct}%</span><span class="sc-tip-meta">weight ${dim.weight}</span>`;

    tip.appendChild(head);
    tip.appendChild(stat);

    if (Array.isArray(dim.done) && dim.done.length) {
      tip.appendChild(sectionList("Done", dim.done, "sc-done"));
    }
    if (Array.isArray(dim.next) && dim.next.length) {
      tip.appendChild(sectionList("Next", dim.next, "sc-next"));
    }
    return tip;
  }

  function sectionList(title, items, cls) {
    const wrap = document.createElement("div");
    wrap.className = "sc-tip-section " + cls;
    const h = document.createElement("div");
    h.className = "sc-tip-sec-title";
    h.textContent = title;
    const ul = document.createElement("ul");
    items.forEach((txt) => {
      const li = document.createElement("li");
      li.textContent = txt;
      ul.appendChild(li);
    });
    wrap.appendChild(h);
    wrap.appendChild(ul);
    return wrap;
  }

  function aggregate(dims) {
    const totalW = dims.reduce((s, d) => s + (d.weight || 0), 0) || 1;
    const sumWP = dims.reduce((s, d) => s + (d.weight || 0) * (d.pct || 0), 0);
    return Math.round((sumWP / totalW) * 10) / 10;
  }

  function wireTooltipToggle() {
    // Mobile: tap to open / tap outside to close
    document.addEventListener("click", (e) => {
      const seg = e.target.closest(".sc-seg");
      document.querySelectorAll(".sc-seg.sc-open").forEach((el) => {
        if (el !== seg) el.classList.remove("sc-open");
      });
      if (seg) seg.classList.toggle("sc-open");
    });
  }

  async function load() {
    const host = $("selfcalib-section");
    if (!host) return;
    try {
      const res = await fetch("selfcalib.json?t=" + Date.now(), { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      const dims = Array.isArray(data.dimensions) ? data.dimensions : [];
      if (!dims.length) return;

      const pct = aggregate(dims);
      const aggEl = $("sc-aggregate");
      if (aggEl) aggEl.textContent = pct + "%";

      const goalEl = $("sc-goal");
      if (goalEl && data.target_state) goalEl.textContent = data.target_state;

      const subEl = $("sc-subtitle");
      if (subEl && data.subtitle) subEl.textContent = data.subtitle;

      const asOfEl = $("sc-asof");
      if (asOfEl && data.as_of) asOfEl.textContent = "as of " + data.as_of;

      const track = $("sc-track");
      if (track) {
        track.textContent = "";
        dims.forEach((d) => track.appendChild(renderSegment(d)));
      }

      host.hidden = false;
      wireTooltipToggle();
    } catch (e) {
      console.error("selfcalib load failed", e);
    }
  }

  document.addEventListener("DOMContentLoaded", load);
})();
