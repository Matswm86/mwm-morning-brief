/*! Pre-open expansion + ORB go/no-go.
 *  Draws brief.json -> preopen. The call comes from the range model already
 *  shipping on this page; nothing here is a direction call and nothing here is
 *  a claim about ORB profitability. Both facts stay visible on the panel.
 *  No innerHTML from feed data.
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
  function pct(x) { return x == null ? "—" : Math.round(x * 100) + "%"; }
  function num(x) { return x == null ? "—" : Math.round(x).toLocaleString("en-GB"); }
  function orbFlag(v) { return v === "GO" ? "green" : v === "NO-GO" ? "red" : "unknown"; }

  function card(code, d) {
    var rng = d.expected_range_pts || {};
    var g = d.grade || null;
    var rows = [
      ["expected range", num(rng.p50) + " pts", "median forecast"],
      ["80% under", num(rng.p80) + " pts", "8 days in 10 land under this"],
      ["vs 26-day median", (d.vs_median == null ? "—" : d.vs_median + "×"), num(d.median26d_pts) + " pts"],
      ["yesterday", num(d.yesterday_pts) + " pts", (d.events || []).join(", ") || "no tier-1 events"]
    ];
    var body = rows.map(function (r) {
      return el("div", { class: "preopen-row" }, [
        el("span", { class: "k" }, [r[0]]),
        el("span", { class: "v" }, [r[1]]),
        el("span", { class: "n" }, [r[2]])
      ]);
    });
    var verdict = d.orb
      ? el("span", { class: "preopen-verdict is-" + orbFlag(d.orb) }, ["ORB " + d.orb])
      : el("span", { class: "preopen-verdict is-none" }, ["range only"]);
    var ry = d.recent_year;
    var note = g && g.hit != null
      ? "Calls at this distance from the median were right " + pct(g.hit) + " of the time ("
        + g.n + " sessions, 2019-2026)."
        + (ry ? " In " + ry.year + " alone: " + pct(ry.expansion_hit) + " expansion, "
            + pct(ry.contraction_hit) + " contraction." : "")
      : "No range forecast for this session.";
    return el("article", { class: "preopen-card" }, [
      el("div", { class: "preopen-top" }, [
        el("span", { class: "preopen-sym" }, [code]),
        el("span", { class: "preopen-call is-" + orbFlag(d.orb) }, [(d.expansion || d.call || "—") + (g ? " · " + g.strength : "")]),
        verdict
      ]),
      el("p", { class: "preopen-meaning" }, [d.meaning || ""]),
      el("div", { class: "preopen-rows" }, body),
      el("p", { class: "preopen-acc" }, [note])
    ]);
  }

  function render(pre) {
    var grid = $("preopen-grid"), badge = $("preopen-orb"), meta = $("preopen-meta");
    if (!grid) return null;
    grid.replaceChildren();
    if (!pre || pre.status !== "ok") {
      meta.textContent = (pre && pre.error) ? pre.error : "unavailable";
      badge.textContent = "ORB —";
      badge.setAttribute("data-flag", "unknown");
      return null;
    }
    var insts = pre.instruments || {}, codes = Object.keys(insts), mnq = insts.MNQ;
    var mnqCard = null;
    codes.forEach(function (c) {
      var node = card(c, insts[c]);
      if (c === "MNQ") mnqCard = node;
      grid.appendChild(node);
    });

    badge.textContent = mnq && mnq.orb ? "ORB " + mnq.orb : "ORB —";
    badge.setAttribute("data-flag", orbFlag(mnq && mnq.orb));
    meta.textContent = "read " + (pre.decision_time_oslo || "08:00") + " Oslo"
      + (mnq && mnq.session ? " · " + mnq.session : "")
      + (pre.stale ? " · STALE (" + pre.age_hours + "h)" : "");
    $("preopen-foot").textContent = (pre.means || "") + " " + (pre.caveat || "");
    return { card: mnqCard, session: mnq && mnq.session };
  }

  /* 08:00 ET update — a second, later read of the same session. Written by the
   * VPS mwm-preopen-update.timer (preopen_update.json, webroot, protected from
   * the builder's --delete). Rendered only when its session matches the base
   * panel's session; absent or stale files change nothing. */
  function renderUpdate(base, u) {
    if (!base || !base.card || !u || u.schema !== "preopen_update.v1") return;
    var d = (u.instruments || {}).MNQ;
    if (!d || d.status !== "ok" || (base.session && u.session !== base.session)) return;
    var g = d.grade || {};
    var o = d.or15 || {};
    var cr = o.ceiling_risk || {};
    var rows = [
      ["updated range", num(d.pred_day_range_pts) + " pts",
        (d.vs_median == null ? "—" : d.vs_median + "×") + " the 26-day median"],
      ["overnight range", num(d.overnight_range_pts) + " pts", "18:00–08:00 ET, observed"],
      ["opening range est.", num(o.pred_pts) + " pts",
        "P(outside " + (o.band || [20, 200]).join("–") + " band) " + pct(cr.p_out_of_band)]
    ].map(function (r) {
      return el("div", { class: "preopen-row" }, [
        el("span", { class: "k" }, [r[0]]),
        el("span", { class: "v" }, [r[1]]),
        el("span", { class: "n" }, [r[2]])
      ]);
    });
    var note = g.hit != null
      ? "Updated calls at this rung were right " + pct(g.hit) + " of the time ("
        + g.n + " sessions, walk-forward 2021–2026)"
        + (g.hit_2026 != null ? "; 2026 alone: " + pct(g.hit_2026) + " (n=" + g.n_2026 + ")." : ".")
      : "";
    var block = el("div", { class: "preopen-update" }, [
      el("div", { class: "preopen-update-top" }, [
        el("span", { class: "preopen-update-tag" }, ["08:00 ET update"]),
        el("span", { class: "preopen-call is-" + orbFlag(d.orb) },
          [(d.expansion || "—") + (g.strength ? " · " + g.strength : "")]),
        el("span", { class: "preopen-verdict is-" + orbFlag(d.orb) }, ["ORB " + (d.orb || "—")])
      ]),
      el("p", { class: "preopen-meaning" }, [d.meaning || ""]),
      el("div", { class: "preopen-rows" }, rows),
      el("p", { class: "preopen-acc" }, [note])
    ]);
    base.card.appendChild(block);
    var badge = $("preopen-orb"), meta = $("preopen-meta");
    if (d.orb) {
      badge.textContent = "ORB " + d.orb;
      badge.setAttribute("data-flag", orbFlag(d.orb));
      meta.textContent = meta.textContent + " · updated 08:00 ET";
    }
  }

  fetch("brief.json", { cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (b) {
      var base = render(b && b.preopen);
      return fetch("preopen_update.json", { cache: "no-store" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (u) { renderUpdate(base, u); })
        .catch(function () {});
    })
    .catch(function () { render(null); });
})();
