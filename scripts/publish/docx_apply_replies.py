#!/usr/bin/env python3
"""Apply reconciled specialist replies into an unpacked .docx.

Input: an unpacked .docx directory (from docx_unpack.py) and a JSON
file listing replies of shape:

    [
      {
        "thread_root_id": <int>,
        "reply_text": "<body>",
        "edit_proposal": {"find": "...", "replace": "..."}   # optional
      },
      ...
    ]

For each entry:

1. Validate reply_text is non-empty.
2. If entry has an `edit_proposal` and --edit-mode is "tracked" or
   "silent", attempt the document-text edit via `docx_edit_ops`. On
   guardrail failure, downgrade to a synthesized "Suggested edit: …"
   prose reply (logged `DOWNGRADE` to stderr).
3. Citation-footer validator: if reply_text mentions a file path, a
   `Source: <path>:<line>  sha256=<hex>@<provenance>` line is required.
4. Role-aware suffix: for opposing-counsel threads, append the
   `[risk: check with counsel before sending]` flag.
5. Mint a new comment id, append to word/comments.xml, append a
   commentEx entry to word/commentsExtended.xml with paraIdParent
   pointing at the thread-root's paraId, and splice the reply's
   commentRangeStart/End/Reference markers into document.xml so Word
   renders the reply threaded under the parent.

Usage:

    python -m scripts.publish.docx_apply_replies \\
        <unpacked-dir>/ <replies.json> \\
        [--author Claude] [--initials C] \\
        [--edit-mode reply|tracked|silent] \\
        [--for-external-use | --internal-only] \\
        [--commenters .claude-commenters.yaml]

Default --edit-mode is "reply" (no document-text changes).
Default is --internal-only (no publication-safety prompt).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from scripts.publish import docx_edit_ops as edit_ops
from scripts.publish._citation import CITATION_LINE_RE, FILE_PATH_RE
from scripts.publish.docx_catalog import build_catalog

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
W15 = "http://schemas.microsoft.com/office/word/2012/wordml"

PUBLICATION_SENSITIVE_ROLES = frozenset(
    {"lawyer", "regulator", "opposing-counsel", "unknown"}
)
OPPOSING_COUNSEL_SUFFIX = "[risk: check with counsel before sending]"


class ApplyError(Exception):
    pass


def xml_escape_body(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _new_para_id() -> str:
    """8-hex-char paraId matching Word's convention."""
    return uuid.uuid4().hex[:8].upper()


def _validate_edit_proposal(ep: Any) -> str:
    if ep is None:
        return ""
    if not isinstance(ep, dict):
        return "edit_proposal-not-dict"
    if "find" not in ep or "replace" not in ep:
        return "edit_proposal-missing-keys"
    find, replace = ep["find"], ep["replace"]
    if not isinstance(find, str) or not isinstance(replace, str):
        return "edit_proposal-non-string"
    if not find:
        return "find-empty"
    return ""


def _synthesize_downgraded_reply(
    reply_text: str, find: str, replace: str, reason: str
) -> str:
    core = f'Suggested edit: «{find}» \u2192 «{replace}».'
    return f"{core} (Edit not applied: {reason}.) {reply_text}".strip()


def _citation_footer_missing(reply_text: str) -> bool:
    """True if reply cites a file path but has no citation footer."""
    if not re.search(FILE_PATH_RE, reply_text):
        return False
    return re.search(CITATION_LINE_RE, reply_text) is None


def _read_comments_xml(path: Path) -> str:
    if not path.exists():
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<w:comments xmlns:w="{W_NS}" xmlns:w14="{W14}"/>'
        )
    return path.read_text(encoding="utf-8")


def _read_extended_xml(path: Path) -> str:
    if not path.exists():
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<w15:commentsEx xmlns:w15="{W15}"/>'
        )
    return path.read_text(encoding="utf-8")


