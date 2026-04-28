"""Tests for scripts/intake/authorities_reconcile.py."""
from __future__ import annotations

import json

from scripts.intake import authorities_reconcile as ar
from scripts.intake._common import DISCLAIMER


def _local_result(authorities: list[dict]) -> dict:
    return {
        "disclaimer": DISCLAIMER,
        "situation": "insurance_dispute",
        "jurisdiction": "MD",
        "warnings": [],
        "authorities": authorities,
    }


def _web_result(authorities: list[dict], sources: list[dict] | None = None) -> dict:
    return {
        "disclaimer": DISCLAIMER,
        "situation": "insurance_dispute",
        "jurisdiction": "MD",
        "warnings": [],
        "authorities": authorities,
        "sources": sources or [
            {"url": a["url"], "accessed_on": "2026-04-27"} for a in authorities
        ],
        "accessed_on": "2026-04-27",
    }


def _mia_local() -> dict:
    return {
        "name": "Maryland Insurance Administration",
        "short_name": "MIA",
        "kind": "regulator",
        "scope": "MD",
        "url": "https://insurance.maryland.gov/Consumer/Pages/FileAComplaint.aspx",
        "notes": "Primary regulator for MD insurance disputes.",
        "status": "populated",
    }


def _mia_web() -> dict:
    return {
        "name": "Maryland Insurance Administration",
        "short_name": "MIA",
        "kind": "regulator",
        "scope": "MD",
        "url": "https://insurance.maryland.gov/Consumer/Pages/default.aspx",
        "notes": "Found via insurance.maryland.gov.",
    }


def test_match_when_short_name_and_domain_agree() -> None:
    result = ar.reconcile(_local_result([_mia_local()]), _web_result([_mia_web()]))
    assert len(result["matched"]) == 1
    assert result["matched"][0]["local"]["short_name"] == "MIA"
    assert result["conflicts"] == []
    assert result["local_only"] == []
    assert result["web_only"] == []
    assert result["staleness_flags"] == []
    assert result["disclaimer"] == DISCLAIMER


def test_conflict_when_url_domain_differs() -> None:
    web = _mia_web()
    web["url"] = "https://example.com/imposter"
    result = ar.reconcile(_local_result([_mia_local()]), _web_result([web]))
    assert len(result["conflicts"]) == 1
    assert "url" in result["conflicts"][0]["fields"]
    assert result["matched"] == []


def test_local_only_when_web_does_not_surface() -> None:
    other_web = {
        "name": "Maryland Office of the Attorney General",
        "short_name": "MD AG",
        "kind": "ag",
        "scope": "MD",
        "url": "https://oag.state.md.us/",
    }
    result = ar.reconcile(_local_result([_mia_local()]), _web_result([other_web]))
    assert len(result["local_only"]) == 1
    assert result["local_only"][0]["short_name"] == "MIA"
    assert len(result["web_only"]) == 1
    assert result["web_only"][0]["short_name"] == "MD AG"


def test_staleness_flag_when_local_domain_absent_from_web_sources() -> None:
    # Web returns a different (renamed) agency; local MIA URL domain
    # never appears in any source -> staleness flag.
    renamed = {
        "name": "Maryland Department of Insurance and Consumer Services",
        "short_name": "MDICS",
        "kind": "regulator",
        "scope": "MD",
        "url": "https://mdics.maryland.gov/",
    }
    result = ar.reconcile(
        _local_result([_mia_local()]),
        _web_result(
            [renamed],
            sources=[{"url": "https://mdics.maryland.gov/", "accessed_on": "2026-04-27"}],
        ),
    )
    assert len(result["staleness_flags"]) == 1
    assert result["staleness_flags"][0]["local"]["short_name"] == "MIA"
    assert "insurance.maryland.gov" in result["staleness_flags"][0]["reason"]


def test_stub_local_entries_are_local_only_not_matched() -> None:
    stub = {
        "name": "TODO: populate",
        "short_name": "TODO",
        "kind": "federal",
        "scope": "federal",
        "url": "",
        "status": "stub",
    }
    result = ar.reconcile(_local_result([stub]), _web_result([_mia_web()]))
    # Stub appears in local_only with stub marker handled by _is_stub.
    assert any(ar._is_stub(a) for a in result["local_only"])
    # Web entry stands alone in web_only.
    assert len(result["web_only"]) == 1


def test_web_unavailable_disables_staleness_and_marks_flag() -> None:
    result = ar.reconcile(_local_result([_mia_local()]), None)
    assert result["web_unavailable"] is True
    assert result["staleness_flags"] == []
    # Local entry is still surfaced as local_only when web is unavailable.
    assert len(result["local_only"]) == 1


def test_match_via_fuzzy_name_when_short_codes_differ() -> None:
    local = _mia_local()
    web = _mia_web()
    web["short_name"] = "MD-IA"  # different code, same agency
    result = ar.reconcile(_local_result([local]), _web_result([web]))
    assert len(result["matched"]) == 1


def test_format_text_always_shows_both_halves() -> None:
    result = ar.reconcile(_local_result([_mia_local()]), _web_result([_mia_web()]))
    text = ar.format_text(result)
    assert "== Local findings ==" in text
    assert "== Web findings ==" in text
    assert "== Reconciliation ==" in text
    assert DISCLAIMER in text
    assert "Use your own judgement" in text


def test_format_text_says_web_unavailable_when_missing() -> None:
    result = ar.reconcile(_local_result([_mia_local()]), None)
    text = ar.format_text(result)
    assert "Web pass returned no usable results." in text


def test_cli_round_trip(tmp_path, capsys) -> None:
    local_path = tmp_path / "local.json"
    web_path = tmp_path / "web.json"
    local_path.write_text(json.dumps(_local_result([_mia_local()])), encoding="utf-8")
    web_path.write_text(json.dumps(_web_result([_mia_web()])), encoding="utf-8")
    rc = ar.main(["--local", str(local_path), "--web", str(web_path), "--format", "json"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["situation"] == "insurance_dispute"
    assert parsed["disclaimer"] == DISCLAIMER
    assert len(parsed["matched"]) == 1
