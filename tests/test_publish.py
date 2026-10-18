import json
import shutil
import sys

import pytest
from conftest import FAKES, git
from test_claim_launch import TASK, orca_calls
from test_finish import ready_to_finish as ready_to_finish  # noqa: F401

from swfactory.cli import main

MINOR = {"severity": "minor", "file": "src/bookings/model.py", "line": 1, "problem": "name is vague",
         "fix": "rename RULE"}


@pytest.fixture
def done(ready_to_finish, capsys, tmp_path):  # noqa: F811
    store = ready_to_finish["store"]
    store.update_task(TASK, lambda s: {**s, "reviews": [{**s["reviews"][0], "findings": [MINOR]}]}, "x")
    assert main(["task", "finish", TASK, "--memory", "Added ADR 0003"]) == 0
    capsys.readouterr()
    return ready_to_finish


def publish(capsys):
    code = main(["task", "publish", TASK, "--json"])
    return code, json.loads(capsys.readouterr().out)


def remote_branches(repo):
    return sorted(line.split("refs/heads/")[1] for line in
                  git("ls-remote", "--heads", "origin", cwd=repo.root).splitlines())


def test_publish_pushes_only_the_branch_and_opens_a_pr(done, fake_gh, fake_orca, capsys):
    repo, store = done["repo"], done["store"]
    main_before = git("rev-parse", "origin/main", cwd=repo.root)
    code, out = publish(capsys)
    assert code == 0, out
    assert remote_branches(repo) == ["main", f"user/{TASK}"]
    assert git("ls-remote", "origin", f"refs/heads/user/{TASK}", cwd=repo.root).split()[0] == \
        git("rev-parse", "HEAD", cwd=done["workspace"])
    assert git("rev-parse", "origin/main", cwd=repo.root) == main_before
    prs = fake_gh.prs()
    assert len(prs) == 1
    assert (prs[0]["head"], prs[0]["base"]) == (f"user/{TASK}", "main")
    assert prs[0]["title"] == f"{TASK}: Add recurrence model and validation"
    assert store.read_task(TASK)["pull_request"] == {"number": 1, "url": prs[0]["url"]}
    card = orca_calls(fake_orca, "worktree set")[-1]
    assert card[card.index("--comment") + 1] == "2/2 AC verified · PR #1"


def test_pr_body_has_every_section(done, fake_gh, capsys):
    publish(capsys)
    body = fake_gh.prs()[0]["body"]
    for text in ("CHG-0012", "## Acceptance criteria", "AC-01", "verified", "AC-02", "evidence",
                 "## Reviews", "quality", "pass", "name is vague", "## Memory", "Added ADR 0003",
                 "## Pending"):
        assert text in body, text


def test_republish_pushes_again_to_the_same_pr(done, fake_gh, capsys):
    publish(capsys)
    done["repo"].commit("docs/notes.md", "more\n", "Docs after publish", cwd=done["workspace"])
    code, out = publish(capsys)
    assert code == 0, out
    assert len(fake_gh.prs()) == 1
    assert git("ls-remote", "origin", f"refs/heads/user/{TASK}", cwd=done["repo"].root).split()[0] == \
        git("rev-parse", "HEAD", cwd=done["workspace"])
    assert out["data"]["pull_request"]["number"] == 1


def test_push_never_forces(done, fake_gh, capsys):
    repo = done["repo"]
    publish(capsys)
    # someone rewrites the remote branch: a normal push is rejected and nothing is forced
    other = repo.root.parent / "other-clone"
    git("clone", "-q", str(repo.remote), str(other), cwd=repo.root)
    git("checkout", "-q", f"user/{TASK}", cwd=other)
    repo.commit("x.txt", "x\n", "remote change", cwd=other)
    git("push", "-q", "origin", f"user/{TASK}", cwd=other)
    repo.commit("src/bookings/y.py", "y = 1\n", "local change", cwd=done["workspace"])
    code, out = publish(capsys)
    assert code == 5
    assert out["error"]["code"] == "push_rejected"
    assert git("log", "-1", "--format=%s", f"user/{TASK}", cwd=repo.root) == "local change"


def test_without_gh_the_branch_is_pushed_and_the_pr_left_to_the_person(done, capsys, tmp_path,
                                                                        monkeypatch, fake_orca):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(shutil.which("git"))
    (bin_dir / "python3").symlink_to(sys.executable)
    (bin_dir / "orca").symlink_to(FAKES / "orca")
    monkeypatch.setenv("PATH", str(bin_dir))
    code, out = publish(capsys)
    assert code == 0, out
    assert remote_branches(done["repo"]) == ["main", f"user/{TASK}"]
    assert out["data"]["pull_request"] is None
    assert any("gh" in w for w in out["warnings"])


def test_gh_not_usable(done, fake_gh, capsys):
    fake_gh.fail("gh: not logged in")
    code, out = publish(capsys)
    assert code == 0
    assert out["data"]["pull_request"] is None
    assert any("not logged in" in w for w in out["warnings"])


def test_publish_requires_done(ready_to_finish, fake_gh, capsys):  # noqa: F811
    code, out = publish(capsys)
    assert (code, out["error"]["code"]) == (3, "invalid_transition")


def test_pr_body_is_masked(done, fake_gh, capsys):
    store = done["store"]
    secret = "ghp_" + "q" * 36
    store.update_task(TASK, lambda s: {**s, "memory": f"rotated {secret}"}, "x")
    publish(capsys)
    assert secret not in fake_gh.prs()[0]["body"]
