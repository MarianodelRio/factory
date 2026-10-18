from __future__ import annotations

from pathlib import Path

import pytest
from conftest import Repo

from swfactory import paths
from swfactory.output import EXIT_PRECONDITION, EXIT_UNAVAILABLE, FactoryError


def test_main_checkout_and_state_dir_are_the_same_from_main_and_worktree(repo: Repo) -> None:
    worktree = repo.add_worktree("feature")
    root = repo.root.resolve()
    assert paths.main_checkout(repo.root) == root
    assert paths.main_checkout(worktree) == root
    assert paths.state_dir(repo.root) == root / ".factory" / "state"
    assert paths.state_dir(worktree) == paths.state_dir(repo.root)


def test_repo_root_and_changes_dir_follow_the_current_checkout(repo: Repo) -> None:
    worktree = repo.add_worktree("feature")
    assert paths.repo_root(repo.root) == repo.root.resolve()
    assert paths.repo_root(worktree) == worktree.resolve()
    assert paths.changes_dir(repo.root) == repo.root.resolve() / ".factory" / "changes"
    assert paths.changes_dir(worktree) == worktree.resolve() / ".factory" / "changes"


def test_works_from_a_subdirectory(repo: Repo) -> None:
    worktree = repo.add_worktree("feature")
    sub = worktree / "src" / "pkg"
    sub.mkdir(parents=True)
    assert paths.repo_root(sub) == worktree.resolve()
    assert paths.state_dir(sub) == repo.root.resolve() / ".factory" / "state"


def test_defaults_to_the_current_directory(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    worktree = repo.add_worktree("feature")
    monkeypatch.chdir(worktree)
    assert paths.repo_root() == worktree.resolve()
    assert paths.main_checkout() == repo.root.resolve()


def test_does_not_create_directories(repo: Repo) -> None:
    paths.state_dir(repo.root)
    paths.changes_dir(repo.root)
    assert not (repo.root / ".factory").exists()


def test_outside_a_git_repo_is_not_a_git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    for function in (paths.repo_root, paths.main_checkout, paths.state_dir, paths.changes_dir):
        with pytest.raises(FactoryError) as caught:
            function(plain)
        assert caught.value.code == "not_a_git_repo"
        assert caught.value.exit_code == EXIT_PRECONDITION


def test_git_missing_is_git_unavailable(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    with pytest.raises(FactoryError) as caught:
        paths.state_dir(repo.root)
    assert caught.value.code == "git_unavailable"
    assert caught.value.exit_code == EXIT_UNAVAILABLE
