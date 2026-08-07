/*! Scheduled US macro — reads brief.json sections.event_calendar.
 *  The Regime block's middle tier: what is on the calendar between the
 *  structural backdrop and today's intraday read.
 *
 *  Two rules this file exists to honour:
 *   1. The countdown is computed in the browser from when_utc, not baked in by
 *      the builder, so a brief.json that is six hours old still says the truth.
 *   2. A failed scrape must NOT render as an empty timeline. "Nothing
 *      scheduled" and "we could not find out" look identical and mean opposite
 *      things; only one of them is safe to trade around.
 */
(function () {
  const $ = (id) => document.getElementById(id);

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function countdown(iso) {
    const ms = new Date(iso).getTime() - Date.now();
    if (isNaN(ms)) return "";
    if (ms < 0) return "now";
    const h = Math.floor(ms / 3600000);
    const d = Math.floor(h / 24);
    if (d >= 1) return d + "d " + (h % 24) + "h";
    if (h >= 1) return h + "h " + Math.floor((ms % 3600000) / 60000) + "m";
    return Math.max(1, Math.round(ms / 60000)) + "m";
  }

  function fail(msg) {
    $("events-meta").textContent = msg;
    $("events-next").textContent = "next —";
    $("events-next").dataset.flag = "red";
    $("events-list").innerHTML =
      '<li class="events-fail">Schedule unknown — this is a fetch failure, ' +
      "not an empty calendar. Assume releases are scheduled and check " +
      '<a href="https://tradingeconomics.com/calendar" target="_blank" ' +
      'rel="noopener">tradingeconomics.com/calendar</a> before sizing.</li>';
  }

  function render(brief) {
    const s = (brief.sections || {}).event_calendar;
    if (!s) return fail("event_calendar section missing");
    if (s.status === "err") return fail(s.error || "calendar fetch failed");

    const items = s.items || [];
    const fomc = s.fomc || {};
    $("events-source").textContent = s.source || "—";
    $("events-fomc").textContent = fomc.next
      ? "next FOMC " + fomc.next.start + " – " + fomc.next.end.slice(5) +
        " · " + (fomc.source || "")
      : "FOMC schedule unavailable";

    if (!items.length) {
      $("events-meta").textContent =
        "no qualifying US releases in the next " + (s.horizon_days || 7) + " days";
      $("events-next").textContent = "next —";
      $("events-list").innerHTML = "";
      return;
    }

    const first = items[0];
    $("events-meta").textContent =
      items.length + " releases · " + (s.horizon_days || 7) + "d · times ET and Oslo";
    const badge = $("events-next");
    badge.textContent = "next: " + first.family + " in " + countdown(first.when_utc);
    badge.dataset.flag = first.impact === "HIGH" ? "red" : "yellow";

    let lastDay = null;
    $("events-list").innerHTML = items
      .map((it) => {
        const newDay = it.day_et !== lastDay;
        lastDay = it.day_et;
        return (
          (newDay ? `<li class="events-day">${esc(it.day_et)}</li>` : "") +
          `<li class="events-item" data-impact="${esc(it.impact)}">` +
          `<span class="events-time"><b>${esc(it.time_et)}</b> ET` +
          `<span class="events-oslo">${esc(it.time_oslo)} Oslo</span></span>` +
          `<span class="wire-tag" data-tag="${esc(it.instrument)}">${esc(it.instrument)}</span>` +
          `<span class="events-text"><span class="events-name">${esc(it.family)}` +
          `${it.period ? ` <span class="events-period">${esc(it.period)}</span>` : ""}</span>` +
          `<span class="events-why">${esc(it.driver)} · ${esc(it.impact.toLowerCase())} impact` +
          `${it.forecast ? " · cons " + esc(it.forecast) : ""}` +
          `${it.previous ? " · prev " + esc(it.previous) : ""}` +
          ` · in ${countdown(it.when_utc)}</span></span></li>`
        );
      })
      .join("");
  }

  fetch("brief.json", { cache: "no-store" })
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(render)
    .catch(() => fail("brief.json unavailable"));
})();
