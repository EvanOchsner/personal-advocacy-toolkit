"""End-to-end three-layer writer + reproducibility-script tests.

The writer is what turns a single source file into the on-disk
``raw/`` + ``structured/`` + ``readable/`` triple plus the per-source
reproducibility script under ``<case>/extraction/scripts/``. These
tests pin the file shape, the manifest contract, and the recipe's
ability to detect drift.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.extraction import recipe
from scripts.extraction.writer import write_three_layer


def _run_replay(script: Path) -> subprocess.CompletedProcess:
    """Invoke the recipe replay script with the toolkit on PYTHONPATH."""
    repo_root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env=env,
    )


# ---- Three-layer outputs -----------------------------------------------

def test_writer_produces_raw_structured_readable_for_pdf(
    case_root, make_simple_pdf
) -> None:
    pytest.importorskip("pypdf")
    src = make_simple_pdf(pages=["A genuinely readable single-page synthetic PDF."])
    out_dir = case_root / "evidence" / "policy"

    record = write_three_layer(
        src,
        out_dir,
        case_root=case_root,
        interactive=False,
    )

    sid = record["source_id"]
    assert (out_dir / "raw" / f"{sid}.pdf").is_file()
    assert (out_dir / "structured" / f"{sid}.json").is_file()
    assert (out_dir / "readable" / f"{sid}.txt").is_file()
    # Readable text matches what the writer reported.
    rt = (out_dir / "readable" / f"{sid}.txt").read_text(encoding="utf-8")
    assert "genuinely readable" in rt


def test_writer_produces_recipe_script_when_case_root_supplied(
    case_root, make_simple_pdf
) -> None:
    pytest.importorskip("pypdf")
    src = make_simple_pdf(pages=["Clean text body with words and stuff."])
    out_dir = case_root / "evidence" / "policy"
    record = write_three_layer(src, out_dir, case_root=case_root, interactive=False)

    script = case_root / "extraction" / "scripts" / f"extract_{record['source_id']}.py"
    assert script.is_file()
    assert script.stat().st_mode & 0o111  # executable bit set


def test_writer_skips_recipe_script_without_case_root(
    case_root, make_simple_pdf
) -> None:
    pytest.importorskip("pypdf")
    src = make_simple_pdf(pages=["Clean text."])
    out_dir = case_root / "evidence" / "policy"
    record = write_three_layer(src, out_dir, case_root=None, interactive=False)

    # No case_root means no per-source script. The writer should not
    # have created the extraction/scripts/ directory either.
    assert not list((case_root / "extraction" / "scripts").iterdir())


def test_writer_records_method_tier_provider_in_structured(
    case_root, make_simple_pdf
) -> None:
    pytest.importorskip("pypdf")
    src = make_simple_pdf(pages=["Clean text body with enough real words."])
    out_dir = case_root / "evidence" / "policy"
    record = write_three_layer(src, out_dir, case_root=case_root, interactive=False)

    sj = json.loads((out_dir / "structured" / f"{record['source_id']}.json").read_text())
    assert sj["method"] == "pypdf"
    assert sj["tier"] == 0
    assert sj["vlm_provider"] is None  # no VLM for clean tier-0 path
    assert sj["source_sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
    assert sj["text_chars"] > 0
    assert "extraction" in sj  # full to_metadata_dict() blob


def test_writer_appends_to_manifest(case_root, make_simple_pdf) -> None:
    pytest.importorskip("pypdf")
    pytest.importorskip("yaml")
    src = make_simple_pdf(pages=["Clean text body with enough real words."])
    out_dir = case_root / "evidence" / "policy"
    manifest = out_dir / "manifest.yaml"
    record = write_three_layer(
        src, out_dir, case_root=case_root, manifest_path=manifest, interactive=False
    )

    import yaml  # type: ignore[import-untyped]

    data = yaml.safe_load(manifest.read_text())
    assert data["entries"][0]["source_id"] == record["source_id"]
    assert data["entries"][0]["kind"] == "extract_pdf"


def test_writer_force_overwrites_existing_manifest_entry(
    case_root, make_simple_pdf
) -> None:
    pytest.importorskip("pypdf")
    pytest.importorskip("yaml")
    src = make_simple_pdf(pages=["Body."])
    out_dir = case_root / "evidence" / "policy"
    manifest = out_dir / "manifest.yaml"

    write_three_layer(
        src, out_dir, case_root=case_root, manifest_path=manifest, interactive=False
    )
    # Re-run without force should fail.
    with pytest.raises(FileExistsError):
        write_three_layer(
            src,
            out_dir,
            case_root=case_root,
            manifest_path=manifest,
            interactive=False,
        )
    # With force, it succeeds.
    write_three_layer(
        src,
        out_dir,
        case_root=case_root,
        manifest_path=manifest,
        interactive=False,
        force=True,
    )


# ---- Recipe replay -----------------------------------------------------

def test_recipe_dict_carries_relative_paths(case_root, make_simple_pdf) -> None:
    pytest.importorskip("pypdf")
    src = make_simple_pdf(pages=["Body."])
    out_dir = case_root / "evidence" / "policy"
    record = write_three_layer(src, out_dir, case_root=case_root, interactive=False)

    # Read the generated script and parse the embedded JSON recipe.
    # The template wraps it as `json.loads(r"""...""")` so we slice
    # between the raw-string delimiters.
    script = case_root / "extraction" / "scripts" / f"extract_{record['source_id']}.py"
    text = script.read_text(encoding="utf-8")
    sentinel_start = 'json.loads(r"""'
    sentinel_end = '""")'
    assert sentinel_start in text
    blob = text[text.index(sentinel_start) + len(sentinel_start) :]
    blob = blob[: blob.index(sentinel_end)]
    recipe_dict = json.loads(blob)

    assert recipe_dict["source_file_relative"].startswith("evidence/policy/raw/")
    assert recipe_dict["readable_path_relative"].startswith("evidence/policy/readable/")
    assert recipe_dict["structured_path_relative"].startswith("evidence/policy/structured/")
    # Pinned to the source bytes — drift check.
    assert recipe_dict["expected"]["source_sha256"] == hashlib.sha256(
        (out_dir / "raw" / f"{record['source_id']}.pdf").read_bytes()
    ).hexdigest()


