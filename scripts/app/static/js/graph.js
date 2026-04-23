/* graph.js — three-column SVG renderer for case-map entities.
 *
 * Layout is deterministic: columns derived from entity.role, vertical
 * stacking in declaration order. No force layout, no third-party JS.
 */
(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const COLS = {
    self: { x: 0.18, label: "ally" },
    ally: { x: 0.18, label: "ally" },
    neutral: { x: 0.5, label: "neutral" },
    adversary: { x: 0.82, label: "adversary" },
  };
  const NODE_R = 22;
  const ROW_GAP = 80;
  const TOP_GAP = 50;

  function svg(tag, attrs, children) {
    const el = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      for (const k of Object.keys(attrs)) {
        el.setAttribute(k, attrs[k]);
      }
    }
    if (children) {
      for (const c of children) el.appendChild(c);
    }
    return el;
  }

  function layout(entities, width, height) {
    const groups = { self_ally: [], neutral: [], adversary: [] };
    for (const e of entities) {
      if (e.role === "self" || e.role === "ally") groups.self_ally.push(e);
      else if (e.role === "neutral") groups.neutral.push(e);
      else if (e.role === "adversary") groups.adversary.push(e);
    }
    const positions = {};
    function placeColumn(list, xFrac) {
      const x = Math.round(width * xFrac);
      const needed = TOP_GAP + ROW_GAP * list.length;
      const effectiveHeight = Math.max(height, needed);
      list.forEach((e, i) => {
        positions[e.id] = { x, y: TOP_GAP + i * ROW_GAP };
      });
      return effectiveHeight;
    }
    const h1 = placeColumn(groups.self_ally, COLS.ally.x);
    const h2 = placeColumn(groups.neutral, COLS.neutral.x);
    const h3 = placeColumn(groups.adversary, COLS.adversary.x);
    return { positions, height: Math.max(h1, h2, h3) };
  }

  function render(graph) {
    const container = document.getElementById("graph");
    if (!container) return;
    container.innerHTML = "";
    const rect = container.getBoundingClientRect();
    const width = Math.max(600, rect.width || 900);
    const baseHeight = Math.max(400, rect.height || 500);
    const { positions, height } = layout(graph.entities, width, baseHeight);

    container.setAttribute("viewBox", `0 0 ${width} ${height}`);
    container.setAttribute("preserveAspectRatio", "xMidYMid meet");

    // Edges first so nodes render on top.
    const edgeLayer = svg("g", { class: "graph-edges" });
    for (const r of graph.relationships) {
      const a = positions[r.from];
      const b = positions[r.to];
      if (!a || !b) continue;
      const path = svg("line", {
        class: "graph-edge",
        x1: a.x,
        y1: a.y,
        x2: b.x,
        y2: b.y,
      });
      const title = svg("title", {}, [
        document.createTextNode(
          r.kind + (r.summary ? "\n" + r.summary : "")
        ),
      ]);
      path.appendChild(title);
      edgeLayer.appendChild(path);
    }
    container.appendChild(edgeLayer);

    const nodeLayer = svg("g", { class: "graph-nodes" });
    for (const e of graph.entities) {
      const pos = positions[e.id];
      if (!pos) continue;
      const g = svg("g", {
        class: "graph-node",
        "data-entity-id": e.id,
        transform: `translate(${pos.x},${pos.y})`,
        tabindex: "0",
        role: "button",
        "aria-label": e.display_name,
      });
      const circle = svg("circle", {
        r: NODE_R,
        fill: e.color,
      });
      const initials = (e.display_name || e.id)
        .split(/\s+/)
        .map((w) => w[0] || "")
        .join("")
        .slice(0, 2)
        .toUpperCase();
      const iconText = svg(
        "text",
        {
          "text-anchor": "middle",
          "dominant-baseline": "central",
          fill: "#fff",
          "font-weight": "600",
        },
        [document.createTextNode(initials)]
      );
      const label = svg(
        "text",
        {
          "text-anchor": "middle",
          y: NODE_R + 16,
        },
        [document.createTextNode(e.display_name)]
      );
      g.appendChild(circle);
      g.appendChild(iconText);
      g.appendChild(label);
      g.addEventListener("click", () => {
        window.CaseMap.selectEntity(e.id);
      });
      g.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          window.CaseMap.selectEntity(e.id);
        }
      });
      nodeLayer.appendChild(g);
    }
    container.appendChild(nodeLayer);
  }

  function markSelected(id) {
    const nodes = document.querySelectorAll(".graph-node");
    nodes.forEach((n) => {
      if (n.getAttribute("data-entity-id") === id) {
        n.classList.add("selected");
      } else {
        n.classList.remove("selected");
      }
    });
  }

  window.CaseMap = window.CaseMap || {};
  window.CaseMap.graph = { render: render, markSelected: markSelected };
})();
