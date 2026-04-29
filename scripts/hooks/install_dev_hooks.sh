#!/usr/bin/env bash
# Install the advocacy-toolkit *developer* git hooks into this repo.
#
# Distinct from `install_hooks.sh`, which installs the evidence-immutability
# pre-commit hook into a case workspace. This installer wires the dev-side
# pre-push hook (lint + tests, mirroring CI) into the toolkit repo itself.
#
# Usage:
#   scripts/hooks/install_dev_hooks.sh
#
# Skip in an emergency with `git push --no-verify`.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
HOOK_DIR="$REPO_ROOT/.git/hooks"
HOOK="$HOOK_DIR/pre-push"

if [ ! -d "$HOOK_DIR" ]; then
    echo "no .git/hooks directory at $HOOK_DIR" >&2
    echo "is $REPO_ROOT a git repo?" >&2
    exit 2
fi

# Tiny shim — execs the committed script so updates land without re-running
# this installer.
cat > "$HOOK" <<'SHIM'
#!/usr/bin/env bash
# advocacy-toolkit dev pre-push shim
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
exec bash "$REPO_ROOT/scripts/hooks/dev_pre_push.sh" "$@"
SHIM

chmod +x "$HOOK"
echo "installed advocacy-toolkit dev pre-push hook at $HOOK"
