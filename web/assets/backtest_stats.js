/*! Strategy Performance panel
 *  Reads brief.json `.backtest_stats` block. Numbers mirror the
 *  trading.mwmai.no strategy showcase (1-year backtest, live Combine cells).
 */
(function () {
  const $ = (id) => document.getElementById(id);

  function fmtUsd(n) {
    if (n === null || n === undefined) return "—";
    const abs = Math.abs(n);
    const sign = n >= 0 ? "+" : "−";
    if (abs >= 1000) {
      return sign + "$" + abs.toLocaleString("en-US");
    }
    return sign + "$" + abs;
  }

  function fmtPct(n, decimals) {
    if (n === null || n === undefined) return "—";
    const d = (decimals === undefined) ? (Math.abs(n) < 1 ? 2 : 1) : decimals;
    const sign = n >= 0 ? "+" : "";
    return sign + Number(n).toFixed(d) + "%";
  }

  function fmtNum(n, decimals, suffix) {
    if (n === null || n === undefined) return "—";
    return Number(n).toFixed(decimals) + (suffix || "");
  }

  function setText(id, value, cls) {
    const el = $(id);
    if (!el) return;
    el.textContent = value;
    if (cls !== undefined) {
      const base = el.className.replace(/\bss-positive\b|\bss-negative\b/g, "").trim();
      el.className = cls ? base + " " + cls : base;
    }
  }

  function renderCard(prefix, data) {
    if (!data || data.status !== "ok") {
      const card = $("ss-card-" + prefix);
      if (card) card.classList.add("ss-error");
      return;
    }

    // Header
    const labelEl = $("ss-label-" + prefix);
    if (labelEl) labelEl.textContent = data.label || prefix;
    const periodEl = $("ss-period-" + prefix);
    if (periodEl) periodEl.textContent = data.period || "—";

    // Core metrics
    setText("ss-wr-" + prefix, fmtNum(data.win_rate_pct, 1, "%"), "ss-positive");
    setText("ss-pf-" + prefix, fmtNum(data.profit_factor, 2), "");
    setText("ss-dd-" + prefix, fmtNum(data.max_dd_pct, 1, "%"), "ss-negative");

    // Risk per trade
    const riskPct = data.risk_per_trade_pct;
    const riskUsd = data.risk_per_trade_usd;
    const riskStr = (riskPct != null && riskUsd != null)
      ? fmtNum(riskPct, 2, "%") + "  (~$" + Math.abs(riskUsd) + "/tr)"
      : "—";
    setText("ss-risk-" + prefix, riskStr, "ss-negative");

    // Monthly averages
    setText("ss-mo-usd-" + prefix, fmtUsd(data.monthly_avg_usd), "ss-positive");
    setText("ss-mo-pct-" + prefix, fmtPct(data.monthly_avg_pct), "ss-positive");
    setText("ss-mo-tr-" + prefix,
      data.monthly_avg_trades ? data.monthly_avg_trades + " tr/mo" : "—", "");

    // Yearly averages
    setText("ss-yr-usd-" + prefix, fmtUsd(data.yearly_avg_usd), "ss-positive");
    setText("ss-yr-pct-" + prefix, fmtPct(data.yearly_avg_pct), "ss-positive");
    setText("ss-yr-tr-" + prefix,
      data.yearly_avg_trades ? data.yearly_avg_trades + " tr/yr" : "—", "");

    // Footer note
    const refEl = $("ss-ref-" + prefix);
    if (refEl && data.ref_capital) {
      refEl.textContent = "$" + (data.ref_capital / 1000).toFixed(0) + "k ref · " +
                          data.ref_contracts + "ct · " + (data.source || "");
    }
  }

  async function load() {
    try {
      const res = await fetch("brief.json?t=" + Date.now(), { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const brief = await res.json();
      const bs = brief.backtest_stats;
      if (!bs) return;
      renderCard("liqsweep", bs.liqsweep);   // LiqSweep MNQ
      renderCard("orb-br", bs.orb_br);       // LiqSweep MGC (own card)
      renderCard("orb", bs.orb);             // ORB Breakout
    } catch (e) {
      console.error("backtest_stats panel load failed", e);
    }
  }

  document.addEventListener("DOMContentLoaded", load);
})();
