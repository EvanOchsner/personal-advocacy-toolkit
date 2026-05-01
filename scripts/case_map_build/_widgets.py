"""Per-widget content generators for the case-map dashboard.

Each generator is a pure function: it reads from disk under <case>,
returns a JSON-serializable payload, and never mutates input files. The
deterministic generators are the default; LLM enrichment is opt-in and
falls back to deterministic when the API is unavailable or errors.

Widgets:
    central_issue   — header synopsis (case_name, situation_type, issue blurb)
    parties         — three buckets {allies, neutrals, adversaries} of party cards
    references      — list of governing-document cards (citation, title, synopsis)
    adjudicators    — list of regulators/courts/ombuds (a special slice of NEUTRAL)
    timeline        — Plotly figure spec + filter metadata for the timeline band
"""
from __future__ import annotations

from datetime import date as date_cls
from pathlib import Path
from typing import Any

from scripts.intake._common import DISCLAIMER, data_dir, load_yaml

from scripts.app._aggregate import build_timeline
from scripts.app._loaders import LoadedCaseMap


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #


def widget_inputs(case_dir: Path, widget: str) -> list[Path]:
    """Files whose hashes determine whether `widget` needs regeneration."""
    case_dir = case_dir.resolve()
    if widget == "central_issue":
        return _existing(case_dir, ["case-facts.yaml"])
    if widget == "parties":
        return _existing(case_dir, ["case-facts.yaml", "entities.yaml"])
    if widget == "references":
        candidates = [case_dir / "references" / ".references-manifest.yaml"]
        manifest = candidates[0]
        if manifest.is_file():
            data = load_yaml(manifest)
            entries = data.get("entries") or []
            for entry in entries:
                rp = entry.get("readable_path") if isinstance(entry, dict) else None
                if rp:
                    p = (case_dir / rp).resolve()
                    if _is_within(p, case_dir) and p.is_file():
                        candidates.append(p)
        return [p for p in candidates if p.is_file()]
    if widget == "adjudicators":
        paths = _existing(case_dir, ["case-facts.yaml"])
        ar_dir = case_dir / "notes" / "authorities-research"
        if ar_dir.is_dir():
            for p in sorted(ar_dir.glob("*.json")):
                if p.is_file():
                    paths.append(p)
        return paths
    if widget == "timeline":
        return _existing(
            case_dir,
            ["case-facts.yaml", "entities.yaml", "events.yaml"],
        )
    raise ValueError(f"unknown widget: {widget}")


# --------------------------------------------------------------------------- #
# Generators
# --------------------------------------------------------------------------- #


def gen_central_issue(loaded: LoadedCaseMap, *, llm: Any | None) -> dict[str, Any]:
    cf = loaded.case_facts or {}
    case_name = str(cf.get("case_name") or cf.get("case_slug") or loaded.case_dir.name)
    situation = str(cf.get("situation_type") or "")
    subtype = str(cf.get("subtype") or "")
    loss = cf.get("loss") or {}
    loss_date = str(loss.get("date") or "")
    loss_loc = str(loss.get("location") or "")
    relief = cf.get("relief_sought") or []
    if not isinstance(relief, list):
        relief = []
    disputed = cf.get("disputed_amounts") or {}

    deterministic = _build_central_issue_blurb(cf, situation, subtype, loss_date, loss_loc)

    blurb = deterministic
    enriched = False
    if llm is not None:
        try:
            blurb = llm.summarize_central_issue(cf, deterministic) or deterministic
            enriched = True
        except Exception:  # noqa: BLE001 — never let LLM failures break the build
            blurb = deterministic
            enriched = False

    return {
        "case_name": case_name,
        "situation_type": situation,
        "subtype": subtype,
        "loss_date": loss_date,
        "loss_location": loss_loc,
        "blurb": blurb,
        "relief_sought": [str(r) for r in relief],
        "disputed_amounts": _shallow_serializable(disputed),
        "enriched": enriched,
        "disclaimer": DISCLAIMER,
    }


