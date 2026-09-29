/*! Self-calibration progress — the Funny Pages, fourth printing.
 *  Reads brief._selfcalib via "brief:loaded". Four gags rotate by the as-of
 *  date: The Allotment (plant height = pct), Report Card Day (letter grade
 *  per dimension), The Long Run (shipped vs still-to-ship counts) and the
 *  original Firing Isn't Growing strip. Every figure is read from the feed;
 *  hover a bar, pot or grade for its evidence.
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

  /* ——— the gags. Each takes the same facts and returns panels + a caption.
   * One runs per day, rotated by the as-of date, so the funny pages change
   * like the rest of the paper. Every number drawn is read from the feed. ——— */

  function gagFiring(f) {
    const W = 300, H = 200, dims = f.dims, gap = f.gap;
    /* 1 — pride */
    let b1 = '<rect x="7" y="7" width="' + (W - 14) + '" height="70" fill="url(#ht)"/>';
    b1 += ground(W, 168);
    b1 += organism(196, 128, 27, f.agg / 100, "happy", true);
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
      const bw = 8 + ((d.weight || 0) / f.totalW) * 46;
      const bh = (Math.min(100, Math.max(0, d.pct || 0)) / 100) * (ch - 10);
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
    b3 += organism(90, 138, 24, f.agg / 100, "sad");
    b3 += '<g><path d="M40 164 q-6 0 -6 -5 q0 -5 6 -5 q5 0 5 5 M46 164 h-14 M34 154 q0 -5 4 -5" fill="none" stroke="' + INK + '" stroke-width="1.1"/>' +
      '<path d="M50 158 q3 -2 5 0" fill="none" stroke="' + INK + '" stroke-width="0.9" opacity="0.6"/></g>';
    b3 += doctor(228, 148);
    b3 += bubble(206, 44, ["FIRING ISN’T", "GROWING."], 222, 92);
    b3 += '<text x="' + (W - 14) + '" y="192" text-anchor="end" class="comic-hand" font-size="12" fill="' + RED + '">TO BE CONTINUED…</text>';
    return { title: "Firing Isn’t Growing", panels: [[W, H, b1], [W, H, b2], [W, H, b3]], caption: null };
  }

  function pot(x, y, d, maxH) {
    const pct = Math.min(100, Math.max(0, d.pct || 0)) / 100;
    const h = 18 + pct * maxH;
    const wilt = pct < 0.5;
    let o = '<g class="comic-hit"><title>' + dimTip(d) + "</title>";
    o += '<path d="M' + (x - 24) + " " + y + " L" + (x + 24) + " " + y + " L" + (x + 18) + " " + (y + 34) + " L" + (x - 18) + " " + (y + 34) +
      ' Z" fill="url(#ht)" stroke="' + INK + '" stroke-width="1.4" stroke-linejoin="round"/>' +
      '<path d="' + wob(x - 27, y, x + 27, y, 3) + '" stroke="' + INK + '" stroke-width="2.2" fill="none"/>';
    const tipX = wilt ? x + 26 : x + (rnd() - 0.5) * 6;
    const tipY = wilt ? y - h * 0.62 : y - h;
    const cX = wilt ? x + 6 : x;
    const cY = y - h * (wilt ? 0.95 : 0.55);
    o += '<path d="M' + x + " " + y + " Q" + N(cX) + " " + N(cY) + " " + N(tipX) + " " + N(tipY) + '" fill="none" stroke="' + INK + '" stroke-width="1.6" stroke-linecap="round"/>';
    const leaves = Math.max(1, Math.round(pct * 4));
    for (let i = 1; i <= leaves; i++) {
      const t = i / (leaves + 1);
      const lx = (1 - t) * (1 - t) * x + 2 * (1 - t) * t * cX + t * t * tipX;
      const ly = (1 - t) * (1 - t) * y + 2 * (1 - t) * t * cY + t * t * tipY;
      const s = i % 2 ? 1 : -1;
      const droop = wilt ? 7 : -4;
      o += '<path d="M' + N(lx) + " " + N(ly) + " q" + N(s * 8) + " " + N(droop - 6) + " " + N(s * 15) + " " + N(droop) +
        " q" + N(-s * 8) + " " + 3 + " " + N(-s * 15) + " " + N(-droop) + '" fill="' + PAPER + '" stroke="' + INK + '" stroke-width="1.1"/>';
    }
    if (pct >= 0.7) {
      for (let k = 0; k < 6; k++) {
        const a = (k / 6) * Math.PI * 2;
        o += '<ellipse cx="' + N(tipX + Math.cos(a) * 7) + '" cy="' + N(tipY + Math.sin(a) * 7) + '" rx="5" ry="3.4" transform="rotate(' +
          N((a * 180) / Math.PI) + " " + N(tipX + Math.cos(a) * 7) + " " + N(tipY + Math.sin(a) * 7) + ')" fill="' + PAPER + '" stroke="' + INK + '" stroke-width="1"/>';
      }
      o += '<circle cx="' + N(tipX) + '" cy="' + N(tipY) + '" r="4" fill="' + INK + '" opacity="0.8"/>';
    } else {
      o += '<ellipse cx="' + N(tipX) + '" cy="' + N(tipY) + '" rx="4" ry="6" transform="rotate(' + (wilt ? 70 : 0) + " " + N(tipX) + " " + N(tipY) + ')" fill="url(#ht)" stroke="' + INK + '" stroke-width="1.1"/>';
    }
    o += '<text x="' + x + '" y="' + (y + 50) + '" text-anchor="middle" class="comic-label">' + esc(d.id) + " · " + Math.round(d.pct || 0) + "%</text></g>";
    return o;
  }

  function gagGarden(f) {
    const W = 900, H = 300;
    const beds = f.dims.slice().sort((a, b) => (b.pct || 0) - (a.pct || 0));
    const top = beds[0], low = beds[beds.length - 1];
    let o = '<rect x="7" y="7" width="' + (W - 14) + '" height="54" fill="url(#ht)"/>';
    o += ground(W, 241);
    const x0 = 250, step = Math.min(110, 560 / Math.max(1, beds.length - 1));
    beds.forEach((d, i) => { o += pot(x0 + i * step, 206, d, 120); });
    // the gardener, watering the bed that needs it least
    o += organism(120, 190, 28, f.agg / 100, "happy");
    o += '<g><path d="M156 170 h34 l6 -8 M160 170 v22 h26 v-22" fill="' + PAPER + '" stroke="' + INK + '" stroke-width="1.5" stroke-linejoin="round"/>' +
      '<path d="M186 176 L222 150" stroke="' + INK + '" stroke-width="2" stroke-linecap="round"/>' +
      '<path d="M226 150 q6 10 4 22 M232 146 q8 12 6 26 M221 153 q2 8 0 16" fill="none" stroke="' + INK + '" stroke-width="1" stroke-dasharray="2 4" stroke-linecap="round"/></g>';
    const lx = x0 + (beds.length - 1) * step;
    o += bubble(Math.min(W - 70, lx - 10), 70, ["PSST."], lx + 8, 140, 14);
    return {
      title: "The Allotment",
      panels: [[W, H, o]],
      caption: "Watering " + top.id + " again (" + (top.label || "") + ", " + Math.round(top.pct || 0) + "%). " +
        low.id + " (" + (low.label || "") + ", " + Math.round(low.pct || 0) + "%) would like a word.",
    };
  }

  const grade = (p) => (p >= 90 ? "A" : p >= 80 ? "B" : p >= 70 ? "C" : p >= 60 ? "D" : "F");

  function gagReport(f) {
    const W = 900, H = 300;
    const low = f.dims.slice().sort((a, b) => (a.pct || 0) - (b.pct || 0))[0];
    const top = f.dims.slice().sort((a, b) => (b.pct || 0) - (a.pct || 0))[0];
    let o = '<rect x="7" y="7" width="' + (W - 14) + '" height="54" fill="url(#ht)"/>';
    o += ground(W, 262);
    o += organism(190, 214, 30, f.agg / 100, "sad");
    // the card
    const cx = 330, cy = 44, cw = 250, rowH = 26, chh = 50 + f.dims.length * rowH;
    o += '<g transform="rotate(-2 ' + (cx + cw / 2) + " " + (cy + chh / 2) + ')">' +
      '<rect x="' + cx + '" y="' + cy + '" width="' + cw + '" height="' + chh + '" fill="' + PAPER + '" stroke="' + INK + '" stroke-width="1.6"/>' +
      '<text x="' + (cx + cw / 2) + '" y="' + (cy + 26) + '" text-anchor="middle" class="comic-hand" font-size="17">REPORT CARD</text>' +
      '<path d="' + wob(cx + 14, cy + 36, cx + cw - 14, cy + 36, 4) + '" stroke="' + INK + '" stroke-width="1" fill="none"/>';
    f.dims.forEach((d, i) => {
      const y = cy + 58 + i * rowH, g = grade(d.pct || 0), bad = g === "F" || g === "D";
      o += '<g class="comic-hit"><title>' + dimTip(d) + "</title>" +
        '<text x="' + (cx + 18) + '" y="' + y + '" class="comic-hand" font-size="14">' + esc(d.id + "  " + (d.label || "")) + "</text>" +
        '<text x="' + (cx + cw - 22) + '" y="' + y + '" text-anchor="end" class="comic-hand" font-size="18" fill="' + (bad ? RED : INK) + '">' + g + "</text></g>";
      if (d === low) o += '<ellipse cx="' + (cx + cw - 28) + '" cy="' + (y - 6) + '" rx="15" ry="12" fill="none" stroke="' + RED + '" stroke-width="1.5"/>';
    });
    o += "</g>";
    // organism holds the card up
    o += '<path d="M218 206 L330 160" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>';
    o += doctor(720, 258, "point");
    o += bubble(740, 110, [low.id + ": SEE ME", "AFTER CLASS."], 724, 196, 15);
    return {
      title: "Report Card Day",
      panels: [[W, H, o]],
      caption: "Top of the class in " + (top.label || top.id).toLowerCase() + " (" + Math.round(top.pct || 0) + "%). " +
        "Overall " + f.agg.toFixed(1) + "%. The red pen was reserved for " + (low.label || low.id).toLowerCase() + ".",
    };
  }

  function gagMarathon(f) {
    const W = 300, H = 200;
    const shipped = f.dims.reduce((a, d) => a + (d.done_n || 0), 0);
    const toGo = f.dims.reduce((a, d) => a + (d.next_n || 0), 0);
    /* 1 — the start */
    let b1 = '<rect x="7" y="7" width="' + (W - 14) + '" height="40" fill="url(#ht)"/>' + ground(W, 168);
    b1 += '<path d="M40 168 V70 M40 70 h60 l-8 12 l8 12 h-60" fill="' + PAPER + '" stroke="' + INK + '" stroke-width="1.4" stroke-linejoin="round"/>' +
      '<text x="68" y="86" text-anchor="middle" class="comic-hand" font-size="12">START</text>';
    b1 += organism(170, 128, 26, f.agg / 100, "happy", true);
    b1 += bubble(200, 44, [f.agg.toFixed(1) + "% THERE!"], 184, 92);
    /* 2 — the long middle */
    let b2 = '<rect x="7" y="7" width="' + (W - 14) + '" height="40" fill="url(#ht)"/>' + ground(W, 168);
    for (let i = 0; i < 4; i++) b2 += '<path d="M' + (20 + i * 70) + ' 180 h36" stroke="' + INK + '" stroke-width="1.2" opacity="0.5"/>';
    b2 += '<path d="M226 168 V96 M192 94 h68 v34 h-68 z" fill="' + PAPER + '" stroke="' + INK + '" stroke-width="1.3"/>' +
      '<text x="226" y="107" text-anchor="middle" class="comic-label">SHIPPED</text>' +
      '<text x="226" y="123" text-anchor="middle" class="comic-hand" font-size="12">' + shipped + "</text>";
    b2 += organism(110, 130, 24, f.agg / 100, "happy");
    b2 += '<path d="M140 104 q3 6 0 9 M147 112 q3 6 0 9" fill="none" stroke="' + INK + '" stroke-width="1.1"/>' +
      '<path d="M70 120 h-22 M72 132 h-30 M70 144 h-18" stroke="' + INK + '" stroke-width="1" opacity="0.6"/>';
    /* 3 — the finish, somewhere */
    let b3 = '<rect x="7" y="7" width="' + (W - 14) + '" height="40" fill="url(#ht)"/>' + ground(W, 168);
    b3 += '<path d="M150 168 L150 152 M126 152 h48 v-14 h-48 z" fill="' + PAPER + '" stroke="' + INK + '" stroke-width="1"/>' +
      '<text x="150" y="148" text-anchor="middle" class="comic-label">FINISH</text>';
    b3 += '<text x="150" y="128" text-anchor="middle" class="comic-hand" font-size="11" fill="' + RED + '">' + (100 - f.agg).toFixed(1) + "% →</text>";
    b3 += organism(70, 138, 24, f.agg / 100, "sad");
    b3 += doctor(248, 148);
    b3 += bubble(214, 44, [toGo + " MORE", "TO SHIP."], 236, 92);
    return { title: "The Long Run", panels: [[W, H, b1], [W, H, b2], [W, H, b3]], caption: null };
  }

  const GAGS = [gagGarden, gagReport, gagMarathon, gagFiring];

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
    // the dimension carrying the most weight × remaining growth
    const gap = dims.slice().sort((a, b) =>
      (b.weight || 0) * (100 - (b.pct || 0)) - (a.weight || 0) * (100 - (a.pct || 0)))[0];

    const day = sc.as_of ? new Date(sc.as_of + "T12:00:00Z") : new Date();
    const doy = Math.floor((day - Date.UTC(day.getUTCFullYear(), 0, 0)) / 864e5);
    const gag = GAGS[doy % GAGS.length]({ dims, totalW, agg, gap });

    $("sc-asof").textContent = sc.as_of ? "as of " + sc.as_of : "—";
    const title = document.querySelector("#selfcalib-section .comic-title");
    if (title) title.textContent = gag.title;
    $("sc-goal").innerHTML = "The Calibrating Organism &middot; &ldquo;" + esc(sc.target_state || "") + "&rdquo; &middot; " +
      "<strong>" + agg.toFixed(1) + "% grown</strong> &middot; every figure is real &mdash; hover for evidence";
    const track = $("sc-track");
    track.classList.toggle("single", gag.panels.length === 1);
    track.innerHTML = gag.panels.map((pn, i) => panel(pn[0], pn[1], pn[2], i + 1)).join("") +
      (gag.caption ? '<p class="comic-cap">' + esc(gag.caption) + "</p>" : "");
    $("sc-subtitle").textContent = sc.subtitle || "";
  }

  document.addEventListener("brief:loaded", (e) => render(e.detail._selfcalib));
  if (window.__brief) render(window.__brief._selfcalib);
})();
