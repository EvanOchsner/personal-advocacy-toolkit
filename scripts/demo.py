"""Run the Maryland-Mustang synthetic example end-to-end.

Copies the shipped example to a working directory and executes the full
pipeline against it — evidence hashing, provenance, ingest demo,
situation classification, authorities, deadlines, manifest, dashboard,
packet build, letter drafting, and PII-scrub dry-run.

CLI:
    uv run python -m scripts.demo
    uv run python -m scripts.demo --output ~/my-demo --force
    uv run python -m scripts.demo --verbose
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SRC = REPO_ROOT / "examples" / "maryland-mustang"
DEFAULT_OUTPUT = Path.home() / "advocacy-demo" / "maryland-mustang"

CANNED_ANSWERS = textwrap.dedent("""\
    claimant_name: "Sally Ridesdale"
    jurisdiction_state: "MD"
    counterparty_kind: "insurer"
    situation: >
      Classic-car agreed-value policy, insurer deducted from payout
      and moved vehicle to salvage during active negotiation.
    loss_date: "2025-03-15"
    notes: "Agreed-value endorsement — CIM-AV-ENDT-2023."
""")

CANNED_SUBSTITUTIONS = textwrap.dedent("""\
    substitutions:
      "Sally Ridesdale":                 "Jane Doe"
      "Chesapeake Indemnity Mutual": "Example Indemnity Mutual"
    policy_number_patterns:
      - "CIM-[A-Z]+-\\\\d{4}"
    extra_banned:
      - "414 Aigburth Vale"
""")


def _uv_cmd(*args: str) -> list[str]:
    return ["uv", "run", "python", "-m", *args]


def _run_step(
    number: int,
    total: int,
    label: str,
    cmd: list[str],
    *,
    verbose: bool = False,
    allow_fail: bool = False,
) -> bool:
    tag = f"[{number}/{total}]"
    print(f"\n{tag} {label}...", flush=True)
    kwargs: dict = {"cwd": REPO_ROOT}
    if not verbose:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        if allow_fail:
            print("  ⤷ skipped (non-zero exit, continuing)")
            if not verbose and result.stderr:
                for line in result.stderr.strip().splitlines()[:5]:
                    print(f"    {line}")
            return False
        print(f"  ✗ failed (exit {result.returncode})")
        if not verbose and result.stderr:
            for line in result.stderr.strip().splitlines()[:10]:
                print(f"    {line}")
        return False
    print("  ✓ done")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the synthetic Maryland-Mustang example end-to-end.",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Where to place the demo copy (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output directory if it already exists.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show full subprocess output.",
    )
    args = parser.parse_args(argv)
    out: Path = args.output.resolve()
    verbose: bool = args.verbose
    total = 11

    # -- Copy example tree ------------------------------------------------
    if out.exists():
        if not args.force:
            print(
                f"Output directory already exists: {out}\n"
                f"Use --force to overwrite, or --output to pick a different path."
            )
            return 1
        shutil.rmtree(out)

    print(f"Copying example to {out} ...")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(EXAMPLE_SRC, out)
    print("  ✓ copied")

    ok = True

    with tempfile.TemporaryDirectory(prefix="pat-demo-") as tmpdir:
        tmp = Path(tmpdir)

        answers_path = tmp / "answers.yaml"
        answers_path.write_text(CANNED_ANSWERS, encoding="utf-8")

        subs_path = tmp / "substitutions.yaml"
        subs_path.write_text(CANNED_SUBSTITUTIONS, encoding="utf-8")

        steps: list[tuple[str, list[str], bool]] = [
            (
                "Hash the evidence tree",
                _uv_cmd(
                    "scripts.evidence_hash",
                    "--root", str(out / "evidence"),
                    "--manifest", str(out / ".evidence-manifest.sha256"),
                ),
                False,
            ),
            (
                "Capture provenance snapshot",
                _uv_cmd(
                    "scripts.provenance_snapshot",
                    "--root", str(out / "evidence"),
                    "--snapshot-dir", str(out / "provenance" / "snapshots"),
                ),
                False,
            ),
            (
                "Ingest demo (cascade extraction over .eml)",
                _uv_cmd(
                    "scripts.extraction",
                    str(out / "evidence" / "emails" / "raw"),
                    "--out-dir", str(tmp / "mustang-extraction-demo"),
                    "--non-interactive",
                ),
                False,
            ),
            (
                "Classify the situation",
                _uv_cmd(
                    "scripts.intake.situation_classify",
                    "--answers", str(answers_path),
                    "--out", str(out / "case-intake.yaml"),
                ),
                False,
            ),
            (
                "Look up authorities (MD insurance)",
                _uv_cmd(
                    "scripts.intake.authorities_lookup",
                    "--situation", "insurance_dispute",
                    "--jurisdiction", "MD",
                ),
                False,
            ),
            (
                "Compute deadlines",
                _uv_cmd(
                    "scripts.intake.deadline_calc",
                    "--situation", "insurance_dispute",
                    "--jurisdiction", "MD",
                    "--loss-date", "2025-03-15",
                    "--notice-of-loss", "2025-03-16",
                    "--denial-date", "2025-05-09",
                    "--last-act", "2025-06-24",
                ),
                False,
            ),
            (
                "Build unified evidence manifest",
                _uv_cmd(
                    "scripts.manifest.evidence_manifest",
                    "--root", str(out / "evidence"),
                    "--out", str(out / "evidence-manifest.yaml"),
                ),
                False,
            ),
            (
                "Render case dashboard",
                _uv_cmd(
                    "scripts.status.case_dashboard",
                    "--intake", str(out / "case-facts.yaml"),
                    "--manifest", str(out / "evidence-manifest.yaml"),
                    "--packet-dir", str(out / "complaint_packet"),
                ),
                False,
            ),
            (
                "Build complaint packet",
                _uv_cmd(
                    "scripts.packet.build",
                    str(out / "complaint_packet" / "packet-manifest.yaml"),
                    "-v",
                ),
                True,  # allow_fail — may need soffice
            ),
            (
                "Draft a demand letter",
                _uv_cmd(
                    "scripts.letters.draft",
                    "--kind", "demand",
                    "--intake", str(out / "case-facts.yaml"),
                    "--out", str(out / "drafts" / "demo-demand-letter.docx"),
                ),
                False,
            ),
            (
                "PII scrub dry-run",
                _uv_cmd(
                    "scripts.publish.pii_scrub",
                    "--root", str(out / "drafts"),
                    "--substitutions", str(subs_path),
                    "--report", str(out / "drafts" / "scrub-dryrun.json"),
                ),
                True,  # allow_fail — scrub report is optional
            ),
        ]

        for i, (label, cmd, allow_fail) in enumerate(steps, 1):
            success = _run_step(i, total, label, cmd, verbose=verbose, allow_fail=allow_fail)
            if not success and not allow_fail:
                ok = False

    # -- Summary ----------------------------------------------------------
    print("\n" + "=" * 60)
    if ok:
        print("Demo complete.")
    else:
        print("Demo finished with errors (see above).")
    print(f"Output directory: {out}")
    print(
        f"\nExplore the results:\n"
        f"  cat {out}/CLAUDE.md\n"
        f"  cat {out}/case-intake.yaml\n"
        f"  ls {out}/complaint_packet/\n"
        f"\nLaunch the case-map app:\n"
        f"  uv run python -m scripts.app --case-dir {out}\n"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
