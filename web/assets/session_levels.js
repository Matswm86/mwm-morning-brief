/*! Session liquidity pools on the MNQ chart.
 *
 *  Draws the high and the low of each of the last N completed sessions as a
 *  horizontal price line. Sessions are Mats's own Oslo blocks, produced by
 *  fetchers/session_levels.py:
 *      Asia 02:00-07:00 · London 09:00-15:30 · New York 15:30-22:00
 *
 *  Only closed sessions produce levels, and a level is removed outright once
 *  price trades back to it: the resting orders are filled, so it is no longer
 *  a pool. What stays on the chart is only what is still untaken.
 *
 *  Colours are the dataviz categorical slots 1/2/7 (blue, orange, violet),
 *  chosen so they stay separable AFTER the .price-chart sepia filter and
 *  never collide with the green/red candles. Validated all-pairs on the
 *  post-filter surface #fff4e0: worst CVD deltaE 13.6 deutan, normal-vision
 *  15.2. The orange sits at 2.96:1 contrast, just under the 3:1 gate, so the
 *  legend chips and the level table below the chart are required relief.
 *  Do not remove them.
 */
(function () {
  const URL = 'session_levels_mnq.json';
  const CHART_KEY = 'MNQ';
  const STORE_KEY = 'mwm.pools.v2';
  const COUNTS = [5, 10, 15, 20, 30];

  const SESSIONS = {
    asia: { label: 'Asia', short: 'ASIA', color: '#2a78d6' },
    london: { label: 'London', short: 'LDN', color: '#eb6834' },
    ny: { label: 'New York', short: 'NY', color: '#4a3aa7' },
  };

  const DEFAULTS = {
    on: true,
    count: 10,
    fit: true,
    labels: true,
    enabled: { asia: true, london: true, ny: true },
  };

  let state = loadState();
  let payload = null;
  let lines = [];
  let series = null;
  let chartObj = null;

  function loadState() {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      if (!raw) return { ...DEFAULTS, enabled: { ...DEFAULTS.enabled } };
      const s = JSON.parse(raw);
      return {
        on: s.on !== false,
        count: COUNTS.includes(s.count) ? s.count : DEFAULTS.count,
        fit: s.fit !== false,
        labels: s.labels !== false,
        enabled: { ...DEFAULTS.enabled, ...(s.enabled || {}) },
      };
    } catch (e) {
      return { ...DEFAULTS, enabled: { ...DEFAULTS.enabled } };
    }
  }

  function saveState() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(state));
    } catch (e) {
      /* private window or blocked site data — the toggles still work, they
         just do not survive a reload. */
    }
  }

  const fmt = (v) =>
    Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  /** The levels to draw, newest first: one entry per surviving high or low.
   *
   *  A session only qualifies once it has closed — a high that is still being
   *  made is not a level yet. And a level price has already traded back to is
   *  dropped outright rather than dimmed: the resting orders there are filled,
   *  so it is no longer a pool and no longer belongs on the chart. */
  function selection() {
    if (!payload || !payload.sessions) return [];
    const blocks = payload.sessions
      .filter((s) => s.complete && state.enabled[s.session])
      .slice(0, state.count);
    const out = [];
    blocks.forEach((b) => {
      if (!b.high_swept) out.push({ block: b, side: 'high', price: b.high });
      if (!b.low_swept) out.push({ block: b, side: 'low', price: b.low });
    });
    return out;
  }

  function clearLines() {
    if (!series) return;
    lines.forEach((l) => {
      try {
        series.removePriceLine(l.line);
      } catch (e) {
        /* series was recreated under us; the line went with it */
      }
    });
    lines = [];
  }

  function addLine(level) {
    const meta = SESSIONS[level.block.session];
    const day = level.block.date.slice(5); // MM-DD
    lines.push({
      price: level.price,
      color: meta.color,
      // The price line's own `title` only ever renders inside the price-axis
      // label, which buries the scale once several are drawn. So the labels
      // below are drawn as HTML over the pane instead, axis label off.
      text: `${day} ${meta.short} ${level.side === 'high' ? 'H' : 'L'} ${fmt(level.price)}`,
      line: series.createPriceLine({
        price: level.price,
        color: meta.color,
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Solid,
        axisLabelVisible: false,
      }),
    });
  }

  function draw() {
    if (!series || !payload) return;
    clearLines();
    if (state.on) selection().forEach(addLine);
    // Untaken levels are by definition ones price has not reached, so they
    // sit outside the candles' own autoscale almost by construction. Widen
    // the price scale to take them in, or the lines exist but are off-screen.
    series.applyOptions({
      autoscaleInfoProvider: (original) => {
        const base = original();
        if (!state.on || !state.fit || !lines.length) return base;
        const prices = lines.map((l) => l.price);
        let lo = Math.min(...prices);
        let hi = Math.max(...prices);
        if (base && base.priceRange) {
          lo = Math.min(lo, base.priceRange.minValue);
          hi = Math.max(hi, base.priceRange.maxValue);
        }
        return { priceRange: { minValue: lo, maxValue: hi }, margins: { above: 8, below: 8 } };
      },
    });
    if (chartObj) {
      // Surviving levels can sit ~800 points apart on MNQ; the taller pane
      // keeps them from stacking. Give the height back when the scale is
      // only carrying today's candles again.
      chartObj.applyOptions({ height: state.on && state.fit ? 500 : 340 });
    }
    positionLabels();
  }

  // ------------------------------------------------------------------- labels

  /** Price-tag labels drawn as HTML over the chart pane. Right edge first;
   *  a tag that would sit on top of one already placed moves to the left
   *  edge, and if that is taken too it is dropped — the level table below
   *  the chart still lists it. */
  function positionLabels() {
    const layer = document.getElementById('pool-labels');
    if (!layer || !series || !chartObj) return;
    layer.innerHTML = '';
    if (!state.on || !state.labels) return;

    let axisW = 0;
    try {
      axisW = chartObj.priceScale('right').width() || 0;
    } catch (e) {
      axisW = 0;
    }
    const paneH = layer.clientHeight;
    const MIN_GAP = 14;
    const placed = { right: [], left: [] };

    lines
      .map((l) => ({ ...l, y: series.priceToCoordinate(l.price) }))
      .filter((l) => l.y != null && l.y >= 6 && l.y <= paneH - 6)
      .sort((a, b) => a.y - b.y)
      .forEach((l) => {
        const free = (side) => placed[side].every((y) => Math.abs(y - l.y) >= MIN_GAP);
        const side = free('right') ? 'right' : free('left') ? 'left' : null;
        if (!side) return;
        placed[side].push(l.y);

        const tag = el('span', 'pool-tag', l.text);
        tag.style.top = Math.round(l.y) + 'px';
        tag.style.color = l.color;
        if (side === 'right') tag.style.right = Math.round(axisW + 6) + 'px';
        else tag.style.left = '6px';
        layer.appendChild(tag);
      });
  }

  // ---------------------------------------------------------------- controls

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function buildControls() {
    const section = document.getElementById('chart-section-mnq');
    const chartEl = document.getElementById('mnq-chart');
    if (!section || !chartEl || document.getElementById('pool-bar')) return;

    const bar = el('div', 'pool-bar');
    bar.id = 'pool-bar';

    const master = el('button', 'pool-master');
    master.type = 'button';
    function paintMaster() {
      master.textContent = state.on ? 'Pools on' : 'Pools off';
      master.setAttribute('aria-pressed', String(state.on));
      bar.classList.toggle('is-off', !state.on);
    }
    master.addEventListener('click', () => {
      state.on = !state.on;
      saveState();
      paintMaster();
      draw();
      renderTable();
    });
    paintMaster();
    bar.appendChild(master);

    // Session chips double as the legend: identity is never colour alone.
    Object.entries(SESSIONS).forEach(([key, meta]) => {
      const chip = el('button', 'pool-chip');
      chip.type = 'button';
      chip.dataset.session = key;
      const sw = el('span', 'pool-swatch');
      sw.style.background = meta.color;
      chip.appendChild(sw);
      chip.appendChild(el('span', null, meta.label));
      function paint() {
        chip.classList.toggle('is-off', !state.enabled[key]);
        chip.setAttribute('aria-pressed', String(!!state.enabled[key]));
      }
      chip.addEventListener('click', () => {
        state.enabled[key] = !state.enabled[key];
        saveState();
        paint();
        draw();
        renderTable();
      });
      paint();
      bar.appendChild(chip);
    });

    const count = el('select', 'pool-count');
    count.setAttribute('aria-label', 'how many prior sessions to draw');
    COUNTS.forEach((n) => {
      const o = el('option', null, `last ${n}`);
      o.value = String(n);
      if (n === state.count) o.selected = true;
      count.appendChild(o);
    });
    count.addEventListener('change', () => {
      state.count = Number(count.value);
      saveState();
      draw();
      renderTable();
    });
    bar.appendChild(count);

    // Checkbox options. `fit` is the one with a real cost: widening the price
    // scale to reach a 10-session span shrinks today's candles, so it has to
    // be switchable rather than assumed.
    [
      ['fit', 'fit levels'],
      ['labels', 'price tags'],
    ].forEach(([key, text]) => {
      const wrap = el('label', 'pool-opt');
      const box = el('input');
      box.type = 'checkbox';
      box.checked = !!state[key];
      box.addEventListener('change', () => {
        state[key] = box.checked;
        saveState();
        draw();
        renderTable();
      });
      wrap.appendChild(box);
      wrap.appendChild(el('span', null, text));
      bar.appendChild(wrap);
    });

    section.insertBefore(bar, chartEl);

    // Label layer sits over the chart canvas; pointer-events off so the
    // crosshair still works underneath.
    const wrapper = el('div', 'pool-chart-wrap');
    chartEl.parentNode.insertBefore(wrapper, chartEl);
    wrapper.appendChild(chartEl);
    const layer = el('div', 'pool-labels');
    layer.id = 'pool-labels';
    wrapper.appendChild(layer);

    const table = el('div', 'pool-table');
    table.id = 'pool-table';
    section.appendChild(table);
  }

  /** The table view: the same surviving levels the chart draws, in price
   *  order so it reads as a ladder above and below the current price. */
  function renderTable() {
    const host = document.getElementById('pool-table');
    if (!host) return;
    host.innerHTML = '';
    if (!state.on || !payload) return;
    const rows = selection().slice().sort((a, b) => b.price - a.price);
    if (!rows.length) {
      host.appendChild(
        el('p', 'pool-empty', 'Every level in this range has been traded back to. Nothing left to draw.')
      );
      return;
    }

    const t = el('table');
    const head = el('tr');
    ['Level', 'Session', 'Side'].forEach((h) => head.appendChild(el('th', null, h)));
    t.appendChild(head);

    rows.forEach((lv) => {
      const meta = SESSIONS[lv.block.session];
      const tr = el('tr');
      tr.appendChild(el('td', 'pool-px', fmt(lv.price)));

      const name = el('td', 'pool-name');
      const sw = el('span', 'pool-swatch');
      sw.style.background = meta.color;
      name.appendChild(sw);
      name.appendChild(el('span', null, `${lv.block.date.slice(5)} ${meta.label}`));
      tr.appendChild(name);

      tr.appendChild(el('td', 'pool-state', lv.side === 'high' ? 'high' : 'low'));
      t.appendChild(tr);
    });
    host.appendChild(t);

    const defs = payload.session_defs || {};
    const caption = Object.entries(SESSIONS)
      .map(([k, m]) => `${m.label} ${(defs[k] || []).join('-')}`)
      .join(' · ');
    host.appendChild(
      el(
        'p',
        'pool-caption',
        `${caption} Oslo. Only closed sessions count, and a level disappears the ` +
          `moment price trades back to it. Source ${payload.source || 'n/a'}.`
      )
    );
  }

  // ------------------------------------------------------------------- wiring

  async function load() {
    try {
      const resp = await fetch(URL, { cache: 'no-store' });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      payload = await resp.json();
      draw();
      renderTable();
    } catch (e) {
      console.error('session pools load failed', e);
    }
  }

  function attach() {
    const c = window.MWMCharts && window.MWMCharts[CHART_KEY];
    if (!c || series === c.candles) return;
    series = c.candles;
    chartObj = c.chart;
    lines = [];
    buildControls();
    draw();
    renderTable();
    startLabelLoop();
  }

  /** The price scale moves on new bars, on resize, and while the user drags
   *  or zooms it, and lightweight-charts fires no event for that. Rather than
   *  guess at every trigger, recheck each label's y on an animation frame and
   *  only touch the DOM when one has actually moved. */
  let labelLoop = null;
  function startLabelLoop() {
    if (labelLoop) return;
    let lastKey = '';
    const tick = () => {
      labelLoop = requestAnimationFrame(tick);
      if (!series || !state.on || !state.labels || !lines.length) return;
      const layer = document.getElementById('pool-labels');
      if (!layer || !layer.clientHeight) return;
      const key =
        lines
          .map((l) => {
            const y = series.priceToCoordinate(l.price);
            return y == null ? 'x' : Math.round(y);
          })
          .join(',') +
        '|' +
        layer.clientWidth;
      if (key === lastKey) return;
      lastKey = key;
      positionLabels();
    };
    labelLoop = requestAnimationFrame(tick);
  }

  if (typeof LightweightCharts === 'undefined') return;
  window.addEventListener('mwm:chart-ready', (e) => {
    if (!e.detail || e.detail.label === CHART_KEY) attach();
  });
  attach(); // chart.js may already have run
  load();
  setInterval(load, 5 * 60 * 1000); // the fetcher rewrites the JSON every 5 min
})();