def test_recipe_replay_succeeds_on_unchanged_inputs(
    case_root, make_simple_pdf
) -> None:
    """Running the generated script should exit 0 against on-disk outputs."""
    pytest.importorskip("pypdf")
    src = make_simple_pdf(pages=["Stable body content with enough real words for tier 0."])
    out_dir = case_root / "evidence" / "policy"
    record = write_three_layer(src, out_dir, case_root=case_root, interactive=False)

    script = case_root / "extraction" / "scripts" / f"extract_{record['source_id']}.py"
    proc = _run_replay(script)
    assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout


def test_recipe_replay_fails_when_readable_text_drifts(
    case_root, make_simple_pdf
) -> None:
    pytest.importorskip("pypdf")
    src = make_simple_pdf(pages=["Stable body content with enough real words."])
    out_dir = case_root / "evidence" / "policy"
    record = write_three_layer(src, out_dir, case_root=case_root, interactive=False)

    # Tamper with the readable file — the recipe should detect this.
    readable = out_dir / "readable" / f"{record['source_id']}.txt"
    readable.write_text("totally different text\n", encoding="utf-8")

    script = case_root / "extraction" / "scripts" / f"extract_{record['source_id']}.py"
    proc = _run_replay(script)
    assert proc.returncode != 0
    assert "differs" in (proc.stderr + proc.stdout).lower() or "error" in (proc.stderr + proc.stdout).lower()


def test_recipe_replay_fails_when_source_bytes_change(
    case_root, make_simple_pdf
) -> None:
    pytest.importorskip("pypdf")
    src = make_simple_pdf(pages=["Stable body content."])
    out_dir = case_root / "evidence" / "policy"
    record = write_three_layer(src, out_dir, case_root=case_root, interactive=False)

    # Tamper with the raw file — recipe should refuse to even attempt.
    raw_path = out_dir / "raw" / f"{record['source_id']}.pdf"
    raw_path.write_bytes(b"definitely not a PDF anymore")

    script = case_root / "extraction" / "scripts" / f"extract_{record['source_id']}.py"
    proc = _run_replay(script)
    assert proc.returncode != 0
    assert "sha256 mismatch" in (proc.stderr + proc.stdout).lower()


# ---- Recipe scrubbing of unserializable values ------------------------

def test_recipe_dict_handles_unserializable_settings(tmp_path: Path) -> None:
    """Settings dicts may carry weird stuff; recipe must never crash."""
    from scripts.extraction.result import ExtractionResult

    weird = ExtractionResult(
        text="hi",
        method="x",
        tier=0,
        settings={"path": Path("/tmp/foo")},  # not JSON-serializable
    )
    out = recipe.recipe_dict(
        case_root=tmp_path,
        source_file=tmp_path / "src.pdf",
        source_sha256="abc" * 21 + "a",
        structured_path=tmp_path / "structured" / "x.json",
        readable_path=tmp_path / "readable" / "x.txt",
        result=weird,
    )
    # No exception, and the path got scrubbed to a repr.
    assert isinstance(out["settings"]["path"], str)
