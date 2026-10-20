"""Keep the main checkout in step with `origin`: fetch, fast-forward the base branch and push the
approval commits, so merges done on GitHub are seen and new work starts from the latest base.

Never forces, never merges and never touches uncommitted work: anything it cannot do safely is
returned as a warning for the person. Raises nothing but the codes of factory.git for a missing git.
"""

from __future__ import annotations

import time
from pathlib import Path

from swfactory import git
from swfactory.output import FactoryError

FETCH_EVERY_SECONDS = 60.0  # read-only views (status, board) fetch at most this often
STAMP = "last_fetch"
# Commits that only touch these paths are Factory bookkeeping (approvals, rejections) that
# may be rebased onto the remote base and pushed.
BOOKKEEPING = ".factory/changes/"


def fetch(main_checkout: Path, state_dir: Path, force: bool = True) -> list[str]:
    """`git fetch origin`; without `force`, only if the last fetch is older than a minute."""
    if not git.has_remote("origin", main_checkout):
        return []
    stamp = state_dir / STAMP
    if not force and stamp.exists() and time.time() - stamp.stat().st_mtime < FETCH_EVERY_SECONDS:
        return []
    try:
        git.fetch(main_checkout)
    except FactoryError as exc:
        return [f"could not fetch origin (working with the local state): {exc.message}"]
    state_dir.mkdir(parents=True, exist_ok=True)
    stamp.write_text(f"{time.time()}\n", encoding="utf-8")
    return []


def update_base(main_checkout: Path, base: str) -> list[str]:
    """Bring the local base branch up to `origin/<base>` when the main checkout is on it: a
    fast-forward, or a rebase of local approval commits; then push those commits."""
    upstream = f"origin/{base}"
    if not git.ref_exists(upstream, main_checkout) or git.current_branch(main_checkout) != base:
        return []
    ahead = git.commits_in(f"{upstream}..{base}", main_checkout)
    behind = git.commits_in(f"{base}..{upstream}", main_checkout)
    bookkeeping = _only_bookkeeping(main_checkout, base)
    if behind and not ahead:
        try:
            git.run(["merge", "-q", "--ff-only", upstream], main_checkout)
        except FactoryError as exc:
            return [f"could not fast-forward {base} to {upstream}: {exc.message}"]
    elif behind and ahead:
        if not bookkeeping or not git.is_clean(main_checkout):
            return [f"{base} has diverged from {upstream}: pull it yourself (git pull)"]
        try:
            git.run(["rebase", "-q", upstream], main_checkout)
        except FactoryError as exc:
            try:
                git.run(["rebase", "--abort"], main_checkout)
            except FactoryError:
                pass  # no rebase in progress: the failure below is what matters
            return [f"could not rebase the approval commits of {base} onto {upstream}: {exc.message}"]
    if ahead and bookkeeping:
        return push_approvals(main_checkout, base)
    return []


def _only_bookkeeping(main_checkout: Path, base: str) -> bool:
    """The base branch is ahead of `origin/<base>` only with Factory bookkeeping commits."""
    revision_range = f"origin/{base}..{base}"
    return bool(git.commits_in(revision_range, main_checkout)) and all(
        path.startswith(BOOKKEEPING) for path in git.paths_in(revision_range, main_checkout))


def push_approvals(main_checkout: Path, base: str) -> list[str]:
    """Push the base branch (never forced) so approvals reach the remote, only when what it would
    publish is Factory bookkeeping: the person's own unpushed commits are never pushed."""
    if not git.has_remote("origin", main_checkout) or not git.ref_exists(f"origin/{base}", main_checkout):
        return []
    if not git.commits_in(f"origin/{base}..{base}", main_checkout):
        return []
    if not _only_bookkeeping(main_checkout, base):
        return [f"{base} has other unpushed commits besides the approval: push it yourself when ready"]
    try:
        git.push_branch(base, main_checkout)
    except FactoryError as exc:
        return [f"{base} was not pushed: {exc.message}"]
    return []


def refresh(main_checkout: Path, state_dir: Path, base: str | None, force: bool = True) -> list[str]:
    """Fetch, then update the local base branch."""
    warnings = fetch(main_checkout, state_dir, force)
    if base:
        warnings += update_base(main_checkout, base)
    return warnings
