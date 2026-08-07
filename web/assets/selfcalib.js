/*! Self-calibration progress — growth rings.
 *  Reads brief._selfcalib via "brief:loaded".
 *
 *  Form: a cross-section. One concentric ring per dimension, ordered core to
 *  rind. Ring THICKNESS is its weight in the aggregate; the arc SWEEP is how
 *  much of that dimension has shipped; the remaining sweep is left as an open
 *  hairline, so the ring reads as a season only partly grown rather than a bar
 *  waiting to fill. The organism accretes outward — the rind is the newest
 *  work. Engraved on paper: no fills, no hue, thickness and sweep carry it.
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const INK = "#211d14";
  const TAU = Math.PI * 2;

  function polar(cx, cy, r, t) {
    const a = -Math.PI / 2 + t * TAU; // 12 o'clock, clockwise
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  }

  function arc(cx, cy, r, t0, t1) {
    const span = t1 - t0;
    if (span <= 0) return "";
    if (span >= 0.9999) {
      // full turn: two half arcs, an SVG arc cannot close on itself
      const [x0, y0] = polar(cx, cy, r, 0);
      const [x1, y1] = polar(cx, cy, r, 0.5);
      return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r} ${r} 0 0 1 ${x1.toFixed(2)} ${y1.toFixed(2)}` +
             `A${r} ${r} 0 0 1 ${x0.toFixed(2)} ${y0.toFixed(2)}`;
    }
    const [x0, y0] = polar(cx, cy, r, t0);
    const [x1, y1] = polar(cx, cy, r, t1);
    return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r} ${r} 0 ${span > 0.5 ? 1 : 0} 1 ` +
           `${x1.toFixed(2)} ${y1.toFixed(2)}`;
  }

  function rings(dims, aggregate) {
    const S = 300, cx = S / 2, cy = S / 2;
    const CORE = 26, RIND = 142, GAP = 2.4;
    const totalW = dims.reduce((a, d) => a + (d.weight || 0), 0) || 1;
    const span = RIND - CORE - GAP * dims.length;

    let out = "";
    // the core: the aggregate, set as the heartwood figure
    out += `<circle cx="${cx}" cy="${cy}" r="${CORE - 4}" fill="none" stroke="${INK}" stroke-width="1" opacity="0.5"/>`;
    out += `<text x="${cx}" y="${cy + 4}" text-anchor="middle" class="sc-core-fig">` +
      (aggregate != null ? aggregate.toFixed(1) + "%" : "—") + `</text>`;

    // radial hairlines every quarter turn — the reader's clock
    for (let q = 0; q < 4; q++) {
      const [x0, y0] = polar(cx, cy, CORE + 1, q / 4);
      const [x1, y1] = polar(cx, cy, RIND + 5, q / 4);
      out += `<line x1="${x0.toFixed(2)}" y1="${y0.toFixed(2)}" x2="${x1.toFixed(2)}" y2="${y1.toFixed(2)}" ` +
        `stroke="${INK}" stroke-width="0.5" opacity="0.16"/>`;
    }

    let r = CORE;
    dims.forEach((d, i) => {
      const w = Math.max(3.2, (span * (d.weight || 0)) / totalW);
      const rc = r + w / 2;
      const pct = Math.min(100, Math.max(0, d.pct || 0)) / 100;
      const doneN = (d.done || []).length, nextN = (d.next || []).length;
      const tip = `${d.id} — ${d.label}\n${Math.round(pct * 100)}% · weight ${d.weight}\n` +
        `${doneN} shipped · ${nextN} next` + (d.last_shipped ? `\nlast shipped ${d.last_shipped}` : "");

      // the ungrown remainder, left open
      const rest = arc(cx, cy, rc, 0, 1);
      // the grown season, solid
      const grown = pct > 0 ? arc(cx, cy, rc, 0, pct) : "";

      out += `<g class="sc-ring" data-id="${d.id}"><title>${tip}</title>` +
        `<path d="${rest}" fill="none" stroke="${INK}" stroke-width="${w.toFixed(2)}" opacity="0.09"/>` +
        (grown
          ? `<path d="${grown}" fill="none" stroke="${INK}" stroke-width="${w.toFixed(2)}" opacity="0.88" stroke-linecap="butt"/>`
          : "") +
        // the growth front: where this season stopped
        (pct > 0.01 && pct < 0.99
          ? (() => {
              const [fx, fy] = polar(cx, cy, rc, pct);
              return `<circle cx="${fx.toFixed(2)}" cy="${fy.toFixed(2)}" r="${Math.min(2.6, w / 2)}" fill="#f2ecdf" stroke="${INK}" stroke-width="0.9"/>`;
            })()
          : "") +
        `<path d="${rest}" fill="none" stroke="transparent" stroke-width="${(w + GAP).toFixed(2)}"/>` +
        `</g>`;
      r += w + GAP;
    });

    return `<svg class="sc-rings" viewBox="0 0 ${S} ${S}" role="img" ` +
      `aria-label="Growth rings: one ring per dimension, thickness is weight, sweep is completion">${out}</svg>`;
  }

  function legend(dims) {
    const total = dims.reduce((a, d) => a + (d.weight || 0), 0) || 1;
    return dims.map((d) => {
      const pct = Math.min(100, Math.max(0, d.pct || 0));
      const doneN = (d.done || []).length, nextN = (d.next || []).length;
      return `<li class="sc-key" data-id="${d.id}">` +
        `<span class="sc-key-id">${d.id}</span>` +
        `<span class="sc-key-label">${d.label || ""}</span>` +
        `<span class="sc-key-bar"><span class="sc-key-fill" style="width:${pct}%"></span></span>` +
        `<span class="sc-key-pct">${pct}%</span>` +
        `<span class="sc-key-meta">weight ${((d.weight || 0) / total * 100).toFixed(0)}% · ` +
        `${doneN} shipped${nextN ? " · " + nextN + " next" : ""}` +
        (d.last_shipped ? " · " + d.last_shipped : "") + `</span>` +
        `</li>`;
    }).join("");
  }

  function render(sc) {
    const section = $("selfcalib-section");
    if (!sc || !Array.isArray(sc.dimensions) || !sc.dimensions.length) {
      section.hidden = true;
      return;
    }
    section.hidden = false;

    $("sc-asof").textContent = sc.as_of ? "as of " + sc.as_of : "—";
    const agg = $("sc-aggregate"); // optional — the ring core carries the figure
    if (agg) agg.textContent = sc.aggregate_pct != null ? sc.aggregate_pct.toFixed(1) + "%" : "—%";
    $("sc-goal").textContent = sc.target_state || "";
    $("sc-subtitle").textContent = sc.subtitle || "";

    // core to rind, heaviest at the heart
    const dims = sc.dimensions.slice().sort((a, b) => (b.weight || 0) - (a.weight || 0));
    $("sc-track").innerHTML = rings(dims, sc.aggregate_pct);
    $("sc-keys").innerHTML = legend(dims);

    // hovering a key lights its ring, and the reverse. The dimming is driven
    // by a class on the svg, not :hover, so it also fires from the legend.
    const wrap = $("selfcalib-section");
    const svg = wrap.querySelector(".sc-rings");
    wrap.querySelectorAll(".sc-key").forEach((k) => {
      const id = k.dataset.id;
      const ring = wrap.querySelector('.sc-ring[data-id="' + id + '"]');
      const on = () => {
        k.classList.add("is-on");
        if (ring) ring.classList.add("is-on");
        if (svg) svg.classList.add("is-probing");
      };
      const off = () => {
        k.classList.remove("is-on");
        if (ring) ring.classList.remove("is-on");
        if (svg) svg.classList.remove("is-probing");
      };
      k.addEventListener("mouseenter", on);
      k.addEventListener("mouseleave", off);
      if (ring) { ring.addEventListener("mouseenter", on); ring.addEventListener("mouseleave", off); }
    });
  }

  document.addEventListener("brief:loaded", (e) => render(e.detail._selfcalib));
  if (window.__brief) render(window.__brief._selfcalib);
})();
