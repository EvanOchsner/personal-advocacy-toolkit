"""CLI tests for ``python -m scripts.extraction``.

We invoke the CLI through ``main()`` directly so we can capture exit
codes without spawning a subprocess. The aim is contract pinning,
not coverage — most behavior is exercised via the cascade tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.extraction.__main__ import main


def test_list_providers_prints_table_and_exits_zero(capsys) -> None:
    rc = main(["--list-providers"])
    assert rc == 0
    out = capsys.readouterr().out
    for name in ("tesseract", "olmocr", "claude", "openai", "http"):
        assert name in out


def test_no_inputs_returns_nonzero(capsys) -> None:
    rc = main([])
    assert rc != 0
    err = capsys.readouterr().err
    assert "no inputs" in err.lower()


def test_missing_out_dir_returns_nonzero(tmp_path: Path, capsys) -> None:
    f = tmp_path / "x.pdf"
    f.write_bytes(b"%PDF-1.4\n%%EOF\n")
    rc = main([str(f)])
    assert rc != 0
    err = capsys.readouterr().err
    assert "--out-dir" in err


def test_unknown_extension_skipped_with_warning(tmp_path: Path, capsys) -> None:
    f = tmp_path / "weird.xyz"
    f.write_bytes(b"random")
    out_dir = tmp_path / "out"
    rc = main([str(f), "--out-dir", str(out_dir), "--non-interactive"])
    err = capsys.readouterr().err
    assert "skip" in err.lower()
    assert rc != 0


def test_processes_pdf_end_to_end(tmp_path: Path, make_simple_pdf, capsys) -> None:
    pytest.importorskip("pypdf")
    pdf = make_simple_pdf(pages=["A real PDF body with enough words to pass tier 0."])
    out_dir = tmp_path / "out"
    rc = main(
        [
            str(pdf),
            "--out-dir", str(out_dir),
            "--non-interactive",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr().out
    assert "tier 0" in captured
    assert "via pypdf" in captured

    # Three-layer triple landed in --out-dir.
    assert (out_dir / "raw").is_dir()
    assert any((out_dir / "structured").iterdir())
    assert any((out_dir / "readable").iterdir())


def test_directory_input_expands_to_supported_files(
    tmp_path: Path, make_simple_pdf, make_eml
) -> None:
    pytest.importorskip("pypdf")
    indir = tmp_path / "drop"
    indir.mkdir()
    p1 = make_simple_pdf(pages=["pdf body content"], name="a.pdf")
    p1.replace(indir / "a.pdf")
    eml = make_eml()
    eml.replace(indir / "b.eml")
    # A non-supported file should be ignored.
    (indir / "skip.xyz").write_bytes(b"ignored")

    out_dir = tmp_path / "out"
    rc = main([str(indir), "--out-dir", str(out_dir), "--non-interactive"])
    assert rc == 0
    structured = list((out_dir / "structured").iterdir())
    assert len(structured) == 2  # one per supported input


def test_force_overwrites_manifest_entry(
    tmp_path: Path, make_simple_pdf
) -> None:
    pytest.importorskip("pypdf")
    pytest.importorskip("yaml")
    pdf = make_simple_pdf(pages=["body"])
    out_dir = tmp_path / "out"
    manifest = out_dir / "manifest.yaml"
    base_args = [
        str(pdf),
        "--out-dir", str(out_dir),
        "--manifest", str(manifest),
        "--non-interactive",
    ]
    assert main(base_args) == 0
    # Second run without --force should fail.
    assert main(base_args) != 0
    # With --force it works.
    assert main(base_args + ["--force"]) == 0
