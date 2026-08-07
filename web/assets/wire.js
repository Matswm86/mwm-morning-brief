/*! Trading News · 24h — reads brief.json sections.trading_news.
 *  A wire feed, not a card: every line states WHICH instrument it bears on and
 *  WHY it qualified (the driver family), so relevance is never left implicit.
 */
(function () {
  const $ = (id) => document.getElementById(id);

  function hhmm(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function render(brief) {
    const s = (brief.sections || {}).trading_news;
    const meta = $("wire-meta");
    const list = $("wire-list");
    if (!s || !(s.items || []).length) {
      meta.textContent = s ? "no qualifying stories in the last 24h" : "unavailable";
      list.innerHTML = "";
      return;
    }
    const c = s.instrument_counts || {};
    meta.textContent =
      `${s.count} stories · MNQ ${(c.MNQ || 0) + (c.BOTH || 0)} · ` +
      `MGC ${(c.MGC || 0) + (c.BOTH || 0)} · ${s.source || ""}`;
    $("wire-lede").textContent = s.lede || "";

    list.innerHTML = s.items
      .map((it) => {
        const tag = it.instrument || "BOTH";
        const head = it.url
          ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.headline)}</a>`
          : esc(it.headline);
        return (
          `<li class="wire-item">` +
          `<span class="wire-tag" data-tag="${esc(tag)}">${esc(tag)}</span>` +
          `<span class="wire-text"><span class="wire-head-line">${head}</span>` +
          `<span class="wire-why">${esc(it.driver || "")}` +
          `${it.published ? " · " + hhmm(it.published) : ""}` +
          `${it.source ? " · " + esc(it.source) : ""}</span></span></li>`
        );
      })
      .join("");
  }

  fetch("brief.json", { cache: "no-store" })
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(render)
    .catch(() => { $("wire-meta").textContent = "brief.json unavailable"; });
})();
