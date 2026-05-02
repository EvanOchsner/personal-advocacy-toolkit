"""Shared fixtures for extraction tests.

Most tests in this directory operate against synthesized inputs
(reportlab-generated PDFs, hand-rolled HTML strings, stdlib-built
.eml files) so they don't depend on the in-repo synthetic case.
The fixtures here provide a stable, reusable case_root layout.
"""
from __future__ import annotations

import email.message
import email.policy
from email.utils import format_datetime
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pytest


@pytest.fixture
def case_root(tmp_path: Path) -> Path:
    """A minimal case workspace with the directories the cascade expects."""
    root = tmp_path / "case"
    (root / "evidence" / "policy" / "raw").mkdir(parents=True)
    (root / "evidence" / "policy" / "structured").mkdir(parents=True)
    (root / "evidence" / "policy" / "readable").mkdir(parents=True)
    (root / "extraction" / "overrides").mkdir(parents=True)
    (root / "extraction" / "scripts").mkdir(parents=True)
    return root


@pytest.fixture
def make_eml(tmp_path: Path) -> Callable[..., Path]:
    """Build a tiny `.eml` on disk and return its path.

    Useful for testing the email tier-0 extractor without committing
    a fixture file. The output is RFC 5322-compliant via stdlib's
    email package.
    """

    def _build(
        *,
        from_addr: str = "Sally <sally@example.com>",
        to_addr: str = "Adjuster <adjuster@cim.example>",
        subject: str = "test",
        body: str = "Hello, world.",
        date: datetime | None = None,
        message_id: str = "<test@example.com>",
    ) -> Path:
        msg = email.message.EmailMessage(policy=email.policy.default)
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg["Message-ID"] = message_id
        msg["Date"] = format_datetime(date or datetime(2025, 6, 1, tzinfo=timezone.utc))
        msg.set_content(body)
        path = tmp_path / "synth.eml"
        path.write_bytes(bytes(msg))
        return path

    return _build


@pytest.fixture
def make_simple_pdf(tmp_path: Path) -> Callable[..., Path]:
    """Build a synthetic PDF with a real text layer using reportlab."""

    def _build(*, pages: list[str] | None = None, name: str = "synth.pdf") -> Path:
        reportlab = pytest.importorskip("reportlab")  # noqa: F841
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter

        page_texts = pages or ["Page one with several real words about insurance claims."]
        path = tmp_path / name
        c = canvas.Canvas(str(path), pagesize=letter)
        for text in page_texts:
            c.drawString(72, 720, text)
            c.showPage()
        c.save()
        return path

    return _build


@pytest.fixture
def make_html(tmp_path: Path) -> Callable[..., Path]:
    """Write a small HTML doc to disk."""

    def _build(body: str, *, title: str = "T", name: str = "synth.html") -> Path:
        doc = (
            f"<!DOCTYPE html><html><head><title>{title}</title>"
            f"<meta charset='utf-8'></head><body>{body}</body></html>"
        )
        path = tmp_path / name
        path.write_bytes(doc.encode("utf-8"))
        return path

    return _build
