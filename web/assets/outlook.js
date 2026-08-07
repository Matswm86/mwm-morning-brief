/* Instrument Outlook — MNQ/NQ + MGC/Gold regime & prediction cards.
 * Listens for "brief:loaded" from app.js.
 *
 * Data contract per instrument (same schema as the existing NQ regime block):
 *   MNQ: brief.regime                       (legacy location, unchanged)
 *   MGC: brief.regimes.MGC || brief.regime_gold
 * Optional per-instrument `levels` object: { pdh, pdl, on_high, on_low }.
 * Falls back to raw.tier_a overnight_open/close + asia_range when absent.
 */
(function () {
  const INSTRUMENTS = [
    { code: "MNQ", name: "Nasdaq 100 · NQ", pick: b => (b.regimes && b.regimes.MNQ) || b.regime },
    { code: "MGC", name: "Gold · GC",       pick: b => (b.regimes && b.regimes.MGC) || b.regime_gold },
  ];

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, ch => (
    { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[ch]
  ));
  const fmtTime = (iso) => iso
    ? new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
    : "—";
  const fmtNum = (n) => (n == null || !Number.isFinite(Number(n)))
    ? "—"
    : Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 });

  function levelEntries(r) {
    const raw = (r.raw && r.raw.tier_a) || {};
    const lv = r.levels || {};
    const entries = [
      ["Prior day H", lv.pdh],
      ["Prior day L", lv.pdl],
      ["O/N high", lv.on_high],
      ["O/N low", lv.on_low],
      ["O/N open", raw.overnight_open],
      ["O/N close", raw.overnight_close],
      ["Asia range", raw.asia_range],
    ].filter(([, v]) => v != null && Number.isFinite(Number(v)));
    return entries.slice(0, 4); // keep the row tight; prefer explicit levels first
  }

  function sessionTiles(r, grid) {
    const sessions = r.sessions || {};
    const keys = ["LDN", "NY"].filter(k => sessions[k]);
    if (!keys.length && r.session) { sessions[r.session] = r; keys.push(r.session); }
    let latestKey = null, latestTs = 0;
    keys.forEach(k => {
      const t = Date.parse(sessions[k].generated_at || "");
      if (Number.isFinite(t) && t > latestTs) { latestTs = t; latestKey = k; }
    });
    grid.innerHTML = "";
    keys.forEach(k => {
      const s = sessions[k];
      const tier = (s.tier || "-").toUpperCase();
      const tierValid = ["A","B","C"].includes(tier);
      const tile = document.createElement("article");
      tile.className = "session-tile" + (k === latestKey ? " session-tile-latest" : "");
      if (tierValid) tile.dataset.tier = tier;
      tile.innerHTML = `
        <div class="session-tile-head">
          <span class="session-tile-name">${esc(k)}</span>
          <span class="session-tile-tier">${tierValid ? tier : "—"}</span>
        </div>
        <div class="session-tile-regime">${esc(s.regime || s.tier_caption || "—")}</div>
        <div class="session-tile-strategy">${esc(s.direction || "—")}</div>
        <div class="session-tile-time">${esc(fmtTime(s.generated_at))}</div>
      `;
      grid.appendChild(tile);
    });
  }

  function renderInstrument(inst, r) {
    const tpl = $("outlook-template");
    const node = tpl.content.cloneNode(true);
    const card = node.querySelector(".outlook-card");
    card.dataset.symbol = inst.code;

    node.querySelector(".outlook-sym-code").textContent = inst.code;
    node.querySelector(".outlook-sym-name").textContent = inst.name;

    if (!r) {
      card.classList.add("awaiting");
      node.querySelector(".outlook-regime-label").textContent = "awaiting feed";
      node.querySelector(".outlook-regime-score").textContent = "detector not live yet";
      node.querySelector(".outlook-levels").remove();
      node.querySelector(".outlook-sessions").remove();
      return node;
    }

    const tier = (r.tier || "-").toUpperCase();
    const badge = node.querySelector(".outlook-tier-badge");
    badge.textContent = ["A","B","C"].includes(tier) ? tier : "—";
    badge.dataset.tier = tier;

    node.querySelector(".outlook-regime-label").textContent = r.regime || "—";
    node.querySelector(".outlook-regime-score").textContent =
      r.score != null ? `score ${Number(r.score).toFixed(0)} / 100` : "—";

    node.querySelector(".outlook-dir-label").textContent = r.direction || "—";
    const conf = Math.round(Math.min(1, Math.max(0, r.direction_confidence || 0)) * 100);
    node.querySelector(".outlook-conf-fill").style.width = conf + "%";
    node.querySelector(".outlook-conf-caption").textContent = `confidence ${conf}%`;

    node.querySelector(".outlook-vol").textContent = r.volatility || "—";
    node.querySelector(".outlook-age").textContent = r.generated_at ? fmtTime(r.generated_at) : "—";

    const lvGrid = node.querySelector(".outlook-levels-grid");
    const entries = levelEntries(r);
    if (!entries.length) {
      node.querySelector(".outlook-levels").remove();
    } else {
      entries.forEach(([label, val]) => {
        const div = document.createElement("div");
        div.className = "outlook-level";
        div.innerHTML = `<span class="k">${esc(label)}</span><span class="num">${esc(fmtNum(val))}</span>`;
        lvGrid.appendChild(div);
      });
    }

    sessionTiles(r, node.querySelector(".outlook-sessions-grid"));
    return node;
  }

  function render(brief) {
    const grid = $("outlook-grid");
    if (!grid) return;
    grid.innerHTML = "";
    let newest = 0;
    INSTRUMENTS.forEach(inst => {
      const r = inst.pick(brief) || null;
      if (r && r.generated_at) {
        const t = Date.parse(r.generated_at);
        if (Number.isFinite(t) && t > newest) newest = t;
      }
      grid.appendChild(renderInstrument(inst, r));
    });
    if (newest) {
      $("outlook-updated").textContent =
        "Market Detector · updated " + fmtTime(new Date(newest).toISOString());
    }
  }

  document.addEventListener("brief:loaded", (e) => render(e.detail));
  if (window.__brief) render(window.__brief);
})();
