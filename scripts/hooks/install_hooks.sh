#!/usr/bin/env bash
# Install the advocacy-toolkit git hooks into a case workspace.
#
# Usage:
#   scripts/hooks/install_hooks.sh [REPO_ROOT]
#
# With no argument, installs into the current repo (as determined by
# `git rev-parse --show-toplevel`). The hook itself is a tiny shim that
# invokes `python -m scripts.hooks.pre_commit`, so updates to the Python
# logic take effect immediately without re-running this installer.
#
# Users who prefer the `pre-commit` framework should instead install it
# from the repo's `.pre-commit-config.yaml`, which wires the same Python
# entry point as a local hook.

set -euo pipefail

REPO_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
HOOK_DIR="$REPO_ROOT/.git/hooks"
HOOK="$HOOK_DIR/pre-commit"

if [ ! -d "$HOOK_DIR" ]; then
    echo "no .git/hooks directory at $HOOK_DIR" >&2
    echo "is $REPO_ROOT a git repo?" >&2
    exit 2
fi

cat > "$HOOK" <<'SHIM'
#!/usr/bin/env bash
# advocacy-toolkit pre-commit shim
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
exec python3 -m scripts.hooks.pre_commit --repo-root "$REPO_ROOT"
SHIM

chmod +x "$HOOK"
echo "installed advocacy-toolkit pre-commit hook at $HOOK"
