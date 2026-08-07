/*! Intraday Regime Nowcast — reads nowcast.json (VPS producer every 15 min,
 *  research/regime-nowcast). Advisory only; UNKNOWN is an honest abstain.
 *
 *  Form: diverging state strip. Vertical DIRECTION is the primary encoding
 *  (up = TREND_UP, down = TREND_DOWN, midline block = CHOP, hairline tick =
 *  UNKNOWN), so identity never rests on hue. The two chromatic poles
 *  (#0f7a52 / #bb3a26) pass all six palette checks against the #f2ecdf paper
 *  surface; CHOP/UNKNOWN carry no hue at all.
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const UP = "#0f7a52";
  const DOWN = "#bb3a26";
  const INK = "#211d14";
  const FAINT = "rgba(33, 29, 20, 0.30)";

  const LABEL = {
    TREND_UP: "trending up",
    TREND_DOWN: "trending down",
    CHOP: "chopping",
    UNKNOWN: "no call",
  };

  function pct(x) { return x == null ? "—" : Math.round(x * 100) + "%"; }

  /* ---- strip: one slot per pre-registered checkpoint, 10:00 -> 15:30 ---- */
  function strip(d) {
    const cps = d.all_checkpoints || [];
    const byCp = {};
    (d.track || []).forEach((t) => { byCp[t.cp] = t.call; });
    const curve = d.holdout_curve || {};

    const W = 100, H = 50, MID = 22, PAD = 1;
    const slot = cps.length ? W / cps.length : W;
    const bw = Math.max(slot - 0.9, 0.6);
    const parts = [];

    // midline (recessive)
    parts.push(
      `<line x1="0" y1="${MID}" x2="${W}" y2="${MID}" stroke="${FAINT}" stroke-width="0.4"/>`
    );

    cps.forEach((cp, i) => {
      const x = i * slot + (slot - bw) / 2;
      const call = byCp[cp];
      const isNow = cp === d.checkpoint;
      const h = curve[cp] || {};
      const prec =
        call === "CHOP" ? h.chop_precision
        : (call === "TREND_UP" || call === "TREND_DOWN") ? h.trend_precision
        : null;
      let mark;
      if (call === "TREND_UP") {
        mark = `<rect x="${x}" y="${PAD}" width="${bw}" height="${MID - PAD - 1}" rx="0.8" fill="${UP}"/>`;
      } else if (call === "TREND_DOWN") {
        mark = `<rect x="${x}" y="${MID + 1}" width="${bw}" height="${MID - PAD - 1}" rx="0.8" fill="${DOWN}"/>`;
      } else if (call === "CHOP") {
        mark = `<rect x="${x}" y="${MID - 2.6}" width="${bw}" height="5.2" rx="0.8" fill="${INK}" opacity="0.55"/>`;
      } else if (call === "UNKNOWN") {
        mark = `<rect x="${x}" y="${MID - 0.5}" width="${bw}" height="1" fill="${FAINT}"/>`;
      } else {
        mark = `<rect x="${x + bw / 2 - 0.25}" y="${MID - 0.5}" width="0.5" height="1" fill="${FAINT}" opacity="0.5"/>`;
      }
      // "now" marker: a rule under the slot, not a box around it — the box
      // out-shouted the mark it was meant to point at.
      const cursor = isNow
        ? `<rect x="${x - 0.3}" y="${H - 2.6}" width="${bw + 0.6}" height="1.4" fill="${INK}"/>`
        : "";
      const tip = call
        ? `${cp} ET · ${LABEL[call]}${prec != null ? " · holdout " + pct(prec) : ""}`
        : `${cp} ET · not reached`;
      parts.push(
        `<g><title>${tip}</title>${mark}${cursor}` +
        `<rect x="${i * slot}" y="0" width="${slot}" height="${H}" fill="transparent"/></g>`
      );
    });

    return (
      `<svg class="nowcast-strip" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" ` +
      `role="img" aria-label="Session nowcast by 15-minute checkpoint">${parts.join("")}</svg>`
    );
  }

  function axis(d) {
    const cps = d.all_checkpoints || [];
    if (!cps.length) return "";
    const marks = ["10:00", "11:30", "13:00", "14:30", "15:30"];
    return marks
      .map((m) => {
        const i = cps.indexOf(m);
        if (i < 0) return "";
        const left = ((i + 0.5) / cps.length) * 100;
        return `<span class="nowcast-tick" style="left:${left}%">${m}</span>`;
      })
      .join("");
  }

  function render(d) {
    const call = d.call || (d.status === "WAITING" ? "PRE-OPEN" : "NO READ");
    const badge = $("nowcast-call");
    badge.textContent = d.call ? LABEL[d.call] : call.toLowerCase();
    badge.dataset.state = d.call || d.status;

    $("nowcast-meta").textContent =
      d.status === "LIVE"
        ? `${d.session} · ${d.checkpoint} ET`
        : `${d.status}${d.grey_reason ? " · " + d.grey_reason : ""}`;

    const plot = $("nowcast-plot");
    if (d.status === "LIVE" || (d.track && d.track.length)) {
      plot.innerHTML = strip(d) + `<div class="nowcast-axis">${axis(d)}</div>`;
      plot.hidden = false;
    } else {
      plot.hidden = true;
    }

    const h = d.holdout_at_checkpoint || {};
    const f = d.features || {};
    if (d.status !== "LIVE") {
      $("nowcast-body").textContent =
        d.status === "WAITING"
          ? "first checkpoint 10:00 ET"
          : d.grey_reason || "no live read";
      $("nowcast-note").textContent = "";
      return;
    }
    const own = d.call === "CHOP" ? h.chop_precision
      : (d.call === "TREND_UP" || d.call === "TREND_DOWN") ? h.trend_precision
      : null;
    $("nowcast-body").innerHTML =
      (own != null
        ? `<strong>${pct(own)}</strong> of calls like this were right at ${d.checkpoint} ET ` +
          `over ${h.n_sessions || "—"} held-out sessions`
        : `abstains on ${pct(h.unknown_rate)} of sessions at this checkpoint`) +
      ` · efficiency ${f.part_eff != null ? f.part_eff.toFixed(2) : "—"}` +
      ` · range ${f.range_frac != null ? f.range_frac.toFixed(2) : "—"}×ADR`;
    $("nowcast-note").textContent = d.before_stable_window
      ? `provisional — precision only settles from ${d.stable_from} ET`
      : "";
  }

  function load() {
    fetch("nowcast.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(render)
      .catch(() => { $("nowcast-meta").textContent = "nowcast.json unavailable"; });
  }
  load();
  setInterval(load, 60_000);
})();
