/* panel.js — drilldown side panel renderer.
 *
 * Renders only fields present in the payload. If a field is missing
 * (e.g. notes_file not declared), the section is simply absent — we
 * never fabricate a placeholder that a reader could mistake for
 * case content.
 */
(function () {
  "use strict";

  function el(tag, attrs, children) {
    const e = document.createElement(tag);
    if (attrs) {
      for (const k of Object.keys(attrs)) {
        if (k === "text") {
          e.textContent = attrs[k];
        } else if (k === "html") {
          e.innerHTML = attrs[k];  // only used with server-sanitized HTML
        } else {
          e.setAttribute(k, attrs[k]);
        }
      }
    }
    if (children) for (const c of children) e.appendChild(c);
    return e;
  }

  function formatValue(v) {
    if (v === null || v === undefined) return "";
    if (typeof v === "string" || typeof v === "number") return String(v);
    if (Array.isArray(v)) {
      return v.map(formatValue).filter(Boolean).join(", ");
    }
    if (typeof v === "object") {
      return Object.entries(v)
        .map(([k, val]) => `${k}: ${formatValue(val)}`)
        .join(" · ");
    }
    return String(v);
  }

  function renderResolved(resolved) {
    if (!resolved || typeof resolved !== "object") return null;
    const keys = Object.keys(resolved);
    if (!keys.length) return null;
    const dl = el("dl", { class: "panel-resolved" });
    for (const k of keys) {
      const val = formatValue(resolved[k]);
      if (!val) continue;
      dl.appendChild(el("dt", { text: k }));
      dl.appendChild(el("dd", { text: val }));
    }
    return dl;
  }

  function renderRelList(rels, direction) {
    if (!rels || !rels.length) return null;
    const ul = el("ul", { class: "panel-rel-list" });
    for (const r of rels) {
      const peer = direction === "out" ? r.to : r.from;
      const arrow = direction === "out" ? "→" : "←";
      const txt = `${arrow} ${peer} (${r.kind})` +
        (r.summary ? ` — ${r.summary}` : "");
      ul.appendChild(el("li", { text: txt }));
    }
    return ul;
  }

  function renderEvents(events) {
    if (!events || !events.length) return null;
    const ul = el("ul", { class: "panel-event-list" });
    for (const ev of events) {
      const txt = `${ev.date} — ${ev.title}` +
        (ev.summary ? ` (${ev.summary})` : "");
      ul.appendChild(el("li", { text: txt }));
    }
    return ul;
  }

  function section(heading, child) {
    if (!child) return null;
    const s = el("section", { class: "panel-section" });
    s.appendChild(el("h3", { text: heading }));
    s.appendChild(child);
    return s;
  }

  function render(payload) {
    const panel = document.getElementById("panel");
    if (!panel) return;
    panel.innerHTML = "";

    const header = el("header", { class: "panel-header" });
    header.appendChild(el("h2", { text: payload.display_name }));
    header.appendChild(
      el("span", {
        class: "panel-role-chip role-" + payload.role,
        text: payload.role,
      })
    );
    panel.appendChild(header);

    if (payload.labels && payload.labels.length) {
      const ul = el("ul", { class: "panel-labels" });
      payload.labels.forEach((lab) =>
        ul.appendChild(el("li", { text: lab }))
      );
      panel.appendChild(ul);
    }

    const resolved = renderResolved(payload.resolved);
    const resolvedSection = section("From case-facts.yaml", resolved);
    if (resolvedSection) panel.appendChild(resolvedSection);

    if (payload.notes_html) {
      const notes = el("div", {
        class: "panel-notes",
        html: payload.notes_html,   // server already sanitized via _markdown.py
      });
      const sec = el("section", { class: "panel-section" });
      sec.appendChild(el("h3", { text: "Notes" }));
      sec.appendChild(notes);
      panel.appendChild(sec);
    }

    const relOut = renderRelList(payload.relationships_out, "out");
    const relOutSec = section("Relationships (outbound)", relOut);
    if (relOutSec) panel.appendChild(relOutSec);

    const relIn = renderRelList(payload.relationships_in, "in");
    const relInSec = section("Relationships (inbound)", relIn);
    if (relInSec) panel.appendChild(relInSec);

    const events = renderEvents(payload.events);
    const eventsSec = section("Events touching this entity", events);
    if (eventsSec) panel.appendChild(eventsSec);

    const footer = el("p", {
      class: "panel-empty-note",
      text: payload.disclaimer || "",
    });
    panel.appendChild(footer);
  }

  window.CaseMap = window.CaseMap || {};
  window.CaseMap.panel = { render: render };
})();
