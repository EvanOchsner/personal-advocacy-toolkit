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

# When invoked as a real git pre-push hook, git exports GIT_DIR (and
# sometimes GIT_WORK_TREE) into our environment. pytest then inherits
# them, and any test that shells out to `git init` / `git -C tmp ...`
# in a tmp_path fixture gets confused — the inherited GIT_DIR points
# at *our* repo, not the tmp test repo. That breaks
# test_provenance.py and test_pre_commit_hook.py on worktree pushes.
# Unset before the test pass so each subprocess git sees a clean env
# and discovers its own tmp repo from cwd.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE

echo "[pre-push] ruff check ."
uv run ruff check .

echo "[pre-push] pytest -q"
uv run pytest -q

echo "[pre-push] OK"
