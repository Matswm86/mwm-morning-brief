/*! Cell Activity panel
 *  Reads brief.json `.cell_activity` block (7 live practice cells).
 */
(function () {
  const $ = (id) => document.getElementById(id);

  const STATUS_LABELS = {
    active:      { text: "fired",   cls: "cell-s-active"   },
    in_position: { text: "in pos",  cls: "cell-s-inpos"    },
    armed:       { text: "armed",   cls: "cell-s-armed"    },
    off_day:     { text: "off-day", cls: "cell-s-offday"   },
    stale:       { text: "stale",   cls: "cell-s-stale"    },
    error:       { text: "error",   cls: "cell-s-error"    },
  };

  function fmtAge(seconds) {
    if (seconds === null || seconds === undefined) return "—";
    if (seconds < 60) return Math.round(seconds) + "s";
    const m = Math.floor(seconds / 60);
    if (m < 60) return m + "m";
    return Math.floor(m / 60) + "h" + (m % 60) + "m";
  }

  function fmtSyncAge(isoUtc) {
    if (!isoUtc) return "sync —";
    const then = Date.parse(isoUtc);
    if (isNaN(then)) return "sync —";
    const diffS = Math.max(0, (Date.now() - then) / 1000);
    if (diffS < 60) return "sync " + Math.round(diffS) + "s ago";
    const m = Math.floor(diffS / 60);
    return "sync " + m + "m ago";
  }

  function fmtDow(trade_dow) {
    if (!Array.isArray(trade_dow) || trade_dow.length !== 7) return "—";
    const names = ["M", "T", "W", "T", "F", "S", "S"];
    return names.map((n, i) => trade_dow[i] ? n : "·").join("");
  }

  function renderRow(cell) {
    const pill = STATUS_LABELS[cell.status] || STATUS_LABELS.error;
    const row = document.createElement("article");
    row.className = "cell-row";

    const name = document.createElement("span");
    name.className = "cell-col-name";
    const lbl = document.createElement("span");
    lbl.className = "cell-name-label";
    lbl.textContent = cell.label || cell.service || "—";
    const engine = document.createElement("span");
    engine.className = "cell-name-engine";
    engine.textContent = cell.engine || "";
    name.appendChild(lbl);
    name.appendChild(engine);

    const spec = document.createElement("span");
    spec.className = "cell-col-spec";
    spec.textContent = `${cell.symbol || "—"} · ${cell.contracts || 0}ct · ${cell.timeframe || "—"}`;

    const window = document.createElement("span");
    window.className = "cell-col-window";
    const wlbl = document.createElement("span");
    wlbl.className = "cell-window-label";
    wlbl.textContent = cell.window || "—";
    const dow = document.createElement("span");
    dow.className = "cell-window-dow";
    dow.textContent = fmtDow(cell.trade_dow);
    window.appendChild(wlbl);
    window.appendChild(dow);

    const counts = document.createElement("span");
    counts.className = "cell-col-counts";
    const f = cell.entries_today || 0;
    const s = cell.signals_today || 0;
    const b = cell.bars_today || 0;
    counts.innerHTML =
      `<span class="cell-cnt cell-cnt-entries ${f > 0 ? "has-entries" : ""}">${f}</span>` +
      `<span class="cell-cnt-sep">/</span>` +
      `<span class="cell-cnt cell-cnt-signals">${s}</span>` +
      `<span class="cell-cnt-meta">bars ${b}</span>`;

    const status = document.createElement("span");
    status.className = "cell-col-status";
    const badge = document.createElement("span");
    badge.className = `cell-badge ${pill.cls}`;
    badge.textContent = pill.text;
    const detail = document.createElement("span");
    detail.className = "cell-detail";
    detail.textContent = cell.status_detail || "";
    status.appendChild(badge);
    status.appendChild(detail);

    row.appendChild(name);
    row.appendChild(spec);
    row.appendChild(window);
    row.appendChild(counts);
    row.appendChild(status);
    return row;
  }

  function renderSummary(summary, syncUtc) {
    const parts = [];
    if (summary.active > 0)      parts.push(`${summary.active} fired`);
    if (summary.in_position > 0) parts.push(`${summary.in_position} in-pos`);
    if (summary.armed > 0)       parts.push(`${summary.armed} armed`);
    if (summary.off_day > 0)     parts.push(`${summary.off_day} off-day`);
    if (summary.stale > 0)       parts.push(`${summary.stale} stale`);
    if (summary.error > 0)       parts.push(`${summary.error} error`);
    const summaryText = parts.length
      ? `${summary.total} services · ${parts.join(" · ")}`
      : `${summary.total} services · ${summary.alive} alive`;
    const el = $("cell-summary");
    if (el) el.textContent = summaryText;
    const syncEl = $("cell-sync");
    if (syncEl) syncEl.textContent = fmtSyncAge(syncUtc);
  }

  async function load() {
    try {
      const res = await fetch("brief.json?t=" + Date.now(), { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const brief = await res.json();
      const ca = brief.cell_activity;
      if (!ca || !ca.cells || !ca.cells.length) return;

      const section = $("cell-section");
      if (section) section.hidden = false;

      const grid = $("cell-grid");
      if (!grid) return;
      // Clear everything after the header row
      while (grid.children.length > 1) grid.removeChild(grid.lastChild);
      ca.cells.forEach((cell) => grid.appendChild(renderRow(cell)));

      renderSummary(ca.summary || {}, ca.last_sync_utc);
    } catch (e) {
      console.error("cell activity load failed", e);
    }
  }

  document.addEventListener("DOMContentLoaded", load);
})();
