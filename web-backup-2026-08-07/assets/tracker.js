/*! Live Trading Tracker panel
 *  Reads brief.json `.trade_tracker` block (refreshed with each brief build)
 *  and renders daily + weekly trade counts with win/loss split.
 */
(function () {
  const $ = (id) => document.getElementById(id);

  function fmt(n, fallback) {
    return (n === null || n === undefined) ? fallback : String(n);
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" }) +
             " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    } catch (e) { return iso; }
  }

  function renderPeriod(prefix, total, wins, losses) {
    const totalEl = $(prefix + "-total");
    const winsEl  = $(prefix + "-wins");
    const lossEl  = $(prefix + "-losses");
    const barEl   = $(prefix + "-bar");

    if (!totalEl) return;
    totalEl.textContent = fmt(total, "—");

    const hasData = total !== null && total !== undefined;
    if (hasData && total === 0) {
      if (winsEl) winsEl.textContent = "—";
      if (lossEl) lossEl.textContent = "—";
      if (barEl) barEl.style.width = "0%";
      return;
    }

    if (winsEl) {
      winsEl.textContent = fmt(wins, "—") + "W";
      winsEl.className = "tracker-win" + (wins > 0 ? " has-wins" : "");
    }
    if (lossEl) {
      lossEl.textContent = fmt(losses, "—") + "L";
      lossEl.className = "tracker-loss" + (losses > 0 ? " has-losses" : "");
    }
    if (barEl && total > 0 && wins !== null) {
      barEl.style.width = Math.round((wins / total) * 100) + "%";
    }
  }

  function render(tracker) {
    if (!tracker || tracker.status === "error") {
      ["track-day", "track-week"].forEach(p => {
        const el = $(p + "-total");
        if (el) el.textContent = "—";
      });
      const upd = $("tracker-updated");
      if (upd) upd.textContent = tracker && tracker.error ? "unavailable" : "—";
      return;
    }

    renderPeriod("track-day",
      tracker.daily_trades, tracker.daily_wins, tracker.daily_losses);
    renderPeriod("track-week",
      tracker.weekly_trades, tracker.weekly_wins, tracker.weekly_losses);

    const upd = $("tracker-updated");
    if (upd) upd.textContent = "updated " + fmtTime(tracker.generated_at);
  }

  async function load() {
    try {
      const res = await fetch("brief.json?t=" + Date.now(), { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const brief = await res.json();
      render(brief.trade_tracker);
    } catch (e) {
      console.error("tracker panel load failed", e);
    }
  }

  document.addEventListener("DOMContentLoaded", load);
})();
