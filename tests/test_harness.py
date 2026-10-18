"""Checks of the test harness itself: temp repositories and the fake tools."""

import json
import subprocess
import sys
from pathlib import Path

from conftest import FAKES, git, orca_error


def run(tool, *argv, cwd):
    """Run a fake tool the way the CLI does (its Python script), so it works on every OS."""
    return subprocess.run([sys.executable, str(FAKES / tool), *argv], cwd=cwd, capture_output=True, text=True)


def test_repo_has_remote_and_worktrees(repo):
    worktree = repo.add_worktree("feature")
    listing = git("worktree", "list", "--porcelain", cwd=worktree)
    assert Path(listing.splitlines()[0].removeprefix("worktree ")).resolve() == repo.root.resolve()
    assert git("rev-parse", "origin/main", cwd=repo.root) == git("rev-parse", "HEAD", cwd=repo.root)


def test_fake_orca_unknown_command(repo, fake_orca):
    result = run("orca", "nonsense", "--json", cwd=repo.root)
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == "unknown_command"


def test_real_tools_are_never_reached_without_fixtures(tmp_path):
    for tool in ("orca", "gh"):
        result = run(tool, "--version", cwd=tmp_path)
        assert result.returncode == 1
        assert "fixture" in result.stderr


def test_fake_orca_worktree_create_uses_the_repo_not_the_cwd(repo, fake_orca, tmp_path):
    result = run("orca", "worktree", "create", "--name", "w1", "--json", cwd=tmp_path)
    assert result.returncode == 0
    assert "w1" in git("worktree", "list", "--porcelain", cwd=repo.root)


def test_fake_orca_sequence_and_per_terminal_answers(repo, fake_orca):
    fake_orca.respond_fixture("terminal show", "terminal-show-closed", target="term_dead")
    alive = run("orca", "terminal", "show", "--terminal", "term_live", "--json", cwd=repo.root)
    dead = run("orca", "terminal", "show", "--terminal", "term_dead", "--json", cwd=repo.root)
    assert json.loads(alive.stdout)["result"]["terminal"]["connected"] is True
    assert json.loads(dead.stdout)["result"]["terminal"]["connected"] is False
    fake_orca.respond_sequence("status", [{"exit": 1, "stdout": orca_error("down", "x")},
                                          {"exit": 0, "stdout": {"ok": True}}])
    assert run("orca", "status", "--json", cwd=repo.root).returncode == 1
    assert run("orca", "status", "--json", cwd=repo.root).stdout.strip() == '{\n  "ok": true\n}'
    assert json.loads(run("orca", "status", "--json", cwd=repo.root).stdout)["result"]["target"]


def test_fake_gh_failure_keeps_version(repo, fake_gh):
    fake_gh.fail()
    assert run("gh", "--version", cwd=repo.root).returncode == 0
