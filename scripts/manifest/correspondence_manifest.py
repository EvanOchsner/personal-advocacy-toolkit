#!/usr/bin/env python3
"""Build a correspondence manifest by matching messages against config-driven
search criteria.

This replaces the hardcoded `find_claim_emails.py` from the source project.
All search criteria live in an external YAML or TOML file; nothing about
claim numbers, party names, or date windows is baked into the code.

Input can be:
  - one or more `.eml` files / directories of `.eml` files,
  - one or more `.mbox` files,
  - one or more `.json` files produced by email_eml_to_json.py,
  - or any mix of the above.

Usage:
    python -m scripts.manifest.correspondence_manifest \
        --config cfg.yaml \
        --out manifest.yaml \
        path/to/inbox.mbox path/to/eml-dir/

Config schema: see docs/concepts/correspondence-manifest-schema.md.

Top-level keys (all optional, all AND-combined; within each key matches
are OR-combined):

    parties:              # match if any From/To/Cc/Bcc/Reply-To address
      - "adjuster@insco.example"    #   equals (case-insensitive) or
      - "@insco.example"            #   endswith this string.

    subject_regex:         # Python regex, matched against Subject.
      - "(?i)\\bclaim\\b"
      - "(?i)policy #?\\d+"

    body_regex:            # Python regex, matched against plain-text body.
      - "(?i)coverage denied"

    header_contains:       # dict of header-name -> list of substrings.
      X-Claim-Number:
        - "ACR61-3"

    date_range:
      start: "2024-01-01"  # inclusive, ISO-8601
      end:   "2024-12-31"  # inclusive

    identifiers:           # free-form strings searched anywhere in the
      - "ACR61-3"          # message (subject + body + headers).
      - "Claim #12345"
"""
from __future__ import annotations

import argparse
import email
import email.policy
import json
import mailbox
import re
import sys
from datetime import date, datetime, timezone
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable


# --------------------------------------------------------------------------- #
# Config loading
# --------------------------------------------------------------------------- #


def load_config(path: Path) -> dict[str, Any]:
    """Load a YAML or TOML config. Returns {} for an empty file."""
    text = path.read_text()
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                "PyYAML is required to read YAML configs. "
                "Install with: pip install pyyaml"
            ) from exc
        return yaml.safe_load(text) or {}
    if suffix == ".toml":
        try:
            import tomllib  # py311+
        except ImportError:  # pragma: no cover
            import tomli as tomllib  # type: ignore
        return tomllib.loads(text)
    if suffix == ".json":
        return json.loads(text)
    raise SystemExit(f"unsupported config format: {suffix}")


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #


def _parse_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value))


def _message_date(msg: Message) -> date | None:
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def _message_addrs(msg: Message) -> list[str]:
    fields = [v for v in (msg.get(h) for h in ("From", "To", "Cc", "Bcc", "Reply-To")) if v]
    return [addr.lower() for _, addr in getaddresses(fields) if addr]


def _message_plaintext(msg: Message) -> str:
    """Best-effort plain-text body extraction across stdlib parse modes."""
    if hasattr(msg, "get_body"):
        try:
            part = msg.get_body(preferencelist=("plain",))  # type: ignore[attr-defined]
            if part is not None:
                return part.get_content()  # type: ignore[no-any-return]
        except (KeyError, LookupError):
            pass
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", "replace")
        return ""
    payload = msg.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode(msg.get_content_charset() or "utf-8", "replace")
    return str(payload or "")


def _match_parties(msg: Message, parties: list[str]) -> bool:
    addrs = _message_addrs(msg)
    for needle in parties:
        n = needle.lower()
        for a in addrs:
            if n.startswith("@"):
                if a.endswith(n):
                    return True
            elif a == n:
                return True
    return False


def _match_regex_list(value: str | None, patterns: list[str]) -> bool:
    if not value:
        return False
    for pat in patterns:
        if re.search(pat, value):
            return True
    return False


def _match_header_contains(msg: Message, spec: dict[str, list[str]]) -> bool:
    for header, needles in spec.items():
        hv = msg.get(header) or ""
        for n in needles:
            if n in hv:
                return True
    return False


def _match_identifiers(msg: Message, identifiers: list[str]) -> bool:
    hay = " ".join(
        [
            msg.get("Subject") or "",
            _message_plaintext(msg) or "",
            "\n".join(f"{k}: {v}" for k, v in msg.items()),
        ]
    )
    return any(ident in hay for ident in identifiers)


