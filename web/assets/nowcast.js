/*! Intraday Regime Nowcast — MNQ + MGC side by side.
 *  Reads nowcast.json, either shape:
 *    { instruments: { MNQ: {...}, MGC: {...} }, generated_at }
 *    { ...single-instrument payload... }        ← treated as MNQ
 *  Each instrument payload is the existing producer schema (status, call,
 *  checkpoint, all_checkpoints, track, holdout_*, features).
 *
 *  Hero = the price path itself, extruded: a climbing zigzag, a falling one,
 *  an oscillation caged between two rails. Chart = the regime walk, rising
 *  through up-calls and falling through down-calls, with holdout uncertainty
 *  as a shaded envelope. Shape carries the message; colour only reinforces.
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const INSTRUMENTS = [
    { code: "MNQ", name: "Nasdaq 100 · NQ" },
    { code: "MGC", name: "Gold · GC" },
  ];

  const FACE = {
    TREND_UP:   { top: "#1a8f61", front: "#0b6b47", side: "#084f34" },
    TREND_DOWN: { top: "#d0492f", front: "#a83220", side: "#7d2416" },
    CHOP:       { top: "#6b6455", front: "#453f34", side: "#302b23" },
    UNKNOWN:    { top: "#c4bca8", front: "#a29a8a", side: "#847d6f" },
  };
  const INK = "#211d14";
  const PAPER = "#f2ecdf";
  const FAINT = "rgba(33, 29, 20, 0.42)";
  const HAIR = "rgba(33, 29, 20, 0.20)";

  const LABEL = { TREND_UP: "trending up", TREND_DOWN: "trending down", CHOP: "chopping", UNKNOWN: "no call" };
  const HEADLINE = { TREND_UP: "Trending up", TREND_DOWN: "Trending down", CHOP: "Chopping", UNKNOWN: "No call" };

  const pct = (x) => (x == null ? "—" : Math.round(x * 100) + "%");
  const clamp01 = (x) => Math.max(0, Math.min(1, x));
  const N = (v) => v.toFixed(2);

  /* Same convention as play.js: the session the play card verdicts are for. */
  function etToday() {
    return new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
  }
  const isPrevSession = (d) => !!(d && d.session && d.session < etToday());

  function precisionFor(call, h) {
    if (!h) return null;
    if (call === "CHOP") return h.chop_precision;
    if (call === "TREND_UP" || call === "TREND_DOWN") return h.trend_precision;
    return null;
  }

  /* ---- hero: the price path, extruded ----------------------------------- */
  const PATHS = {
    TREND_UP: [[10, 80], [23, 63], [32, 71], [45, 49], [55, 57], [69, 33], [79, 41], [94, 17]],
    TREND_DOWN: [[10, 17], [23, 41], [32, 33], [45, 57], [55, 49], [69, 71], [79, 63], [94, 80]],
    CHOP: [[10, 52], [27, 42], [44, 62], [61, 42], [78, 62], [94, 50]],
    UNKNOWN: [[10, 54], [94, 54]],
  };

  function heroBlock(state) {
    const f = FACE[state] || FACE.UNKNOWN;
    const W = 108, H = 96, DEPTH = 13, ux = 0.58, uy = -0.34;
    const pts = PATHS[state] || PATHS.UNKNOWN;
    const thin = state === "UNKNOWN";
    const sw = thin ? 2.6 : state === "CHOP" ? 5 : 6;
    const d = pts.map((p, i) => (i ? "L" : "M") + p[0] + " " + p[1]).join(" ");

    let rails = "";
    if (state === "CHOP") {
      [34, 70].forEach((y) => {
        rails += '<line x1="6" y1="' + y + '" x2="98" y2="' + y + '" stroke="' + INK +
          '" stroke-width="0.9" stroke-dasharray="4 3.5" opacity="0.4"/>';
      });
    }

    let body = "";
    for (let i = DEPTH; i >= 1; i--) {
      const c = i > DEPTH * 0.45 ? f.side : f.front;
      body += '<path d="' + d + '" fill="none" stroke="' + c + '" stroke-width="' + sw +
        '" stroke-linecap="round" stroke-linejoin="round" transform="translate(' +
        N(i * ux) + " " + N(i * uy) + ')"/>';
    }
    body += '<path d="' + d + '" fill="none" stroke="' + f.top + '" stroke-width="' + sw +
      '" stroke-linecap="round" stroke-linejoin="round" transform="translate(' +
      N(DEPTH * ux) + " " + N(DEPTH * uy) + ')"/>';

    return '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + (LABEL[state] || "no call") + '">' +
      '<ellipse cx="54" cy="90" rx="40" ry="4.5" fill="' + INK + '" opacity="0.12"/>' +
      rails + body + "</svg>";
  }

  /* ---- the session chart: the regime walk as a line ---------------------- */
  function walkChart(d, uid) {
    const cps = d.all_checkpoints || [];
    const byCp = {};
    (d.track || []).forEach((t) => { byCp[t.cp] = t.call; });
    const curve = d.holdout_curve || {};
    if (!cps.length) return { svg: "", nowPct: null };

    const W = 340, H = 132, padL = 9, padR = 9;
    const slot = (W - padL - padR) / cps.length;
    const MID = H / 2, STEP = 11, CLAMP = 4.4;

    let cum = 0;
    const pts = [];
    cps.forEach((cp, i) => {
      const call = byCp[cp];
      if (!call) return;
      if (call === "TREND_UP") cum = Math.min(CLAMP, cum + 1);
      else if (call === "TREND_DOWN") cum = Math.max(-CLAMP, cum - 1);
      pts.push({
        i, cp, call, prec: precisionFor(call, curve[cp]),
        x: padL + (i + 0.5) * slot, y: MID - cum * STEP,
      });
    });
    if (!pts.length) return { svg: "", nowPct: null };

    const first = { x: padL, y: MID };
    const path = [first].concat(pts);

    let grid = "";
    [-4, -2, 2, 4].forEach((k) => {
      const y = MID - k * STEP;
      if (y < 4 || y > H - 4) return;
      grid += '<line x1="' + padL + '" y1="' + N(y) + '" x2="' + (W - padR) + '" y2="' + N(y) +
        '" stroke="' + HAIR + '" stroke-width="0.6" stroke-dasharray="1.5 3"/>';
    });
    grid += '<line x1="' + padL + '" y1="' + MID + '" x2="' + (W - padR) + '" y2="' + MID +
      '" stroke="' + FAINT + '" stroke-width="0.9"/>';

    const band = path.map((p) => (p.prec == null ? 4.5 : 1.5 + (1 - p.prec) * 13));
    const up = path.map((p, k) => (k ? "L" : "M") + N(p.x) + " " + N(p.y - band[k])).join(" ");
    const dn = path.slice().reverse()
      .map((p, k) => "L" + N(p.x) + " " + N(p.y + band[band.length - 1 - k])).join(" ");
    const envelope = '<path d="' + up + " " + dn + ' Z" fill="' + INK + '" opacity="0.10"/>';

    const line = path.map((p, k) => (k ? "L" : "M") + N(p.x) + " " + N(p.y)).join(" ");
    const last = path[path.length - 1];
    const clipId = "nc-area-" + uid;
    const area =
      '<clipPath id="' + clipId + '"><path d="' + line + " L" + N(last.x) + " " + MID +
      " L" + N(first.x) + " " + MID + ' Z"/></clipPath>' +
      '<rect x="0" y="0" width="' + W + '" height="' + MID + '" fill="' + FACE.TREND_UP.front +
      '" opacity="0.34" clip-path="url(#' + clipId + ')"/>' +
      '<rect x="0" y="' + MID + '" width="' + W + '" height="' + (H - MID) + '" fill="' +
      FACE.TREND_DOWN.front + '" opacity="0.34" clip-path="url(#' + clipId + ')"/>';

    const stroke = '<path d="' + line + '" fill="none" stroke="' + INK +
      '" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>';

    let marks = "", nowPct = null;
    pts.forEach((p) => {
      let m;
      if (p.call === "CHOP") {
        m = '<rect x="' + N(p.x - 3.2) + '" y="' + N(p.y - 3.2) +
          '" width="6.4" height="6.4" fill="' + PAPER + '" stroke="' + INK + '" stroke-width="1.2"/>';
      } else if (p.call === "UNKNOWN") {
        m = '<circle cx="' + N(p.x) + '" cy="' + N(p.y) + '" r="2.6" fill="' + PAPER +
          '" stroke="' + FAINT + '" stroke-width="1.2"/>';
      } else {
        const c = p.call === "TREND_UP" ? FACE.TREND_UP.front : FACE.TREND_DOWN.front;
        m = '<circle cx="' + N(p.x) + '" cy="' + N(p.y) + '" r="2.8" fill="' + c + '"/>';
      }
      const tip = p.cp + " ET · " + LABEL[p.call] + (p.prec != null ? " · holdout " + pct(p.prec) : "");
      marks += '<g class="nc-pt"><title>' + tip + "</title>" + m +
        '<rect x="' + N(p.x - slot / 2) + '" y="0" width="' + N(slot) + '" height="' + H + '" fill="transparent"/></g>';
      if (p.cp === d.checkpoint) {
        nowPct = ((p.x - padL) / (W - padL - padR)) * 100;
        marks += '<line x1="' + N(p.x) + '" y1="4" x2="' + N(p.x) + '" y2="' + (H - 4) +
          '" stroke="' + INK + '" stroke-width="0.8" stroke-dasharray="2 2.5" opacity="0.6"/>' +
          '<circle cx="' + N(p.x) + '" cy="' + N(p.y) + '" r="5" fill="none" stroke="' + INK + '" stroke-width="1.3"/>';
      }
    });

    return {
      svg: '<svg class="nowcast-ribbon" viewBox="0 0 ' + W + " " + H +
        '" role="img" aria-label="Session regime walk: the line rises through up-calls and falls through down-calls">' +
        grid + area + envelope + stroke + marks + "</svg>",
      nowPct,
    };
  }

  function axis(d, nowPct) {
    const cps = d.all_checkpoints || [];
    if (!cps.length) return "";
    const ticks = ["10:00", "11:30", "13:00", "14:30", "15:30"].map((m) => {
      const i = cps.indexOf(m);
      if (i < 0) return "";
      const left = ((i + 0.5) / cps.length) * 100;
      if (nowPct != null && Math.abs(left - nowPct) < 6) return "";
      return '<span class="nowcast-tick" style="left:' + left + '%">' + m + "</span>";
    }).join("");
    const now = nowPct != null && d.checkpoint
      ? '<span class="nowcast-tick is-now" style="left:' + nowPct + '%">' + d.checkpoint + "</span>" : "";
    return ticks + now;
  }

  /* The blended 252-session precision hides a real year-over-year decay
     (MNQ TREND at 11:00: 0.702 in 2025, 0.613 in 2026). Show the recent year
     next to the blend rather than quoting the flattering average alone. */
  function recentYearFoot(d, own) {
    const ry = d.holdout_recent_year;
    const v = ry ? precisionFor(d.call, ry) : null;
    if (v == null) return (d.holdout_at_checkpoint || {}).n_sessions || "—";
    return ry.year + " " + pct(v) + (v < own - 0.02 ? " \u2193" : "");
  }

  function reliability(el, d) {
    const h = d.holdout_at_checkpoint || {};
    const own = precisionFor(d.call, h);
    if (d.status !== "LIVE" || own == null) {
      el.innerHTML =
        '<span class="nowcast-rel-fig">' + pct(h.unknown_rate) + "</span>" +
        '<span class="nowcast-rel-cap">abstain rate here</span>' +
        '<div class="nowcast-rel-bar"><div class="nowcast-rel-fill" style="width:' +
        (clamp01(h.unknown_rate || 0) * 100).toFixed(1) + '%"></div></div>' +
        '<div class="nowcast-rel-foot"><span>' + (h.n_sessions || "—") + " sessions</span><span>held out</span></div>";
      return;
    }
    el.innerHTML =
      '<span class="nowcast-rel-fig">' + pct(own) + "</span>" +
      '<span class="nowcast-rel-cap">holdout precision</span>' +
      '<div class="nowcast-rel-bar"><div class="nowcast-rel-fill" style="width:' +
      (clamp01(own) * 100).toFixed(1) + '%"></div>' +
      '<div class="nowcast-rel-base" style="left:50%" title="coin flip"></div></div>' +
      '<div class="nowcast-rel-foot"><span>' + recentYearFoot(d, own) + "</span><span>abstains " +
      pct(h.unknown_rate) + "</span></div>";
  }

  function meter(k, val, lo, hi, note, fmt) {
    const v = val == null ? null : clamp01((val - lo) / (hi - lo));
    const bar = '<svg class="nc-meter-svg" viewBox="0 0 100 20" preserveAspectRatio="none" aria-hidden="true">' +
      '<rect x="0" y="9" width="100" height="4" fill="' + HAIR + '"/>' +
      (v == null ? "" : '<rect x="0" y="7" width="' + (v * 100).toFixed(1) + '" height="6" fill="' + INK + '"/>') +
      '<line x1="50" y1="4" x2="50" y2="17" stroke="' + FAINT + '" stroke-width="0.8"/></svg>';
    return '<div class="nc-meter"><div class="nc-meter-head"><span class="nc-meter-k">' + k + "</span>" +
      '<span class="nc-meter-v">' + (val == null ? "—" : fmt(val)) + "</span></div>" + bar +
      '<div class="nc-meter-note">' + note + "</div></div>";
  }

  function renderPanel(inst, d) {
    const node = $("nowcast-template").content.cloneNode(true);
    const panel = node.querySelector(".nowcast-panel");
    const q = (s) => node.querySelector(s);
    panel.dataset.symbol = inst.code;
    q(".nowcast-panel-sym").textContent = inst.code;
    q(".nowcast-panel-name").textContent = inst.name;

    if (!d) {
      panel.classList.add("is-awaiting");
      q(".nowcast-panel-meta").textContent = "feed not live";
      q(".nowcast-headline").textContent = "No feed";
      q(".nowcast-arrow").innerHTML = heroBlock("UNKNOWN");
      q(".nowcast-body").textContent = "The nowcast producer is not publishing this instrument yet.";
      q(".nowcast-plotwrap").hidden = true;
      q(".nowcast-reliability").remove();
      q(".nowcast-meters").remove();
      return node;
    }

    const state = d.call || (d.status === "WAITING" ? "UNKNOWN" : d.status) || "UNKNOWN";
    const blockState = FACE[state] ? state : "UNKNOWN";

    const badge = q(".nowcast-badge");
    badge.textContent = d.call ? LABEL[d.call] : String(d.status || "no read").toLowerCase();
    badge.dataset.state = state;

    q(".nowcast-arrow").innerHTML = heroBlock(blockState);
    const headline = q(".nowcast-headline");
    headline.textContent = d.call ? HEADLINE[d.call] : d.status === "WAITING" ? "Pre-open" : "No read";
    headline.dataset.state = state;

    const prev = isPrevSession(d);
    if (prev) {
      panel.classList.add("is-prevsession");
      const tag = document.createElement("span");
      tag.className = "nowcast-yday";
      tag.textContent = "YESTERDAY'S SESSION";
      badge.parentNode.insertBefore(tag, badge);
    }
    q(".nowcast-panel-meta").textContent = d.status === "LIVE"
      ? (prev ? d.session + " final · " + d.checkpoint + " ET" : d.session + " · " + d.checkpoint + " ET")
      : String(d.status || "") + (d.grey_reason ? " · " + d.grey_reason : "");

    const plot = q(".nowcast-plot");
    if (d.status === "LIVE" || (d.track && d.track.length)) {
      const r = walkChart(d, inst.code);
      plot.innerHTML = r.svg + '<div class="nowcast-axis">' + axis(d, r.nowPct) + "</div>";
      plot.hidden = false;
      q(".nowcast-plotwrap").hidden = false;
    } else {
      plot.hidden = true;
      q(".nowcast-plotwrap").hidden = true;
    }

    reliability(q(".nowcast-reliability"), d);

    const f = d.features || {};
    q(".nowcast-meters").innerHTML =
      meter("Participation efficiency", f.part_eff, 0, 1, "how much of the travel became direction", (x) => x.toFixed(2)) +
      meter("Range vs. ADR", f.range_frac, 0, 2, "day's range against its average", (x) => x.toFixed(2) + "×");

    const h = d.holdout_at_checkpoint || {};
    const own = precisionFor(d.call, h);
    if (d.status !== "LIVE") {
      q(".nowcast-body").textContent = d.status === "WAITING"
        ? "First checkpoint at 10:00 ET. The walk builds as the session prints."
        : d.grey_reason || "No live read.";
    } else {
      const ry = d.holdout_recent_year || null;
      const ryOwn = ry ? precisionFor(d.call, ry) : null;
      q(".nowcast-body").innerHTML = own != null
        ? "<strong>" + pct(own) + "</strong> of calls like this one were right at " + d.checkpoint +
          " ET across " + (h.n_sessions || "—") + " held-out sessions." +
          (ryOwn != null
            ? " In " + ry.year + " alone (" + (ry.n_sessions || "—") + " sessions) it was <strong>" +
              pct(ryOwn) + "</strong>" +
              (ryOwn < own - 0.02 ? " — the edge has been decaying, read the lower number." : ".")
            : "")
        : "The model abstains on " + pct(h.unknown_rate) +
          " of sessions at this checkpoint — today's read is one of them.";
      const reg = prev && REGIMES && REGIMES[inst.code];
      q(".nowcast-note").textContent = prev
        ? "Final read from the " + d.session + " session — today's first call lands " +
          (d.earliest_valid || "10:45") + " ET." +
          (reg
            ? " Overnight detector now: " + (reg.tier_caption || reg.regime || "—") +
              (reg.volatility ? ", " + reg.volatility + " vol." : ".")
            : "")
        : d.before_stable_window
          ? "Provisional — precision only settles from " + d.stable_from + " ET." : "";
    }
    return node;
  }

  function render(data) {
    const insts = data.instruments || { MNQ: data };
    const pair = $("nowcast-pair");
    pair.innerHTML = "";
    INSTRUMENTS.forEach((inst) => pair.appendChild(renderPanel(inst, insts[inst.code] || null)));

    const stamp = data.generated_at || (insts.MNQ && insts.MNQ.generated_at);
    const anyPrev = INSTRUMENTS.some((i) => isPrevSession(insts[i.code]));
    const first = INSTRUMENTS.map((i) => insts[i.code]).find((d) => d && d.session);
    $("nowcast-meta").textContent = anyPrev && first
      ? "final read · " + first.session + " session · today from " + (first.earliest_valid || "10:45") + " ET"
      : stamp
        ? "as of " + new Date(stamp).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
        : "15-minute checkpoints · 252-session holdout";
  }

  let REGIMES = null; // Market Detector block from brief.json, for the reconcile line

  function load() {
    fetch("brief.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((b) => { if (b && b.regimes) REGIMES = b.regimes; })
      .catch(() => {})
      .then(() =>
        fetch("nowcast.json", { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
          .then(render)
          .catch(() => { $("nowcast-meta").textContent = "nowcast.json unavailable"; }));
  }
  load();
  setInterval(load, 60000);
})();