def _ensure_ns_on_root(xml_text: str, root_tag: str, ns_prefix: str,
                      ns_uri: str) -> str:
    """Inject xmlns:<prefix>="<uri>" into <root> if missing."""
    attr = f'xmlns:{ns_prefix}="{ns_uri}"'
    if attr in xml_text:
        return xml_text
    return re.sub(
        rf"<{re.escape(root_tag)}\b",
        f"<{root_tag} {attr}",
        xml_text,
        count=1,
    )


def _append_before_close(xml_text: str, close_tag: str, new_xml: str) -> str:
    """Insert new_xml just before </close_tag> in xml_text.

    Handles the self-closing form <tag/> by expanding it into <tag></tag>
    first so we can insert children.
    """
    # Self-closing form like '<w:comments xmlns:w="..."/>' — expand.
    open_tag = close_tag.split(":", 1)[-1] if ":" in close_tag else close_tag
    self_close = re.compile(
        rf"<({re.escape(close_tag)})(\s[^>]*?)?/>", re.DOTALL
    )
    m = self_close.search(xml_text)
    if m:
        attrs = m.group(2) or ""
        xml_text = (
            xml_text[:m.start()]
            + f"<{close_tag}{attrs}>{new_xml}</{close_tag}>"
            + xml_text[m.end():]
        )
        return xml_text
    end = xml_text.rfind(f"</{close_tag}>")
    if end < 0:
        raise ApplyError(f"cannot find </{close_tag}> in XML")
    return xml_text[:end] + new_xml + xml_text[end:]


def _build_comment_element(
    comment_id: int,
    para_id: str,
    author: str,
    initials: str,
    iso_date: str,
    escaped_body: str,
) -> str:
    return (
        f'<w:comment w:id="{comment_id}" '
        f'w:author="{xml_escape_body(author)}" '
        f'w:initials="{xml_escape_body(initials)}" '
        f'w:date="{iso_date}">'
        f'<w:p w14:paraId="{para_id}">'
        f'<w:r><w:t xml:space="preserve">{escaped_body}</w:t></w:r>'
        f'</w:p></w:comment>'
    )


def _build_comment_ex(para_id: str, parent_para_id: str) -> str:
    parent_attr = (
        f' w15:paraIdParent="{parent_para_id}"' if parent_para_id else ""
    )
    return (
        f'<w15:commentEx w15:paraId="{para_id}" w15:done="0"{parent_attr}/>'
    )


def _nest_markers(
    doc_text: str, parent_id: int, reply_id: int
) -> str:
    """Inject reply's range-start / range-end / reference markers nested
    inside the parent's existing range-start / range-end pair.

    String-only surgery; no DOM.
    """
    start_pat = rf'<w:commentRangeStart\s+[^>]*w:id="{parent_id}"[^>]*/>'
    end_pat = rf'<w:commentRangeEnd\s+[^>]*w:id="{parent_id}"[^>]*/>'
    ref_pat = (
        rf'<w:r[^>]*>\s*<w:commentReference\s+[^>]*w:id="{parent_id}"'
        rf'[^>]*/>\s*</w:r>'
    )

    m_start = re.search(start_pat, doc_text)
    m_end = re.search(end_pat, doc_text)
    m_ref = re.search(ref_pat, doc_text, re.DOTALL)
    if not (m_start and m_end and m_ref):
        raise ApplyError(
            f"missing anchor markers for parent comment {parent_id}"
        )
    new_start = f'<w:commentRangeStart w:id="{reply_id}"/>'
    new_end = f'<w:commentRangeEnd w:id="{reply_id}"/>'
    new_ref = (
        f'<w:r><w:commentReference w:id="{reply_id}"/></w:r>'
    )
    # Do insertions from the end of the string backward so offsets for
    # earlier insertions remain valid.
    positions = sorted(
        [
            (m_ref.end(), new_ref),
            (m_end.start(), new_end),
            (m_start.end(), new_start),
        ],
        reverse=True,
    )
    for pos, snippet in positions:
        doc_text = doc_text[:pos] + snippet + doc_text[pos:]
    return doc_text


def _next_comment_id(comments_xml: str) -> int:
    ids = [
        int(m.group(1))
        for m in re.finditer(r'<w:comment\b[^>]*w:id="(\d+)"', comments_xml)
    ]
    return (max(ids) + 1) if ids else 0


