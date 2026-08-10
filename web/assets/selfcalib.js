/*! Self-calibration progress — back-page funnies.
 *  Reads brief._selfcalib via "brief:loaded", same as the old growth rings,
 *  and draws it as a four-panel strip. Informative and true: every figure
 *  in the panels — aggregate, per-dimension percent, weight, ranking, the
 *  remainder — is read from the feed, never invented.
 *    I.   The Organism      — who it is, how grown (aggregate %)
 *    II.  The Measuring     — one plant per dimension: height = pct, bloom = weight
 *    III. The Standings     — dimensions ranked by pct, weights noted
 *    IV.  Next Episode      — the three least-grown dimensions, remainder shown
 *  Ink line art + one spot colour, halftone skies — hover anything for the
 *  same evidence the rings used to carry (shipped / next / last shipped).
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const INK = "#251e10";
  const RED = "#8e2f1e";
  const PAPER = "#f2ecdf";

  /* deterministic wobble so the strip doesn't shimmer on refresh */
  let seed = 7;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const N = (x) => x.toFixed(1);

  function wobblyLine(x0, y0, x1, y1, segs) {
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

  function panelFrame(w, h) {
    const m = 5;
    return '<path d="' +
      wobblyLine(m, m, w - m, m, 6) + " " + wobblyLine(w - m, m, w - m, h - m, 5).replace("M", "L") +
      " " + wobblyLine(w - m, h - m, m, h - m, 6).replace("M", "L") +
      " " + wobblyLine(m, h - m, m, m, 5).replace("M", "L") +
      ' Z" fill="none" stroke="' + INK + '" stroke-width="1.6" stroke-linejoin="round"/>';
  }

  /* one pattern per panel — a duplicated SVG id would make every panel's sky
   * resolve against panel I's defs */
  function halftone(pid) {
    return '<defs><pattern id="ht-' + pid + '" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(20)">' +
      '<circle cx="2" cy="2" r="1" fill="' + INK + '" opacity="0.14"/></pattern></defs>';
  }

  function sky(w, hTop, pid) {
    return '<rect x="7" y="7" width="' + (w - 14) + '" height="' + hTop + '" fill="url(#ht-' + pid + ')"/>';
  }

  function ground(w, y) {
    return '<path d="' + wobblyLine(8, y, w - 8, y, 7) + '" fill="none" stroke="' + INK + '" stroke-width="1.2"/>';
  }

  /* the organism: a walking tree-stump cross-section — its growth rings ARE the data */
  function organism(cx, cy, r, pctGrown, mood) {
    let out = "";
    // rings: outer = full outline; inner rings drawn solid up to the grown share
    const ringCount = 4;
    for (let i = ringCount; i >= 1; i--) {
      const rr = (r * i) / ringCount;
      const grown = i / ringCount <= pctGrown + 0.13;
      out += '<ellipse cx="' + cx + '" cy="' + cy + '" rx="' + N(rr * (1 + (rnd() - 0.5) * 0.06)) +
        '" ry="' + N(rr * (1 + (rnd() - 0.5) * 0.06)) + '" fill="' + (i === ringCount ? PAPER : "none") +
        '" stroke="' + INK + '" stroke-width="' + (i === ringCount ? 1.6 : 1) +
        '"' + (grown ? "" : ' stroke-dasharray="2.5 3" opacity="0.5"') + "/>";
    }
    // face on the heartwood
    const ex = r * 0.22, ey = cy - r * 0.1;
    out += '<circle cx="' + N(cx - ex) + '" cy="' + N(ey) + '" r="1.7" fill="' + INK + '"/>' +
           '<circle cx="' + N(cx + ex) + '" cy="' + N(ey) + '" r="1.7" fill="' + INK + '"/>';
    out += mood === "worried"
      ? '<path d="M' + N(cx - 5) + " " + N(cy + r * 0.22) + " q2.5 -3 5 0 q2.5 3 5 0" +
        '" fill="none" stroke="' + INK + '" stroke-width="1.3" stroke-linecap="round"/>' +
        '<path d="M' + N(cx + r * 0.78) + " " + N(cy - r * 0.85) + ' q3 2 1.6 6" fill="none" stroke="' + INK +
        '" stroke-width="1.2" stroke-linecap="round"/>'
      : '<path d="M' + N(cx - 6) + " " + N(cy + r * 0.18) + " q6 6 12 0" +
        '" fill="none" stroke="' + INK + '" stroke-width="1.3" stroke-linecap="round"/>';
    // arms + legs
    out += '<path d="' + wobblyLine(cx - r, cy + 2, cx - r - 10, cy - 8, 2) + '" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>' +
           '<path d="' + wobblyLine(cx + r, cy + 2, cx + r + 10, cy - 8, 2) + '" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>' +
           '<path d="' + wobblyLine(cx - r * 0.4, cy + r, cx - r * 0.45, cy + r + 9, 2) + '" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>' +
           '<path d="' + wobblyLine(cx + r * 0.4, cy + r, cx + r * 0.45, cy + r + 9, 2) + '" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>' +
           '<path d="M' + N(cx - r * 0.45 - 4) + " " + N(cy + r + 9) + ' h9" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>' +
           '<path d="M' + N(cx + r * 0.45 - 4) + " " + N(cy + r + 9) + ' h9" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>';
    return out;
  }

  function bubble(cx, cy, w, h, lines, tailX, tailY, big) {
    const rx = w / 2, ry = h / 2;
    let out = '<ellipse cx="' + cx + '" cy="' + cy + '" rx="' + rx + '" ry="' + ry +
      '" fill="' + PAPER + '" stroke="' + INK + '" stroke-width="1.3"/>';
    out += '<path d="M' + N(cx - rx * 0.25) + " " + N(cy + ry * 0.86) + " L" + N(tailX) + " " + N(tailY) +
      " L" + N(cx + rx * 0.12) + " " + N(cy + ry * 0.92) + ' Z" fill="' + PAPER + '" stroke="' + INK +
      '" stroke-width="1.3" stroke-linejoin="round"/>' +
      '<path d="M' + N(cx - rx * 0.22) + " " + N(cy + ry * 0.84) + " L" + N(cx + rx * 0.1) + " " + N(cy + ry * 0.9) +
      '" stroke="' + PAPER + '" stroke-width="2.5"/>';
    const fs = big ? 13.5 : 11.5;
    const y0 = cy - ((lines.length - 1) / 2) * (fs + 2);
    lines.forEach((ln, i) => {
      out += '<text x="' + cx + '" y="' + N(y0 + i * (fs + 2) + fs * 0.34) +
        '" text-anchor="middle" class="comic-hand" font-size="' + fs + '">' + ln + "</text>";
    });
    return out;
  }

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const trunc = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

  function dimTip(d) {
    return esc(d.id + " — " + (d.label || "") + "\n" + Math.round(d.pct || 0) + "% grown · weight " + (d.weight || 0) +
      "\n" + (d.done || []).length + " shipped · " + (d.next || []).length + " next" +
      (d.last_shipped ? "\nlast shipped " + d.last_shipped : ""));
  }

  function panel(no, title, w, h, body, caption) {
    return '<figure class="comic-panel">' +
      '<div class="comic-panel-no">' + no + " · " + esc(title) + "</div>" +
      '<svg viewBox="0 0 ' + w + " " + h + '">' + halftone(no) + body + panelFrame(w, h) + "</svg>" +
      '<figcaption class="comic-caption">' + caption + "</figcaption></figure>";
  }

  /* ---- Panel I: the organism introduces itself -------------------------- */
  function p1(sc, agg) {
    const W = 250, H = 208;
    let b = sky(W, 74, "I");
    b += ground(W, 172);
    b += organism(78, 128, 30, (agg || 0) / 100, "happy");
    b += bubble(163, 55, 150, 66, ["I AM", Math.round(agg) + "% GROWN!"], 110, 96, true);
    // a passing bird, as is traditional
    b += '<path d="M205 130 q4 -4 8 0 q4 -4 8 0" fill="none" stroke="' + INK + '" stroke-width="1.1"/>';
    return panel("I", "The Organism", W, H, b,
      "Our hero, <em>" + esc(sc.target_state || "the organism") + "</em>, counts its rings: " +
      "<strong>" + (agg != null ? agg.toFixed(1) + "%" : "—") + "</strong> of the way to a full trunk. Dashed rings are seasons not yet grown.");
  }

  /* ---- Panel II: the garden — one plant per dimension -------------------- */
  function p2(dims) {
    const W = 250, H = 208;
    const totalW = dims.reduce((a, d) => a + (d.weight || 0), 0) || 1;
    let b = sky(W, 46, "II");
    const gy = 176;
    b += ground(W, gy);
    const n = dims.length;
    const slot = (W - 36) / n;
    dims.forEach((d, i) => {
      const x = 24 + slot * (i + 0.5);
      const pct = Math.min(100, Math.max(0, d.pct || 0)) / 100;
      const stemH = 14 + pct * 96;
      const bloomR = 4 + ((d.weight || 0) / totalW) * 26;
      const topY = gy - 12 - stemH;
      let g = '<g class="comic-hit"><title>' + dimTip(d) + "</title>";
      // pot
      g += '<path d="M' + N(x - 9) + " " + N(gy - 12) + " h18 l-3 11 h-12 Z" + '" fill="' + PAPER +
        '" stroke="' + INK + '" stroke-width="1.3" stroke-linejoin="round"/>';
      // stem + leaves
      g += '<path d="' + wobblyLine(x, gy - 12, x, topY, 4) + '" fill="none" stroke="' + INK + '" stroke-width="1.4" stroke-linecap="round"/>';
      g += '<path d="M' + N(x) + " " + N(gy - 26 - pct * 30) + ' q-8 -2 -10 -9" fill="none" stroke="' + INK + '" stroke-width="1.1" stroke-linecap="round"/>';
      // bloom: leader blooms in the spot colour
      const lead = !dims.some((o) => (o.pct || 0) > (d.pct || 0));
      for (let p = 0; p < 6; p++) {
        const a = (p / 6) * Math.PI * 2;
        g += '<circle cx="' + N(x + Math.cos(a) * bloomR * 0.72) + '" cy="' + N(topY + Math.sin(a) * bloomR * 0.72) +
          '" r="' + N(bloomR * 0.42) + '" fill="' + PAPER + '" stroke="' + (lead ? RED : INK) + '" stroke-width="1.2"/>';
      }
      g += '<circle cx="' + N(x) + '" cy="' + N(topY) + '" r="' + N(bloomR * 0.4) + '" fill="' + (lead ? RED : INK) + '"/>';
      g += '<text x="' + N(x) + '" y="' + N(topY - bloomR - 4) + '" text-anchor="middle" class="comic-hand" font-size="10.5">' +
        Math.round(pct * 100) + "%</text>";
      g += '<text x="' + N(x) + '" y="' + N(gy + 12) + '" text-anchor="middle" class="comic-label">' + esc(d.id) + "</text>";
      b += g + "</g>";
    });
    return panel("II", "The Measuring", W, H, b,
      "The garden, measured true: <strong>stem height is progress</strong>, <strong>bloom size is weight</strong> in the aggregate. Hover a plant for its evidence.");
  }

  /* ---- Panel III: the standings ------------------------------------------ */
  function p3(dims) {
    const W = 250, H = 208;
    const ranked = dims.slice().sort((a, b) => (b.pct || 0) - (a.pct || 0));
    let b = sky(W, 30, "III");
    // the sign hangs from the frame on two strings
    b += '<path d="M60 7 L66 34 M190 7 L184 34" stroke="' + INK + '" stroke-width="1"/>';
    b += '<path d="' + wobblyLine(26, 34, W - 26, 34, 5) + " " + wobblyLine(W - 26, 34, W - 26, 196, 5).replace("M", "L") +
      " " + wobblyLine(W - 26, 196, 26, 196, 5).replace("M", "L") + " " + wobblyLine(26, 196, 26, 34, 5).replace("M", "L") +
      ' Z" fill="' + PAPER + '" stroke="' + INK + '" stroke-width="1.4" stroke-linejoin="round"/>';
    b += '<text x="' + W / 2 + '" y="52" text-anchor="middle" class="comic-label" font-size="11">THE STANDINGS</text>' +
      '<path d="' + wobblyLine(40, 58, W - 40, 58, 4) + '" stroke="' + INK + '" stroke-width="0.8" fill="none"/>';
    const rows = ranked.slice(0, 6);
    rows.forEach((d, i) => {
      const y = 76 + i * 21;
      const last = i === rows.length - 1 && rows.length > 1;
      let g = '<g class="comic-hit"><title>' + dimTip(d) + "</title>";
      if (i === 0) g += '<circle cx="42" cy="' + (y - 4) + '" r="6" fill="none" stroke="' + RED + '" stroke-width="1.2"/>' +
        '<path d="M39 ' + (y + 1) + ' l-2 6 M45 ' + (y + 1) + ' l2 6" stroke="' + RED + '" stroke-width="1.1"/>';
      g += '<text x="54" y="' + y + '" class="comic-hand" font-size="12">' + (i + 1) + ". " + esc(d.id) + "</text>" +
        '<text x="92" y="' + y + '" class="comic-label" style="font-size:8.5px;letter-spacing:0.05em">' + esc(trunc((d.label || "").toUpperCase(), 14)) + "</text>" +
        '<text x="' + (W - 36) + '" y="' + y + '" text-anchor="end" class="comic-hand" font-size="12"' +
        (i === 0 ? ' fill="' + RED + '"' : "") + ">" + Math.round(d.pct || 0) + "%</text>";
      // the last-placed gets a snail
      if (last) g += '<path d="M34 ' + (y - 2) + " q-5 0 -5 -4 q0 -4 5 -4 q4 0 4 4 M38 " + (y - 2) +
        ' h-10 M30 ' + (y - 8) + ' q0 -4 3 -4" fill="none" stroke="' + INK + '" stroke-width="1"/>';
      b += g + "</g>";
    });
    return panel("III", "The Standings", W, H, b,
      "Ranked by growth. The laurel goes to the tallest season; the snail keeps the slowest company. Weights are on the garden next door.");
  }

  /* ---- Panel IV: next episode -------------------------------------------- */
  function p4(dims, agg) {
    const W = 250, H = 208;
    const todo = dims.slice().sort((a, b) => (a.pct || 0) - (b.pct || 0)).slice(0, 3);
    let b = sky(W, 60, "IV");
    b += ground(W, 176);
    b += organism(52, 134, 26, (agg || 0) / 100, "worried");
    // signpost with one arrow board per unfinished dimension
    const px = 168;
    b += '<path d="' + wobblyLine(px, 176, px, 62, 5) + '" stroke="' + INK + '" stroke-width="2" fill="none"/>';
    todo.forEach((d, i) => {
      const y = 70 + i * 30;
      const remain = Math.max(0, 100 - Math.round(d.pct || 0));
      b += '<g class="comic-hit"><title>' + dimTip(d) + "</title>" +
        '<path d="M' + (px - 46) + " " + (y - 11) + " h74 l12 11 l-12 11 h-74 Z" +
        '" fill="' + PAPER + '" stroke="' + INK + '" stroke-width="1.3" stroke-linejoin="round"/>' +
        '<text x="' + (px - 8) + '" y="' + (y + 4) + '" text-anchor="middle" class="comic-hand" font-size="10.5">' +
        esc(d.id) + " · " + remain + "% TO GO</text></g>";
    });
    b += bubble(84, 46, 132, 54, ["SO MUCH", "STILL TO GROW…"], 62, 100, false);
    b += '<text x="' + (W - 16) + '" y="196" text-anchor="end" class="comic-hand" font-size="12" fill="' + RED + '">TO BE CONTINUED…</text>';
    return panel("IV", "Next Episode", W, H, b,
      "The road ahead, longest legs first: the three least-grown seasons and what remains of each. Same paper, next edition.");
  }

  function render(sc) {
    const section = $("selfcalib-section");
    if (!sc || !Array.isArray(sc.dimensions) || !sc.dimensions.length) {
      section.hidden = true;
      return;
    }
    section.hidden = false;
    seed = 7; // stable wobble across refreshes

    const dims = sc.dimensions;
    const totalW = dims.reduce((a, d) => a + (d.weight || 0), 0) || 1;
    const agg = sc.aggregate_pct != null
      ? sc.aggregate_pct
      : dims.reduce((a, d) => a + (d.pct || 0) * (d.weight || 0), 0) / totalW;

    $("sc-asof").textContent = sc.as_of ? "as of " + sc.as_of : "—";
    $("sc-goal").innerHTML = "&ldquo;" + esc(sc.target_state || "") + "&rdquo; &mdash; drawn from the week's ledger" +
      (sc.as_of ? ", " + esc(sc.as_of) : "") + ". Every figure is real.";
    $("sc-track").innerHTML = p1(sc, agg) + p2(dims) + p3(dims) + p4(dims, agg);
    $("sc-subtitle").textContent = sc.subtitle || "";
  }

  document.addEventListener("brief:loaded", (e) => render(e.detail._selfcalib));
  if (window.__brief) render(window.__brief._selfcalib);
})();
