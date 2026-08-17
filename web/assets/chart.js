/*! Live price charts — MNQ + MGC, uses lightweight-charts.
 *  MNQ reads bars_mnq.json, MGC reads bars_mgc.json (both refreshed by
 *  mwm-brief-bars-refresh.timer from TopstepX via project-x-py).
 *  Polls every 60s.
 */
(function () {
  if (typeof LightweightCharts === 'undefined') return;

  const THEME = {
    layout: {
      background: { type: 'solid', color: '#f2ecdf' },
      textColor: '#56503f',
      fontFamily: '"Spline Sans Mono", ui-monospace, monospace',
    },
    grid: {
      vertLines: { color: 'rgba(33,29,20,0.07)' },
      horzLines: { color: 'rgba(33,29,20,0.07)' },
    },
    rightPriceScale: { borderColor: 'rgba(33,29,20,0.22)' },
    timeScale: { borderColor: 'rgba(33,29,20,0.22)', timeVisible: true, secondsVisible: false },
    crosshair: { mode: 0 },
    height: 340,
  };

  function fmt(n) {
    return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function setupChart(cfg) {
    const container = document.getElementById(cfg.containerId);
    if (!container) return;
    const section = document.getElementById(cfg.sectionId);
    const last = document.getElementById(cfg.lastId);
    const updated = document.getElementById(cfg.updatedId);

    let chart = null, candles = null, volume = null;

    function ensureChart() {
      if (chart) return;
      chart = LightweightCharts.createChart(container, THEME);
      candles = chart.addCandlestickSeries({
        upColor: '#2c6b4c', downColor: '#a23423',
        borderVisible: false,
        wickUpColor: '#2c6b4c', wickDownColor: '#a23423',
      });
      volume = chart.addHistogramSeries({
        priceFormat: { type: 'volume' },
        priceScaleId: '',
        scaleMargins: { top: 0.82, bottom: 0 },
        color: 'rgba(33,29,20,0.28)',
      });
      window.addEventListener('resize', () => {
        chart.applyOptions({ width: container.clientWidth });
      });
    }

    async function load() {
      try {
        const resp = await fetch(cfg.url, { cache: 'no-store' });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        if (!data.bars || !data.bars.length) {
          if (!cfg.optional) last.textContent = 'no data';
          return;
        }
        if (section && section.hidden) section.hidden = false;
        ensureChart();
        // lightweight-charts draws epoch seconds as UTC. Shift each bar by the
        // viewer's local offset so the axis reads local wall-clock (Oslo for Mats):
        // bars are 11:05 UTC = 13:05 Oslo, and the axis must say 13:05.
        const toLocal = (t) => t - new Date(t * 1000).getTimezoneOffset() * 60;
        const bars = data.bars.map(b => ({ ...b, time: toLocal(b.time) }));
        candles.setData(bars);
        volume.setData(bars.map(b => ({
          time: b.time,
          value: b.volume,
          color: b.close >= b.open ? 'rgba(44,107,76,0.35)' : 'rgba(162,52,35,0.35)',
        })));
        chart.timeScale().fitContent();

        const lastBar = data.bars[data.bars.length - 1];
        const prev = data.prev_close || lastBar.open;
        const chg = lastBar.close - prev;
        const pct = (chg / prev) * 100;
        const sign = chg >= 0 ? '+' : '';
        last.textContent = `${fmt(lastBar.close)}  (${sign}${fmt(chg)} / ${sign}${pct.toFixed(2)}%)`;
        last.style.color = chg >= 0 ? '#2c6b4c' : '#a23423';

        if (data.generated_at) {
          const d = new Date(data.generated_at);
          updated.textContent = 'updated ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        }
        const srcEl = document.getElementById(cfg.sourceId);
        if (srcEl) {
          const feed = data.source === 'project-x-py' ? 'TopstepX' : 'Yahoo';
          srcEl.textContent = `${feed} · ${cfg.label} · ${data.interval || '5m'}`;
        }
      } catch (e) {
        if (cfg.optional) return; // reserved for feeds not yet live
        last.textContent = 'fetch failed';
        console.error(cfg.url + ' chart load failed', e);
      }
    }

    load();
    setInterval(load, 60 * 1000);
  }

  setupChart({
    containerId: 'mnq-chart', sectionId: 'chart-section-mnq',
    lastId: 'chart-last-mnq', updatedId: 'chart-updated-mnq',
    sourceId: 'chart-source-mnq', label: 'MNQ',
    url: 'bars_mnq.json', optional: false,
  });
  setupChart({
    containerId: 'mgc-chart', sectionId: 'chart-section-mgc',
    lastId: 'chart-last-mgc', updatedId: 'chart-updated-mgc',
    sourceId: 'chart-source-mgc', label: 'MGC',
    url: 'bars_mgc.json', optional: false,
  });
})();
