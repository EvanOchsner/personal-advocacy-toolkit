/* timeline.js — vanilla SVG horizontal timeline renderer.
 *
 * Data model: array of markers, each
 *   { date: "YYYY-MM-DD", kind, source, title, summary, entity_ids, ref }
 *
 * Layout:
 *   - X = linear interpolation between min and max dates in the set.
 *   - Y = one of three lanes: event (top), correspondence (mid),
 *         deadline (bottom).
 *   - Shape: circle for events, square for correspondence, diamond
 *            for deadlines.
 *   - Colour: the selected entity's colour when selected and the
 *             marker touches that entity; otherwise grey.
 *   - Hover: native SVG <title> tooltip (works offline, no JS lib).
 *   - Click: calls window.CaseMap.showTimelineMarker(marker).
 */
(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const LANE_Y = { event: 45, correspondence: 85, deadline: 125 };
  const LANE_LABELS = {
    event: "events.yaml",
    correspondence: "correspondence",
    deadline: "deadlines",
  };
  const MARGIN = { left: 60, right: 30, top: 20, bottom: 30 };

  function svg(tag, attrs, children) {
    const el = document.createElementNS(SVG_NS, tag);
    if (attrs) for (const k of Object.keys(attrs)) el.setAttribute(k, attrs[k]);
    if (children) for (const c of children) el.appendChild(c);
    return el;
  }

  function parseDate(s) {
    // ISO YYYY-MM-DD → Date (UTC midnight to keep tick math stable).
    const [y, m, d] = s.split("-").map(Number);
    return Date.UTC(y, m - 1, d);
  }

  function fmtMonthYear(ts) {
    const d = new Date(ts);
    return d.toLocaleString("en-US", {
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    });
  }

  function markerShape(kind, x, y, fill) {
    if (kind === "event") {
      return svg("circle", { cx: x, cy: y, r: 7, fill });
    }
    if (kind === "correspondence") {
      return svg("rect", {
        x: x - 6,
        y: y - 6,
        width: 12,
        height: 12,
        fill,
      });
    }
    if (kind === "deadline") {
      // Diamond via rotated square.
      return svg("rect", {
        x: x - 6,
        y: y - 6,
        width: 12,
        height: 12,
        transform: `rotate(45 ${x} ${y})`,
        fill,
      });
    }
    return svg("circle", { cx: x, cy: y, r: 5, fill });
  }

  function render(payload) {
    const container = document.getElementById("timeline");
    if (!container) return;
    container.innerHTML = "";
    const markers = (payload && payload.markers) || [];
    if (!markers.length) {
      const note = document.createElement("p");
      note.className = "timeline-empty";
      note.textContent =
        "No timeline markers. Add events to events.yaml, or pass " +
        "--correspondence-manifest to the server.";
      container.appendChild(note);
      return;
    }

    const rect = container.getBoundingClientRect();
    const width = Math.max(700, rect.width || 900);
    const height = 180;
    const xStart = MARGIN.left;
    const xEnd = width - MARGIN.right;

    const timestamps = markers.map((m) => parseDate(m.date));
    const minT = Math.min(...timestamps);
    const maxT = Math.max(...timestamps);
    const span = Math.max(1, maxT - minT);

    function xFor(ts) {
      if (span === 0) return (xStart + xEnd) / 2;
      return xStart + ((ts - minT) / span) * (xEnd - xStart);
    }

    const root = svg("svg", {
      viewBox: `0 0 ${width} ${height}`,
      preserveAspectRatio: "xMidYMid meet",
      role: "img",
      "aria-label": "case timeline",
    });

    // Lane labels.
    for (const lane of Object.keys(LANE_Y)) {
      const y = LANE_Y[lane];
      root.appendChild(
        svg(
          "text",
          {
            x: 8,
            y: y + 4,
            class: "timeline-lane-label",
          },
          [document.createTextNode(LANE_LABELS[lane])]
        )
      );
      root.appendChild(
        svg("line", {
          x1: xStart,
          y1: y,
          x2: xEnd,
          y2: y,
          class: "timeline-lane",
        })
      );
    }

    // Axis ticks — one per unique year/month present.
    const tickSet = new Set();
    for (const ts of timestamps) {
      const d = new Date(ts);
      tickSet.add(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));
    }
    const axisY = height - MARGIN.bottom + 10;
    for (const ts of Array.from(tickSet).sort()) {
      const x = xFor(ts);
      root.appendChild(
        svg("line", {
          x1: x,
          y1: MARGIN.top,
          x2: x,
          y2: axisY - 8,
          class: "timeline-tick",
        })
      );
      root.appendChild(
        svg(
          "text",
          { x, y: axisY, class: "timeline-tick-label" },
          [document.createTextNode(fmtMonthYear(ts))]
        )
      );
    }

    // Markers.
    const state = (window.CaseMap && window.CaseMap.state) || {};
    const graph = state.graph || {};
    const selectedId = state.selectedEntityId;
    const entityColor = {};
    for (const e of graph.entities || []) entityColor[e.id] = e.color;

    for (const m of markers) {
      const ts = parseDate(m.date);
      const x = xFor(ts);
      const laneKind =
        m.kind === "event" || m.kind === "deadline" || m.kind === "correspondence"
          ? m.kind
          : "event";
      const y = LANE_Y[laneKind];

      let fill = "#999";
      let dim = false;
      if (selectedId) {
        if ((m.entity_ids || []).indexOf(selectedId) !== -1) {
          fill = entityColor[selectedId] || "#222";
        } else {
          fill = "#bbb";
          dim = true;
        }
      } else {
        // When nothing is selected, colour by lane for quick readability.
        fill =
          laneKind === "event"
            ? "#27a"
            : laneKind === "correspondence"
            ? "#2a7"
            : "#a22";
      }

      const shape = markerShape(laneKind, x, y, fill);
      shape.classList.add("timeline-marker");
      if (dim) shape.setAttribute("opacity", "0.4");
      const tip = `${m.date} — ${m.title}` +
        (m.summary ? `\n${m.summary}` : "") +
        (m.entity_ids && m.entity_ids.length
          ? `\nentities: ${m.entity_ids.join(", ")}`
          : "");
      shape.appendChild(svg("title", {}, [document.createTextNode(tip)]));
      shape.addEventListener("click", () => {
        if (window.CaseMap && window.CaseMap.showTimelineMarker) {
          window.CaseMap.showTimelineMarker(m);
        }
      });
      root.appendChild(shape);
    }

    container.appendChild(root);
  }

  function rerenderForSelection() {
    const payload = (window.CaseMap && window.CaseMap.state.timeline) || null;
    if (payload) render(payload);
  }

  window.CaseMap = window.CaseMap || {};
  window.CaseMap.timeline = { render, rerenderForSelection };
})();
