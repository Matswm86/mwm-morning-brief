/*! Self-calibration progress — reads brief._selfcalib via "brief:loaded". */
(function () {
  const $ = (id) => document.getElementById(id);

  function render(sc) {
    const section = $("selfcalib-section");
    if (!sc || !Array.isArray(sc.dimensions) || !sc.dimensions.length) {
      section.hidden = true;
      return;
    }
    section.hidden = false;

    $("sc-asof").textContent = sc.as_of ? "as of " + sc.as_of : "—";
    $("sc-aggregate").textContent =
      sc.aggregate_pct != null ? sc.aggregate_pct.toFixed(1) + "%" : "—%";
    $("sc-goal").textContent = sc.target_state || "";
    $("sc-subtitle").textContent = sc.subtitle || "";

    const track = $("sc-track");
    track.innerHTML = "";
    const totalWeight = sc.dimensions.reduce((a, d) => a + (d.weight || 0), 0) || 1;
    sc.dimensions.forEach(d => {
      const seg = document.createElement("div");
      seg.className = "sc-seg";
      seg.style.flex = String((d.weight || 0) / totalWeight);
      const pct = Math.min(100, Math.max(0, d.pct || 0));
      seg.innerHTML =
        `<div class="sc-seg-fill" style="width:${pct}%"></div>` +
        `<span class="sc-seg-label">${d.id} ${pct}%</span>`;
      const doneN = (d.done || []).length;
      const nextN = (d.next || []).length;
      seg.title = `${d.id} — ${d.label}\n${pct}% · weight ${d.weight}\n` +
        `${doneN} shipped · ${nextN} next` +
        (d.last_shipped ? `\nlast shipped ${d.last_shipped}` : "");
      track.appendChild(seg);
    });
  }

  document.addEventListener("brief:loaded", (e) => render(e.detail._selfcalib));
  if (window.__brief) render(window.__brief._selfcalib);
})();
