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

# Execute using 'uv run' from the Repo Root
# We export PYTHONPATH=$GIT_ROOT so that 'import cli.commands' works correctly
# regardless of how python is invoked.
export PYTHONPATH="$GIT_ROOT"

(cd "$GIT_ROOT" && uv run cli/bag.py "$@")
