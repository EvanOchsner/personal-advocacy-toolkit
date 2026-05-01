/* case-map app — boot + shared state.
 *
 * Airgap rule: this file must not reference any external URL. CI greps
 * scripts/app/static/ for `http` / `fetch("http` / `src="http` etc.
 * (vendor/ is excluded — see static/vendor/README.md).
 */
(function () {
  "use strict";

  window.CaseMap = window.CaseMap || {};
  const state = (window.CaseMap.state = {
    dashboard: null,       // {central_issue, parties, references, adjudicators}
    timeline: null,        // {figure, markers, tracks}
    selectedEntityId: null,
    entityCache: {},       // id -> drilldown payload
  });

  window.CaseMap.selectEntity = async function selectEntity(id) {
    if (state.selectedEntityId === id) {
      state.selectedEntityId = null;
      if (window.CaseMap.dashboard && window.CaseMap.dashboard.markSelected) {
        window.CaseMap.dashboard.markSelected(null);
      }
      return;
    }
    state.selectedEntityId = id;
    if (window.CaseMap.dashboard && window.CaseMap.dashboard.markSelected) {
      window.CaseMap.dashboard.markSelected(id);
    }
    let payload = state.entityCache[id];
    if (!payload) {
      const res = await fetch("/api/entity/" + encodeURIComponent(id), {
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        console.warn("entity fetch failed", id, res.status);
        return;
      }
      payload = await res.json();
      state.entityCache[id] = payload;
    }
    if (window.CaseMap.panel && window.CaseMap.panel.renderEntity) {
      window.CaseMap.panel.renderEntity(payload);
    }
  };

  window.CaseMap.showTimelineMarker = function showTimelineMarker(marker) {
    if (window.CaseMap.panel && window.CaseMap.panel.renderTimelineMarker) {
      window.CaseMap.panel.renderTimelineMarker(marker);
    }
  };

  window.CaseMap.showReference = function showReference(card) {
    if (window.CaseMap.panel && window.CaseMap.panel.renderReference) {
      window.CaseMap.panel.renderReference(card);
    }
  };

  window.CaseMap.showAdjudicator = function showAdjudicator(card) {
    if (window.CaseMap.panel && window.CaseMap.panel.renderAdjudicator) {
      window.CaseMap.panel.renderAdjudicator(card);
    }
  };

  async function boot() {
    const [dashRes, tlRes] = await Promise.all([
      fetch("/api/dashboard", { headers: { Accept: "application/json" } }),
      fetch("/api/timeline", { headers: { Accept: "application/json" } }),
    ]);
    if (dashRes.ok) {
      state.dashboard = await dashRes.json();
      if (window.CaseMap.dashboard && window.CaseMap.dashboard.render) {
        window.CaseMap.dashboard.render(state.dashboard);
      }
    } else {
      const central = document.getElementById("central-issue");
      if (central) central.textContent = "failed to load dashboard";
    }
    if (tlRes.ok) {
      state.timeline = await tlRes.json();
      if (window.CaseMap.timeline && window.CaseMap.timeline.render) {
        window.CaseMap.timeline.render(state.timeline);
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
