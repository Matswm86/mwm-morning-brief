/*! MNQ live chart — uses lightweight-charts
 *  Fetches /bars_mnq.json (written by fetchers/bars.py) and renders
 *  a candlestick chart with volume histogram below.
 *  Polls every 60s to pick up fresh bars when the bar-refresh cron runs.
 */
(function () {
  const container = document.getElementById('mnq-chart');
  if (!container || typeof LightweightCharts === 'undefined') return;

  // Theme aligned with the rest of the morning-brief (warm cream + umber)
  const chart = LightweightCharts.createChart(container, {
    layout: {
      background: { type: 'solid', color: '#F9F5EC' },
      textColor: '#3B2F2F',
      fontFamily: 'Inter, system-ui, sans-serif',
    },
    grid: {
      vertLines: { color: 'rgba(59,47,47,0.08)' },
      horzLines: { color: 'rgba(59,47,47,0.08)' },
    },
    rightPriceScale: { borderColor: 'rgba(59,47,47,0.20)' },
    timeScale: {
      borderColor: 'rgba(59,47,47,0.20)',
      timeVisible: true,
      secondsVisible: false,
    },
    crosshair: { mode: 0 },
    height: 340,
  });

  const candles = chart.addCandlestickSeries({
    upColor: '#2F7D52', downColor: '#C8553D',
    borderVisible: false,
    wickUpColor: '#2F7D52', wickDownColor: '#C8553D',
  });
  const volume = chart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: '',
    scaleMargins: { top: 0.82, bottom: 0 },
    color: 'rgba(59,47,47,0.30)',
  });

  // Legend element
  const last = document.getElementById('chart-last');
  const updated = document.getElementById('chart-updated');

  function fmt(n) {
    return n.toLocaleString('en-US', {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
  }

  async function load() {
    try {
      const resp = await fetch('bars_mnq.json?t=' + Date.now(), { cache: 'no-store' });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      if (!data.bars || !data.bars.length) {
        last.textContent = 'no data';
        return;
      }
      candles.setData(data.bars);
      volume.setData(data.bars.map(b => ({
        time: b.time,
        value: b.volume,
        color: b.close >= b.open ? 'rgba(47,125,82,0.35)' : 'rgba(200,85,61,0.35)',
      })));
      chart.timeScale().fitContent();

      const lastBar = data.bars[data.bars.length - 1];
      const prev = data.prev_close || lastBar.open;
      const chg = lastBar.close - prev;
      const pct = (chg / prev) * 100;
      const sign = chg >= 0 ? '+' : '';
      last.textContent =
        `${fmt(lastBar.close)}  (${sign}${fmt(chg)} / ${sign}${pct.toFixed(2)}%)`;
      last.style.color = chg >= 0 ? '#2F7D52' : '#C8553D';

      if (data.generated_at) {
        const d = new Date(data.generated_at);
        updated.textContent = 'updated ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
      }
    } catch (e) {
      last.textContent = 'fetch failed';
      console.error('MNQ chart load failed', e);
    }
  }

  // Initial load + 60s polling (bar-refresh cron writes every 5 min during mkt hours)
  load();
  setInterval(load, 60 * 1000);

  // Resize handling
  window.addEventListener('resize', () => {
    chart.applyOptions({ width: container.clientWidth });
  });
})();
