"""Tests for scripts/case_map_build/.

Covers the precompute CLI end-to-end against synthetic input plus
hash-based cache invalidation. The Maryland-Mustang fixture is also
exercised so the build step is validated against the same case the
viewer tests run against.
"""
from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

yaml = pytest.importorskip("yaml")

from scripts.case_map_build import _cache, _widgets
from scripts.case_map_build.__main__ import main as build_main


CASE_FACTS = dedent(
    """\
    case_name: "Test Case"
    case_slug: "test-case"
    situation_type: "insurance_dispute"
    subtype: "auto_total_loss_bad_faith"
    claimant:
      name: Sally Ridesdale
      email: sally@example.com
    parties:
      insurer:
        name: Chesapeake Indemnity Mutual
        role: counterparty_insurer
        email: claims@cim.example
    jurisdiction:
      state: MD
    loss:
      date: "2025-03-15"
      location: "Columbia, MD"
      description: "Rear-end collision; claimant not at fault."
    disputed_amounts:
      agreed_value_usd: 58000
      insurer_acv_offer_usd: 52719.50
    relief_sought:
      - "Full agreed value."
    regulator:
      name: "Maryland Insurance Administration"
      short_name: "MIA"
      case_number: "MIA-SYN-0000"
      filed_date: "2025-09-12"
      url: "https://insurance.maryland.gov/"
    """
)

ENTITIES = dedent(
    """\
    entities:
      - id: self
        role: self
        ref: claimant
      - id: cim
        role: adversary
        ref: parties.insurer
      - id: mia
        role: neutral
        ref: regulator
    """
)

EVENTS = dedent(
    """\
    events:
      - id: collision
        date: 2025-03-15
        kind: incident
        title: Collision
        entities: [self]
      - id: insurer_offer
        date: 2025-04-17
        kind: filing
        title: Insurer offer
        entities: [self, cim]
    """
)


def _seed(tmp_path: Path) -> Path:
    (tmp_path / "case-facts.yaml").write_text(CASE_FACTS, encoding="utf-8")
    (tmp_path / "entities.yaml").write_text(ENTITIES, encoding="utf-8")
    (tmp_path / "events.yaml").write_text(EVENTS, encoding="utf-8")
    return tmp_path


def test_build_writes_cache_files(tmp_path: Path) -> None:
    _seed(tmp_path)
    rc = build_main(["--case-dir", str(tmp_path)])
    assert rc == 0
    cache_dir = tmp_path / ".case-map"
    assert cache_dir.is_dir()
    for widget in ("central_issue", "parties", "references", "adjudicators", "timeline"):
        assert (cache_dir / f"{widget}.json").is_file(), widget
    assert (cache_dir / "manifest.json").is_file()
    assert (cache_dir / "dashboard.json").is_file()


def test_build_central_issue_populates_blurb(tmp_path: Path) -> None:
    _seed(tmp_path)
    build_main(["--case-dir", str(tmp_path)])
    central = json.loads((tmp_path / ".case-map" / "central_issue.json").read_text(encoding="utf-8"))
    assert central["case_name"] == "Test Case"
    assert "Rear-end collision" in central["blurb"]
    assert central["enriched"] is False  # deterministic-only path
    assert central["loss_date"] == "2025-03-15"


def test_build_parties_buckets_by_role(tmp_path: Path) -> None:
    _seed(tmp_path)
    build_main(["--case-dir", str(tmp_path)])
    parties = json.loads((tmp_path / ".case-map" / "parties.json").read_text(encoding="utf-8"))
    ally_ids = {c["id"] for c in parties["allies"]}
    neutral_ids = {c["id"] for c in parties["neutrals"]}
    adv_ids = {c["id"] for c in parties["adversaries"]}
    assert ally_ids == {"self"}
    assert neutral_ids == {"mia"}
    assert adv_ids == {"cim"}


def test_build_adjudicators_pulls_regulator(tmp_path: Path) -> None:
    _seed(tmp_path)
    build_main(["--case-dir", str(tmp_path)])
    adj = json.loads((tmp_path / ".case-map" / "adjudicators.json").read_text(encoding="utf-8"))
    names = [c["name"] for c in adj["cards"]]
    assert "Maryland Insurance Administration" in names


