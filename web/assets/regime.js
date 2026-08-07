/*! Long-term regime monitor — reads regime.json, renders trend/vol/credit/
 *  tripwire rows + VIX history chart (lightweight-charts area series).
 */
(function () {
  const $ = (id) => document.getElementById(id);

  function pct(n) { return (n >= 0 ? "+" : "") + n.toFixed(2); }

  function render(r) {
    // verdict + edge badge
    const v = r.verdict || {};
    $("regime-verdict").textContent = v.regime || "—";
    const badge = $("edge-badge");
    badge.dataset.flag = v.strategy_edge || "unknown";
    badge.textContent = "edge " + (v.strategy_edge || "—");
    $("regime-rationale").textContent = v.rationale || "";

    // trend
    const t = r.trend || {};
    $("trend-state").textContent = t.state || "—";
    $("trend-body").textContent =
      `SPX ${t.spx_last != null ? t.spx_last.toFixed(0) : "—"} · ` +
      `50d ${t.above_50 ? "above" : "below"} (${t.sma50 != null ? t.sma50.toFixed(0) : "—"}, ${t.sma50_slope || "—"}) · ` +
      `200d ${t.above_200 ? "above" : "below"} (${t.sma200 != null ? t.sma200.toFixed(0) : "—"})`;

    // volatility
    const vol = r.vol || {};
    const ts = vol.term_structure || {};
    $("vol-label").textContent = vol.tone || "—";
    $("vol-body").textContent =
      `VIX ${vol.vix_spot != null ? vol.vix_spot.toFixed(1) : "—"} · ` +
      `RV20 ${vol.rv_20d != null ? vol.rv_20d.toFixed(1) : "—"} (ratio ${vol.ratio != null ? vol.ratio.toFixed(2) : "—"}) · ` +
      `${ts.state || "—"} (VIX3M ${ts.vix3m != null ? ts.vix3m.toFixed(1) : "—"})`;

    // credit / curve
    const c = r.credit || {};
    $("credit-label").textContent = (c.direction || "—") + (c.inverted ? " · inverted" : "");
    $("credit-body").textContent =
      `HY OAS ${c.hy_oas != null ? c.hy_oas.toFixed(2) : "—"}% (${c.delta_1mo != null ? pct(c.delta_1mo) : "—"} 1mo) · ` +
      `10Y-2Y ${c.t10y2y != null ? pct(c.t10y2y) : "—"}pp`;

    // tripwires
    const tw = r.tripwires || {};
    const names = [
      ["vix_25_5d", "VIX>25 5d"],
      ["vix_backwardated", "backwardation"],
      ["hy_wide_and_widening", "HY widening"],
      ["curve_inv_below_200sma", "inv + <200d"],
    ];
    $("tripwires-label").textContent = `${tw.count_active || 0} / 4`;
    const active = names.filter(([k]) => tw[k]).map(([, l]) => l);
    $("tripwires-body").textContent = active.length ? "active: " + active.join(", ") : "none active";

    if (r.generated_at) {
      $("regime-updated").textContent = "updated " +
        new Date(r.generated_at).toLocaleString("en-GB", {
          day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
        });
    }

    renderVix(r);
  }

  let vixChart = null;
  function renderVix(r) {
    const container = $("vix-chart");
    if (!container || typeof LightweightCharts === "undefined") return;
    const hist = r.vix_history || [];
    if (!hist.length) return;
    if (vixChart) { vixChart.remove(); vixChart = null; }

    vixChart = LightweightCharts.createChart(container, {
      layout: {
        background: { type: "solid", color: "#f2ecdf" },
        textColor: "#56503f",
        fontFamily: '"Spline Sans Mono", ui-monospace, monospace',
      },
      grid: {
        vertLines: { color: "rgba(33,29,20,0.07)" },
        horzLines: { color: "rgba(33,29,20,0.07)" },
      },
      rightPriceScale: { borderColor: "rgba(33,29,20,0.22)" },
      timeScale: { borderColor: "rgba(33,29,20,0.22)", minBarSpacing: 0.001 },
      crosshair: { mode: 0 },
      height: 260,
    });

    const area = vixChart.addAreaSeries({
      lineColor: "#211d14",
      lineWidth: 1,
      topColor: "rgba(33,29,20,0.18)",
      bottomColor: "rgba(33,29,20,0.02)",
    });
    area.setData(hist);

    // bands at 12 / 20 / 30 / 50
    [12, 20, 30, 50].forEach(level => {
      area.createPriceLine({
        price: level,
        color: level >= 30 ? "#a23423" : "rgba(33,29,20,0.35)",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
      });
    });

    // strategy-valid era shading: baseline area over the era, drawn under main series
    if (r.strategy_era_start) {
      const eraTs = Math.floor(new Date(r.strategy_era_start).getTime() / 1000);
      const eraPts = hist.filter(p => p.time >= eraTs);
      if (eraPts.length) {
        const maxV = Math.max(...hist.map(p => p.value));
        const era = vixChart.addAreaSeries({
          lineColor: "rgba(187,58,38,0)",
          topColor: "rgba(187,58,38,0.10)",
          bottomColor: "rgba(187,58,38,0.10)",
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        era.setData(eraPts.map(p => ({ time: p.time, value: maxV })));
      }
    }

    vixChart.timeScale().fitContent();
    window.addEventListener("resize", () => {
      vixChart.applyOptions({ width: container.clientWidth });
    });
  }

  async function load() {
    try {
      const resp = await fetch("regime.json", { cache: "no-store" });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      render(await resp.json());
    } catch (e) {
      $("regime-verdict").textContent = "load failed";
      console.error("regime load failed", e);
    }
  }

  load();
  setInterval(load, 30 * 60 * 1000);
})();