def message_matches(msg: Message, cfg: dict[str, Any]) -> bool:
    """All top-level criteria AND together; within each, OR."""
    if not cfg:
        return True
    if "parties" in cfg and cfg["parties"]:
        if not _match_parties(msg, list(cfg["parties"])):
            return False
    if "subject_regex" in cfg and cfg["subject_regex"]:
        if not _match_regex_list(msg.get("Subject"), list(cfg["subject_regex"])):
            return False
    if "body_regex" in cfg and cfg["body_regex"]:
        if not _match_regex_list(_message_plaintext(msg), list(cfg["body_regex"])):
            return False
    if "header_contains" in cfg and cfg["header_contains"]:
        if not _match_header_contains(msg, dict(cfg["header_contains"])):
            return False
    if "identifiers" in cfg and cfg["identifiers"]:
        if not _match_identifiers(msg, list(cfg["identifiers"])):
            return False
    if "date_range" in cfg and cfg["date_range"]:
        dr = cfg["date_range"]
        start = _parse_date(dr.get("start"))
        end = _parse_date(dr.get("end"))
        mdate = _message_date(msg)
        if mdate is None:
            return False
        if start and mdate < start:
            return False
        if end and mdate > end:
            return False
    return True


# --------------------------------------------------------------------------- #
# Input iteration
# --------------------------------------------------------------------------- #


def _iter_messages(paths: Iterable[Path]) -> Iterable[tuple[str, Message]]:
    """Yield (source_label, Message) pairs across .eml / .mbox / directories."""
    for p in paths:
        if p.is_dir():
            yield from _iter_messages(sorted(p.iterdir()))
            continue
        suffix = p.suffix.lower()
        if suffix == ".eml":
            with p.open("rb") as fh:
                yield str(p), email.message_from_binary_file(fh, policy=email.policy.default)
        elif suffix == ".mbox":
            mb = mailbox.mbox(str(p))
            try:
                for i, msg in enumerate(mb):
                    yield f"{p}#{i}", msg
            finally:
                mb.close()
        elif suffix == ".json":
            # Already-parsed records — reconstruct a minimal Message for matching.
            record = json.loads(p.read_text())
            m = email.message.EmailMessage()
            if record.get("subject"):
                m["Subject"] = record["subject"]
            if record.get("date_raw"):
                m["Date"] = record["date_raw"]
            for field, key in (("From", "from"), ("To", "to"), ("Cc", "cc"), ("Bcc", "bcc")):
                addrs = record.get(key) or []
                if addrs:
                    m[field] = ", ".join(
                        f"{a.get('name','')} <{a.get('email','')}>".strip() for a in addrs
                    )
            for k, v in (record.get("headers") or {}).items():
                if k not in m:
                    try:
                        m[k] = v
                    except Exception:  # noqa: BLE001 - header round-trip best-effort
                        pass
            if record.get("body_text"):
                m.set_content(record["body_text"])
            yield str(p), m


# --------------------------------------------------------------------------- #
# Manifest output
# --------------------------------------------------------------------------- #


def _entry(source: str, msg: Message) -> dict[str, Any]:
    return {
        "source": source,
        "message_id": msg.get("Message-ID"),
        "date": (str(_message_date(msg)) if _message_date(msg) else None),
        "subject": msg.get("Subject"),
        "from": msg.get("From"),
        "to": msg.get("To"),
    }


def build_manifest(paths: list[Path], cfg: dict[str, Any]) -> dict[str, Any]:
    matched: list[dict[str, Any]] = []
    for source, msg in _iter_messages(paths):
        if message_matches(msg, cfg):
            matched.append(_entry(source, msg))
    matched.sort(key=lambda e: (e.get("date") or "", e.get("message_id") or ""))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "criteria": cfg,
        "count": len(matched),
        "entries": matched,
    }


def write_manifest(manifest: dict[str, Any], out_path: Path) -> None:
    suffix = out_path.suffix.lower()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("PyYAML required to write YAML manifests.") from exc
        out_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    else:
        out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("inputs", nargs="+", type=Path)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    manifest = build_manifest(args.inputs, cfg)
    write_manifest(manifest, args.out)
    print(f"matched {manifest['count']} messages -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