def test_build_timeline_emits_plotly_figure(tmp_path: Path) -> None:
    _seed(tmp_path)
    build_main(["--case-dir", str(tmp_path)])
    tl = json.loads((tmp_path / ".case-map" / "timeline.json").read_text(encoding="utf-8"))
    assert "figure" in tl
    fig = tl["figure"]
    assert fig["data"]
    # Each trace carries its track id in meta.
    tracks = {trace["meta"]["track"] for trace in fig["data"]}
    # Both events.yaml events are non-empty, so we expect at least one event track.
    assert tracks & {"self_event", "adverse_event", "neutral_event"}
    # Markers list mirrors the trace points and is sorted.
    dates = [m["date"] for m in tl["markers"]]
    assert dates == sorted(dates)


def test_cache_skips_when_inputs_unchanged(tmp_path: Path, capsys) -> None:
    _seed(tmp_path)
    build_main(["--case-dir", str(tmp_path)])
    capsys.readouterr()  # drain
    # Second run should mark every widget cached.
    build_main(["--case-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "central_issue: cached" in out
    assert "parties: cached" in out
    assert "regenerated" not in out


def test_cache_regenerates_only_affected_widgets(tmp_path: Path, capsys) -> None:
    _seed(tmp_path)
    build_main(["--case-dir", str(tmp_path)])
    capsys.readouterr()
    # Mutate events.yaml only — central_issue / parties / adjudicators / references should stay cached.
    extra_event = (
        "  - id: extra\n"
        "    date: 2025-05-09\n"
        "    kind: filing\n"
        "    title: Extra\n"
        "    entities: [self]\n"
    )
    (tmp_path / "events.yaml").write_text(EVENTS + extra_event, encoding="utf-8")
    build_main(["--case-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "timeline: regenerated" in out
    assert "central_issue: cached" in out
    assert "parties: cached" in out


def test_force_invalidates_cache(tmp_path: Path, capsys) -> None:
    _seed(tmp_path)
    build_main(["--case-dir", str(tmp_path)])
    capsys.readouterr()
    build_main(["--case-dir", str(tmp_path), "--force"])
    out = capsys.readouterr().out
    # --force should regenerate every widget.
    for widget in ("central_issue", "parties", "references", "adjudicators", "timeline"):
        assert f"{widget}: regenerated" in out, widget


def test_dashboard_payload_assembled_from_widgets(tmp_path: Path) -> None:
    _seed(tmp_path)
    build_main(["--case-dir", str(tmp_path)])
    dashboard = json.loads((tmp_path / ".case-map" / "dashboard.json").read_text(encoding="utf-8"))
    for k in ("central_issue", "parties", "references", "adjudicators"):
        assert k in dashboard
    # Note: timeline lives in its own /api/timeline payload, not the dashboard.
    assert "timeline" not in dashboard


def test_widget_inputs_files_must_exist(tmp_path: Path) -> None:
    # references and adjudicators are tolerant of missing optional files.
    _seed(tmp_path)
    inputs = _widgets.widget_inputs(tmp_path, "references")
    assert inputs == []  # no references manifest in this case
    inputs = _widgets.widget_inputs(tmp_path, "adjudicators")
    # only case-facts (regulator block) — the notes/ dir doesn't exist
    assert all(p.name == "case-facts.yaml" for p in inputs)


def test_hash_file_matches_sha256(tmp_path: Path) -> None:
    p = tmp_path / "f.txt"
    p.write_bytes(b"hello world\n")
    h = _cache.hash_file(p)
    # sha256("hello world\n") = a948904f2f0f479b8f8197694b30184b0d2ed1c1cd2a1ec0fb85d299a192a447
    assert h == "a948904f2f0f479b8f8197694b30184b0d2ed1c1cd2a1ec0fb85d299a192a447"


def test_mustang_seed_builds_cleanly() -> None:
    case_dir = Path(__file__).parent.parent / "examples" / "maryland-mustang"
    rc = build_main(["--case-dir", str(case_dir), "--force"])
    assert rc == 0
    cache_dir = case_dir / ".case-map"
    refs = json.loads((cache_dir / "references.json").read_text(encoding="utf-8"))
    citations = {c["citation"] for c in refs["cards"]}
    assert "Md. Code Ins. § 27-303" in citations
