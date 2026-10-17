"""Where Factory keeps its files, the same from the main checkout and from any worktree.

Live state lives in the main checkout; versioned changes are read from the current checkout.
Nothing here creates directories. Raises the FactoryError codes of factory.git
(git_unavailable, not_a_git_repo, git_failed).
"""

from __future__ import annotations

from pathlib import Path

from factory import git
from factory.output import FactoryError


def repo_root(cwd: Path | None = None) -> Path:
    """Root of the current checkout (main or worktree)."""
    return git.toplevel(cwd)


def main_checkout(cwd: Path | None = None) -> Path:
    """The main checkout of the clone: first entry of `git worktree list --porcelain`."""
    worktrees = git.worktree_paths(cwd)
    if not worktrees:
        raise FactoryError("git_failed", "git worktree list returned no worktrees")
    return worktrees[0]


def state_dir(cwd: Path | None = None) -> Path:
    """Live state shared by every workspace: `<main_checkout>/.factory/state`."""
    return main_checkout(cwd) / ".factory" / "state"


def changes_dir(cwd: Path | None = None) -> Path:
    """Versioned change files of the current checkout: `<repo_root>/.factory/changes`."""
    return repo_root(cwd) / ".factory" / "changes"
