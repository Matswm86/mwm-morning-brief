/*! Today's Play — reads brief.json play (built by strategy.pick_play).
 *  One card per strategy with a RUN / SKIP / UNKNOWN / CLOSED verdict and the
 *  measured reason. Two honesty rules:
 *   1. Verdicts are baked for play.date_et. If the browser's ET date has moved
 *      on, the card greys itself and says it is stale — a leftover RUN from
 *      yesterday must never read as today's advice.
 *   2. UNKNOWN (calendar fetch failed) renders as loudly as SKIP. "We could
 *      not check the schedule" and "nothing scheduled" mean opposite things.
 */
(function () {
  const $ = (id) => document.getElementById(id);

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function etToday() {
    return new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
  }

  function render(brief) {
    const p = brief.play;
    const meta = $("play-meta");
    const grid = $("play-grid");
    if (!p || !(p.rows || []).length) {
      meta.textContent = p && p.error ? "builder error: " + p.error : "unavailable";
      return;
    }
    const stale = p.date_et !== etToday() && !p.weekend;
    meta.textContent = stale
      ? "STALE — built for " + p.date_et + ", refresh pending"
      : p.date_et + (p.weekend ? " · markets closed" : " · verdicts for this session");

    grid.innerHTML = p.rows
      .map((r) => {
        const v = String(r.verdict || "").toLowerCase();
        return (
          `<div class="play-card${stale ? " play-stale" : ""}">` +
          `<div class="play-card-top"><span class="play-name">${esc(r.strategy)}</span>` +
          `<span class="play-verdict play-${esc(v)}">${esc(r.verdict)}</span></div>` +
          `<div class="play-size">${esc(r.size || "")}</div>` +
          `<p class="play-why">${esc(r.why || "")}</p></div>`
        );
      })
      .join("");
    $("play-evidence").textContent = p.evidence || "";
  }

  fetch("brief.json", { cache: "no-store" })
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(render)
    .catch(() => { $("play-meta").textContent = "brief.json unavailable"; });
})();
