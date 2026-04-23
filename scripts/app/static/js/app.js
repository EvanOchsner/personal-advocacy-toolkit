/* case-map app — boot + shared state.
 *
 * Airgap rule: this file must not reference any external URL. CI greps
 * scripts/app/static/ for `http` / `fetch("http` / `src="http` etc.
 */
(function () {
  "use strict";

  window.CaseMap = window.CaseMap || {};
  const state = (window.CaseMap.state = {
    graph: null,           // {entities, relationships, caption}
    timeline: null,        // {markers}
    selectedEntityId: null,
    entityCache: {},       // id -> drilldown payload
  });

  window.CaseMap.selectEntity = async function selectEntity(id) {
    // Toggle off when clicking the same entity twice.
    if (state.selectedEntityId === id) {
      state.selectedEntityId = null;
      if (window.CaseMap.graph && window.CaseMap.graph.markSelected) {
        window.CaseMap.graph.markSelected(null);
      }
      if (window.CaseMap.timeline && window.CaseMap.timeline.rerenderForSelection) {
        window.CaseMap.timeline.rerenderForSelection();
      }
      return;
    }
    state.selectedEntityId = id;
    if (window.CaseMap.graph && window.CaseMap.graph.markSelected) {
      window.CaseMap.graph.markSelected(id);
    }
    if (window.CaseMap.timeline && window.CaseMap.timeline.rerenderForSelection) {
      window.CaseMap.timeline.rerenderForSelection();
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
    if (window.CaseMap.panel && window.CaseMap.panel.render) {
      window.CaseMap.panel.render(payload);
    }
  };

  window.CaseMap.showTimelineMarker = function showTimelineMarker(marker) {
    if (window.CaseMap.panel && window.CaseMap.panel.renderTimelineMarker) {
      window.CaseMap.panel.renderTimelineMarker(marker);
    }
  };

  async function boot() {
    const [graphRes, timelineRes] = await Promise.all([
      fetch("/api/graph", { headers: { Accept: "application/json" } }),
      fetch("/api/timeline", { headers: { Accept: "application/json" } }),
    ]);
    if (graphRes.ok) {
      state.graph = await graphRes.json();
      if (window.CaseMap.graph && window.CaseMap.graph.render) {
        window.CaseMap.graph.render(state.graph);
      }
    } else {
      document.getElementById("graph").textContent = "failed to load graph";
    }
    if (timelineRes.ok) {
      state.timeline = await timelineRes.json();
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
