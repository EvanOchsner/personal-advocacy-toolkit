"""CLI entry point for the case-map app.

Usage:
    uv run python -m scripts.app --case-dir path/to/case
                                 [--port 8765] [--no-browser]

Binds 127.0.0.1 only (see scripts/app/__init__.py for airgap notes).
Opens the default browser at the bound URL unless --no-browser.
"""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

from scripts.intake._common import DISCLAIMER

from scripts.app._schema import CaseMapError
from scripts.app.server import BIND_HOST, DEFAULT_PORT, make_app


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Quiet the default per-request log line; keep errors.
        sys.stderr.write(
            "%s  %s\n" % (self.client_address[0], format % args)
        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--case-dir", type=Path, required=True)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open the browser after bind.",
    )
    args = p.parse_args(argv)

    try:
        app = make_app(args.case_dir)
    except CaseMapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    url = f"http://{BIND_HOST}:{args.port}/"
    httpd = make_server(BIND_HOST, args.port, app, handler_class=_QuietHandler)
    print(f"case-map app serving at {url} (case: {args.case_dir})")
    print(DISCLAIMER, file=sys.stderr)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down.")
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
