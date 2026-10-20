"""Keeping the main checkout in step with origin: fetch, fast-forward, approvals pushed."""

import json

import pytest
from conftest import git
from test_approve import CHANGE, DESIGN, FOLDER

from swfactory import sync
from swfactory.cli import main


def cli(capsys, *argv):
    code = main([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


@pytest.fixture
def other(repo, tmp_path):
    """Another clone of the same remote, standing in for merges done on GitHub."""
    path = tmp_path / "other"
    git("clone", "-q", str(repo.remote), str(path), cwd=tmp_path)
    return path


def push_from(other, name):
    git("pull", "-q", "--rebase", "origin", "main", cwd=other)
    (other / name).write_text("merged on the remote\n")
    git("add", name, cwd=other)
    git("commit", "-q", "-m", f"add {name}", cwd=other)
    git("push", "-q", "origin", "main", cwd=other)
    return git("rev-parse", "HEAD", cwd=other)


@pytest.fixture
def project(repo, fake_orca, monkeypatch):
    monkeypatch.chdir(repo.root)
    return repo


def test_sync_fast_forwards_the_base_branch(project, other, capsys):
    remote_head = push_from(other, "merged.txt")
    code, out = cli(capsys, "sync")
    assert code == 0, out
    assert out["warnings"] == []
    assert out["data"]["head"] == remote_head
    assert git("rev-parse", "HEAD", cwd=project.root) == remote_head


def test_status_sees_remote_merges(project, other, capsys):
    remote_head = push_from(other, "merged.txt")
    code, _ = cli(capsys, "status")
    assert code == 0
    assert git("rev-parse", "HEAD", cwd=project.root) == remote_head


def test_local_approvals_are_rebased_onto_the_remote_and_pushed(project, other, capsys):
    folder = project.root / FOLDER
    folder.mkdir(parents=True)
    (folder / "design.md").write_text(DESIGN)
    git("add", ".", cwd=project.root)
    git("commit", "-q", "-m", "Approve by hand", cwd=project.root)  # only .factory/changes
    remote_head = push_from(other, "merged.txt")
    code, out = cli(capsys, "sync")
    assert code == 0, out
    assert out["warnings"] == []
    assert git("rev-parse", "HEAD~1", cwd=project.root) == remote_head
    assert git("rev-parse", "origin/main", cwd=project.root) == git("rev-parse", "HEAD", cwd=project.root)


def test_the_persons_commits_are_never_rebased_or_pushed(project, other, capsys):
    mine = project.commit("src/app.py", "x = 1\n", "my work")
    push_from(other, "merged.txt")
    code, out = cli(capsys, "sync")
    assert code == 0
    assert git("rev-parse", "HEAD", cwd=project.root) == mine
    assert any("has diverged" in w for w in out["warnings"])


def test_another_branch_is_left_alone(project, other, capsys):
    git("checkout", "-q", "-b", "feature", cwd=project.root)
    before = git("rev-parse", "main", cwd=project.root)
    remote_head = push_from(other, "merged.txt")
    code, out = cli(capsys, "sync")
    assert code == 0, out
    assert git("rev-parse", "main", cwd=project.root) == before
    assert git("rev-parse", "origin/main", cwd=project.root) == remote_head


def test_without_a_remote_nothing_happens(project, capsys):
    git("remote", "remove", "origin", cwd=project.root)
    code, out = cli(capsys, "sync")
    assert code == 0, out
    assert out["warnings"] == []


def test_read_only_views_fetch_at_most_once_a_minute(project, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(sync.git, "fetch", lambda cwd: calls.append(cwd))
    state = tmp_path / "state"
    sync.fetch(project.root, state, force=False)
    sync.fetch(project.root, state, force=False)
    assert len(calls) == 1
    sync.fetch(project.root, state)  # an action always fetches
    assert len(calls) == 2


def test_a_task_starts_from_the_remote_base(project, other, capsys):
    folder = project.root / FOLDER
    folder.mkdir(parents=True)
    (folder / "design.md").write_text(DESIGN)
    assert cli(capsys, "design", "approve", CHANGE, "--message", "apruebo CHG-0012")[0] == 0
    remote_head = push_from(other, "merged.txt")
    code, out = cli(capsys, "task", "claim", "CHG-0012-01")
    assert code == 0, out
    assert git("merge-base", "--is-ancestor", remote_head, "HEAD", cwd=out["data"]["path"]) == ""