def gen_parties(loaded: LoadedCaseMap, *, llm: Any | None) -> dict[str, Any]:
    """Bucket entities into three sectors keyed by role."""
    allies: list[dict[str, Any]] = []
    neutrals: list[dict[str, Any]] = []
    adversaries: list[dict[str, Any]] = []

    for ent in loaded.entities:
        res = loaded.resolved[ent.id]
        contact_lines: list[str] = []
        for k in ("email", "phone"):
            v = res.resolved.get(k) if isinstance(res.resolved, dict) else None
            if v:
                contact_lines.append(f"{k}: {v}")
        addr = (res.resolved or {}).get("address") if isinstance(res.resolved, dict) else None
        if isinstance(addr, str):
            contact_lines.append(addr)
        elif isinstance(addr, dict):
            parts = [
                addr.get("street"),
                addr.get("city"),
                addr.get("state"),
                addr.get("zip"),
            ]
            joined = ", ".join(str(p) for p in parts if p)
            if joined:
                contact_lines.append(joined)

        role_descr = _role_description(res.resolved.get("role")) if isinstance(res.resolved, dict) else ""
        deterministic_blurb = role_descr or _labels_blurb(ent.labels)

        blurb = deterministic_blurb
        enriched = False
        if llm is not None:
            try:
                blurb = llm.summarize_party(ent, res.resolved, deterministic_blurb) or deterministic_blurb
                enriched = True
            except Exception:  # noqa: BLE001
                blurb = deterministic_blurb
                enriched = False

        card = {
            "id": ent.id,
            "role": ent.role,
            "icon": ent.icon or "person",
            "display_name": res.display_name,
            "labels": list(ent.labels),
            "blurb": blurb,
            "contact": contact_lines,
            "enriched": enriched,
        }
        if ent.role in ("self", "ally"):
            allies.append(card)
        elif ent.role == "adversary":
            adversaries.append(card)
        else:
            neutrals.append(card)

    # Stable ordering: self first, then ally, then alpha by display_name.
    def _ally_key(c: dict[str, Any]) -> tuple[int, str]:
        return (0 if c["role"] == "self" else 1, c["display_name"].lower())

    allies.sort(key=_ally_key)
    neutrals.sort(key=lambda c: c["display_name"].lower())
    adversaries.sort(key=lambda c: c["display_name"].lower())

    return {
        "allies": allies,
        "neutrals": neutrals,
        "adversaries": adversaries,
        "disclaimer": DISCLAIMER,
    }


def gen_references(case_dir: Path, *, llm: Any | None) -> dict[str, Any]:
    manifest_path = case_dir / "references" / ".references-manifest.yaml"
    cards: list[dict[str, Any]] = []
    if manifest_path.is_file():
        data = load_yaml(manifest_path)
        for entry in data.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            citation = str(entry.get("citation") or "").strip()
            title = str(entry.get("title") or "").strip()
            kind = str(entry.get("kind") or "").strip()
            jurisdiction = str(entry.get("jurisdiction") or "").strip()
            readable_rel = entry.get("readable_path")
            structured_rel = entry.get("structured_path")
            raw_rel = entry.get("raw_path")
            source_url = str(entry.get("source_url") or "").strip()

            extract = ""
            if isinstance(readable_rel, str):
                rp = (case_dir / readable_rel).resolve()
                if _is_within(rp, case_dir) and rp.is_file():
                    extract = _first_paragraph(rp.read_text(encoding="utf-8", errors="replace"))

            blurb = extract or title or citation
            enriched = False
            if llm is not None:
                try:
                    blurb = llm.summarize_reference(citation, title, extract) or blurb
                    enriched = True
                except Exception:  # noqa: BLE001
                    enriched = False

            cards.append(
                {
                    "id": str(entry.get("source_id") or "")[:16] or citation,
                    "citation": citation,
                    "title": title,
                    "kind": kind,
                    "jurisdiction": jurisdiction,
                    "blurb": blurb,
                    "links": {
                        "readable": readable_rel if isinstance(readable_rel, str) else None,
                        "structured": structured_rel if isinstance(structured_rel, str) else None,
                        "raw": raw_rel if isinstance(raw_rel, str) else None,
                    },
                    "source_url": source_url,
                    "enriched": enriched,
                }
            )

    return {
        "cards": cards,
        "disclaimer": DISCLAIMER,
    }


