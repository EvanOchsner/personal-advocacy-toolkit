"""Regenerators for the Maryland-Mustang synthetic example artifacts.

Phase 2 shipped several example artifacts as markdown fallbacks because
Pillow / reportlab / python-docx were not available in that authoring
environment. This package regenerates the real PDF / JPEG / DOCX
artifacts from their canonical markdown sources.

CLI entry point: ``uv run python -m scripts.synthetic_case.regenerate``.

Every output is stamped ``SYNTHETIC -- NOT A REAL CASE`` in both
visible content (header/footer/watermark) and file metadata
(PDF /Info, EXIF UserComment, docx core-properties description).
EXIF GPS and author-identifying fields are explicitly emptied.
"""
