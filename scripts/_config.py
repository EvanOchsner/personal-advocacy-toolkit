"""Shared config loader for advocacy-toolkit scripts.

Reads `advocacy.toml` from the repo root (or a path supplied by the caller)
and returns a plain dict with defaults filled in. Keeping this loader tiny
and dependency-free is deliberate: these tools need to run on a fresh
machine with nothing but a stdlib Python.
"""

from __future__ import annotations

try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULTS: dict[str, Any] = {
    "evidence": {
        "root": "evidence",
        "manifest": "evidence/MANIFEST.sha256",
        "exclude": [".DS_Store", "**/.DS_Store", "Thumbs.db"],
    },
    "provenance": {
        "snapshot_dir": "provenance/snapshots",
        "report": "provenance/report.json",
    },
    "hooks": {
        "protected_paths": ["evidence"],
        "enforce_manifest_consistency": True,
    },
}


@dataclass
class Config:
    repo_root: Path
    evidence_root: Path
    manifest_path: Path
    exclude: list[str] = field(default_factory=list)
    snapshot_dir: Path = Path("provenance/snapshots")
    report_path: Path = Path("provenance/report.json")
    protected_paths: list[str] = field(default_factory=list)
    enforce_manifest_consistency: bool = True

    @property
    def raw(self) -> dict[str, Any]:
        return {
            "evidence": {
                "root": str(self.evidence_root),
                "manifest": str(self.manifest_path),
                "exclude": list(self.exclude),
            },
            "provenance": {
                "snapshot_dir": str(self.snapshot_dir),
                "report": str(self.report_path),
            },
            "hooks": {
                "protected_paths": list(self.protected_paths),
                "enforce_manifest_consistency": self.enforce_manifest_consistency,
            },
        }


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def find_repo_root(start: Path) -> Path:
    """Walk upward looking for a marker (advocacy.toml, .git, or pyproject.toml)."""
    cur = start.resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / "advocacy.toml").exists():
            return candidate
        if (candidate / ".git").exists():
            return candidate
        if (candidate / "pyproject.toml").exists():
            return candidate
    return start.resolve()


def load_config(
    repo_root: Path | None = None,
    config_path: Path | None = None,
) -> Config:
    """Load config.

    Precedence: explicit `config_path` > `<repo_root>/advocacy.toml` > defaults.
    """
    if repo_root is None:
        repo_root = find_repo_root(Path.cwd())
    repo_root = repo_root.resolve()

    if config_path is None:
        cand = repo_root / "advocacy.toml"
        if cand.exists():
            config_path = cand

    data: dict[str, Any] = dict(DEFAULTS)
    if config_path is not None and config_path.exists():
        with open(config_path, "rb") as fh:
            loaded = tomllib.load(fh)
        data = _deep_merge(DEFAULTS, loaded)

    ev = data["evidence"]
    pr = data["provenance"]
    hk = data["hooks"]

    return Config(
        repo_root=repo_root,
        evidence_root=(repo_root / ev["root"]).resolve(),
        manifest_path=(repo_root / ev["manifest"]).resolve(),
        exclude=list(ev.get("exclude", [])),
        snapshot_dir=(repo_root / pr["snapshot_dir"]).resolve(),
        report_path=(repo_root / pr["report"]).resolve(),
        protected_paths=list(hk.get("protected_paths", [])),
        enforce_manifest_consistency=bool(hk.get("enforce_manifest_consistency", True)),
    )
