"""Initialize a new case workspace.

Creates the standard directory tree, copies starter templates, and runs
an interactive intake questionnaire. Handles partial information
gracefully — skipped fields mean some downstream steps are deferred,
with the exact manual command printed for later.

CLI:
    uv run python -m scripts.init_case --output ~/cases/my-case
    uv run python -m scripts.init_case --output ~/cases/my-case --git
    uv run python -m scripts.init_case --output ~/cases/my-case --non-interactive
    uv run python -m scripts.init_case --output ~/cases/my-case --answers answers.yaml
"""

from __future__ import annotations

import argparse
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

CASE_DIRS = [
    "evidence/emails/raw",
    "evidence/emails/structured",
    "evidence/emails/readable",
    "evidence/policy",
    "evidence/valuation",
    "evidence/photos",
    "drafts",
    "complaint_packet/exhibits",
    "complaint_packet/appendix",
    "provenance/snapshots",
    "notes/entities",
]

US_STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

_STATE_NAME_TO_CODE = {v.lower(): k for k, v in US_STATES.items()}

KNOWN_COUNTERPARTY_KINDS = [
    "insurer", "insurance_company",
    "hospital", "provider", "billing_service",
    "merchant", "contractor", "online_seller",
    "individual", "online_platform",
    "landlord", "property_manager",
    "debt_collector", "collection_agency",
    "employer", "former_employer",
]


# -- Fuzzy input helpers -------------------------------------------------

def _normalize_jurisdiction(raw: str) -> tuple[str, str | None]:
    """Return (stored_value, warning_or_None).

    Tries to map free text to a 2-letter US state code.  Always stores
    *something* — never rejects.
    """
    text = raw.strip()
    if not text:
        return "", None

    upper = text.upper()
    if upper in US_STATES:
        return upper, None

    lower = text.lower()
    if lower in _STATE_NAME_TO_CODE:
        code = _STATE_NAME_TO_CODE[lower]
        return code, None

    for name, code in _STATE_NAME_TO_CODE.items():
        if name.startswith(lower) or lower.startswith(name):
            return code, f'Interpreted as {US_STATES[code]} ({code}).'

    return text, (
        "Could not match to a US state. If your jurisdiction is outside "
        "the US, note that authority lookups and deadline data are "
        "US-focused — verify these independently."
    )


