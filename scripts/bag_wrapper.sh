#!/bin/bash

# Bag CLI Wrapper
# Automatically finds and runs the cli/bag.py associated with the current git worktree/repo.

# 1. Find the Git Root (works for main repo and worktrees)
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)

if [ -z "$GIT_ROOT" ]; then
    echo "⚠️  Not inside a git repository."
    echo "   Running global/default bag..."
    # Fallback to the hardcoded main repo if not in a git dir? 
    # Or just exit. For safety, let's error out to prevent confusion.
    exit 1
fi

# 2. Check for the Bag CLI executable in this repo
BAG_EXE="$GIT_ROOT/cli/bag.py"

if [ ! -f "$BAG_EXE" ]; then
    echo "⚠️  Could not find 'cli/bag.py' in current repo ($GIT_ROOT)."
    exit 1
fi

# 3. Execute using 'uv run' from the Repo Root
# We run from GIT_ROOT to ensure python path/imports work correctly.
# But we might want to preserve the original CWD for some commands?
# 'bag app start' finds root dynamically, so running from GIT_ROOT is safer for imports.
# However, if we pass args that are relative paths, valid from original CWD, this `cd` breaks them.
# BUT, `bag` commands usually don't take file args.
# Let's try running relative to CWD but setting PYTHONPATH?
# Actually 'uv run' usually handles project root detection if pyproject.toml is there.

# Simplest reliable method: cd to root, run, but pass original CWD context if needed?
# Most bag commands seem global or auto-detect root.

(cd "$GIT_ROOT" && uv run cli/bag.py "$@")
