/*! Trade Environment panel
 *  Reads brief.json `.trade_guard` block (written daily at 05:30 UTC by
 *  the trade_guard_daily fetcher) and renders verdicts + risk bars +
 *  ORB handoff status.
 */
(function () {
  const URL = "brief.json";
  const $ = (id) => document.getElementById(id);

  const VERDICT_CLASS = {
    PROCEED: "tg-proceed",
    CAUTION: "tg-caution",
    SKIP: "tg-skip",
  };
  const HANDOFF_CLASS = {
    OK: "tg-proceed",
    WARN: "tg-caution",
    CRITICAL: "tg-skip",
    ERROR: "tg-skip",
  };

  function fmtTime(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" }) +
             " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    } catch (e) { return iso; }
  }

  function setVerdict(strat, payload) {
    const v = $("tg-verdict-" + strat);
    const r = $("tg-risk-" + strat);
    const bar = $("tg-bar-" + strat);
    const c = $("tg-concern-" + strat);
    if (!v || !payload) return;

    const verdict = payload.verdict || "—";
    v.textContent = verdict;
    v.className = "tg-verdict tg-badge " + (VERDICT_CLASS[verdict] || "");

    const score = payload.risk_score;
    r.textContent = (score === null || score === undefined) ? "—" : (score + " / 100");
    bar.style.width = (typeof score === "number") ? Math.min(100, Math.max(0, score)) + "%" : "0%";
    bar.className = "tg-risk-fill " + (VERDICT_CLASS[verdict] || "");

    c.textContent = payload.top_concern || "—";
  }

  function renderHandoff(handoff) {
    const pill = $("tg-handoff-pill");
    const line = $("tg-handoff-line");
    if (!handoff || !handoff.status) {
      if (pill) pill.textContent = "handoff —";
      if (line) line.textContent = "ORB handoff: —";
      return;
    }
    if (pill) {
      pill.textContent = "handoff " + handoff.status + " (" + (handoff.verdict || "?") + ")";
      pill.className = "eyebrow-soft " + (HANDOFF_CLASS[handoff.verdict] || "");
    }
    if (line) {
      const age = (handoff.age_h !== null && handoff.age_h !== undefined) ? handoff.age_h.toFixed(1) + "h" : "—";
      const drift = (handoff.price_drift_pct !== null && handoff.price_drift_pct !== undefined)
        ? handoff.price_drift_pct.toFixed(2) + "%"
        : "—";
      line.textContent = "ORB handoff: " + handoff.status + " · age " + age +
                         " · drift " + drift + " · " + (handoff.next_action || "");
    }
  }

  function renderEmpty(msg) {
    ["liqsweep", "orb"].forEach((s) => {
      const v = $("tg-verdict-" + s);
      if (v) v.textContent = "—";
      const c = $("tg-concern-" + s);
      if (c) c.textContent = msg;
    });
  }

  async function load() {
    try {
      const resp = await fetch(URL + "?t=" + Date.now(), { cache: "no-store" });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      const brief = await resp.json();
      const tg = brief.trade_guard;
      if (!tg || !tg.per_strategy) {
        renderEmpty("trade_guard block missing");
        return;
      }
      setVerdict("liqsweep", tg.per_strategy.liqsweep);
      setVerdict("orb", tg.per_strategy.orb);
      renderHandoff(tg.orb_handoff || {});
      const upd = $("tg-updated");
      if (upd) upd.textContent = "updated " + fmtTime(tg.generated_at);
      const src = $("tg-source");
      if (src && tg.source) src.textContent = tg.source.replace("trade_guard.", "");
    } catch (e) {
      console.error("trade_guard panel load failed", e);
      renderEmpty("load failed");
    }
  }

  document.addEventListener("DOMContentLoaded", load);
})();
