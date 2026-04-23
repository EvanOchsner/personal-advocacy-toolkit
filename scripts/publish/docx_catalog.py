#!/usr/bin/env python3
"""Extract a catalog of comments and threads from an unpacked .docx.

Reads:

    word/comments.xml          — comment bodies, authors, dates
    word/commentsExtended.xml  — parent/child thread linkage (w15:paraIdParent)
    word/document.xml          — anchor elements for anchor_text extraction

Emits a JSON catalog that:

- Indexes comments by id and groups them into threads via the paraId /
  paraIdParent chain in `commentsExtended.xml`.
- Identifies threads that need a reply: `last commenter != claude_identity`
  AND the last comment is not a `[skip — ...]` marker.
- Parses the tag grammar (`F`, `Q`, `A`, `S`, `F+Q`, etc.) from the
  latest comment text so the driver can pre-route without a router
  specialist call.
- Annotates the latest commenter's `role` from `.claude-commenters.yaml`
  (if present).
- For each needs-reply thread, records any `prior_substantive_reply`
  from Claude on the same thread (>80 chars, not a skip marker) so the
  router can pre-skip obvious re-asks.

Usage:

    uv run python -m scripts.publish.docx_catalog <unpacked-dir>/ \\
        [--claude Claude] \\
        [--commenters .claude-commenters.yaml] \\
        [--out catalog.json]

If `--out` is omitted, JSON is written to stdout. A one-line summary
(`threads_total=N threads_needing_reply=M`) is always printed to stderr.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from defusedxml import ElementTree as DET

# Namespaces we care about. W_NS = wordprocessingml (2006), W14 = 2010
# (adds paraId), W15 = 2012 (adds commentsExtended / paraIdParent).
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
W15_NS = "http://schemas.microsoft.com/office/word/2012/wordml"

SKIP_MARKER_PREFIX = "[skip \u2014 "  # em-dash, matches the source convention

# Comments with a prior substantive Claude reply beyond this length are
# treated as re-asks and flagged to the router.
_SUBSTANTIVE_LEN = 80

# Case-insensitive tag grammar. Matches at start of comment body:
#   F, Q, A, S alone or in combinations joined by '+'
#   optionally followed by ':'
#   optionally followed by body text
_TAG_RE = re.compile(
    r"^\s*((?:[FQA])(?:\+[FQA])*|S)\s*(?::\s*|\s*$)",
    re.IGNORECASE,
)

_CANON_ORDER = {"F": 0, "Q": 1, "A": 2}


def _qname(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def _strip_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_tag(text: str) -> tuple[str, str]:
    """Return (canonical_tag, stripped_text).

    canonical_tag is "" for untagged, "S" for skip, or a "+"-joined
    uppercase subset of F/Q/A in canonical order (F < Q < A). For
    example, "q+f: details" → ("F+Q", "details").
    """
    m = _TAG_RE.match(text)
    if not m:
        return "", text
    raw = m.group(1).upper()
    tail = text[m.end():]
    if raw == "S":
        return "S", tail
    parts = sorted(set(raw.split("+")), key=_CANON_ORDER.get)
    return "+".join(parts), tail


def is_skip_marker(text: str) -> bool:
    return text.lstrip().startswith(SKIP_MARKER_PREFIX)


# ---------------------------------------------------------------------------
# XML parsing


def _parse_comments(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    root = DET.fromstring(path.read_bytes())
    comments: list[dict[str, Any]] = []
    for c in root.findall(_qname(W_NS, "comment")):
        cid = c.attrib.get(_qname(W_NS, "id"))
        if cid is None:
            continue
        # para_id lives on the first inner <w:p>'s w14:paraId attribute.
        para_id = ""
        first_p = c.find(_qname(W_NS, "p"))
        if first_p is not None:
            para_id = first_p.attrib.get(_qname(W14_NS, "paraId"), "")
        # Body text = concatenated <w:t> under this <w:comment>, flattened.
        text_parts: list[str] = []
        for t in c.iter(_qname(W_NS, "t")):
            if t.text:
                text_parts.append(t.text)
        body_text = "".join(text_parts)
        comments.append({
            "id": int(cid),
            "para_id": para_id,
            "author": c.attrib.get(_qname(W_NS, "author"), ""),
            "initials": c.attrib.get(_qname(W_NS, "initials"), ""),
            "date": c.attrib.get(_qname(W_NS, "date"), ""),
            "text": body_text,
        })
    return comments


def _parse_extended(path: Path) -> dict[str, str]:
    """Return {paraId: paraIdParent} from commentsExtended.xml.

    Entries whose paraIdParent is unset map to "" (they are thread roots).
    """
    if not path.exists():
        return {}
    root = DET.fromstring(path.read_bytes())
    out: dict[str, str] = {}
    for ex in root.findall(_qname(W15_NS, "commentEx")):
        pid = ex.attrib.get(_qname(W15_NS, "paraId"), "")
        parent = ex.attrib.get(_qname(W15_NS, "paraIdParent"), "")
        if pid:
            out[pid] = parent
    return out


def _parse_anchors(document_xml: Path) -> dict[int, dict[str, Any]]:
    """Walk document.xml and collect anchor text + para_idx per comment id.

    For each commentRangeStart/End pair, accumulate text content from any
    <w:t> elements that fall within. Also track the paragraph index of
    the range-start so threads can be ordered by document position.
    """
    if not document_xml.exists():
        return {}
    tree = DET.parse(str(document_xml))
    root = tree.getroot()

    active: dict[int, list[str]] = {}
    collected: dict[int, dict[str, Any]] = {}
    para_idx = -1
    crs = _qname(W_NS, "commentRangeStart")
    cre = _qname(W_NS, "commentRangeEnd")
    wp = _qname(W_NS, "p")
    wt = _qname(W_NS, "t")

    for el in root.iter():
        tag = el.tag
        if tag == wp:
            para_idx += 1
        elif tag == crs:
            cid_raw = el.attrib.get(_qname(W_NS, "id"))
            if cid_raw is None:
                continue
            cid = int(cid_raw)
            active[cid] = []
            # Record para_idx only for the first range-start of this id.
            if cid not in collected:
                collected[cid] = {"text": "", "para_idx": max(0, para_idx)}
        elif tag == cre:
            cid_raw = el.attrib.get(_qname(W_NS, "id"))
            if cid_raw is None:
                continue
            cid = int(cid_raw)
            chunks = active.pop(cid, None)
            if chunks is None:
                continue
            joined = _strip_ws("".join(chunks))
            # Cap anchor text so catalogs stay small.
            if len(joined) > 800:
                joined = joined[:800] + " […]"
            if cid in collected and not collected[cid]["text"]:
                collected[cid]["text"] = joined
        elif tag == wt and el.text:
            # Append to every active anchor range.
            for cid in list(active):
                active[cid].append(el.text)
    return collected


# ---------------------------------------------------------------------------
# Commenter roles


def _load_commenters(path: Path | None) -> tuple[list[dict[str, Any]], str]:
    """Return (rules, default_role) loaded from .claude-commenters.yaml.

    Missing file → ([], "unknown"). Malformed file → ([], "unknown") with
    a warning to stderr.
    """
    if path is None or not path.exists():
        return [], "unknown"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        print(f"warning: {path} is not valid YAML ({exc})", file=sys.stderr)
        return [], "unknown"
    rules = data.get("commenters") or []
    default = data.get("default_role", "unknown") or "unknown"
    if not isinstance(rules, list):
        print(f"warning: {path} 'commenters' is not a list", file=sys.stderr)
        rules = []
    return rules, default


def role_for(
    author: str, initials: str, rules: list[dict[str, Any]], default: str
) -> str:
    """Pick the first matching role in rules; default if nothing matches."""
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        match = rule.get("match") or {}
        role = rule.get("role", default)
        want_author = match.get("author")
        want_initials = match.get("initials")
        if want_author is not None and want_author != author:
            continue
        if want_initials is not None and want_initials != initials:
            continue
        # A rule with no match clauses would match everything; skip those
        # unless they were explicitly intended as a catch-all at the end.
        if want_author is None and want_initials is None:
            continue
        return role
    return default


# ---------------------------------------------------------------------------
# Thread building


def _find_root(para_id: str, parents: dict[str, str]) -> str:
    seen: set[str] = set()
    current = para_id
    while current and current in parents and parents[current]:
        if current in seen:
            break
        seen.add(current)
        current = parents[current]
    return current


def build_catalog(
    unpacked_dir: Path,
    *,
    claude_identity: str = "Claude",
    commenters_path: Path | None = None,
) -> dict[str, Any]:
    comments_xml = unpacked_dir / "word" / "comments.xml"
    extended_xml = unpacked_dir / "word" / "commentsExtended.xml"
    document_xml = unpacked_dir / "word" / "document.xml"

    if not document_xml.exists():
        raise FileNotFoundError(f"{document_xml} does not exist")

    comments = _parse_comments(comments_xml)
    parent_map = _parse_extended(extended_xml)
    anchors = _parse_anchors(document_xml)
    rules, default_role = _load_commenters(commenters_path)

    # Annotate each comment with role, thread root, anchor text, skip flag.
    by_id: dict[int, dict[str, Any]] = {}
    by_para: dict[str, dict[str, Any]] = {}
    for c in comments:
        c["role"] = role_for(c["author"], c["initials"], rules, default_role)
        c["is_skip_marker"] = is_skip_marker(c["text"])
        by_id[c["id"]] = c
        if c["para_id"]:
            by_para[c["para_id"]] = c

    # Resolve thread root for each comment.
    for c in comments:
        root_para = _find_root(c["para_id"], parent_map) or c["para_id"]
        c["para_id_parent"] = parent_map.get(c["para_id"], "")
        root_comment = by_para.get(root_para)
        c["thread_root_id"] = root_comment["id"] if root_comment else c["id"]
        anchor = anchors.get(c["thread_root_id"], {})
        c["anchor_text"] = anchor.get("text", "")
        c["para_idx"] = anchor.get("para_idx", 0)

    # Group into threads by root id.
    threads: dict[int, list[dict[str, Any]]] = {}
    for c in comments:
        threads.setdefault(c["thread_root_id"], []).append(c)
    # Each thread: sort by (date, id) so chronology survives even if IDs
    # were reassigned on a prior edit.
    thread_list: list[dict[str, Any]] = []
    for root_id, group in threads.items():
        group.sort(key=lambda x: (x["date"], x["id"]))
        root = group[0]
        last = group[-1]
        needs_reply = (
            last["author"] != claude_identity
            and not last["is_skip_marker"]
        )
        thread_list.append({
            "root_id": root_id,
            "root_para_id": root["para_id"],
            "comment_ids": [c["id"] for c in group],
            "last_author": last["author"],
            "last_author_role": last["role"],
            "last_date": last["date"],
            "last_comment_id": last["id"],
            "needs_reply": needs_reply,
            "anchor_text": root["anchor_text"],
            "para_idx": root["para_idx"],
        })
    thread_list.sort(key=lambda t: t["para_idx"])

    # Build needs_reply entries with thread_context and prior-reply flag.
    needs_reply: list[dict[str, Any]] = []
    for t in thread_list:
        if not t["needs_reply"]:
            continue
        group = threads[t["root_id"]]
        latest = group[-1]
        tag, stripped = parse_tag(latest["text"])
        prior = _find_prior_substantive_reply(group, claude_identity)
        context = [
            {
                "id": c["id"],
                "author": c["author"],
                "role": c["role"],
                "date": c["date"],
                "text": c["text"],
                "is_skip_marker": c["is_skip_marker"],
            }
            for c in group[:-1]  # everything before the latest
        ]
        entry: dict[str, Any] = {
            "thread_root_id": t["root_id"],
            "latest_comment_id": latest["id"],
            "latest_author": latest["author"],
            "latest_author_role": latest["role"],
            "latest_date": latest["date"],
            "raw_text": latest["text"],
            "tag": tag,
            "stripped_text": stripped,
            "anchor_text": t["anchor_text"],
            "para_idx": t["para_idx"],
            "thread_context": context,
        }
        if prior is not None:
            entry["prior_substantive_reply"] = prior
        needs_reply.append(entry)

    next_id = (max((c["id"] for c in comments), default=-1) + 1) if comments else 0

    return {
        "claude_identity": claude_identity,
        "next_comment_id": next_id,
        "skip_marker_prefix": SKIP_MARKER_PREFIX,
        "commenters_default_role": default_role,
        "threads_total": len(thread_list),
        "threads_needing_reply": len(needs_reply),
        "comments": comments,
        "threads": thread_list,
        "needs_reply": needs_reply,
    }


def _find_prior_substantive_reply(
    group: list[dict[str, Any]], claude_identity: str
) -> dict[str, Any] | None:
    # Walk everything except the last comment (which is the latest
    # non-Claude entry asking for a reply). If Claude previously
    # answered at length, flag that as a re-ask candidate.
    for c in reversed(group[:-1]):
        if c["author"] != claude_identity:
            continue
        if c["is_skip_marker"]:
            continue
        if len(c["text"]) < _SUBSTANTIVE_LEN:
            continue
        return {"comment_id": c["id"], "author": c["author"], "date": c["date"]}
    return None


# ---------------------------------------------------------------------------
# CLI


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("unpacked_dir", type=Path)
    p.add_argument("--claude", default="Claude", help="Claude author identity")
    p.add_argument(
        "--commenters",
        type=Path,
        default=None,
        help="path to .claude-commenters.yaml (default: none)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output JSON path (default: stdout)",
    )
    args = p.parse_args(argv)

    try:
        catalog = build_catalog(
            args.unpacked_dir,
            claude_identity=args.claude,
            commenters_path=args.commenters,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(catalog, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    else:
        sys.stdout.write(payload + "\n")
    print(
        f"threads_total={catalog['threads_total']} "
        f"threads_needing_reply={catalog['threads_needing_reply']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
