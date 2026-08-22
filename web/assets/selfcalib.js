/*! Self-calibration progress — back-page gag strip, third printing.
 *  Reads brief._selfcalib via "brief:loaded". Three panels, one joke,
 *  all true: it fires every week (top dimension), the doctor reads the
 *  real chart (every bar is a dimension, height = pct), and the heaviest
 *  organ is the least grown. Hover the chart for evidence.
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const INK = "#251e10";
  const RED = "#8e2f1e";
  const PAPER = "#f2ecdf";

  let seed = 7;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const N = (x) => x.toFixed(1);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function wob(x0, y0, x1, y1, segs) {
    segs = segs || 4;
    let d = "M" + N(x0) + " " + N(y0);
    for (let i = 1; i <= segs; i++) {
      const t = i / segs;
      const jx = i === segs ? 0 : (rnd() - 0.5) * 2.2;
      const jy = i === segs ? 0 : (rnd() - 0.5) * 2.2;
      d += " L" + N(x0 + (x1 - x0) * t + jx) + " " + N(y0 + (y1 - y0) * t + jy);
    }
    return d;
  }

  function frame(w, h) {
    const m = 5;
    return '<path d="' + wob(m, m, w - m, m, 6) + " " + wob(w - m, m, w - m, h - m, 5).replace("M", "L") +
      " " + wob(w - m, h - m, m, h - m, 6).replace("M", "L") + " " + wob(m, h - m, m, m, 5).replace("M", "L") +
      ' Z" fill="none" stroke="' + INK + '" stroke-width="1.6" stroke-linejoin="round"/>';
  }

  /* one pattern id per panel — three inline SVGs share the page's DOM, so a
   * repeated id="ht" would make every panel resolve against the first defs */
  const DEFS = (pid) =>
    '<defs><pattern id="ht-' + pid + '" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(20)">' +
    '<circle cx="2" cy="2" r="1" fill="' + INK + '" opacity="0.14"/></pattern></defs>';

  const ground = (w, y) => '<path d="' + wob(8, y, w - 8, y, 7) + '" fill="none" stroke="' + INK + '" stroke-width="1.2"/>';

  function organism(cx, cy, r, pctGrown, mood, jump) {
    let out = "";
    for (let i = 4; i >= 1; i--) {
      const rr = (r * i) / 4;
      const grown = i / 4 <= pctGrown + 0.13;
      out += '<ellipse cx="' + cx + '" cy="' + cy + '" rx="' + N(rr * (1 + (rnd() - 0.5) * 0.06)) +
        '" ry="' + N(rr * (1 + (rnd() - 0.5) * 0.06)) + '" fill="' + (i === 4 ? PAPER : "none") +
        '" stroke="' + INK + '" stroke-width="' + (i === 4 ? 1.6 : 1) + '"' +
        (grown ? "" : ' stroke-dasharray="2.5 3" opacity="0.5"') + "/>";
    }
    const ex = r * 0.22, ey = cy - r * 0.1;
    out += '<circle cx="' + N(cx - ex) + '" cy="' + N(ey) + '" r="1.8" fill="' + INK + '"/>' +
           '<circle cx="' + N(cx + ex) + '" cy="' + N(ey) + '" r="1.8" fill="' + INK + '"/>';
    if (mood === "sad")
      out += '<path d="M' + N(cx - 6) + " " + N(cy + r * 0.3) + ' q6 -5 12 0" fill="none" stroke="' + INK + '" stroke-width="1.3" stroke-linecap="round"/>' +
             '<path d="M' + N(cx + r * 0.78) + " " + N(cy - r * 0.85) + ' q3 2 1.6 6" fill="none" stroke="' + INK + '" stroke-width="1.2" stroke-linecap="round"/>';
    else
      out += '<path d="M' + N(cx - 6) + " " + N(cy + r * 0.18) + ' q6 6 12 0" fill="none" stroke="' + INK + '" stroke-width="1.3" stroke-linecap="round"/>';
    const up = jump ? -14 : mood === "sad" ? 10 : -8;
    out += '<path d="' + wob(cx - r, cy + 2, cx - r - 10, cy + up, 2) + '" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>' +
           '<path d="' + wob(cx + r, cy + 2, cx + r + 10, cy + up, 2) + '" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>';
    if (jump)
      out += '<path d="' + wob(cx - r * 0.4, cy + r, cx - r * 0.55, cy + r + 6, 2) + '" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>' +
             '<path d="' + wob(cx + r * 0.4, cy + r, cx + r * 0.6, cy + r + 7, 2) + '" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>' +
             '<path d="M' + N(cx - 14) + " " + N(cy + r + 13) + ' h9 M' + N(cx + 6) + " " + N(cy + r + 14) + ' h9" stroke="' + INK + '" stroke-width="1.2"/>';
    else
      out += '<path d="' + wob(cx - r * 0.4, cy + r, cx - r * 0.45, cy + r + 9, 2) + '" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>' +
             '<path d="' + wob(cx + r * 0.4, cy + r, cx + r * 0.45, cy + r + 9, 2) + '" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>' +
             '<path d="M' + N(cx - r * 0.45 - 4) + " " + N(cy + r + 9) + ' h9" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>' +
             '<path d="M' + N(cx + r * 0.45 - 4) + " " + N(cy + r + 9) + ' h9" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>';
    return out;
  }

  function doctor(x, y, arm) {
    let o = "";
    o += '<circle cx="' + x + '" cy="' + (y - 40) + '" r="9" fill="' + PAPER + '" stroke="' + INK + '" stroke-width="1.4"/>';
    o += '<circle cx="' + x + '" cy="' + (y - 47) + '" r="3.6" fill="none" stroke="' + INK + '" stroke-width="1.2"/>';
    o += '<circle cx="' + (x - 3) + '" cy="' + (y - 41) + '" r="1.3" fill="' + INK + '"/>' +
         '<circle cx="' + (x + 3) + '" cy="' + (y - 41) + '" r="1.3" fill="' + INK + '"/>' +
         '<path d="M' + (x - 2) + " " + (y - 36) + ' h5" stroke="' + INK + '" stroke-width="1.2"/>';
    o += '<path d="M' + (x - 10) + " " + (y - 31) + " L" + (x - 13) + " " + y + " M" + (x + 10) + " " + (y - 31) +
         " L" + (x + 13) + " " + y + " M" + (x - 10) + " " + (y - 31) + ' h20" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linejoin="round"/>';
    o += arm === "point"
      ? '<path d="M' + (x - 10) + " " + (y - 26) + ' q-12 -2 -20 -10" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>'
      : '<path d="M' + (x - 10) + " " + (y - 26) + ' q-9 3 -10 12" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>';
    o += '<path d="M' + (x + 10) + " " + (y - 26) + ' q8 4 8 12" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>';
    o += '<path d="M' + (x - 5) + " " + y + " v7 M" + (x + 5) + " " + y + " v7 M" + (x - 9) + " " + (y + 7) + " h8 M" + (x + 1) + " " + (y + 7) + ' h8" stroke="' + INK + '" stroke-width="1.3"/>';
    return o;
  }

  function bubble(cx, cy, lines, tailX, tailY, fs) {
    fs = fs || 13;
    const maxLen = lines.reduce((a, l) => Math.max(a, l.length), 1);
    const rx = Math.max(34, maxLen * fs * 0.27 + 12);
    const ry = (lines.length * (fs + 2)) / 2 + 9;
    let out = '<ellipse cx="' + cx + '" cy="' + cy + '" rx="' + N(rx) + '" ry="' + N(ry) +
      '" fill="' + PAPER + '" stroke="' + INK + '" stroke-width="1.3"/>';
    const dir = tailX < cx ? -1 : 1;
    out += '<path d="M' + N(cx + dir * rx * 0.2) + " " + N(cy + ry * 0.86) + " L" + N(tailX) + " " + N(tailY) +
      " L" + N(cx + dir * rx * 0.45) + " " + N(cy + ry * 0.78) + ' Z" fill="' + PAPER + '" stroke="' + INK +
      '" stroke-width="1.3" stroke-linejoin="round"/>' +
      '<path d="M' + N(cx + dir * rx * 0.22) + " " + N(cy + ry * 0.82) + " L" + N(cx + dir * rx * 0.42) + " " + N(cy + ry * 0.75) +
      '" stroke="' + PAPER + '" stroke-width="3"/>';
    const y0 = cy - ((lines.length - 1) / 2) * (fs + 2);
    lines.forEach((ln, i) => {
      out += '<text x="' + cx + '" y="' + N(y0 + i * (fs + 2) + fs * 0.34) +
        '" text-anchor="middle" class="comic-hand" font-size="' + fs + '">' + esc(ln) + "</text>";
    });
    return out;
  }

  function dimTip(d) {
    return esc(d.id + " — " + (d.label || "") + "\n" + Math.round(d.pct || 0) + "% grown · weight " + (d.weight || 0) +
      "\n" + (d.done_n || 0) + " shipped · " + (d.next_n || 0) + " next");
  }

  const panel = (w, h, body, pid) =>
    '<figure class="comic-panel"><svg viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="xMidYMid meet">' +
    DEFS(pid) + body.replace(/url\(#ht\)/g, "url(#ht-" + pid + ")") + frame(w, h) + "</svg></figure>";

  function render(sc) {
    const section = $("selfcalib-section");
    if (!sc || !Array.isArray(sc.dimensions) || !sc.dimensions.length) {
      section.hidden = true;
      return;
    }
    section.hidden = false;
    seed = 7;

    const dims = sc.dimensions;
    const totalW = dims.reduce((a, d) => a + (d.weight || 0), 0) || 1;
    const agg = sc.aggregate_pct != null
      ? sc.aggregate_pct
      : dims.reduce((a, d) => a + (d.pct || 0) * (d.weight || 0), 0) / totalW;
    // the joke's target: the dimension carrying the most weight × remaining growth
    const gap = dims.slice().sort((a, b) =>
      (b.weight || 0) * (100 - (b.pct || 0)) - (a.weight || 0) * (100 - (a.pct || 0)))[0];
    const W = 300, H = 200;

    /* 1 — pride */
    let b1 = '<rect x="7" y="7" width="' + (W - 14) + '" height="70" fill="url(#ht)"/>';
    b1 += ground(W, 168);
    b1 += organism(196, 128, 27, agg / 100, "happy", true);
    b1 += '<path d="M160 158 q4 -3 8 0 M222 160 q4 -3 8 0" fill="none" stroke="' + INK + '" stroke-width="0.9" opacity="0.6"/>';
    b1 += '<g><circle cx="66" cy="150" r="14" fill="' + PAPER + '" stroke="' + INK + '" stroke-width="1.5"/>' +
      '<circle cx="58" cy="136" r="4" fill="none" stroke="' + INK + '" stroke-width="1.3"/>' +
      '<circle cx="74" cy="136" r="4" fill="none" stroke="' + INK + '" stroke-width="1.3"/>' +
      '<path d="M66 150 v-8 M66 150 l6 3" stroke="' + INK + '" stroke-width="1.3" stroke-linecap="round"/>' +
      '<path d="M58 164 l-4 4 M74 164 l4 4" stroke="' + INK + '" stroke-width="1.3"/></g>' +
      '<text x="66" y="120" text-anchor="middle" class="comic-hand" font-size="12" fill="' + RED + '">RRRING!</text>';
    b1 += bubble(172, 48, ["I FIRE EVERY WEEK!"], 184, 90);

    /* 2 — the chart */
    let b2 = '<rect x="7" y="7" width="' + (W - 14) + '" height="40" fill="url(#ht)"/>';
    b2 += ground(W, 168);
    const cx0 = 40, cy1 = 150, ch = 84;
    b2 += '<path d="' + wob(cx0 - 8, cy1, cx0 + 172, cy1, 5) + " " + wob(cx0 - 8, cy1, cx0 - 8, cy1 - ch, 4) + '" fill="none" stroke="' + INK + '" stroke-width="1.2"/>';
    let bx = cx0;
    dims.forEach((d) => {
      const bw = 8 + ((d.weight || 0) / totalW) * 46;
      const pct = Math.min(100, Math.max(0, d.pct || 0)) / 100;
      const bh = pct * (ch - 10);
      const isGap = d === gap;
      b2 += '<g class="comic-hit"><title>' + dimTip(d) + "</title>" +
        '<rect x="' + N(bx) + '" y="' + N(cy1 - bh) + '" width="' + N(bw) + '" height="' + N(bh) +
        '" fill="url(#ht)" stroke="' + (isGap ? RED : INK) + '" stroke-width="' + (isGap ? 1.7 : 1.2) + '"/>' +
        '<text x="' + N(bx + bw / 2) + '" y="' + (cy1 + 13) + '" text-anchor="middle" class="comic-label">' + esc(d.id) + "</text></g>";
      if (isGap) b2 += '<ellipse cx="' + N(bx + bw / 2) + '" cy="' + N(cy1 - bh / 2) + '" rx="' + N(bw / 2 + 8) + '" ry="' + N(bh / 2 + 10) + '" fill="none" stroke="' + RED + '" stroke-width="1.4" transform="rotate(-4 ' + N(bx + bw / 2) + " " + N(cy1 - bh / 2) + ')"/>';
      bx += bw + 6;
    });
    b2 += doctor(252, 148, "point");
    b2 += bubble(226, 38, [gap.id + ": " + Math.round(gap.pct || 0) + "%."], 244, 96);

    /* 3 — the punchline */
    let b3 = '<rect x="7" y="7" width="' + (W - 14) + '" height="40" fill="url(#ht)"/>';
    b3 += ground(W, 168);
    b3 += organism(90, 138, 24, agg / 100, "sad");
    // the snail overtakes
    b3 += '<g><path d="M40 164 q-6 0 -6 -5 q0 -5 6 -5 q5 0 5 5 M46 164 h-14 M34 154 q0 -5 4 -5" fill="none" stroke="' + INK + '" stroke-width="1.1"/>' +
      '<path d="M50 158 q3 -2 5 0" fill="none" stroke="' + INK + '" stroke-width="0.9" opacity="0.6"/></g>';
    b3 += doctor(228, 148);
    b3 += bubble(206, 44, ["FIRING ISN\u2019T", "GROWING."], 222, 92);
    b3 += '<text x="' + (W - 14) + '" y="192" text-anchor="end" class="comic-hand" font-size="12" fill="' + RED + '">TO BE CONTINUED\u2026</text>';

    $("sc-asof").textContent = sc.as_of ? "as of " + sc.as_of : "—";
    $("sc-goal").innerHTML = "&ldquo;" + esc(sc.target_state || "") + "&rdquo; &middot; " +
      (agg != null ? "<strong>" + agg.toFixed(1) + "% grown</strong>" : "") +
      " &middot; every bar is real &mdash; hover for evidence";
    $("sc-track").innerHTML = panel(W, H, b1, 1) + panel(W, H, b2, 2) + panel(W, H, b3, 3);
    $("sc-subtitle").textContent = sc.subtitle || "";
  }

  document.addEventListener("brief:loaded", (e) => render(e.detail._selfcalib));
  if (window.__brief) render(window.__brief._selfcalib);
})();
