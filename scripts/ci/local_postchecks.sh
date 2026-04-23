#!/usr/bin/env bash
# scripts/ci/local_postchecks.sh
#
# Local mirror of the CI `publication-safety-postchecks` and
# `publication-prep-grep` jobs. Run before pushing:
#
#   bash scripts/ci/local_postchecks.sh
#
# Exits 0 if every post-check is clean, non-zero otherwise. Stdout is
# the same output CI will produce (plus a few local-only banners), so
# diagnosing a CI failure usually means "run this script locally and
# read the output."
#
# The script cd's to the repo root (the parent of scripts/) so it works
# when invoked from anywhere.

set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

TMPDIR="${TMPDIR:-$REPO_ROOT/.tmp}"
mkdir -p "$TMPDIR"

FAIL=0

echo "=========================================================="
echo "[1/4] EXIF scrub post-check over examples/"
echo "=========================================================="
# exif_scrub exits 1 if any image has surviving EXIF/GPS/XMP/etc.
# Dry-run (no --apply): only scans. Synthetic examples should be clean;
# if not, the offending file is printed and we fail.
if uv run python -m scripts.publish.exif_scrub --root examples/; then
  echo "  EXIF post-check: OK"
else
  echo "  EXIF post-check: FAIL" >&2
  FAIL=1
fi

echo
echo "=========================================================="
echo "[2/4] .docx metadata post-check over examples/ and templates/"
echo "=========================================================="
# docx_metadata_scrub's CLI is single-file (--in/--out). We loop over
# every .docx in examples/ and templates/, scrub each to a throwaway
# output, and rely on the script's own post-check (it exits 1 and
# deletes the output if sensitive metadata survived).
DOCX_COUNT=0
DOCX_FAIL=0
DOCX_OUT_DIR="$TMPDIR/docx-postcheck"
rm -rf "$DOCX_OUT_DIR"
mkdir -p "$DOCX_OUT_DIR"

while IFS= read -r -d '' DOCX; do
  DOCX_COUNT=$((DOCX_COUNT + 1))
  OUT="$DOCX_OUT_DIR/$(echo "$DOCX" | tr '/' '_').docx"
  if uv run python -m scripts.publish.docx_metadata_scrub --in "$DOCX" --out "$OUT"; then
    echo "  OK: $DOCX"
  else
    echo "  FAIL: $DOCX" >&2
    DOCX_FAIL=$((DOCX_FAIL + 1))
  fi
done < <(find examples templates -type f -name '*.docx' -print0 2>/dev/null)

if [ "$DOCX_COUNT" -eq 0 ]; then
  echo "  no .docx files found under examples/ or templates/ — skipping"
elif [ "$DOCX_FAIL" -ne 0 ]; then
  echo "  .docx metadata post-check: FAIL ($DOCX_FAIL / $DOCX_COUNT)" >&2
  FAIL=1
else
  echo "  .docx metadata post-check: OK ($DOCX_COUNT files)"
fi

echo
echo "=========================================================="
echo "[3/4] PII scrub dry-run over examples/ (synthetic subs)"
echo "=========================================================="
# pii_scrub exits 0 if no banned-term survivors, 1 if any survive.
# Dry-run (no --apply): files are not mutated; survivor check runs
# against the in-memory scrubbed text. The `--strict` flag does not
# exist on this CLI (the script is strict-by-default: exit 1 on any
# survivor). We pass --report so the sidecar JSON is reviewable.
PII_REPORT="$TMPDIR/pii_scrub_report.json"
if uv run python -m scripts.publish.pii_scrub \
    --root examples/ \
    --substitutions ci/example-subs.yaml \
    --report "$PII_REPORT"; then
  echo "  PII post-check: OK (report: $PII_REPORT)"
else
  echo "  PII post-check: FAIL (report: $PII_REPORT)" >&2
  FAIL=1
fi

echo
echo "=========================================================="
echo "[4/4] Publication-prep banned-terms grep (ci/banned-terms.txt)"
echo "=========================================================="
# Skip blank lines and comments; if the effective term list is empty,
# there is nothing to match and we succeed trivially.
EFFECTIVE_TERMS="$TMPDIR/banned-terms.effective"
grep -vE '^[[:space:]]*(#|$)' ci/banned-terms.txt > "$EFFECTIVE_TERMS" || true

if [ ! -s "$EFFECTIVE_TERMS" ]; then
  echo "  banned-terms.txt is empty (no terms configured) — OK"
else
  # rg -F: fixed-string match. -f FILE: one pattern per line.
  # --no-ignore: do not honor .gitignore; we want to scan everything
  # tracked by the repo. Exclude this file and this script so a banned
  # term listed in banned-terms.txt never matches itself.
  if rg -F -n \
        --no-ignore \
        --glob '!ci/banned-terms.txt' \
        --glob '!scripts/ci/local_postchecks.sh' \
        -f "$EFFECTIVE_TERMS" \
        .; then
    echo "  banned-terms grep: FAIL (see matches above)" >&2
    FAIL=1
  else
    echo "  banned-terms grep: OK (no matches)"
  fi
fi

echo
if [ "$FAIL" -ne 0 ]; then
  echo "LOCAL POST-CHECKS: FAIL" >&2
  exit 1
fi
echo "LOCAL POST-CHECKS: OK"
exit 0
