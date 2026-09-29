/*! Page one — headline board. Reads brief.json -> headlines (composed by
 *  headlines.py). Lead headline + deck, three wire sub-heads, the ear, the
 *  weather and the corrections box. All text from the feed goes in via
 *  textContent; only the URL is attribute-bound, and only after a scheme check.
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
  function safeU(u) {
    if (!u) return null;
    try {
      var p = new URL(String(u), window.location.origin);
      return (p.protocol === "https:" || p.protocol === "http:") ? p.href : null;
    } catch (e) { return null; }
  }

  function render(brief) {
    var h = brief.headlines, root = $("headlines");
    if (!root) return;
    root.replaceChildren();
    if (!h || h.status !== "ok" || !h.lead) {
      root.appendChild(el("p", { class: "hl-note" }, ["Page one is being set. " + ((h && h.error) || "")]));
      return;
    }
    var ear = $("ear-note");
    if (ear && h.ear) ear.textContent = "“" + h.ear + "”";
    // Masthead ear: the weather's first sentence. Issue number: day of the year.
    var ew = $("ear-weather");
    if (ew && h.weather) ew.textContent = String(h.weather).split(/(?<=\.)\s/)[0];
    var iss = $("issue-no");
    if (iss && h.date_et) {
      var d = new Date(h.date_et + "T12:00:00Z"), y0 = Date.UTC(d.getUTCFullYear(), 0, 0);
      iss.textContent = "No. " + Math.floor((d - y0) / 864e5);
    }

    var lead = h.lead;
    // Stacked decks, as an old front page set them: the deck's first sentence
    // becomes a second headline in small caps, the rest runs as body copy.
    var parts = String(lead.deck || "").split(/(?<=\.)\s+/);
    var subdeck = parts.length > 1 ? parts[0] : null;
    var body = parts.length > 1 ? parts.slice(1).join(" ") : parts[0];
    root.setAttribute("data-tone", lead.tone || "range");
    var leadNode = el("div", { class: "hl-lead" }, [
      el("span", { class: "hl-kicker" }, [lead.kicker || ""]),
      el("h2", { class: "hl-head" }, [lead.headline || ""]),
      el("div", { class: "hl-rule", "aria-hidden": "true" }, []),
      subdeck ? el("p", { class: "hl-subdeck" }, [subdeck]) : null,
      subdeck ? el("div", { class: "hl-rule hl-rule-short", "aria-hidden": "true" }, []) : null,
      el("p", { class: "hl-deck" }, [body]),
      el("p", { class: "hl-jump" }, [el("a", { href: "#nq-section" }, ["Continued in The Week Ahead, below"])]),
      h.notice ? el("p", { class: "hl-notice" }, [h.notice]) : null,
      h.desk_line ? el("p", { class: "hl-desk" }, [h.desk_line]) : null
    ]);

    var subs = el("div", { class: "hl-subs" }, (h.subheads || []).map(function (s) {
      var u = safeU(s.url);
      var head = u
        ? el("a", { href: u, target: "_blank", rel: "noopener noreferrer" }, [s.headline || ""])
        : el("span", {}, [s.headline || ""]);
      return el("div", { class: "hl-sub" }, [
        el("span", { class: "wire-tag", "data-tag": s.tag || "BOTH" }, [s.tag || "BOTH"]),
        el("span", { class: "hl-sub-head" }, [head]),
        el("span", { class: "hl-sub-why" }, [(s.driver || "") + (s.source ? " · " + s.source : "")])
      ]);
    }));
    if (!(h.subheads || []).length) subs.appendChild(el("p", { class: "hl-note" }, ["No qualifying wire stories in the last 24h."]));

    var side = el("aside", { class: "hl-side" }, [
      el("div", { class: "hl-box" }, [
        el("span", { class: "k" }, ["Weather"]),
        el("p", {}, [h.weather || "—"])
      ]),
      el("div", { class: "hl-box" }, [
        el("span", { class: "k" }, ["Corrections"]),
        el("p", {}, [h.correction || "—"])
      ]),
      el("div", { class: "hl-box" }, [
        el("span", { class: "k" }, ["Inside"]),
        el("p", {}, [
          el("a", { href: "analyst.html" }, ["The Strategy Desk"]),
          " · the 90-day book, who is live, who is benched, and who is asking for a comeback. ",
          el("a", { href: "week-ahead.html" }, ["The Week Ahead"]),
          " · the master analysis."
        ])
      ])
    ]);

    root.appendChild(leadNode);
    root.appendChild(el("div", { class: "hl-below" }, [subs, side]));
  }

  document.addEventListener("brief:loaded", function (e) { render(e.detail); });
  if (window.__brief) render(window.__brief);
})();
