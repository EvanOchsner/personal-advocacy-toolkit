/* dashboard.js — sector layout renderer.
 *
 * Renders three sectors of party cards (allies / neutrals / adversaries),
 * the central-issue blurb, the governing-documents strip, and the
 * adjudicators list. Wires every clickable card to the side drilldown
 * panel via window.CaseMap.{selectEntity, showReference, showAdjudicator}.
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
          e.innerHTML = attrs[k];
        } else if (k.startsWith("on") && typeof attrs[k] === "function") {
          e.addEventListener(k.slice(2), attrs[k]);
        } else if (k === "data") {
          for (const dk of Object.keys(attrs[k])) {
            e.dataset[dk] = attrs[k][dk];
          }
        } else {
          e.setAttribute(k, attrs[k]);
        }
      }
    }
    if (children) for (const c of children) if (c) e.appendChild(c);
    return e;
  }

  function renderCentralIssue(payload) {
    const root = document.getElementById("central-issue");
    if (!root) return;
    root.innerHTML = "";
    if (!payload) {
      root.textContent = "(no central-issue summary)";
      return;
    }
    const blurb = el("p", { class: "central-issue-blurb", text: payload.blurb || "" });
    root.appendChild(blurb);

    const meta = [];
    if (payload.situation_type) meta.push(payload.situation_type.replace(/_/g, " "));
    if (payload.subtype) meta.push(payload.subtype.replace(/_/g, " "));
    if (payload.loss_date) meta.push("loss " + payload.loss_date);
    if (meta.length) {
      root.appendChild(el("p", { class: "central-issue-meta", text: meta.join(" · ") }));
    }

    if (payload.relief_sought && payload.relief_sought.length) {
      const ul = el("ul", { class: "central-relief" });
      for (const r of payload.relief_sought) {
        ul.appendChild(el("li", { text: r }));
      }
      root.appendChild(el("details", null, [
        el("summary", { text: "Relief sought" }),
        ul,
      ]));
    }
  }

  function partyCard(card) {
    const node = el("article", {
      class: "party-card role-" + card.role,
      data: { entityId: card.id },
      role: "button",
      tabindex: "0",
      "aria-label": card.display_name + " (" + card.role + ")",
    });
    const header = el("header", { class: "party-card-header" }, [
      el("span", { class: "party-card-name", text: card.display_name }),
      el("span", { class: "party-card-role", text: card.role }),
    ]);
    node.appendChild(header);
    if (card.labels && card.labels.length) {
      const labels = el("ul", { class: "party-card-labels" });
      for (const l of card.labels) {
        labels.appendChild(el("li", { text: l }));
      }
      node.appendChild(labels);
    }
    if (card.blurb) {
      node.appendChild(el("p", { class: "party-card-blurb", text: card.blurb }));
    }
    if (card.contact && card.contact.length) {
      const ul = el("ul", { class: "party-card-contact" });
      for (const c of card.contact) {
        ul.appendChild(el("li", { text: c }));
      }
      node.appendChild(ul);
    }
    const open = () => {
      if (window.CaseMap && window.CaseMap.selectEntity) {
        window.CaseMap.selectEntity(card.id);
      }
    };
    node.addEventListener("click", open);
    node.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        open();
      }
    });
    return node;
  }

  function renderSector(rootId, cards) {
    const root = document.getElementById(rootId);
    if (!root) return;
    root.innerHTML = "";
    if (!cards || !cards.length) {
      root.appendChild(el("p", { class: "sector-empty", text: "(none)" }));
      return;
    }
    for (const c of cards) {
      root.appendChild(partyCard(c));
    }
  }

  function renderAdjudicators(cards) {
    const root = document.getElementById("sector-adjudicators");
    if (!root) return;
    root.innerHTML = "";
    if (!cards || !cards.length) return;
    const heading = el("h3", { class: "adjudicator-heading", text: "Adjudicators" });
    root.appendChild(heading);
    for (const c of cards) {
      const node = el("article", {
        class: "adjudicator-card",
        role: "button",
        tabindex: "0",
        "aria-label": c.name + " adjudicator",
      });
      const header = el("header", { class: "adjudicator-card-header" }, [
        el("span", { class: "adjudicator-card-name", text: c.short_name || c.name }),
        el("span", { class: "adjudicator-card-kind", text: c.kind || "regulator" }),
      ]);
      node.appendChild(header);
      if (c.short_name && c.name && c.short_name !== c.name) {
        node.appendChild(el("p", { class: "adjudicator-card-fullname", text: c.name }));
      }
      const meta = [];
      if (c.case_number) meta.push("case " + c.case_number);
      if (c.filed_date) meta.push("filed " + c.filed_date);
      if (c.acknowledged_date) meta.push("acked " + c.acknowledged_date);
      if (meta.length) {
        node.appendChild(el("p", { class: "adjudicator-card-meta", text: meta.join(" · ") }));
      }
      const open = () => {
        if (window.CaseMap && window.CaseMap.showAdjudicator) {
          window.CaseMap.showAdjudicator(c);
        }
      };
      node.addEventListener("click", open);
      node.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          open();
        }
      });
      root.appendChild(node);
    }
  }

  function renderReferences(cards) {
    const root = document.getElementById("references");
    if (!root) return;
    root.innerHTML = "";
    if (!cards || !cards.length) {
      root.appendChild(el("p", { class: "sector-empty", text: "(no governing documents on file)" }));
      return;
    }
    for (const c of cards) {
      const node = el("article", {
        class: "reference-card",
        role: "button",
        tabindex: "0",
        "aria-label": (c.citation || c.title) + " governing document",
      });
      const heading = c.citation || c.title || c.id;
      node.appendChild(el("h4", { class: "reference-card-citation", text: heading }));
      if (c.title && c.title !== heading) {
        node.appendChild(el("p", { class: "reference-card-title", text: c.title }));
      }
      const tags = [];
      if (c.kind) tags.push(c.kind);
      if (c.jurisdiction) tags.push(c.jurisdiction);
      if (tags.length) {
        const tagList = el("ul", { class: "reference-card-tags" });
        for (const t of tags) tagList.appendChild(el("li", { text: t }));
        node.appendChild(tagList);
      }
      if (c.blurb) {
        node.appendChild(el("p", { class: "reference-card-blurb", text: c.blurb }));
      }
      const open = () => {
        if (window.CaseMap && window.CaseMap.showReference) {
          window.CaseMap.showReference(c);
        }
      };
      node.addEventListener("click", open);
      node.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          open();
        }
      });
      root.appendChild(node);
    }
  }

  function render(payload) {
    if (!payload) return;
    renderCentralIssue(payload.central_issue);
    const parties = payload.parties || {};
    renderSector("sector-allies", parties.allies);
    renderSector("sector-neutral", parties.neutrals);
    renderSector("sector-adversaries", parties.adversaries);
    renderAdjudicators((payload.adjudicators || {}).cards);
    renderReferences((payload.references || {}).cards);
  }

  function markSelected(id) {
    document.querySelectorAll(".party-card").forEach((node) => {
      if (id && node.dataset.entityId === id) {
        node.classList.add("selected");
      } else {
        node.classList.remove("selected");
      }
    });
  }

  window.CaseMap = window.CaseMap || {};
  window.CaseMap.dashboard = { render: render, markSelected: markSelected };
})();
