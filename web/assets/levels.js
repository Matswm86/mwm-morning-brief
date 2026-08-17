/*! Key levels in the live-chart footers — PDH / PDL / overnight high-low from
 *  brief.regimes.<SYM>.levels (bar-derived, fetchers/regime_derived.py). This is what
 *  survived the Instrument Outlook card (removed 2026-08-17): the levels are facts,
 *  the "long bias 25%" was not. */
(function () {
  const $ = (id) => document.getElementById(id);
  const fmt = (v) => (v == null || isNaN(v) ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 2 }));
  function render(brief) {
    const R = brief.regimes || {};
    for (const [sym, key] of [["mnq", "MNQ"], ["mgc", "MGC"]]) {
      const el = $("chart-levels-" + sym);
      if (!el) continue;
      const lv = (R[key] && R[key].levels) || null;
      if (!lv) { el.textContent = "levels —"; continue; }
      el.textContent = "PDH " + fmt(lv.pdh) + " · PDL " + fmt(lv.pdl) + " · ON " + fmt(lv.on_low) + "–" + fmt(lv.on_high);
      el.title = "prior-day high/low and overnight range, from 5-min bars";
    }
  }
  fetch("brief.json", { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject(r.status))).then(render).catch(() => {});
})();
