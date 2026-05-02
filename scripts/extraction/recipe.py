"""Recipe writer — emits a per-evidence reproducibility script.

After a successful cascade run, ``write_recipe`` records:

  - the chosen tier (per page for PDFs)
  - the VLM provider name (if any)
  - the exact overrides applied
  - the SHA-256 of the raw source file (so the script can refuse to
    run against drifted bytes)
  - the case-relative paths of the structured + readable outputs

…then renders a small Python script under
``<case>/extraction/scripts/extract_<source_id>.py`` that imports the
cascade, re-runs it, and asserts byte-identical output.

The script is intentionally short and human-auditable. A regulator
or attorney's expert can read it and follow exactly what was done.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .result import ExtractionResult


SCRIPT_TEMPLATE_PATH = Path(__file__).parent / "templates" / "extract_script.py.j2"


def recipe_dict(
    *,
    case_root: Path,
    source_file: Path,
    source_sha256: str,
    structured_path: Path,
    readable_path: Path,
    result: ExtractionResult,
) -> dict[str, Any]:
    case_root = case_root.resolve()
    return {
        "schema": "pat-extraction-recipe/1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_root": str(case_root),
        "source_file_relative": str(source_file.resolve().relative_to(case_root))
        if str(source_file.resolve()).startswith(str(case_root))
        else str(source_file.resolve()),
        "structured_path_relative": str(structured_path.resolve().relative_to(case_root))
        if str(structured_path.resolve()).startswith(str(case_root))
        else str(structured_path.resolve()),
        "readable_path_relative": str(readable_path.resolve().relative_to(case_root))
        if str(readable_path.resolve()).startswith(str(case_root))
        else str(readable_path.resolve()),
        "method": result.method,
        "tier": result.tier,
        "vlm_provider": result.vlm_provider,
        "settings": _scrub_unserializable(result.settings),
        "overrides_applied": dict(result.overrides_applied),
        "warnings": list(result.warnings),
        "expected": {
            "source_sha256": source_sha256,
            "text_chars": len(result.text),
        },
    }


def write_recipe(
    *,
    case_root: Path,
    source_id: str,
    source_file: Path,
    source_sha256: str,
    structured_path: Path,
    readable_path: Path,
    result: ExtractionResult,
) -> Path:
    """Write the per-source reproducibility script. Returns the script path."""
    recipe = recipe_dict(
        case_root=case_root,
        source_file=source_file,
        source_sha256=source_sha256,
        structured_path=structured_path,
        readable_path=readable_path,
        result=result,
    )
    template = SCRIPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    script_text = _render(template, recipe, case_root=case_root, source_file=source_file,
                          structured_path=structured_path, readable_path=readable_path)
    out_dir = case_root / "extraction" / "scripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"extract_{source_id}.py"
    out_path.write_text(script_text, encoding="utf-8")
    out_path.chmod(0o755)
    return out_path


def _render(
    template: str,
    recipe: dict[str, Any],
    *,
    case_root: Path,
    source_file: Path,
    structured_path: Path,
    readable_path: Path,
) -> str:
    """Tiny mustache-style renderer — avoids requiring Jinja2 at runtime.

    The template uses ``{{ name }}`` placeholders; this helper
    substitutes them. Jinja2 is *available* (it's a base dep) but
    using a 6-line renderer here keeps the recipe writer trivially
    auditable and the template self-contained.
    """
    substitutions = {
        "source_file": str(source_file),
        "structured_path": str(structured_path),
        "readable_path": str(readable_path),
        "case_root": str(case_root),
        "generated_at": recipe["generated_at"],
        "recipe_json": json.dumps(recipe, indent=4, sort_keys=True),
    }
    out = template
    for key, value in substitutions.items():
        out = out.replace("{{ " + key + " }}", str(value))
    return out


def _scrub_unserializable(value: Any) -> Any:
    """Recursively replace non-JSON-serializable values with their repr.

    Settings dicts can carry stuff like the parsed email record (a
    full canonical dict) which is fine, or — rarely — a Path or
    datetime. We never want recipe-writing to crash because of a
    setting we didn't anticipate.
    """
    try:
        json.dumps(value)
        return value
    except TypeError:
        pass
    if isinstance(value, dict):
        return {str(k): _scrub_unserializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_unserializable(v) for v in value]
    return repr(value)
