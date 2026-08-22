/*! Regime Lens v1 — the 09:25 ET (15:25 Oslo) pre-open read.
 *  Draws brief.json -> lens. Two pre-registered survivors only: next-RTH range
 *  regime (Target B) and PDH/PDL first-touch draw geometry (Target C').
 *  Direction is not on this panel and never will be; it was measured and failed.
 *  That history stays in FINDINGS.md, not on a public page.
 *  The DOL card emits NO CALL on the 39.3% of sessions that open outside the
 *  prior day's range: there the first touch is settled at the open and scoring
 *  it would report 99.8% for nothing. When it does call, it quotes 77.6%
 *  (n=635), never the 87.4% artifact. No innerHTML from feed data.
 */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };

  function el(tag, attrs, children) {
    var n = document.createElement(tag), k;
    attrs = attrs || {};
    for (k in attrs) if (Object.prototype.hasOwnProperty.call(attrs, k)) n.setAttribute(k, attrs[k]);
    (children || []).forEach(function (c) {
      n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return n;
  }
  function pct(x) { return x == null ? "—" : (Math.round(x * 1000) / 10) + "%"; }
  function num(x) { return x == null ? "—" : Number(x).toLocaleString("en-GB"); }
  function atr(x) { return x == null ? "—" : (Math.round(x * 1000) / 1000) + " ATR"; }

  function row(label, value, note) {
    var r = el("div", { class: "lens-row" }, [
      el("span", { class: "k" }, [label]),
      el("span", { class: "v" }, [value])
    ]);
    if (note) r.appendChild(el("span", { class: "n" }, [note]));
    return r;
  }

  function volCard(v) {
    if (!v || v.status !== "ok") {
      return el("div", { class: "lens-card" }, [el("p", { class: "lens-none" }, ["range read unavailable"])]);
    }
    var cls = v.call === "WIDE" ? "is-green" : "is-red";
    var c = el("div", { class: "lens-card" }, [
      el("div", { class: "lens-top" }, [
        el("span", { class: "lens-sym" }, ["TODAY'S RANGE"]),
        el("span", { class: "lens-call " + cls }, [v.call || "—"])
      ]),
      el("p", { class: "lens-meaning" }, [v.meaning || ""])
    ]);
    if (v.track_record) {
      c.appendChild(row("track record", pct(v.track_record.hit_rate),
        "over " + v.track_record.years + " years"));
    }
    return c;
  }

  function dolCard(g) {
    if (!g || g.status !== "ok") {
      return el("div", { class: "lens-card" }, [el("p", { class: "lens-none" }, ["level read unavailable"])]);
    }
    var can = !!g.callable;
    var c = el("div", { class: "lens-card" }, [
      el("div", { class: "lens-top" }, [
        el("span", { class: "lens-sym" }, ["WHICH LEVEL FIRST"]),
        el("span", { class: "lens-call " + (can ? "is-green" : "is-unknown") }, [can ? (g.call || "—") : "NO CALL"])
      ]),
      el("p", { class: "lens-meaning" }, [g.meaning || ""])
    ]);
    c.appendChild(row("yesterday's high", num(g.pdh), null));
    c.appendChild(row("yesterday's low", num(g.pdl), null));
    c.appendChild(row("price at the read", num(g.px_0924), null));
    if (can) c.appendChild(row("track record", pct(g.acc_inside_5y), "over five years"));
    if (g.basis) c.appendChild(el("p", { class: "lens-caveat" }, [g.basis]));
    return c;
  }

  function render(L) {
    var meta = $("lens-meta"), grid = $("lens-grid"), foot = $("lens-foot"), badge = $("lens-status");
    if (!grid) return;
    if (!L || L.status !== "ok") {
      if (meta) meta.textContent = "unavailable";
      grid.appendChild(el("p", { class: "lens-none" }, [(L && L.error) || "no lens artifact"]));
      return;
    }
    if (meta) {
      meta.textContent = (L.session || "—") + " · read at " +
        (L.decision_time_oslo || "15:25") + " Oslo" + (L.stale ? " · stale" : "");
    }
    if (badge) {
      badge.textContent = L.lens_status || "—";
      badge.setAttribute("data-flag", L.lens_status === "LIVE" && !L.stale ? "green" : "unknown");
    }
    grid.appendChild(volCard(L.vol_regime));
    grid.appendChild(dolCard(L.dol_draw));
    if (foot) foot.textContent = L.caveat || "";
  }

  function boot() {
    fetch("brief.json", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (b) { render(b && b.lens); })
      .catch(function () { render(null); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
