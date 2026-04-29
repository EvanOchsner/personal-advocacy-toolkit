#!/usr/bin/env python3
"""Reconcile two independent authority lookups: local (authorities.yaml) vs.
web research. Pure data shaping — the skill drives I/O.

Both inputs share the JSON shape produced by authorities_lookup.lookup():

    {
      "disclaimer": str,
      "situation": str,
      "jurisdiction": str | None,
      "warnings": [str, ...],
      "authorities": [
        {"name": str, "short_name": str, "kind": str, "scope": str,
         "url": str, "notes": str, "status": "populated" | "stub" | ...},
        ...
      ],
    }

Web results additionally carry:
    "sources": [{"url": str, "accessed_on": str (ISO date)}, ...]
    "accessed_on": str (ISO date)

Reconciliation output:

    {
      "disclaimer": str,
      "situation": str,
      "jurisdiction": str | None,
      "matched":      [{"local": <auth>, "web": <auth>}, ...],
      "local_only":   [<auth>, ...],
      "web_only":     [<auth>, ...],
      "conflicts":    [{"local": <auth>, "web": <auth>,
                        "fields": ["url" | "kind" | ...]}, ...],
      "staleness_flags": [{"local": <auth>, "reason": str}, ...],
      "web_unavailable": bool,
      "local_warnings": [str, ...],
      "web_warnings":   [str, ...],
    }
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts.intake._common import DISCLAIMER


_NAME_MATCH_THRESHOLD = 0.82
_STUB_MARKERS = {"todo", "stub", ""}


def _norm_short(s: str | None) -> str:
    return (s or "").strip().upper()


def _norm_name(s: str | None) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def _is_stub(auth: dict[str, Any]) -> bool:
    if (auth.get("status") or "").lower() in _STUB_MARKERS - {""}:
        return True
    short = _norm_short(auth.get("short_name"))
    if short in {"TODO", ""}:
        return True
    if "todo" in (auth.get("name") or "").lower():
        return True
    return False


def _registrable_domain(url: str | None) -> str:
    """Return the lower-cased host stripped of leading 'www.'.

    Not a true PSL implementation — sufficient for matching .gov/.us hosts
    that this script compares.
    """
    if not url:
        return ""
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _match(local_auth: dict[str, Any], web_auth: dict[str, Any]) -> bool:
    ls = _norm_short(local_auth.get("short_name"))
    ws = _norm_short(web_auth.get("short_name"))
    if ls and ws and ls == "TODO":
        pass
    elif ls and ws and ls == ws:
        return True
    ln = _norm_name(local_auth.get("name"))
    wn = _norm_name(web_auth.get("name"))
    if not ln or not wn:
        return False
    ratio = difflib.SequenceMatcher(None, ln, wn).ratio()
    return ratio >= _NAME_MATCH_THRESHOLD


def _conflict_fields(local: dict[str, Any], web: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    l_dom = _registrable_domain(local.get("url"))
    w_dom = _registrable_domain(web.get("url"))
    if l_dom and w_dom and l_dom != w_dom:
        fields.append("url")
    l_kind = (local.get("kind") or "").strip().lower()
    w_kind = (web.get("kind") or "").strip().lower()
    if l_kind and w_kind and l_kind != w_kind:
        fields.append("kind")
    l_addr = (local.get("mailing_address") or "").strip()
    w_addr = (web.get("mailing_address") or "").strip()
    if l_addr and w_addr and l_addr != w_addr:
        fields.append("mailing_address")
    return fields


def reconcile(
    local_result: dict[str, Any],
    web_result: dict[str, Any] | None,
) -> dict[str, Any]:
    local_auths = list(local_result.get("authorities") or [])
    web_unavailable = web_result is None or not web_result.get("authorities")
    web_auths = list((web_result or {}).get("authorities") or [])
    web_sources = list((web_result or {}).get("sources") or [])
    web_source_domains = {
        _registrable_domain(s.get("url") if isinstance(s, dict) else s)
        for s in web_sources
    }
    web_source_domains.discard("")
    # Also treat web authority URLs themselves as "sources we reached."
    for w in web_auths:
        d = _registrable_domain(w.get("url"))
        if d:
            web_source_domains.add(d)

    matched: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    used_web_idx: set[int] = set()
    local_only: list[dict[str, Any]] = []

    for la in local_auths:
        if _is_stub(la):
            # Stubs do not count as "local has this" for matching purposes,
            # but they still surface in local_only so the reconciler can
            # tell the user "local is incomplete here."
            local_only.append(la)
            continue
        paired_idx: int | None = None
        for i, wa in enumerate(web_auths):
            if i in used_web_idx:
                continue
            if _match(la, wa):
                paired_idx = i
                break
        if paired_idx is None:
            local_only.append(la)
            continue
        used_web_idx.add(paired_idx)
        wa = web_auths[paired_idx]
        fields = _conflict_fields(la, wa)
        if fields:
            conflicts.append({"local": la, "web": wa, "fields": fields})
        else:
            matched.append({"local": la, "web": wa})

    web_only = [w for i, w in enumerate(web_auths) if i not in used_web_idx]

    # Staleness: a populated local entry whose registrable domain isn't seen
    # anywhere in the web pass. Only meaningful when the web pass actually
    # ran and returned something — otherwise we can't conclude staleness.
    staleness_flags: list[dict[str, Any]] = []
    if not web_unavailable:
        for la in local_auths:
            if _is_stub(la):
                continue
            if (la.get("status") or "").lower() != "populated":
                continue
            l_dom = _registrable_domain(la.get("url"))
            if not l_dom:
                continue
            if l_dom not in web_source_domains:
                staleness_flags.append({
                    "local": la,
                    "reason": (
                        f"local URL domain {l_dom!r} not encountered in "
                        "web pass — agency page may have moved or been "
                        "renamed; verify against the agency directly."
                    ),
                })

    return {
        "disclaimer": DISCLAIMER,
        "situation": local_result.get("situation"),
        "jurisdiction": local_result.get("jurisdiction"),
        "matched": matched,
        "local_only": local_only,
        "web_only": web_only,
        "conflicts": conflicts,
        "staleness_flags": staleness_flags,
        "web_unavailable": web_unavailable,
        "local_warnings": list(local_result.get("warnings") or []),
        "web_warnings": list((web_result or {}).get("warnings") or []),
    }


def format_text(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"[{result['disclaimer']}]")
    lines.append(
        f"Reconciliation for situation={result['situation']} "
        f"jurisdiction={result['jurisdiction']}"
    )
    lines.append("")

    def _fmt_auth(a: dict[str, Any]) -> str:
        short = a.get("short_name") or "?"
        name = a.get("name") or "?"
        url = a.get("url") or ""
        return f"{name} ({short}){' — ' + url if url else ''}"

    lines.append("== Local findings ==")
    for w in result["local_warnings"]:
        lines.append(f"  WARNING: {w}")
    local_auths = (
        [m["local"] for m in result["matched"]]
        + [c["local"] for c in result["conflicts"]]
        + list(result["local_only"])
    )
    if not local_auths:
        lines.append("  (no local authorities)")
    for a in local_auths:
        tag = " [STUB]" if _is_stub(a) else ""
        lines.append(f"  - {_fmt_auth(a)}{tag}")

    lines.append("")
    lines.append("== Web findings ==")
    if result["web_unavailable"]:
        lines.append("  Web pass returned no usable results.")
    else:
        for w in result["web_warnings"]:
            lines.append(f"  WARNING: {w}")
        web_auths = (
            [m["web"] for m in result["matched"]]
            + [c["web"] for c in result["conflicts"]]
            + list(result["web_only"])
        )
        if not web_auths:
            lines.append("  (no web authorities)")
        for a in web_auths:
            lines.append(f"  - {_fmt_auth(a)}")

    lines.append("")
    lines.append("== Reconciliation ==")
    if result["matched"]:
        lines.append("  Agreement (both halves):")
        for m in result["matched"]:
            lines.append(f"    - {_fmt_auth(m['local'])}")
    if result["conflicts"]:
        lines.append("  Conflicts (matched but disagree):")
        for c in result["conflicts"]:
            fields = ", ".join(c["fields"])
            lines.append(f"    - {_fmt_auth(c['local'])}")
            lines.append(f"        local: {_fmt_auth(c['local'])}")
            lines.append(f"        web:   {_fmt_auth(c['web'])}")
            lines.append(f"        fields differ: {fields}")
    if result["local_only"]:
        lines.append("  Local-only (web pass did not surface):")
        for a in result["local_only"]:
            tag = " [STUB]" if _is_stub(a) else ""
            lines.append(f"    - {_fmt_auth(a)}{tag}")
    if result["web_only"]:
        lines.append("  Web-only (not in local table):")
        for a in result["web_only"]:
            lines.append(f"    - {_fmt_auth(a)}")
    if result["staleness_flags"]:
        lines.append("  Staleness flags:")
        for f in result["staleness_flags"]:
            lines.append(f"    - {_fmt_auth(f['local'])}")
            lines.append(f"        {f['reason']}")

    lines.append("")
    lines.append(
        "Use your own judgement. Verify against the agency's own intake "
        "page before filing."
    )
    lines.append(f"-- {result['disclaimer']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--local", type=Path, required=True,
                   help="Path to local-lookup JSON (from authorities_lookup --format json)")
    p.add_argument("--web", type=Path, default=None,
                   help="Path to web-research JSON; omit if web pass unavailable")
    p.add_argument("--format", choices=("text", "json"), default="text")
    args = p.parse_args(argv)

    local_result = json.loads(args.local.read_text(encoding="utf-8"))
    web_result: dict[str, Any] | None = None
    if args.web is not None:
        web_result = json.loads(args.web.read_text(encoding="utf-8"))

    result = reconcile(local_result, web_result)
    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
