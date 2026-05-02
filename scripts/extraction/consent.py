"""Per-case consent recording for network-bound VLM providers.

Privacy guardrail: any provider with ``requires_network=True``
triggers a one-time per-case confirmation before its first use. The
answer is recorded in ``<case>/extraction/vlm-consent.yaml`` so
future runs (and reproducibility scripts) don't re-prompt.

The going-public skill reads this file to surface any pages that
were transcribed by an external service before publication.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONSENT_FILENAME = "vlm-consent.yaml"


def consent_path(case_root: Path) -> Path:
    return case_root / "extraction" / CONSENT_FILENAME


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {}
    else:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            return {}
        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError:
            return {}
    return data if isinstance(data, dict) else {}


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        return
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        # Fall back to JSON if YAML isn't available — better to record
        # something than nothing.
        path.with_suffix(".json").write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
        )
        return
    path.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")


def has_consent(case_root: Path, provider_name: str) -> bool:
    data = _load(consent_path(case_root))
    entry = (data.get("providers") or {}).get(provider_name)
    return bool(entry and entry.get("granted"))


def record_consent(
    case_root: Path,
    provider_name: str,
    *,
    description: dict[str, Any] | None = None,
    granted: bool = True,
    note: str | None = None,
) -> Path:
    path = consent_path(case_root)
    data = _load(path)
    providers = dict(data.get("providers") or {})
    providers[provider_name] = {
        "granted": granted,
        "granted_at": datetime.now(timezone.utc).isoformat() if granted else None,
        "description": description or {},
        "note": note,
    }
    data["providers"] = providers
    _save(path, data)
    return path


def list_externally_processed_files(case_root: Path) -> list[dict[str, Any]]:
    """Return the recorded list of files transcribed via a network provider.

    Read by the going-public skill to flag externally-processed pages
    before publication. The cascade appends a row here every time a
    network provider successfully transcribes a page.
    """
    data = _load(consent_path(case_root))
    return list(data.get("externally_processed") or [])


def record_external_processing(
    case_root: Path,
    *,
    source_id: str,
    file: str,
    provider_name: str,
    pages: list[int],
) -> None:
    path = consent_path(case_root)
    data = _load(path)
    rows = list(data.get("externally_processed") or [])
    rows.append(
        {
            "source_id": source_id,
            "file": file,
            "provider": provider_name,
            "pages": list(pages),
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    data["externally_processed"] = rows
    _save(path, data)


def prompt_consent_interactive(
    case_root: Path,
    provider_name: str,
    *,
    description: dict[str, Any],
    file_label: str | None = None,
) -> bool:
    """Interactive Y/N prompt; records the answer and returns it.

    Returns ``True`` only if the user explicitly types ``y`` /
    ``yes``. Anything else (including EOF / KeyboardInterrupt) records
    a denial and returns ``False`` so the cascade can fall back to a
    local provider.
    """
    print(
        f"\n  [PRIVACY] Provider {provider_name!r} sends raw page images "
        f"to a third-party service.",
        file=sys.stderr,
    )
    if file_label:
        print(f"  Document: {file_label}", file=sys.stderr)
    print(
        "  Page images may contain SSNs, medical info, account numbers, "
        "or other sensitive evidence. Once sent, recall is not possible.",
        file=sys.stderr,
    )
    print("  Recommended local alternatives: tesseract (default), olmocr.", file=sys.stderr)
    try:
        answer = input(f"  Allow {provider_name} for this case? [y/N] > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    granted = answer in ("y", "yes")
    record_consent(
        case_root,
        provider_name,
        description=description,
        granted=granted,
        note=None if granted else "denied at interactive prompt",
    )
    return granted