def _normalize_date(raw: str) -> tuple[str, str | None]:
    """Return (stored_value, warning_or_None).

    Tries common date formats.  On failure, stores the raw text with a
    warning about the expected format.
    """
    text = raw.strip()
    if not text:
        return "", None

    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        try:
            datetime.strptime(text, "%Y-%m-%d")
            return text, None
        except ValueError:
            pass

    formats = [
        "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y",
        "%B %d %Y", "%B %d, %Y", "%b %d %Y", "%b %d, %Y",
        "%d %B %Y", "%d %b %Y",
        "%B %Y", "%b %Y",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            iso = parsed.strftime("%Y-%m-%d")
            return iso, f"Interpreted as {iso}."
        except ValueError:
            continue

    return text, (
        "Could not parse as a date. Downstream deadline tools expect "
        "YYYY-MM-DD format — you may need to update this later in "
        "intake-answers.yaml."
    )


def _normalize_counterparty(raw: str) -> tuple[str, str | None]:
    """Return (stored_value, warning_or_None)."""
    text = raw.strip()
    if not text:
        return "", None

    lower = text.lower().replace(" ", "_")
    if lower in KNOWN_COUNTERPARTY_KINDS:
        return lower, None

    for kind in KNOWN_COUNTERPARTY_KINDS:
        if kind.startswith(lower) or lower.startswith(kind):
            return kind, f'Matched to known type "{kind}".'

    return text, (
        "Not a recognized counterparty type — the situation classifier "
        "will do its best with keyword matching."
    )


# -- Interactive intake --------------------------------------------------

INTAKE_FIELDS: list[tuple[str, str, Any]] = [
    ("claimant_name", "Your name (as it should appear in paperwork)", None),
    (
        "jurisdiction_state",
        "Jurisdiction — US state name or 2-letter code (e.g. Maryland or MD)",
        _normalize_jurisdiction,
    ),
    (
        "counterparty_kind",
        (
            "Who is the other party? Common types: insurer, landlord, "
            "employer, hospital, debt_collector, merchant, individual"
        ),
        _normalize_counterparty,
    ),
    ("situation", "Describe your situation in 1-2 sentences", None),
    (
        "loss_date",
        "Date of loss or incident (any format, e.g. March 15 2025, or Enter to skip)",
        _normalize_date,
    ),
    ("notes", "Anything else to capture (optional)", None),
]


def _interactive_intake() -> dict[str, str]:
    """Prompt for intake fields.  Returns a dict of answers (may have blanks)."""
    print("\n--- Case intake ---")
    print("Answer each question, or press Enter to skip.\n")
    answers: dict[str, str] = {}
    try:
        for field, prompt, normalizer in INTAKE_FIELDS:
            raw = input(f"  {prompt}\n  > ")
            if normalizer and raw.strip():
                value, warning = normalizer(raw)
                if warning:
                    print(f"  ⤷ {warning}")
                    if value != raw.strip():
                        confirm = input(f"  Accept \"{value}\"? [Y/n] > ")
                        if confirm.strip().lower() in ("n", "no"):
                            value = raw.strip()
                            print(f"  ⤷ Keeping your original input: \"{value}\"")
                answers[field] = value
            else:
                answers[field] = raw.strip()
            print()
    except (EOFError, KeyboardInterrupt):
        print("\n  (interrupted — saving what we have so far)\n")
    return answers


# -- Structure creation --------------------------------------------------

def _create_tree(root: Path) -> list[str]:
    created = []
    for d in CASE_DIRS:
        p = root / d
        p.mkdir(parents=True, exist_ok=True)
        created.append(d)
    return created


def _copy_templates(root: Path) -> list[str]:
    copied = []
    pairs = [
        (REPO_ROOT / "advocacy.toml.example", root / "advocacy.toml"),
        (REPO_ROOT / "templates" / "CLAUDE.md.template", root / "CLAUDE.md"),
        (REPO_ROOT / ".gitignore", root / ".gitignore"),
    ]
    for src, dst in pairs:
        if src.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            copied.append(dst.name)
    return copied


def _init_git(root: Path) -> bool:
    r1 = subprocess.run(["git", "init"], cwd=root, capture_output=True, text=True)
    if r1.returncode != 0:
        print(f"  git init failed: {r1.stderr.strip()}")
        return False
    hook_script = REPO_ROOT / "scripts" / "hooks" / "install_hooks.sh"
    if hook_script.exists():
        r2 = subprocess.run(
            ["bash", str(hook_script), str(root)],
            cwd=root, capture_output=True, text=True,
        )
        if r2.returncode != 0:
            print(f"  hook install failed: {r2.stderr.strip()}")
    return True


# -- Downstream steps ----------------------------------------------------

def _uv_cmd(*args: str) -> list[str]:
    return ["uv", "run", "python", "-m", *args]


def _write_answers_yaml(answers: dict[str, str], path: Path) -> None:
    import yaml  # type: ignore[import-untyped]
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(answers, fh, default_flow_style=False, allow_unicode=True)


def _run_downstream(root: Path, answers: dict[str, str]) -> None:
    intake_out = root / "case-intake.yaml"

    print("\n--- Running downstream tools ---\n")

    # Always run situation_classify
    answers_path = root / "intake-answers.yaml"
    print("[1/3] Classifying situation...")
    r = subprocess.run(
        _uv_cmd(
            "scripts.intake.situation_classify",
            "--answers", str(answers_path),
            "--out", str(intake_out),
        ),
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"  ✗ situation_classify failed: {r.stderr.strip()[:200]}")
        return
    print(f"  ✓ done — wrote {intake_out.name}")

    # Read back the result
    from scripts.intake._common import load_yaml
    try:
        intake = load_yaml(intake_out)
    except Exception:
        intake = {}
    situation_type = intake.get("situation_type", "unknown")
    print(f"  Situation type: {situation_type}")

    jurisdiction = answers.get("jurisdiction_state", "")
    loss_date = answers.get("loss_date", "")

    # Authorities lookup
    if situation_type != "unknown" and jurisdiction:
        print("\n[2/3] Looking up authorities...")
        r = subprocess.run(
            _uv_cmd(
                "scripts.intake.authorities_lookup",
                "--situation", situation_type,
                "--jurisdiction", jurisdiction,
            ),
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if r.returncode == 0:
            print("  ✓ done")
            if r.stdout.strip():
                for line in r.stdout.strip().splitlines():
                    print(f"    {line}")
        else:
            print(f"  ✗ failed: {r.stderr.strip()[:200]}")
    else:
        print("\n[2/3] Skipping authorities lookup", end="")
        if situation_type == "unknown":
            print(" — situation could not be classified.")
        else:
            print(" — no jurisdiction provided.")
        print(
            "  Run later: uv run python -m scripts.intake.authorities_lookup "
            "--situation <type> --jurisdiction <STATE>"
        )

    # Deadline calc
    if situation_type != "unknown" and jurisdiction and loss_date:
        # Only run if loss_date looks like ISO format
        if re.match(r"^\d{4}-\d{2}-\d{2}$", loss_date):
            print("\n[3/3] Computing deadlines...")
            r = subprocess.run(
                _uv_cmd(
                    "scripts.intake.deadline_calc",
                    "--situation", situation_type,
                    "--jurisdiction", jurisdiction,
                    "--loss-date", loss_date,
                ),
                cwd=REPO_ROOT, capture_output=True, text=True,
            )
            if r.returncode == 0:
                print("  ✓ done")
                if r.stdout.strip():
                    for line in r.stdout.strip().splitlines():
                        print(f"    {line}")
            else:
                print(f"  ✗ failed: {r.stderr.strip()[:200]}")
        else:
            print(f"\n[3/3] Skipping deadline calc — loss date \"{loss_date}\" is not in YYYY-MM-DD format.")
            print(
                f"  Update intake-answers.yaml with an ISO date, then run:\n"
                f"  uv run python -m scripts.intake.deadline_calc "
                f"--situation {situation_type} --jurisdiction {jurisdiction} "
                f"--loss-date YYYY-MM-DD"
            )
    else:
        missing = []
        if situation_type == "unknown":
            missing.append("classified situation")
        if not jurisdiction:
            missing.append("jurisdiction")
        if not loss_date:
            missing.append("loss date")
        print(f"\n[3/3] Skipping deadline calc — missing: {', '.join(missing)}.")
        print(
            "  Run later: uv run python -m scripts.intake.deadline_calc "
            "--situation <type> --jurisdiction <STATE> --loss-date YYYY-MM-DD"
        )


# -- Main ----------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize a new case workspace.",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        required=True,
        help="Path for the new case directory (required).",
    )
    parser.add_argument(
        "--git",
        action="store_true",
        help="Initialize a git repo and install the pre-commit evidence hook.",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip the intake questionnaire (just create structure and templates).",
    )
    parser.add_argument(
        "--answers",
        type=Path,
        default=None,
        help="Pre-filled answers YAML (alternative to interactive prompts).",
    )
    args = parser.parse_args(argv)
    root: Path = args.output.resolve()

    # Guard rail: refuse to create inside the repo tree
    try:
        is_under_repo = root.is_relative_to(REPO_ROOT)
    except AttributeError:
        # Python < 3.9 fallback
        try:
            root.relative_to(REPO_ROOT)
            is_under_repo = True
        except ValueError:
            is_under_repo = False

    if is_under_repo:
        print(
            f"Error: output path is inside the toolkit repo:\n"
            f"  repo:   {REPO_ROOT}\n"
            f"  output: {root}\n"
            f"Case materials must live outside the repo to avoid intermixing.\n"
            f"Try: --output ~/cases/{root.name}"
        )
        return 2

    if root.exists():
        print(f"Error: output directory already exists: {root}")
        return 1

    # Phase A: structure
    print(f"Creating case workspace at {root}\n")
    root.mkdir(parents=True, exist_ok=True)
    dirs = _create_tree(root)
    print(f"  Created {len(dirs)} directories")

    files = _copy_templates(root)
    print(f"  Copied templates: {', '.join(files)}")

    git_ok = False
    if args.git:
        print("  Initializing git repo...")
        git_ok = _init_git(root)
        if git_ok:
            print("  ✓ git repo with pre-commit hook")

    # Phase B: intake
    answers: dict[str, str] = {}
    if args.answers:
        from scripts.intake._common import load_yaml
        raw = load_yaml(args.answers)
        answers = {k: str(v) for k, v in raw.items()}
        print(f"\n  Loaded answers from {args.answers}")
    elif not args.non_interactive:
        answers = _interactive_intake()

    if answers:
        answers_path = root / "intake-answers.yaml"
        _write_answers_yaml(answers, answers_path)
        print(f"  Wrote {answers_path.name}")
        _run_downstream(root, answers)

    # Summary
    print("\n" + "=" * 60)
    print(f"Case initialized at {root}/\n")
    print(f"  Directories:  {len(dirs)}")
    print(f"  Templates:    {', '.join(files)}")
    if answers:
        st = "provided"
        situation = answers.get("situation", "")[:60]
        if situation:
            st = situation + ("..." if len(answers.get("situation", "")) > 60 else "")
        print(f"  Intake:       {st}")
    else:
        print("  Intake:       skipped (use --answers or run interactively)")
    print(f"  Git repo:     {'yes, with pre-commit hook' if git_ok else 'no (use --git to enable)'}")

    print("\nNext steps:")
    print(f"  1. Edit {root}/CLAUDE.md with your case context")
    print(f"  2. Drop evidence files into {root}/evidence/")
    print("  3. Hash the evidence tree:")
    print("     uv run python -m scripts.evidence_hash \\")
    print(f"       --root {root}/evidence \\")
    print(f"       --manifest {root}/.evidence-manifest.sha256")
    print("  4. See docs/tutorials/02-ingesting-evidence.md for the full ingest pipeline")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
