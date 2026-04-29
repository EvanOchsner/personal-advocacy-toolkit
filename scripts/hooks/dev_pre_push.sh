#!/usr/bin/env bash
# advocacy-toolkit dev pre-push hook.
#
# Runs the same checks CI runs (`uv run ruff check .` and `uv run pytest -q`)
# before allowing a `git push` to publish anything. The goal is parity with
# the CI lint+test job: green locally → green on the runner.
#
# Skip in an emergency with `git push --no-verify`. If you find yourself
# reaching for that more than once, fix the underlying issue rather than
# making bypass routine.
#
# Install via scripts/hooks/install_dev_hooks.sh.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

echo "[pre-push] ruff check ."
uv run ruff check .

echo "[pre-push] pytest -q"
uv run pytest -q

echo "[pre-push] OK"
