/* plotly_timeline.js — interactive timeline using vendored Plotly.
 *
 * The build step (scripts.case_map_build) emits a renderer-agnostic
 * Plotly figure spec under /api/timeline. This module passes that spec
 * straight to Plotly.newPlot, then wires marker clicks back to the
 * drilldown panel via window.CaseMap.showTimelineMarker.
 */
(function () {
  "use strict";

  function render(payload) {
    if (typeof Plotly === "undefined") {
      const root = document.getElementById("timeline");
      if (root) root.textContent = "timeline library failed to load";
      return;
    }
    const root = document.getElementById("timeline");
    if (!root) return;
    if (!payload || !payload.figure || !payload.figure.data || !payload.figure.data.length) {
      root.textContent = "(no timeline events)";
      return;
    }
    const fig = payload.figure;
    Plotly.newPlot(root, fig.data, fig.layout, fig.config || {}).then((gd) => {
      gd.on("plotly_click", (ev) => {
        if (!ev || !ev.points || !ev.points.length) return;
        const idx = ev.points[0].customdata;
        if (typeof idx !== "number") return;
        const marker = (payload.markers || [])[idx];
        if (marker && window.CaseMap && window.CaseMap.showTimelineMarker) {
          window.CaseMap.showTimelineMarker(marker);
        }
      });
    });
  }

  window.CaseMap = window.CaseMap || {};
  window.CaseMap.timeline = { render: render };
})();
