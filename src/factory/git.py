"""The only module that runs git (and gh): argument lists, never a shell.

Raises FactoryError with these codes:
- git_unavailable (EXIT_UNAVAILABLE): the git executable is not installed or not on PATH.
- not_a_git_repo (EXIT_PRECONDITION): the working directory is not inside a Git repository.
- git_failed (EXIT_ERROR): any other git failure; the message carries the command and stderr.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from factory.output import EXIT_ERROR, EXIT_PRECONDITION, EXIT_UNAVAILABLE, FactoryError


def run(args: list[str], cwd: Path | None = None) -> str:
    """Run `git <args>` in `cwd` and return its stripped stdout."""
    command = ["git", *args]
    # Untranslated messages so failures can be classified by their text.
    env = {**os.environ, "LC_ALL": "C"}
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    except FileNotFoundError as error:
        if cwd is not None and not cwd.is_dir():
            raise FactoryError("git_failed", f"directory does not exist: {cwd}", EXIT_ERROR) from error
        message = "git is not installed or not on PATH"
        raise FactoryError("git_unavailable", message, EXIT_UNAVAILABLE) from error
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not a git repository" in stderr.lower():
            where = cwd or Path.cwd()
            raise FactoryError("not_a_git_repo", f"not inside a Git repository: {where}", EXIT_PRECONDITION)
        raise FactoryError("git_failed", f"{' '.join(command)} failed: {stderr}", EXIT_ERROR)
    return result.stdout.strip()


def toplevel(cwd: Path | None = None) -> Path:
    """Absolute root of the checkout (main or worktree) that contains `cwd`."""
    return Path(run(["rev-parse", "--show-toplevel"], cwd)).resolve()


def worktree_paths(cwd: Path | None = None) -> list[Path]:
    """Absolute paths of every worktree of the clone, main checkout first."""
    output = run(["worktree", "list", "--porcelain"], cwd)
    prefix = "worktree "
    return [Path(line[len(prefix) :]).resolve() for line in output.splitlines() if line.startswith(prefix)]
