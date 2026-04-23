#!/usr/bin/env bash
# build_pdf.sh — complaint-PDF assembler driven by a packet manifest.
#
# This is a thin wrapper around `uv run python -m scripts.packet.build`. It
# exists so that users (and CI) can invoke packet assembly from shells
# and makefiles without remembering the Python entry point, and so
# that per-authority driver scripts can be written simply as:
#
#     scripts/packet/build_pdf.sh path/to/manifest.yaml
#
# The wrapper performs three jobs:
#   1. Resolve the repo root (the directory containing this script's
#      parent's parent) so `uv run python -m scripts.packet.build` works
#      regardless of the caller's cwd.
#   2. Verify python is available.
#   3. Forward all arguments to the Python entry point.
#
# There are intentionally no authority-specific branches here. All
# authority-, case-, and jurisdiction-specific behaviour lives in the
# manifest passed on the command line.

set -euo pipefail

if [[ $# -lt 1 ]]; then
  cat >&2 <<'USAGE'
Usage: build_pdf.sh MANIFEST [BUILD_ARGS...]

  MANIFEST      Path to a packet-manifest.yaml file.
  BUILD_ARGS    Forwarded verbatim to `uv run python -m scripts.packet.build`.

Example:
  build_pdf.sh examples/mycase/packet-manifest.yaml -v
USAGE
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "build_pdf.sh: python3 not found on PATH" >&2
  exit 1
fi

cd "${REPO_ROOT}"
exec python3 -m scripts.packet.build "$@"
