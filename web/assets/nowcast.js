/*! Intraday Regime Nowcast — reads nowcast.json (written every 15 min by the
 *  VPS producer, research/regime-nowcast). Advisory only; UNKNOWN is honest. */
(function () {
  const $ = (id) => document.getElementById(id);
  const FLAG = {
    TREND_UP: "on", TREND_DOWN: "off", CHOP: "warn", UNKNOWN: "unknown",
  };

  function pct(x) { return x == null ? "—" : (x * 100).toFixed(0) + "%"; }

  function render(d) {
    const call = d.call || (d.status === "WAITING" ? "PRE-OPEN" : "GREY");
    const badge = $("nowcast-call");
    badge.textContent = call;
    badge.dataset.flag = FLAG[d.call] || "unknown";

    const cp = d.checkpoint || "—";
    $("nowcast-meta").textContent =
      d.status === "LIVE"
        ? `${d.session} · ${cp} ET · ${d.contract || ""}`
        : `${d.status}${d.grey_reason ? " · " + d.grey_reason : ""}`;

    if (d.status !== "LIVE") {
      $("nowcast-body").textContent =
        d.status === "WAITING"
          ? "before first checkpoint (10:00 ET)"
          : (d.grey_reason || "no live read");
      return;
    }
    const h = d.holdout_at_checkpoint || {};
    const f = d.features || {};
    const prov = d.before_stable_window
      ? " · PROVISIONAL (stable from " + d.stable_from + " ET)"
      : "";
    $("nowcast-body").textContent =
      `holdout @${cp}: trend ${pct(h.trend_precision)} · chop ${pct(h.chop_precision)}` +
      ` · abstain ${pct(h.unknown_rate)} (n=${h.n_sessions || "—"})` +
      ` · eff ${f.part_eff != null ? f.part_eff.toFixed(2) : "—"}` +
      ` · range ${f.range_frac != null ? f.range_frac.toFixed(2) : "—"}×ADR` + prov;
  }

  function load() {
    fetch("nowcast.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(render)
      .catch(() => {
        $("nowcast-meta").textContent = "nowcast.json unavailable";
      });
  }
  load();
  setInterval(load, 60_000);
})();
