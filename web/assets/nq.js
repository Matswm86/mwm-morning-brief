/*! NQ analyzer → The Week Ahead.
 *  Two entry points, one file:
 *    #nq-section  (front page)  — lead board from brief.json → nq (built by fetchers/nq_analyzer.py)
 *    #wa-root     (week-ahead.html) — the full edition from nq/weekahead-latest.json (schema weekahead.v1)
 *  Honesty rules:
 *    1. A stale run (builder says stale=true: >30 h old on a weekday) greys the board and says so.
 *    2. If the analyst layer failed, the board still renders (rule labels + watchdog verdicts) and says so.
 *    3. Every analyst sentence carries its fact chips; the chips link to the provenance table.
 *    4. The audit verdict of the second model is always shown, never hidden.
 *  Advisory only: Mats flips the QuantCrawler switch, not this page.
 */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);

  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      if (k === "class") n.className = attrs[k];
      else if (k === "html") n.innerHTML = attrs[k];
      else if (k === "on") for (const ev in attrs[k]) n.addEventListener(ev, attrs[k][ev]);
      else if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    }
    for (const c of kids.flat()) {
      if (c == null || c === false) continue;
      n.append(c.nodeType ? c : document.createTextNode(String(c)));
    }
    return n;
  }

  const callClass = (w) => (/CHOP/.test(w) ? "amber" : /UP/.test(w) ? "green" : /DOWN/.test(w) ? "red" : "faint");
  const gateClass = (w) => (/REDUCED|HALF/.test(w) ? "amber" : /STOP|SKIP/.test(w) ? "red" : /RUN/.test(w) ? "green" : "faint");
  const auditClass = (v) => (v === "PASS" ? "green" : v === "REVISE" ? "amber" : v === "FAIL" ? "red" : "faint");
  const dayNames = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" };

  function chips(facts) {
    return (facts || []).map((f) => {
      const id = String(f).replace(/^[fh]-/, "");
      const isH = /^h-/.test(String(f));
      return el("a", { class: "nq-chip", href: "#" + f, title: isH ? "headline " + id : "fact " + id }, (isH ? "H:" : "F:") + id);
    });
  }

  function weekRange(mon, fri) {
    if (!mon) return "";
    const a = new Date(mon + "T00:00:00"), b = new Date((fri || mon) + "T00:00:00");
    const same = a.getMonth() === b.getMonth();
    return a.toLocaleDateString("en-US", { month: "long", day: "numeric" }) + " – " +
      b.toLocaleDateString("en-US", same ? { day: "numeric" } : { month: "long", day: "numeric" }) + ", " + b.getFullYear();
  }

  function fmtGen(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleString("en-GB", { timeZone: "Europe/Oslo", weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) + " Oslo";
    } catch (e) { return iso; }
  }

  function fmtUsd(n) {
    if (n == null || isNaN(n)) return "—";
    return (n < 0 ? "−$" : "$") + Math.abs(Math.round(n)).toLocaleString("en-US");
  }

  function auditLine(au) {
    if (!au) return el("span", { class: "nq-audit faint" }, "no second-model audit");
    if (!au.ok) return el("span", { class: "nq-audit red" }, "audit failed — analyst draft shown unaudited");
    const q = au.quality_0_10 != null ? " " + au.quality_0_10 + "/10" : "";
    const n = au.n_issues != null ? au.n_issues : (au.issues || []).length;
    return el("span", { class: "nq-audit " + auditClass(au.verdict) },
      "audited by " + (au.model || "second model") + " · " + (au.verdict || "—") + q +
      (n ? " · " + n + " issue" + (n === 1 ? "" : "s") : "") +
      (au.applied ? " · corrections applied" : (au.verdict === "PASS" ? "" : " · not applied")));
  }

  /* ───────────────────────────── front page ───────────────────────────── */
  function renderFront(brief) {
    const nq = brief.nq;
    const board = $("nq-board"), foot = $("nq-foot"), meta = $("nq-meta");
    if (!nq || nq.status === "unavailable") {
      meta.textContent = nq && nq.error ? "unavailable: " + nq.error : "unavailable";
      return;
    }
    const stale = !!nq.stale;
    const modeWord = nq.mode === "week" ? "week run" : "day run";
    meta.textContent = (stale ? "STALE — " : "") + modeWord + " · " + (nq.run_date || "") +
      (nq.age_hours != null ? " · " + nq.age_hours + " h old" : "") +
      (nq.status === "fallback" ? " · analyst layer off, rule labels only" : "");
    const o = nq.outlook || {};
    const verdicts = nq.strategy_verdicts || [];
    const gates = (inst) => verdicts.filter((v) => v.instrument === inst).map((v) =>
      el("span", { class: "nq-gate " + gateClass(v.word || "") },
        "\u261E " + String(v.name || "").replace(/\s*\(.*\)$/, "") + " — " + (v.word || "—")));

    const mnqCard = el("a", { class: "nq-col nq-col-mnq" + (stale ? " nq-stale" : ""), href: (nq.hrefs || {}).edition || "week-ahead.html" },
      el("div", { class: "nq-col-top" },
        el("span", { class: "nq-sym" }, "MNQ ", el("span", { class: "nq-sym-name" }, "Micro E-mini Nasdaq-100")),
        el("span", { class: "nq-call " + callClass(o.call || "") }, String(o.call || "UNKNOWN").replace(/_/g, " "))),
      el("div", { class: "nq-col-meta" }, "confidence " + (o.confidence || "—") + " · NQ analyzer " + modeWord +
        (o.labels ? " · vol " + (o.labels.vol || "?") + " · trend " + String(o.labels.trend || "?").replace(/_/g, " ").toLowerCase() : "")),
      el("p", { class: "nq-one" }, o.one_line || "—"),
      el("div", { class: "nq-gates" }, gates("MNQ")));

    const mgc = nq.mgc || {};
    const mgcCard = el("a", { class: "nq-col nq-col-mgc" + (stale ? " nq-stale" : ""), href: (nq.hrefs || {}).edition || "week-ahead.html" },
      el("div", { class: "nq-col-top" },
        el("span", { class: "nq-sym" }, "MGC ", el("span", { class: "nq-sym-name" }, "Micro Gold")),
        el("span", { class: "nq-call faint" }, mgc.call || "PENDING")),
      el("div", { class: "nq-col-meta" }, "same fact contract as MNQ · analyzer pending"),
      el("p", { class: "nq-one nq-one-italic" }, mgc.one_line || "MGC analyzer not yet live."),
      el("div", { class: "nq-gates" }, gates("MGC")));

    board.replaceChildren(mnqCard, mgcCard);
    foot.replaceChildren(
      el("span", {}, "analyst " + (nq.analyst_model || "—") + " · check " + (nq.validation || "—") + " · "),
      auditLine(nq.audit),
      el("span", {}, " · generated " + fmtGen(nq.generated_at) + " · advisory only — you flip the switch"));
  }

  /* ───────────────────────────── edition page ─────────────────────────── */
  function h2(title, note) {
    return el("div", { class: "wa-sechead" }, el("span", { class: "eyebrow" }, title), note ? el("span", { class: "eyebrow-soft" }, note) : null);
  }
  function sub(title) { return el("div", { class: "wa-sub" }, title); }

  function pointRow(p) {
    return el("div", { class: "wa-point" }, el("span", { class: "wa-pilcrow" }, "¶"),
      el("div", { class: "wa-point-text" }, p.text, " ", chips(p.facts)));
  }

  function table(t, small) {
    const heads = t.headers || [];
    const wrap = el("div", { class: "wa-tablewrap" });
    const tb = el("table", { class: "wa-table" + (small ? " wa-table-small" : "") });
    if (heads.length) tb.append(el("tr", {}, heads.map((x) => el("th", {}, x))));
    for (const r of t.rows || []) {
      tb.append(el("tr", {}, r.map((c, i) => {
        if (c && typeof c === "object" && !Array.isArray(c)) {
          return el("td", {}, c.href ? el("a", { href: c.href, target: "_blank", rel: "noopener noreferrer" }, c.text) : c.text,
            c.extra ? el("div", { class: "wa-cell-extra" }, c.extra) : null);
        }
        if (Array.isArray(c)) return el("td", {}, chips(c));
        return el("td", { class: i > 0 && /^[−+\-]?[\d.,%]+$/.test(String(c)) ? "num" : "" }, c == null ? "—" : String(c));
      })));
    }
    wrap.append(tb);
    return wrap;
  }

  function equityChart(eq) {
    if (!eq || eq.length < 2) return el("div", { class: "wa-nochart" }, "no equity curve");
    const w = 600, hgt = 130, p = 6;
    const ys = eq.map((e) => e[1]);
    const min = Math.min(0, ...ys), max = Math.max(1, ...ys);
    const X = (i) => p + (w - 2 * p) * i / Math.max(1, eq.length - 1);
    const Y = (v) => hgt - p - (hgt - 2 * p) * (v - min) / ((max - min) || 1);
    const d = "M" + eq.map((e, i) => X(i).toFixed(1) + " " + Y(e[1]).toFixed(1)).join(" L");
    const area = d + " L" + X(eq.length - 1).toFixed(1) + " " + (hgt - p) + " L" + p + " " + (hgt - p) + " Z";
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 " + w + " " + hgt);
    svg.setAttribute("class", "wa-eq");
    const mk = (tag, attrs, text) => { const n = document.createElementNS(ns, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); if (text != null) n.textContent = text; return n; };
    svg.append(mk("path", { d: area, fill: "rgba(37,30,16,0.07)" }));
    svg.append(mk("line", { x1: p, x2: w - p, y1: Y(0), y2: Y(0), stroke: "rgba(37,30,16,0.35)", "stroke-width": 1, "stroke-dasharray": "2 3" }));
    svg.append(mk("path", { d: d, fill: "none", stroke: "#251e10", "stroke-width": 1.4 }));
    svg.append(mk("text", { x: w - p - 2, y: Y(ys[ys.length - 1]) - 6, "text-anchor": "end", "font-size": "22", "font-weight": "700", "font-family": "Courier Prime, monospace", fill: "#2f5d43" }, fmtUsd(ys[ys.length - 1])));
    return svg;
  }

  function strategyCard(v, bt) {
    const name = String(v.name || "").replace(/\s*\(.*\)$/, "");
    const subLine = ((String(v.name || "").match(/\((.*)\)/) || [])[1] || "");
    const kids = [
      el("div", { class: "wa-card-top" },
        el("div", {}, el("div", { class: "wa-card-name" }, name), el("div", { class: "wa-card-sub" }, subLine)),
        el("span", { class: "nq-verdict " + gateClass(v.word || "") }, v.word || "—")),
      el("div", { class: "wa-card-meta" }, "confidence " + (v.confidence || "—") + " · watchdog " + (v.watchdog || "—") + (v.watchdogAsOf ? " (as of " + v.watchdogAsOf + ")" : "")),
      el("p", { class: "wa-card-why" }, v.why || "—", " ", chips(v.whyFacts)),
    ];
    const wos = v.watchoutList || [];
    if (wos.length) {
      kids.push(el("div", {}, el("div", { class: "wa-mini-head" }, "Watch-outs"),
        el("ul", { class: "wa-watchouts" }, wos.map((w) => el("li", {}, w.text, " ", chips(w.facts))))));
    }
    if (bt) {
      const stats = [
        ["Net P&L", fmtUsd(bt.net)], ["Profit factor", bt.pf != null ? String(bt.pf) : "—"],
        ["Win rate", bt.winRate != null ? Math.round(bt.winRate * 100) + "%" : "—"], ["Max drawdown", fmtUsd(bt.maxDD)],
        ["Trades", (bt.trades || "—") + " · " + (bt.sessions || "—") + " sess."], ["Size", "qty " + (bt.qty || "—")]];
      kids.push(el("div", { class: "wa-bt" },
        el("div", { class: "wa-bt-stats" }, stats.map((s) => el("div", {}, el("span", { class: "wa-bt-k" }, s[0]), el("span", { class: "wa-bt-v" }, s[1])))),
        el("div", { class: "wa-bt-chart" }, equityChart(bt.equity)),
        el("div", { class: "wa-bt-cap" }, "Equity, TradingView backtest · " + (bt.strategy || "") + " on " + (bt.instrument || "") + " · " + (bt.from || "?") + " → " + (bt.to || "?") +
          (bt.chartTz ? " · chart tz " + bt.chartTz : "") + (bt.file ? " · " + bt.file : ""))));
    } else {
      kids.push(el("div", { class: "wa-bt-none" }, "Backtest CSV not attached this run — verdict rests on the watchdog and the regime tables alone."));
    }
    return el("article", { class: "wa-card" }, kids);
  }

  function auditSection(au, meta) {
    const box = el("div", { class: "wa-block" }, sub("The Auditor's Notes"));
    if (!au) { box.append(el("p", { class: "wa-note" }, "No second-model audit ran for this draft.")); return box; }
    if (!au.ok) { box.append(el("p", { class: "wa-note red" }, "Audit layer failed: " + (au.error || "unknown") + ". The analyst draft is shown unaudited.")); return box; }
    box.append(el("div", { class: "wa-audit-head" },
      el("span", { class: "nq-verdict " + auditClass(au.verdict) }, au.verdict || "—"),
      el("span", { class: "wa-audit-meta" }, "quality " + (au.quality_0_10 != null ? au.quality_0_10 + "/10" : "—") + " · auditor " + (au.model || "—") +
        " · analyst " + (meta.analyst_model || "—") + " · " + (au.issues || []).length + " issues · " + (au.patchedPaths || []).length + " paths corrected" +
        (au.applied === false && au.unappliedReason ? " · NOT applied: " + au.unappliedReason : ""))));
    if (au.summary) box.append(el("p", { class: "wa-audit-summary" }, au.summary));
    const chk = au.checks || {};
    const keys = Object.keys(chk);
    if (keys.length) box.append(el("div", { class: "wa-checks" }, keys.map((k) =>
      el("span", { class: "wa-check " + (chk[k] === "PASS" ? "green" : "red") }, k.replace(/_/g, " ") + " " + chk[k]))));
    if ((au.issues || []).length) {
      box.append(table({ headers: ["Severity", "Where", "Problem", "Evidence", "Fix"],
        rows: au.issues.map((i) => [i.severity, i.where, i.problem,
          (String(i.evidence || "").match(/\[[FH]:[^\]]+\]/g) || []).map((x) => x[1].toLowerCase() + "-" + x.slice(3, -1)), i.fix]) }, true));
    }
    if ((au.materialMissed || []).length) {
      box.append(el("div", { class: "wa-mini-head" }, "Material the draft left out"));
      box.append(el("ul", { class: "wa-watchouts" }, au.materialMissed.map((m) => el("li", {}, m.text, " ", chips(m.facts)))));
    }
    if (au.draftOutlook && au.draftOutlook !== (meta._finalCall || au.draftOutlook)) {
      box.append(el("p", { class: "wa-note" }, "The auditor changed the outlook call: draft " + au.draftOutlook + " → printed " + meta._finalCall + "."));
    }
    return box;
  }

  function collapsible(title, count, build) {
    const body = el("div", { class: "wa-fold-body", hidden: "" });
    let built = false;
    const mark = el("span", { class: "wa-mark" }, "\u261E");
    const head = el("div", { class: "wa-fold-head", on: { click: () => {
      const open = body.hasAttribute("hidden");
      if (open && !built) { body.append(build()); built = true; }
      if (open) body.removeAttribute("hidden"); else body.setAttribute("hidden", "");
      mark.textContent = open ? "\u261F" : "\u261E";
    } } }, mark, "\u00a0\u00a0", title, count != null ? el("span", { class: "wa-fold-count" }, " — " + count) : null);
    return el("div", { class: "wa-fold" }, head, body);
  }

  function renderEdition(d) {
    const root = $("wa-root");
    const meta = d.meta || {};
    const mnq = d.mnq || {}, mgc = d.mgc || {};
    meta._finalCall = mnq.call;
    $("wa-dateline").textContent = "Week of " + weekRange(meta.week_monday, meta.week_friday);
    $("wa-genline").textContent = (meta.eyebrow || "") + (meta.mode === "day" ? " · this is the DAY run of " + meta.run_date + " (the week call is refreshed each morning)" : "");
    document.title = (meta.title || "The Week Ahead") + " · The Morning Brief";

    const verdicts = d.strategyVerdicts || [];
    const gateLine = (inst) => verdicts.filter((v) => v.instrument === inst).map((v) =>
      el("span", { class: "nq-gate " + gateClass(v.word || "") }, String(v.name || "").replace(/\s*\(.*\)$/, "") + " — " + (v.word || "—")));

    /* Master call */
    const master = el("section", { class: "wa-section" }, h2("The Master Call", "one verdict per instrument · regime, calendar and strategy gates folded in"),
      el("div", { class: "wa-two" },
        el("div", { class: "wa-half" },
          el("div", { class: "wa-inst" }, el("span", { class: "wa-inst-sym" }, "MNQ"), el("span", { class: "wa-inst-name" }, "Micro E-mini Nasdaq-100")),
          el("div", { class: "wa-bigcall " + callClass(mnq.call || "") }, String(mnq.call || "UNKNOWN").replace(/_/g, " ")),
          el("div", { class: "wa-callmeta" }, "confidence " + (mnq.confidence || "—") + " · NQ analyzer " + (meta.mode || "") + " run" + (mnq.status === "fallback" ? " · ANALYST LAYER OFF — rule labels only" : "")),
          el("p", { class: "wa-lede" }, mnq.oneLiner || "—"),
          el("div", { class: "wa-chips" }, chips(mnq.oneLinerFacts)),
          el("div", { class: "wa-range" }, "Expected week range: " + (mnq.expectedRange || "UNKNOWN") + " ", chips(mnq.expectedRangeFacts)),
          el("div", { class: "wa-gateline" }, "Strategy gates · ", gateLine("MNQ"))),
        el("div", { class: "wa-half wa-half-right" },
          el("div", { class: "wa-inst" }, el("span", { class: "wa-inst-sym" }, "MGC"), el("span", { class: "wa-inst-name" }, "Micro Gold")),
          el("div", { class: "wa-bigcall faint" }, mgc.call || "PENDING"),
          el("div", { class: "wa-callmeta" }, "same fact contract as MNQ · analyzer pending"),
          el("p", { class: "wa-lede wa-lede-italic" }, mgc.oneLiner || "—"),
          el("div", { class: "wa-gateline" }, "Strategy gate · ", gateLine("MGC")))));

    /* Why + flips */
    const why = el("section", { class: "wa-section" }, h2("Why This Call, and What Flips It", "the 3-6 facts behind the verdict · measurable conditions that would change it"),
      el("div", { class: "wa-two" },
        el("div", { class: "wa-half" }, sub("Why"), (mnq.why || []).map(pointRow)),
        el("div", { class: "wa-half wa-half-right" }, sub("Flips if"), (mnq.flipsIf || []).map(pointRow))));

    /* Day by day */
    const dayRows = (mnq.days || []).map((p) => {
      const i = p.text.indexOf(":");
      let label = i > 0 ? p.text.slice(0, i) : "";
      const note = i > 0 ? p.text.slice(i + 1).trim() : p.text;
      const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      label = label.replace(/\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b/g, (m) => dayNames[m])
        .replace(/\b\d{4}-(\d{2})-(\d{2})\b/g, (m, mo, dd) => "· " + months[parseInt(mo, 10) - 1] + " " + parseInt(dd, 10));
      return el("div", { class: "wa-day" }, el("div", { class: "wa-day-label" }, label), el("div", {}, el("span", { class: "wa-day-note" }, note), " ", chips(p.facts)));
    });
    const days = el("section", { class: "wa-section" }, h2("The Week, Day by Day", "bias, history and the tape's appointments"),
      dayRows.length ? dayRows : el("p", { class: "wa-note" }, "No day-by-day lines in this run."));

    /* Strategies */
    const bts = d.backtests || {};
    const btFor = (v) => (v.key === "qcs" ? bts.mnq : v.key === "mnq" ? bts.qcTrendMnq : v.key === "mgc" ? bts.mgc : null);
    const strat = el("section", { class: "wa-section" }, h2("Strategies · Run or Stop", "edge watchdog + regime tables → verdict · the TradingView backtest beneath each"),
      el("div", { class: "wa-cards" }, verdicts.map((v) => strategyCard(v, btFor(v)))));

    /* Inside the analysis */
    const reasoning = d.reasoning || {};
    const inside = el("section", { class: "wa-section" }, h2("Inside the Analysis", "the auditor's notes, the analyst's reasoning, the regime board, and every table behind the call"));
    inside.append(auditSection(d.audit, meta));
    const rb = el("div", { class: "wa-block" }, sub("The Analyst's Reasoning"), el("div", { class: "wa-meta" }, reasoning.meta || ""));
    for (const b of reasoning.blocks || []) {
      rb.append(el("div", { class: "wa-reason" }, el("div", { class: "wa-q" }, b.q),
        b.verdict ? el("div", { class: "wa-verdict" }, b.verdict, " ", chips(b.verdictFacts)) : null,
        (b.points || []).map(pointRow)));
    }
    inside.append(rb);
    inside.append(el("div", { class: "wa-block" }, sub("The Regime Board"),
      el("div", { class: "wa-tiles" }, (d.regimeTiles || []).map((t) => el("div", { class: "wa-tile" },
        el("div", { class: "wa-tile-l" }, t.label), el("div", { class: "wa-tile-n" }, t.name),
        (t.rows || []).map((r) => el("div", { class: "wa-tile-row" }, el("span", {}, r[0]), el("span", { class: "mono" }, r[1]))))))));
    const mx = d.matrix || {};
    inside.append(el("div", { class: "wa-block" }, sub("Confirmation Matrix"), el("p", { class: "wa-note" }, mx.intro || ""),
      table({ headers: mx.headers, rows: (mx.rows || []).map((r) => r.slice(0, 3).concat([{ text: r[3] }])) })));
    const cal = d.calendar || {}, earn = d.earnings || {};
    inside.append(el("div", { class: "wa-block" }, sub("This Week's Calendar & Earnings"),
      el("div", { class: "wa-two" },
        el("div", { class: "wa-half" }, el("div", { class: "wa-mini-head" }, "Scheduled macro"), table(cal, true)),
        el("div", { class: "wa-half wa-half-right" }, el("div", { class: "wa-mini-head" }, "NDX constituents reporting"), table(earn, true))),
      el("div", { class: "wa-note" }, d.calendarFoot || "")));

    /* Back pages */
    const back = el("section", { class: "wa-section" }, h2("The Back Pages", "unfold a section with the manicule · every number carries a source"));
    const t10 = d.top10 || {};
    back.append(collapsible("Ten Most Influential Nasdaq-100 Companies", null, () => el("div", {}, el("p", { class: "wa-note" }, t10.intro || ""),
      table({ headers: t10.headers, rows: (t10.rows || []).map((r) => r.slice(0, 8).concat(r[8] && r[8].length ? [r[8]] : [])) }, true))));
    const news = d.news || {};
    back.append(collapsible("News Audit — Headlines Weighted for MNQ Relevance", (news.rows || []).length + " headlines", () => {
      const wrap = el("div", {}, el("p", { class: "wa-note" }, news.intro || ""));
      for (const r of news.rows || []) {
        const hd = r[4] && typeof r[4] === "object" ? r[4] : { text: r[4] };
        wrap.append(el("div", { class: "wa-news", id: "h-" + String(r[0]).replace(/^H:/, "") },
          el("span", { class: "wa-news-w" }, r[1] + "\u00a0" + r[2]),
          el("div", {}, hd.href ? el("a", { href: hd.href, target: "_blank", rel: "noopener noreferrer" }, hd.text) : el("span", {}, hd.text),
            el("div", { class: "wa-news-meta" }, r[0] + " · " + r[3] + " · " + r[5] + (r[6] ? " — " + r[6] : "") + (hd.extra ? " · " + hd.extra : "")))));
      }
      return wrap;
    }));
    const hist = d.history || {};
    back.append(collapsible("NQ Behaviour Under Similar Conditions", (hist.tables || []).length + " tables", () => el("div", {}, el("p", { class: "wa-note" }, hist.intro || ""),
      (hist.tables || []).map((t) => el("div", { class: "wa-hist" }, el("div", { class: "wa-mini-head" }, t.title), table(t, true))))));
    back.append(collapsible("Your Strategies Under Those Conditions", (d.strategyHistory || []).length + " strategies", () => el("div", {},
      (d.strategyHistory || []).map((g) => el("div", { class: "wa-hist" }, el("div", { class: "wa-card-name" }, g.title), el("div", { class: "wa-meta" }, g.meta),
        el("div", { class: "wa-hist-grid" }, (g.tables || []).map((t) => el("div", {}, el("div", { class: "wa-mini-head" }, t.title), table(t, true)))))))));
    const facts = d.facts || [];
    back.append(collapsible("Provenance — All Facts, Sources & As-Of Stamps", facts.length + " facts", () => {
      const wrap = el("div", {}, el("p", { class: "wa-note" }, d.provenanceNote || ""));
      const tb = el("table", { class: "wa-table wa-table-small" }, el("tr", {}, ["id", "value", "source", "as of", "note"].map((x) => el("th", {}, x))));
      for (const f of facts) tb.append(el("tr", { id: "f-" + f.id, class: f.ok === false ? "wa-fact-failed" : "" },
        el("td", { class: "mono" }, f.id), el("td", { class: "mono" }, f.value), el("td", { class: "wa-src" }, f.source), el("td", { class: "mono" }, f.asof), el("td", { class: "wa-note-cell" }, f.note)));
      wrap.append(el("div", { class: "wa-tablewrap" }, tb));
      return wrap;
    }));

    root.replaceChildren(master, why, days, strat, inside, back);
    $("wa-foot-left").textContent = (d.schema || "weekahead.v1") + " · " + facts.length + " facts · " + (meta.run_date || "") + " · " + (meta.mode || "");
    // if the URL carries a #f-… anchor, open provenance so the target exists
    if (location.hash && /^#[fh]-/.test(location.hash)) {
      const folds = root.querySelectorAll(".wa-fold-head");
      folds.forEach((f) => { if (/Provenance|News Audit/.test(f.textContent)) f.click(); });
      setTimeout(() => { const t = document.querySelector(CSS.escape ? "#" + CSS.escape(location.hash.slice(1)) : location.hash); if (t) t.scrollIntoView(); }, 50);
    }
    document.addEventListener("click", (ev) => {
      const a = ev.target.closest && ev.target.closest("a.nq-chip");
      if (!a) return;
      const id = a.getAttribute("href").slice(1);
      const folds = root.querySelectorAll(".wa-fold-head");
      folds.forEach((f) => { if ((/^f-/.test(id) && /Provenance/.test(f.textContent)) || (/^h-/.test(id) && /News Audit/.test(f.textContent))) { const b = f.nextElementSibling; if (b.hasAttribute("hidden")) f.click(); } });
    });
  }

  if ($("nq-section")) {
    fetch("brief.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(renderFront)
      .catch((e) => { $("nq-meta").textContent = "brief.json unavailable (" + e + ")"; });
  }
  if ($("wa-root")) {
    let url = new URLSearchParams(location.search).get("data") || "nq/weekahead-latest.json";
    if (!/^nq\/weekahead-[\w-]+\.json$/.test(url)) url = "nq/weekahead-latest.json"; // dated editions only, same dir
    fetch(url, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject("HTTP " + r.status)))
      .then(renderEdition)
      .catch((e) => { $("wa-root").replaceChildren(el("p", { class: "wa-note red" }, "Could not load the week-ahead fact pack: " + e)); });
  }
})();
