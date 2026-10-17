"""The only module that runs git (and gh): argument lists, never a shell.

Raises FactoryError with these codes:
- git_unavailable (EXIT_UNAVAILABLE): the git executable is not installed or not on PATH.
- not_a_git_repo (EXIT_PRECONDITION): the working directory is not inside a Git repository.
- git_failed (EXIT_ERROR): any other git failure; the message carries the command and stderr.
- commit_failed (EXIT_PRECONDITION): `git commit` was refused (e.g. by a hook); nothing is committed.
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


def current_branch(cwd: Path | None = None) -> str:
    """The checked-out branch, or "" when HEAD is detached."""
    try:
        return run(["symbolic-ref", "--short", "-q", "HEAD"], cwd)
    except FactoryError as exc:
        if exc.code == "git_failed":
            return ""
        raise


def config_value(key: str, cwd: Path | None = None) -> str:
    """`git config --get <key>`, or "" when it is not set."""
    try:
        return run(["config", "--get", key], cwd)
    except FactoryError as exc:
        if exc.code == "git_failed":
            return ""
        raise


def commit_paths(paths: list[str], message: str, cwd: Path) -> str:
    """Commit the working-tree content of `paths` only (`git commit --only`); other staged or
    unstaged changes stay as they are. New files are made known with `git add -N`, which is
    undone if the commit is refused, so the index ends as it was (commit_failed is raised)."""
    untracked = run(["ls-files", "--others", "--exclude-standard", "--", *paths], cwd).splitlines()
    if untracked:
        run(["add", "-N", "--", *untracked], cwd)
    try:
        run(["commit", "-q", "--only", "-m", message, "--", *paths], cwd)
    except FactoryError as exc:
        if untracked:
            try:
                run(["rm", "-q", "--cached", "--", *untracked], cwd)
            except FactoryError:
                pass  # the commit failure below is what the person needs to see
        message = f"the commit was refused: {exc.message}"
        raise FactoryError("commit_failed", message, EXIT_PRECONDITION) from exc
    return run(["rev-parse", "HEAD"], cwd)