def gen_adjudicators(case_dir: Path, loaded: LoadedCaseMap) -> dict[str, Any]:
    cf = loaded.case_facts or {}
    cards: list[dict[str, Any]] = []

    reg = cf.get("regulator") or {}
    if isinstance(reg, dict) and reg.get("name"):
        cards.append(
            {
                "id": "regulator",
                "kind": "regulator",
                "name": str(reg.get("name") or ""),
                "short_name": str(reg.get("short_name") or ""),
                "case_number": str(reg.get("case_number") or ""),
                "filed_date": str(reg.get("filed_date") or ""),
                "acknowledged_date": str(reg.get("acknowledged_date") or ""),
                "url": str(reg.get("url") or ""),
            }
        )

    ar_dir = case_dir / "notes" / "authorities-research"
    if ar_dir.is_dir():
        import json

        for p in sorted(ar_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            authorities = data.get("authorities") or data.get("agreed") or []
            if not isinstance(authorities, list):
                continue
            for auth in authorities:
                if not isinstance(auth, dict):
                    continue
                name = str(auth.get("name") or "").strip()
                if not name:
                    continue
                cards.append(
                    {
                        "id": str(auth.get("short_name") or name).lower().replace(" ", "_"),
                        "kind": str(auth.get("kind") or "regulator"),
                        "name": name,
                        "short_name": str(auth.get("short_name") or ""),
                        "case_number": "",
                        "filed_date": "",
                        "acknowledged_date": "",
                        "url": str(auth.get("url") or ""),
                        "notes": str(auth.get("notes") or ""),
                        "source_file": str(p.relative_to(case_dir)),
                    }
                )

    return {"cards": cards, "disclaimer": DISCLAIMER}


def gen_timeline(loaded: LoadedCaseMap) -> dict[str, Any]:
    """Compute markers and shape them into a Plotly figure spec.

    The figure spec is renderer-agnostic JSON; the browser passes it
    straight to Plotly.newPlot. Tracks become Plotly traces so the legend
    can toggle them. Click-through is handled separately on the client
    via the `markers` mirror (each point's customdata carries an index
    into `markers` so the drilldown panel can find the full record).
    """
    cf = loaded.case_facts or {}
    deadlines = _compute_deadlines(loaded, cf)
    markers = build_timeline(loaded, deadlines=deadlines)

    # Track display config — order matters for legend layout.
    track_config = [
        ("self_event", "Events (self/ally)", "#1f77b4", "circle"),
        ("adverse_event", "Events (adverse)", "#d62728", "circle"),
        ("neutral_event", "Events (neutral)", "#7f7f7f", "circle"),
        ("outbound", "Outbound correspondence", "#2ca02c", "diamond"),
        ("inbound", "Inbound correspondence", "#ff7f0e", "diamond"),
        ("correspondence", "Other correspondence", "#9467bd", "diamond"),
        ("deadline", "Deadlines", "#8c564b", "x"),
    ]

    # Map track -> stable y-axis position so traces stack on distinct lanes.
    lane_for_track = {t[0]: i for i, t in enumerate(track_config)}

    traces: list[dict[str, Any]] = []
    serialized_markers = [m.to_dict() for m in markers]
    for track, label, color, symbol in track_config:
        xs: list[str] = []
        ys: list[float] = []
        texts: list[str] = []
        customdata: list[int] = []
        for idx, m in enumerate(serialized_markers):
            if m.get("track") != track:
                continue
            xs.append(m["date"])
            ys.append(lane_for_track[track])
            hover_summary = m.get("summary") or ""
            texts.append(f"{m['date']} · {m['title']}\n{hover_summary}".strip())
            customdata.append(idx)
        if not xs:
            continue
        traces.append(
            {
                "type": "scatter",
                "mode": "markers",
                "name": label,
                "x": xs,
                "y": ys,
                "text": texts,
                "customdata": customdata,
                "hovertemplate": "%{text}<extra></extra>",
                "marker": {"color": color, "size": 12, "symbol": symbol, "line": {"width": 1, "color": "#222"}},
                "meta": {"track": track},
            }
        )

    figure = {
        "data": traces,
        "layout": {
            "margin": {"l": 200, "r": 24, "t": 16, "b": 48},
            "height": 360,
            "xaxis": {"type": "date", "title": ""},
            "yaxis": {
                "tickmode": "array",
                "tickvals": [lane_for_track[t[0]] for t in track_config],
                "ticktext": [t[1] for t in track_config],
                "automargin": True,
                "zeroline": False,
                "showgrid": True,
                "gridcolor": "#eee",
                "fixedrange": True,
            },
            "showlegend": True,
            "legend": {"orientation": "h", "y": -0.2},
            "hovermode": "closest",
            "paper_bgcolor": "#ffffff",
            "plot_bgcolor": "#fafafa",
        },
        "config": {
            "displaylogo": False,
            "responsive": True,
            "modeBarButtonsToRemove": [
                "select2d",
                "lasso2d",
                "autoScale2d",
                "toggleSpikelines",
            ],
        },
    }

    return {
        "figure": figure,
        "markers": serialized_markers,
        "tracks": [
            {"id": t[0], "label": t[1], "color": t[2]}
            for t in track_config
        ],
        "disclaimer": DISCLAIMER,
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _existing(case_dir: Path, names: list[str]) -> list[Path]:
    out = []
    for n in names:
        p = case_dir / n
        if p.is_file():
            out.append(p)
    return out


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _build_central_issue_blurb(
    cf: dict[str, Any],
    situation: str,
    subtype: str,
    loss_date: str,
    loss_loc: str,
) -> str:
    bits: list[str] = []
    descr = (cf.get("loss") or {}).get("description") if isinstance(cf, dict) else None
    if isinstance(descr, str) and descr.strip():
        bits.append(descr.strip())
    if situation and not bits:
        topic = situation.replace("_", " ")
        if subtype:
            topic += f" ({subtype.replace('_', ' ')})"
        bits.append(f"This case is a {topic}.")
    if loss_date and loss_loc:
        bits.append(f"Loss date {loss_date}, location {loss_loc}.")
    elif loss_date:
        bits.append(f"Loss date {loss_date}.")
    return " ".join(bits) or "No central-issue summary available."


def _role_description(role_raw: Any) -> str:
    if not isinstance(role_raw, str) or not role_raw.strip():
        return ""
    pretty = role_raw.replace("_", " ").strip()
    return pretty[0].upper() + pretty[1:]


def _labels_blurb(labels: list[str]) -> str:
    if not labels:
        return ""
    return ", ".join(labels)


def _shallow_serializable(value: Any) -> Any:
    """Strip non-JSON types from a nested structure (for case-facts subsections)."""
    if isinstance(value, dict):
        return {str(k): _shallow_serializable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_shallow_serializable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _first_paragraph(text: str, *, max_chars: int = 400) -> str:
    """Return the first non-empty paragraph, truncated to max_chars."""
    if not text:
        return ""
    para_lines: list[str] = []
    for line in text.splitlines():
        if line.strip():
            para_lines.append(line.strip())
        elif para_lines:
            break
    para = " ".join(para_lines)
    if len(para) > max_chars:
        para = para[: max_chars - 1].rstrip() + "…"
    return para


def _compute_deadlines(loaded: LoadedCaseMap, cf: dict[str, Any]) -> dict[str, Any] | None:
    situation = cf.get("situation_type")
    jurisdiction = (cf.get("jurisdiction") or {}).get("state")
    loss_date_str = ((cf.get("loss") or {}).get("date")) or ""
    if not (situation and jurisdiction and loss_date_str):
        return None
    try:
        loss_date = date_cls.fromisoformat(str(loss_date_str))
    except (ValueError, TypeError):
        return None
    try:
        from scripts.intake import deadline_calc as dc

        repo_data_dir = data_dir(Path(__file__).parent)
        data = load_yaml(repo_data_dir / "deadlines.yaml")
        inputs = dc.ClockInputs(loss_date=loss_date)
        return dc.compute_deadlines(data, situation, str(jurisdiction), inputs)
    except Exception:  # noqa: BLE001
        return None
