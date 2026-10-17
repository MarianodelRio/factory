"""Checks of the test harness itself: temp repositories and the fake tools."""

import json
import subprocess

from conftest import git


def run(*argv, cwd):
    return subprocess.run(list(argv), cwd=cwd, capture_output=True, text=True)


def test_repo_has_remote_and_worktrees(repo):
    worktree = repo.add_worktree("feature")
    listing = git("worktree", "list", "--porcelain", cwd=worktree)
    assert listing.splitlines()[0] == f"worktree {repo.root}"
    assert git("rev-parse", "origin/main", cwd=repo.root) == git("rev-parse", "HEAD", cwd=repo.root)


def test_fake_orca_answers_from_fixtures_and_records_calls(repo, fake_orca):
    result = run("orca", "status", "--json", cwd=repo.root)
    assert result.returncode == 0
    assert json.loads(result.stdout)["result"]["target"]["kind"] == "local"
    assert fake_orca.calls() == [["status", "--json"]]


def test_fake_orca_creates_a_real_worktree(repo, fake_orca):
    result = run("orca", "worktree", "create", "--name", "CHG-0001-01", "--json", cwd=repo.root)
    worktree = json.loads(result.stdout)["result"]["worktree"]
    assert worktree["branch"] == "refs/heads/user/CHG-0001-01"
    assert worktree["path"] in git("worktree", "list", "--porcelain", cwd=repo.root)
    shown = run("orca", "worktree", "show", "--worktree", f"id:{worktree['id']}", "--json", cwd=repo.root)
    assert json.loads(shown.stdout)["result"]["worktree"]["path"] == worktree["path"]


def test_fake_orca_can_fail_and_change_liveness(repo, fake_orca):
    fake_orca.fail("agent launch", code="agent_unavailable")
    fake_orca.respond_fixture("terminal show", "terminal-show-closed")
    launch = run("orca", "agent", "launch", "--agent", "claude", "--json", cwd=repo.root)
    assert launch.returncode == 1
    assert json.loads(launch.stdout)["error"]["code"] == "agent_unavailable"
    shown = run("orca", "terminal", "show", "--terminal", "term_x", "--json", cwd=repo.root)
    assert json.loads(shown.stdout)["result"]["terminal"]["connected"] is False


def test_fake_orca_unknown_command(repo, fake_orca):
    result = run("orca", "nonsense", "--json", cwd=repo.root)
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == "unknown_command"


def test_fake_gh_records_pull_requests(repo, fake_gh):
    created = run("gh", "pr", "create", "--head", "b1", "--base", "main", "--title", "T", "--body", "B",
                  cwd=repo.root)
    assert created.stdout.strip() == "https://github.com/example/repo/pull/1"
    listed = run("gh", "pr", "list", "--head", "b1", "--json", "number,url", cwd=repo.root)
    assert json.loads(listed.stdout) == [{"number": 1, "url": "https://github.com/example/repo/pull/1"}]
    assert fake_gh.prs()[0]["body"] == "B"


def test_fake_gh_failure(repo, fake_gh):
    fake_gh.fail()
    assert run("gh", "pr", "list", "--head", "b1", cwd=repo.root).returncode == 1
