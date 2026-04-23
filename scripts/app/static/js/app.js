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
    selectedEntityId: null,
    entityCache: {},       // id -> drilldown payload
  });

  window.CaseMap.selectEntity = async function selectEntity(id) {
    state.selectedEntityId = id;
    if (window.CaseMap.graph && window.CaseMap.graph.markSelected) {
      window.CaseMap.graph.markSelected(id);
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

  async function boot() {
    const res = await fetch("/api/graph", {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) {
      document.getElementById("graph").textContent = "failed to load graph";
      return;
    }
    state.graph = await res.json();
    if (window.CaseMap.graph && window.CaseMap.graph.render) {
      window.CaseMap.graph.render(state.graph);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
