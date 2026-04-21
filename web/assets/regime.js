/*! Regime monitor + long-term VIX chart
 *  Reads /regime.json (written daily by fetchers.regime_monitor) and
 *  populates the regime panel + renders the VIX timeline.
 */
(function () {
  const URL = "regime.json";
  const $ = (id) => document.getElementById(id);

  function fmtTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" }) +
           " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  }

  function tagFlag(active, label) {
    const cls = active ? "flag-on" : "flag-off";
    const sym = active ? "●" : "○";
    return `<span class="${cls}">${sym} ${label}</span>`;
  }

  function renderPanel(r) {
    const v = r.verdict || {};
    const edge = v.strategy_edge || "unknown";
    $("regime-verdict").textContent = v.regime || "—";
    const badge = $("edge-badge");
    badge.textContent = "edge · " + edge;
    badge.dataset.flag = edge;

    // Trend
    const t = r.trend || {};
    $("trend-state").textContent = t.state || "—";
    const spxParts = [];
    if (t.spx_last != null) spxParts.push(`SPX ${t.spx_last.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}`);
    if (t.sma50 != null)    spxParts.push(`50d ${t.sma50.toLocaleString("en-US",{minimumFractionDigits:0,maximumFractionDigits:0})}`);
    if (t.sma200 != null)   spxParts.push(`200d ${t.sma200.toLocaleString("en-US",{minimumFractionDigits:0,maximumFractionDigits:0})}`);
    spxParts.push(`slope ${t.sma50_slope || "—"}`);
    $("trend-body").innerHTML = spxParts.join(" · ");

    // Volatility
    const vo = r.vol || {};
    const ts = vo.term_structure || {};
    const volLabel = vo.vix_spot != null ? `VIX ${vo.vix_spot}` : "—";
    $("vol-label").textContent = volLabel;
    const volParts = [];
    if (vo.rv_20d != null) volParts.push(`RV20 ${vo.rv_20d}`);
    if (vo.ratio != null)  volParts.push(`V/RV ${vo.ratio}`);
    volParts.push(`tone ${vo.tone || "—"}`);
    if (ts.state) volParts.push(`term ${ts.state}${ts.ratio != null ? ` (${ts.ratio})` : ""}`);
    $("vol-body").innerHTML = volParts.join(" · ");

    // Credit / Curve
    const c = r.credit || {};
    const creditLabel = c.hy_oas != null ? `HY OAS ${c.hy_oas}%` : "—";
    $("credit-label").textContent = creditLabel;
    const cParts = [];
    if (c.delta_1mo != null) {
      const sign = c.delta_1mo >= 0 ? "+" : "";
      cParts.push(`Δ1mo ${sign}${c.delta_1mo}`);
    }
    cParts.push(`HY ${c.direction || "—"}`);
    if (c.t10y2y != null) cParts.push(`10y-2y ${c.t10y2y}`);
    cParts.push(c.inverted ? "INVERTED" : "curve ok");
    $("credit-body").innerHTML = cParts.join(" · ");

    // Tripwires
    const tw = r.tripwires || {};
    const active = tw.count_active || 0;
    $("tripwires-label").textContent = `${active} / 4 active`;
    const twParts = [
      tagFlag(tw.vix_25_5d,              "VIX≥25 x5d"),
      tagFlag(tw.vix_backwardated,       "backwardation"),
      tagFlag(tw.hy_wide_and_widening,   "HY wide+widening"),
      tagFlag(tw.curve_inv_below_200sma, "curve inv & SPX<200d"),
    ];
    $("tripwires-body").innerHTML = twParts.join(" &nbsp; ");

    // Rationale
    $("regime-rationale").textContent = v.rationale || "";

    $("regime-updated").textContent = "updated " + fmtTime(r.generated_at);
  }

  function renderVixChart(r) {
    const container = $("vix-chart");
    if (!container || typeof LightweightCharts === "undefined") return;
    const bars = (r.vix_history || []).filter(x => x && x.value != null);
    if (bars.length === 0) { container.innerHTML = '<p class="mono" style="padding:20px;opacity:0.5">no VIX history</p>'; return; }

    const chart = LightweightCharts.createChart(container, {
      layout: {
        background: { type: "solid", color: "#F9F5EC" },
        textColor: "#3B2F2F",
        fontFamily: "Inter, system-ui, sans-serif",
      },
      grid: {
        vertLines: { color: "rgba(59,47,47,0.08)" },
        horzLines: { color: "rgba(59,47,47,0.08)" },
      },
      rightPriceScale: { borderColor: "rgba(59,47,47,0.20)" },
      timeScale: {
        borderColor: "rgba(59,47,47,0.20)",
        timeVisible: false,
        secondsVisible: false,
      },
      crosshair: { mode: 0 },
      height: 260,
    });

    const line = chart.addLineSeries({
      color: "#6B4423",
      lineWidth: 2,
      priceLineVisible: false,
    });
    line.setData(bars);

    // Reference bands at 12 / 20 / 30 / 50
    [
      { price: 12, color: "#2F7D52", label: "calm"   },
      { price: 20, color: "#6B4423", label: "normal" },
      { price: 30, color: "#A36A1A", label: "elev"   },
      { price: 50, color: "#B43E28", label: "panic"  },
    ].forEach(b => {
      line.createPriceLine({
        price: b.price,
        color: b.color,
        lineWidth: 1,
        lineStyle: 2,          // dashed
        axisLabelVisible: true,
        title: b.label,
      });
    });

    // Strategy-era shading — lightweight-charts doesn't ship a native
    // range-highlight primitive. We approximate with a second filled
    // area series drawn only over the strategy-valid era (constant y
    // near the chart's max) at low opacity.
    const eraStart = r.strategy_era_start
      ? Math.floor(new Date(r.strategy_era_start + "T00:00:00Z").getTime() / 1000)
      : null;
    if (eraStart) {
      const maxV = bars.reduce((m, b) => Math.max(m, b.value), 0);
      const topY = Math.ceil(maxV / 10) * 10;
      const eraSeries = chart.addAreaSeries({
        topColor: "rgba(47,125,82,0.08)",
        bottomColor: "rgba(47,125,82,0.02)",
        lineColor: "rgba(47,125,82,0)",
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      const eraData = bars
        .filter(b => b.time >= eraStart)
        .map(b => ({ time: b.time, value: topY }));
      if (eraData.length > 0) eraSeries.setData(eraData);
    }

    // Marker on the latest bar
    const last = bars[bars.length - 1];
    const subtitle = $("vix-chart-subtitle");
    if (subtitle) {
      subtitle.textContent = `last ${last.value} · ${new Date(last.time * 1000).toISOString().slice(0,10)}`;
    }

    chart.timeScale().fitContent();
    window.addEventListener("resize", () => {
      chart.applyOptions({ width: container.clientWidth });
    });
  }

  async function load() {
    try {
      const resp = await fetch(URL + "?t=" + Date.now(), { cache: "no-store" });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      const r = await resp.json();
      renderPanel(r);
      renderVixChart(r);
    } catch (e) {
      console.error("regime.json load failed", e);
      $("regime-verdict").textContent = "load failed";
      $("edge-badge").textContent = "edge —";
    }
  }

  document.addEventListener("DOMContentLoaded", load);
})();
