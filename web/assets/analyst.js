/*! The Strategy Desk — analyst column. Reads book.json (fetchers/book.py).
 *  Three parts: the live pair (90-day book), the bench (candidates with a
 *  comeback question), the retired (with the same question, answered).
 *  Every number on the page comes from the feed; the column prose is
 *  assembled from those numbers with fixed sentences. No innerHTML from data.
 */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };

  function el(tag, attrs, children) {
    var n = document.createElement(tag), k;
    attrs = attrs || {};
    for (k in attrs) if (Object.prototype.hasOwnProperty.call(attrs, k)) n.setAttribute(k, attrs[k]);
    (children || []).forEach(function (c) {
      if (c == null) return;
      n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return n;
  }
  function usd(n) {
    if (n == null || isNaN(n)) return "—";
    return (n < 0 ? "−$" : "$") + Math.abs(Math.round(n)).toLocaleString("en-US");
  }
  function pct(x) { return x == null ? "—" : x + "%"; }
  function num(x) { return x == null ? "—" : String(x); }
  function verdictClass(w) {
    return /CLEARS/.test(w) ? "green" : /BELOW|NO LOSSES/.test(w) ? "amber" : /LOSING/.test(w) ? "red" : "faint";
  }

  /* closed-trade equity sparkline as inline SVG, no library */
  function spark(series, w, h) {
    w = w || 320; h = h || 64;
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    svg.setAttribute("class", "ad-spark");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "closed-trade equity curve");
    if (!series || series.length < 2) return svg;
    var min = Math.min.apply(null, series.concat([0])), max = Math.max.apply(null, series.concat([0]));
    if (max === min) max = min + 1;
    var sx = function (i) { return (i / (series.length - 1)) * (w - 2) + 1; };
    var sy = function (v) { return h - 1 - ((v - min) / (max - min)) * (h - 2); };
    var zero = document.createElementNS("http://www.w3.org/2000/svg", "line");
    zero.setAttribute("x1", 0); zero.setAttribute("x2", w);
    zero.setAttribute("y1", sy(0)); zero.setAttribute("y2", sy(0));
    zero.setAttribute("class", "ad-spark-zero");
    svg.appendChild(zero);
    var d = series.map(function (v, i) { return (i ? "L" : "M") + sx(i).toFixed(1) + " " + sy(v).toFixed(1); }).join(" ");
    var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    path.setAttribute("class", "ad-spark-line " + (series[series.length - 1] >= 0 ? "up" : "down"));
    svg.appendChild(path);
    return svg;
  }

  function statRow(k, v, n) {
    return el("div", { class: "preopen-row" }, [
      el("span", { class: "k" }, [k]),
      el("span", { class: "v" }, [v]),
      el("span", { class: "n" }, [n || ""])
    ]);
  }

  function statsBlock(s, bar) {
    if (!s || !s.trades) return el("p", { class: "wa-note" }, ["No closed trades in this window."]);
    var rows = [
      statRow("trades", num(s.trades), s.from + " → " + s.to + " · " + s.trading_days + " trading days"),
      statRow("win rate", pct(s.win_rate_pct), "bar " + bar.win_rate_pct + "%"),
      statRow("profit factor", num(s.profit_factor), "bar " + bar.profit_factor),
      statRow("net", usd(s.net_usd), usd(s.per_day_usd) + " per trading day · " + s.trades_per_day + " trades/day"),
      statRow("avg win / loss", usd(s.avg_win_usd) + " / " + usd(s.avg_loss_usd), "expectancy " + usd(s.expectancy_usd) + " per trade"),
      statRow("max drawdown", usd(-s.max_dd_usd), "closed-trade equity, peak to trough"),
      statRow("worst trade", usd(s.biggest_loss_usd), "worst day " + usd((s.worst_day || {}).usd) + " on " + ((s.worst_day || {}).date || "—")),
      statRow("best day", usd((s.best_day || {}).usd), (s.best_day || {}).date || "—")
    ];
    return el("div", { class: "preopen-rows" }, rows);
  }

  /* The column's own sentences, from the numbers. */
  function prose(e) {
    var s = e.last_90d || {}, f = e.full || {}, v = e.verdict || {};
    var out = [];
    if (e.role === "live") {
      out.push("Over the last " + s.trading_days + " trading days this export closed " + s.trades + " trades and netted " + usd(s.net_usd) +
        " at " + (e.export_size_contracts || 1) + " contract" + ((e.export_size_contracts || 1) === 1 ? "" : "s") +
        ", " + usd(s.per_day_usd) + " a day, with a worst day of " + usd((s.worst_day || {}).usd) + ".");
      out.push("Win rate " + pct(s.win_rate_pct) + ", profit factor " + num(s.profit_factor) + ", deepest drawdown " + usd(-s.max_dd_usd) +
        ". The full export (" + f.from + " to " + f.to + ", " + f.trades + " trades) reads PF " + num(f.profit_factor) + " and " + usd(f.net_usd) + ".");
      out.push(v.line || "");
    } else {
      out.push("On the desk's 90-day window: " + s.trades + " trades, win rate " + pct(s.win_rate_pct) + ", profit factor " + num(s.profit_factor) +
        ", net " + usd(s.net_usd) + " with a " + usd(-s.max_dd_usd) + " drawdown and a worst single trade of " + usd(s.biggest_loss_usd) + ".");
      out.push(v.line || "");
      if (v.comeback) out.push(v.comeback);
    }
    return out.filter(Boolean);
  }

  function card(e, bar) {
    var v = e.verdict || {};
    var head = el("div", { class: "wa-card-top" }, [
      el("span", { class: "wa-card-name" }, [e.name, el("span", { class: "ad-version" }, [" " + (e.version || "")])]),
      el("span", { class: "nq-verdict " + verdictClass(v.word || "") }, [v.word || "—"])
    ]);
    var meta = el("div", { class: "wa-meta" }, [
      e.instrument + " · " + (e.role === "live" ? "LIVE · " + (e.live_size || "") : e.role.toUpperCase()) +
      " · export " + (e.export_date || "?") + " · " + (e.export_size_contracts || "?") + "ct in the log"
    ]);
    if (e.status !== "ok") {
      return el("article", { class: "wa-card ad-card" }, [head, meta, el("p", { class: "wa-note" }, [e.error || "no export"])]);
    }
    var p = prose(e).map(function (t, i) { return el("p", { class: "ad-p" + (i === 0 ? " ad-drop" : "") }, [t]); });
    return el("article", { class: "wa-card ad-card" }, [
      head, meta,
      el("p", { class: "ad-note" }, [e.note || ""]),
      el("div", { class: "ad-body" }, [
        el("div", { class: "ad-prose" }, p),
        el("div", { class: "ad-stats" }, [
          el("div", { class: "wa-sub" }, ["Last 90 days"]),
          statsBlock(e.last_90d, bar),
          el("div", { class: "wa-bt-cap" }, ["Closed-trade equity, full export " + ((e.full || {}).from || "?") + " → " + ((e.full || {}).to || "?")]),
          spark((e.full || {}).spark)
        ])
      ])
    ]);
  }

  function h2(title, note) {
    return el("div", { class: "wa-sechead" }, [el("span", { class: "eyebrow" }, [title]), note ? el("span", { class: "eyebrow-soft" }, [note]) : null]);
  }

  function leadPara(b) {
    var live = b.live || [], ok = live.filter(function (e) { return e.status === "ok"; });
    if (!ok.length) return el("p", { class: "ad-lede" }, ["The live book has no exports on file."]);
    var names = ok.map(function (e) { return e.name + " on " + e.instrument; }).join(" and ");
    var net = ok.reduce(function (a, e) { return a + ((e.last_90d || {}).net_usd || 0); }, 0);
    var worst = Math.min.apply(null, ok.map(function (e) { return ((e.last_90d || {}).worst_day || {}).usd || 0; }));
    var clears = ok.every(function (e) { return (e.verdict || {}).word === "CLEARS THE BAR"; });
    return el("p", { class: "ad-lede" }, [
      "The paper runs two strategies, one contract each, on one account: " + names + ". " +
      "Their 90-day trade logs sum to " + usd(net) + " of backtest net with a worst single day of " + usd(worst) + ". " +
      (clears ? "Both clear the house bar. " : "Not both clear the house bar; see the cards. ") +
      "Below them sits the bench, and below the bench the retired, each asked the same question: is there a way back?"
    ]);
  }

  function render(b) {
    var root = $("ad-root");
    root.replaceChildren();
    if (!b || b.status !== "ok") {
      root.appendChild(el("p", { class: "wa-note" }, ["The desk has no book to show: " + ((b && b.error) || "book.json unavailable")]));
      return;
    }
    var bar = b.bar || { win_rate_pct: 62, profit_factor: 1.4 };
    $("ad-genline").textContent = "Book compiled " + (b.generated_at || "") + " · " + (b.fill_basis || "");
    try {
      $("ad-dateline").textContent = new Date(b.generated_at).toLocaleDateString("en-GB", { weekday: "long", year: "numeric", month: "long", day: "numeric" });
    } catch (e) { /* leave blank */ }
    $("ad-foot-right").textContent = "house bar: win rate ≥ " + bar.win_rate_pct + "% and PF ≥ " + bar.profit_factor + " together · window " + b.window_days + " days";

    root.appendChild(el("section", { class: "wa-section ad-top" }, [
      h2("The live book", "one contract each · one 50K account"),
      leadPara(b),
      el("div", { class: "wa-cards" }, (b.live || []).map(function (e) { return card(e, bar); }))
    ]));
    root.appendChild(el("section", { class: "wa-section" }, [
      h2("The bench", "candidates with a fill check, not a deployment"),
      el("p", { class: "ad-lede" }, ["Two models the desk audited this month and did not deploy. The question for each is not \"does it make money on paper\"; most things do. It is whether its worst day fits inside a 50K account's daily loss limit with room to be wrong twice."]),
      el("div", { class: "wa-cards" }, (b.bench || []).map(function (e) { return card(e, bar); }))
    ]));
    root.appendChild(el("section", { class: "wa-section" }, [
      h2("The retired", "can any of them come back?"),
      el("p", { class: "ad-lede" }, ["The former main strategy, its gold partner, and the research arc that ended in a null. Retired is not dead; a strategy comes back when a new export clears the bar on a window it has not seen. Until then they sit here, where the paper can keep an eye on them."]),
      el("div", { class: "wa-cards" }, (b.retired || []).map(function (e) { return card(e, bar); }))
    ]));
    root.appendChild(el("section", { class: "wa-section ad-fine" }, [
      h2("How to read this page"),
      el("p", { class: "ad-p" }, ["Every figure is a TradingView strategy-tester fill at the contract size in the export; the live book is traded at one contract regardless of the export size. Win rate and profit factor are judged together against the house bar; a sub-year backtest that fails either reads \"below the bar\", and the number is printed anyway. Drawdown is closed-trade equity, so an open-trade excursion can be worse. Nothing on this page places, sizes, or stops a trade. The reader flips the switch, not the paper."])
    ]));
  }

  fetch("book.json", { cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(render)
    .catch(function () { render(null); });
})();
