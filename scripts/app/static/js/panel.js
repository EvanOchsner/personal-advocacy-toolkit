/* panel.js — drilldown side panel renderer.
 *
 * Renders only fields present in the payload. If a field is missing
 * (e.g. notes_file not declared), the section is simply absent — we
 * never fabricate a placeholder a reader could mistake for case content.
 *
 * Three render entry points:
 *   renderEntity(entity)         — party card click
 *   renderTimelineMarker(marker) — Plotly point click
 *   renderReference(card)        — governing-document card click
 *   renderAdjudicator(card)      — adjudicator card click
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
    if (children) for (const c of children) if (c) e.appendChild(c);
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

  function fileLink(rel) {
    const a = document.createElement("a");
    a.href = "/file/" + encodeURI(rel);
    a.textContent = rel;
    a.target = "_blank";
    a.rel = "noopener";
    return a;
  }

  function panelRoot() {
    return document.getElementById("panel");
  }

  function clearPanel() {
    const panel = panelRoot();
    if (panel) panel.innerHTML = "";
    return panel;
  }

  function renderEntity(payload) {
    const panel = clearPanel();
    if (!panel) return;

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

    if (payload.blurb) {
      panel.appendChild(el("p", { class: "panel-blurb", text: payload.blurb }));
    }

    const resolvedSection = section("From case-facts.yaml", renderResolved(payload.resolved));
    if (resolvedSection) panel.appendChild(resolvedSection);

    if (payload.notes_html) {
      const notes = el("div", {
        class: "panel-notes",
        html: payload.notes_html,
      });
      const sec = el("section", { class: "panel-section" });
      sec.appendChild(el("h3", { text: "Notes" }));
      sec.appendChild(notes);
      panel.appendChild(sec);
    }

    const eventsSec = section("Events touching this party", renderEvents(payload.events));
    if (eventsSec) panel.appendChild(eventsSec);

    panel.appendChild(el("p", {
      class: "panel-empty-note",
      text: payload.disclaimer || "",
    }));
  }

  function renderRefs(container, refs) {
    if (!refs) return;
    const groups = [
      ["correspondence", refs.correspondence],
      ["letters", refs.letters],
      ["evidence", refs.evidence],
    ];
    for (const [label, list] of groups) {
      if (!list || !list.length) continue;
      const sec = el("section", { class: "panel-section" });
      sec.appendChild(el("h3", { text: label }));
      const ul = el("ul", { class: "panel-refs-list" });
      for (const p of list) {
        const li = document.createElement("li");
        li.appendChild(fileLink(p));
        ul.appendChild(li);
      }
      sec.appendChild(ul);
      container.appendChild(sec);
    }
  }

  function renderTimelineMarker(marker) {
    const panel = clearPanel();
    if (!panel) return;

    const header = el("header", { class: "panel-header" });
    header.appendChild(el("h2", { text: marker.title || "(untitled)" }));
    header.appendChild(
      el("span", {
        class: "panel-role-chip track-" + (marker.track || "neutral_event"),
        text: marker.track || marker.kind || "event",
      })
    );
    panel.appendChild(header);

    const meta = el("p", { class: "panel-empty-note" });
    meta.textContent = `${marker.date} · source: ${marker.source}`;
    panel.appendChild(meta);

    if (marker.summary) {
      panel.appendChild(el("p", { text: marker.summary }));
    }

    if (marker.entity_ids && marker.entity_ids.length) {
      const sec = el("section", { class: "panel-section" });
      sec.appendChild(el("h3", { text: "Parties" }));
      const ul = el("ul", { class: "panel-event-list" });
      for (const id of marker.entity_ids) {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = id;
        btn.className = "entity-link";
        btn.addEventListener("click", () => {
          if (window.CaseMap && window.CaseMap.selectEntity) {
            window.CaseMap.selectEntity(id);
          }
        });
        li.appendChild(btn);
        ul.appendChild(li);
      }
      sec.appendChild(ul);
      panel.appendChild(sec);
    }

    if (marker.ref && marker.ref.refs) {
      renderRefs(panel, marker.ref.refs);
    }

    if (marker.source === "correspondence" && marker.ref && marker.ref.source_path) {
      const sec = el("section", { class: "panel-section" });
      sec.appendChild(el("h3", { text: "Source" }));
      const ul = el("ul", { class: "panel-refs-list" });
      const li = document.createElement("li");
      li.appendChild(fileLink(marker.ref.source_path));
      ul.appendChild(li);
      sec.appendChild(ul);
      panel.appendChild(sec);
    }

    if (marker.source === "deadlines" && marker.ref) {
      const dl = el("dl", { class: "panel-resolved" });
      for (const k of ["deadline_kind", "clock_starts", "clock_date", "status", "authority_ref", "verify"]) {
        const v = marker.ref[k];
        if (!v) continue;
        dl.appendChild(el("dt", { text: k }));
        dl.appendChild(el("dd", { text: String(v) }));
      }
      const sec = el("section", { class: "panel-section" });
      sec.appendChild(el("h3", { text: "Deadline details" }));
      sec.appendChild(dl);
      panel.appendChild(sec);
    }
  }

  function renderReference(card) {
    const panel = clearPanel();
    if (!panel) return;

    const header = el("header", { class: "panel-header" });
    header.appendChild(el("h2", { text: card.citation || card.title || card.id }));
    header.appendChild(
      el("span", { class: "panel-role-chip", text: card.kind || "reference" })
    );
    panel.appendChild(header);

    if (card.title && card.title !== card.citation) {
      panel.appendChild(el("p", { class: "panel-blurb", text: card.title }));
    }
    if (card.jurisdiction) {
      panel.appendChild(el("p", {
        class: "panel-empty-note",
        text: "jurisdiction: " + card.jurisdiction,
      }));
    }
    if (card.blurb) {
      panel.appendChild(el("p", { text: card.blurb }));
    }

    const links = card.links || {};
    const linkPairs = [
      ["Readable text", links.readable],
      ["Structured JSON", links.structured],
      ["Raw source", links.raw],
    ].filter(([, v]) => Boolean(v));
    if (linkPairs.length) {
      const sec = el("section", { class: "panel-section" });
      sec.appendChild(el("h3", { text: "Local copy" }));
      const ul = el("ul", { class: "panel-refs-list" });
      for (const [label, rel] of linkPairs) {
        const li = document.createElement("li");
        const a = fileLink(rel);
        a.textContent = label + " — " + rel;
        li.appendChild(a);
        ul.appendChild(li);
      }
      sec.appendChild(ul);
      panel.appendChild(sec);
    }

    if (card.source_url) {
      panel.appendChild(el("p", {
        class: "panel-empty-note",
        text: "fetched from: " + card.source_url + " (text on disk; not re-fetched live)",
      }));
    }
  }

  function renderAdjudicator(card) {
    const panel = clearPanel();
    if (!panel) return;

    const header = el("header", { class: "panel-header" });
    header.appendChild(el("h2", { text: card.name }));
    header.appendChild(
      el("span", { class: "panel-role-chip", text: card.kind || "adjudicator" })
    );
    panel.appendChild(header);

    const dl = el("dl", { class: "panel-resolved" });
    for (const k of ["short_name", "case_number", "filed_date", "acknowledged_date", "url", "notes", "source_file"]) {
      const v = card[k];
      if (!v) continue;
      dl.appendChild(el("dt", { text: k }));
      dl.appendChild(el("dd", { text: String(v) }));
    }
    panel.appendChild(dl);
    if (card.source_file) {
      const sec = el("section", { class: "panel-section" });
      sec.appendChild(el("h3", { text: "Source" }));
      const ul = el("ul", { class: "panel-refs-list" });
      const li = document.createElement("li");
      li.appendChild(fileLink(card.source_file));
      ul.appendChild(li);
      sec.appendChild(ul);
      panel.appendChild(sec);
    }
  }

  window.CaseMap = window.CaseMap || {};
  window.CaseMap.panel = {
    renderEntity: renderEntity,
    renderTimelineMarker: renderTimelineMarker,
    renderReference: renderReference,
    renderAdjudicator: renderAdjudicator,
  };
})();