def _para_id_for(comment_id: int, comments_xml: str) -> str:
    """Extract the top-level w14:paraId of the <w:comment w:id="N">'s first <w:p>."""
    pat = (
        rf'<w:comment\b[^>]*w:id="{comment_id}"[^>]*>'
        rf'.*?<w:p\b[^>]*w14:paraId="([^"]+)"'
    )
    m = re.search(pat, comments_xml, re.DOTALL)
    if not m:
        raise ApplyError(f"cannot find paraId for comment {comment_id}")
    return m.group(1)


def apply_replies(
    unpacked_dir: Path,
    replies: list[dict[str, Any]],
    *,
    author: str = "Claude",
    initials: str = "C",
    edit_mode: str = "reply",
    commenters_path: Path | None = None,
    roles_override: dict[int, str] | None = None,
) -> dict[str, int]:
    """Apply replies in-place. Returns a stats summary."""
    doc_path = unpacked_dir / "word" / "document.xml"
    comments_path = unpacked_dir / "word" / "comments.xml"
    extended_path = unpacked_dir / "word" / "commentsExtended.xml"

    doc_text = doc_path.read_text(encoding="utf-8")
    comments_xml = _read_comments_xml(comments_path)
    extended_xml = _read_extended_xml(extended_path)
    comments_xml = _ensure_ns_on_root(comments_xml, "w:comments", "w14", W14)
    extended_xml = _ensure_ns_on_root(
        extended_xml, "w15:commentsEx", "w15", W15
    )

    # Pre-resolve role for each thread root so we can tag replies.
    roles = dict(roles_override or {})
    if commenters_path is not None and not roles:
        cat = build_catalog(
            unpacked_dir,
            claude_identity=author,
            commenters_path=commenters_path,
        )
        for t in cat["threads"]:
            roles[t["root_id"]] = t["last_author_role"]

    stats = {"applied": 0, "tracked": 0, "silent": 0, "downgrades": 0,
             "failures": 0}

    next_id = _next_comment_id(comments_xml)
    iso = edit_ops.now_iso()

    for entry in replies:
        try:
            parent_id = int(entry["thread_root_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ApplyError(f"missing/invalid thread_root_id: {entry!r}") from exc
        reply_text = entry.get("reply_text") or ""
        if not reply_text.strip():
            raise ApplyError(f"empty reply_text for thread {parent_id}")
        edit_proposal = entry.get("edit_proposal")
        ep_error = _validate_edit_proposal(edit_proposal)

        do_tracked = do_silent = False
        downgrade_reason: str | None = None
        if edit_proposal is not None and not ep_error and edit_mode != "reply":
            if edit_mode == "tracked":
                do_tracked = True
            elif edit_mode == "silent":
                do_silent = True
        elif edit_proposal is not None and ep_error:
            downgrade_reason = ep_error

        find = (edit_proposal or {}).get("find", "") if isinstance(
            edit_proposal, dict
        ) else ""
        replace = (edit_proposal or {}).get("replace", "") if isinstance(
            edit_proposal, dict
        ) else ""

        if do_tracked:
            rev = edit_ops.next_revision_id(doc_text)
            new_doc, ok, reason = edit_ops.apply_tracked_edit(
                doc_text, parent_id, find, replace, rev, author, iso
            )
            if ok:
                doc_text = new_doc
                stats["tracked"] += 1
            else:
                do_tracked = False
                downgrade_reason = reason
        elif do_silent:
            new_doc, ok, reason = edit_ops.apply_silent_edit(
                doc_text, parent_id, find, replace
            )
            if ok:
                doc_text = new_doc
                stats["silent"] += 1
            else:
                do_silent = False
                downgrade_reason = reason

        if downgrade_reason is not None:
            stats["downgrades"] += 1
            print(
                f"DOWNGRADE thread={parent_id} reason={downgrade_reason}",
                file=sys.stderr,
            )
            body = _synthesize_downgraded_reply(
                reply_text, find, replace, downgrade_reason
            )
        elif (
            edit_proposal is not None
            and not ep_error
            and edit_mode == "reply"
        ):
            body = _synthesize_downgraded_reply(
                reply_text, find, replace, "reply-mode"
            )
        else:
            body = reply_text

        # Citation footer check.
        if _citation_footer_missing(body):
            stats["failures"] += 1
            raise ApplyError(
                f"thread {parent_id}: reply cites a file path but has no "
                "'Source: … sha256=…@…' citation footer"
            )

        # Role-aware suffix for opposing-counsel.
        role = roles.get(parent_id, "unknown")
        if role == "opposing-counsel" and OPPOSING_COUNSEL_SUFFIX not in body:
            body = f"{body.rstrip()} {OPPOSING_COUNSEL_SUFFIX}"

        reply_id = next_id
        next_id += 1
        para_id = _new_para_id()
        parent_para_id = _para_id_for(parent_id, comments_xml)
        comment_el = _build_comment_element(
            reply_id, para_id, author, initials, iso, xml_escape_body(body)
        )
        comments_xml = _append_before_close(
            comments_xml, "w:comments", comment_el
        )
        extended_xml = _append_before_close(
            extended_xml, "w15:commentsEx",
            _build_comment_ex(para_id, parent_para_id),
        )
        doc_text = _nest_markers(doc_text, parent_id, reply_id)
        stats["applied"] += 1

    doc_path.write_text(doc_text, encoding="utf-8")
    comments_path.write_text(comments_xml, encoding="utf-8")
    extended_path.write_text(extended_xml, encoding="utf-8")
    return stats


def publication_sensitive_roles(
    unpacked_dir: Path, commenters_path: Path | None, claude_identity: str
) -> set[str]:
    """Return the set of roles present in threads that are being replied to."""
    if commenters_path is None:
        return set()
    cat = build_catalog(
        unpacked_dir,
        claude_identity=claude_identity,
        commenters_path=commenters_path,
    )
    roles = {t["last_author_role"] for t in cat["threads"]}
    return roles & PUBLICATION_SENSITIVE_ROLES


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("unpacked_dir", type=Path)
    p.add_argument("replies_json", type=Path)
    p.add_argument("--author", default="Claude")
    p.add_argument("--initials", default="C")
    p.add_argument(
        "--edit-mode",
        choices=("reply", "tracked", "silent"),
        default="reply",
    )
    p.add_argument(
        "--commenters", type=Path, default=None,
        help="path to .claude-commenters.yaml for role tagging",
    )
    gate = p.add_mutually_exclusive_group()
    gate.add_argument(
        "--for-external-use", dest="external", action="store_true",
        help="warn when outputs will reach sensitive roles (lawyer, "
        "regulator, opposing-counsel). Default is --internal-only.",
    )
    gate.add_argument(
        "--internal-only", dest="external", action="store_false",
        help="skip publication-safety advisories (default).",
    )
    p.set_defaults(external=False)
    args = p.parse_args(argv)

    try:
        replies = json.loads(args.replies_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error reading {args.replies_json}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(replies, list) or not replies:
        print("error: replies JSON must be a non-empty list", file=sys.stderr)
        return 2

    if args.external:
        sensitive = publication_sensitive_roles(
            args.unpacked_dir, args.commenters, args.author
        )
        if sensitive:
            print(
                f"publication-safety: output reaches roles {sorted(sensitive)}. "
                f"Recommend running pii_scrub + docx_metadata_scrub on the "
                f"repacked .docx before handoff.",
                file=sys.stderr,
            )

    try:
        stats = apply_replies(
            args.unpacked_dir,
            replies,
            author=args.author,
            initials=args.initials,
            edit_mode=args.edit_mode,
            commenters_path=args.commenters,
        )
    except ApplyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"apply_replies: applied {stats['applied']} replies, "
        f"{stats['tracked']} tracked-edits, "
        f"{stats['silent']} silent-edits, "
        f"{stats['downgrades']} downgrades, "
        f"{stats['failures']} failures",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
