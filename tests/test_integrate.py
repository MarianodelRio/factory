"""How a finished task reaches the base branch: a PR the person merges, or a merge right away;
the branch is on the remote from the claim, and the workspace can be removed once merged."""

import json

import pytest
import yaml
from conftest import git
from test_approve import FOLDER
from test_claim_launch import TASK, orca_calls
from test_finish import ready_to_finish as ready_to_finish  # noqa: F401
from test_publish import done as finished  # noqa: F401
from test_publish import remote_branches

from swfactory.cli import main


def cli(capsys, *argv):
    code = main([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


def set_git(repo, **values):
    path = repo.root / ".factory/config.toml"
    path.write_text(path.read_text() + "[git]\n" + "".join(f'{k} = "{v}"\n' for k, v in values.items()))


def set_task_field(repo, **fields):
    path = repo.root / FOLDER / "tasks.yaml"
    data = yaml.safe_load(path.read_text())
    data["tasks"][0].update(fields)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_the_branch_is_on_the_remote_from_the_claim(ready_to_finish, capsys):  # noqa: F811
    assert f"user/{TASK}" in remote_branches(ready_to_finish["repo"])


def test_finish_backs_up_the_branch(finished):  # noqa: F811
    repo = finished["repo"]
    pushed = git("ls-remote", "origin", f"refs/heads/user/{TASK}", cwd=repo.root).split()[0]
    assert pushed == git("rev-parse", "HEAD", cwd=finished["workspace"])


def test_pr_mode_leaves_the_merge_to_the_person(finished, fake_gh, fake_orca, capsys):  # noqa: F811
    code, out = cli(capsys, "task", "publish", TASK)
    assert code == 0, out
    assert (out["data"]["integrate"], out["data"]["merged"], out["data"]["state"]) == ("pr", False, "to_merge")
    assert fake_gh.prs()[0].get("state", "OPEN") == "OPEN"
    linked = [c for c in orca_calls(fake_orca, "worktree set") if "--pr" in c]
    assert linked and linked[-1][linked[-1].index("--pr") + 1] == "1"


@pytest.mark.parametrize("where", ["config", "task"])
def test_merge_mode_merges_and_tidies_the_remote(finished, fake_gh, capsys, where):  # noqa: F811
    repo, store = finished["repo"], finished["store"]
    if where == "config":
        set_git(repo, integrate="merge")
    else:
        set_task_field(repo, integrate="merge")
    code, out = cli(capsys, "task", "publish", TASK)
    assert code == 0, out
    assert (out["data"]["integrate"], out["data"]["merged"], out["data"]["state"]) == ("merge", True, "done")
    assert fake_gh.prs()[0]["method"] == "--merge"
    record = store.read_task(TASK)
    assert (record["state"], record["merged_at"]) == ("done", "2026-10-20T12:00:00Z")
    assert remote_branches(repo) == ["main"]  # the merged branch is deleted on the remote


def test_a_merge_github_refuses_leaves_the_pr_open(finished, fake_gh, capsys):  # noqa: F811
    set_git(finished["repo"], integrate="merge")
    cli(capsys, "task", "publish", TASK)  # opens PR #1 and merges it
    finished["store"].update_task(TASK, lambda s: {**s, "state": "to_merge"}, "x")
    fake_gh.set_pr(1, state="OPEN", unmergeable=True)
    code, out = cli(capsys, "task", "publish", TASK)
    assert code == 0, out
    assert out["data"]["state"] == "to_merge"
    assert any("could not be merged" in w for w in out["warnings"])


def test_merge_mode_without_gh_leaves_it_to_the_person(finished, fake_gh, capsys):  # noqa: F811
    set_git(finished["repo"], integrate="merge")
    fake_gh.fail()
    code, out = cli(capsys, "task", "publish", TASK)
    assert code == 0, out
    assert out["data"]["state"] == "to_merge"
    assert any("merge user/" in w for w in out["warnings"])


def merge(finished, capsys):  # noqa: F811
    repo, store = finished["repo"], finished["store"]
    git("merge", "-q", "--no-ff", "-m", "merge", store.read_task(TASK)["workspace"]["branch"], cwd=repo.root)
    code, out = cli(capsys, "status")
    assert code == 0, out
    return next(t for t in out["data"]["tasks"] if t["id"] == TASK), out["data"]


def test_cleanup_is_offered_then_done(finished, capsys):  # noqa: F811
    task, data = merge(finished, capsys)
    assert task["next_step"].startswith("merged: remove its workspace?")
    assert any("remove its workspace" in a for a in data["attention"])
    code, out = cli(capsys, "task", "cleanup", TASK)
    assert code == 0, out
    assert out["data"]["workspace_removed"] is True
    assert not finished["workspace"].exists()
    assert git("branch", "--list", f"user/{TASK}", cwd=finished["repo"].root) == ""
    assert merge_status(capsys)["next_step"] == "nothing: merged into main"


def merge_status(capsys):
    return next(t for t in cli(capsys, "status")[1]["data"]["tasks"] if t["id"] == TASK)


def test_cleanup_can_be_declined(finished, capsys):  # noqa: F811
    merge(finished, capsys)
    assert cli(capsys, "task", "cleanup", TASK, "--keep")[0] == 0
    assert finished["workspace"].exists()
    assert merge_status(capsys)["next_step"] == "nothing: merged into main"


def test_cleanup_never_loses_uncommitted_work(finished, capsys):  # noqa: F811
    merge(finished, capsys)
    (finished["workspace"] / "notes.txt").write_text("not committed\n")
    code, out = cli(capsys, "task", "cleanup", TASK)
    assert (code, out["error"]["code"]) == (3, "workspace_not_clean")
    assert finished["workspace"].exists()


def test_cleanup_always_removes_it_on_merge(finished, capsys):  # noqa: F811
    set_git(finished["repo"], cleanup="always")
    merge(finished, capsys)
    assert not finished["workspace"].exists()


def test_only_a_merged_task_is_cleaned_up(finished, capsys):  # noqa: F811
    code, out = cli(capsys, "task", "cleanup", TASK)
    assert (code, out["error"]["code"]) == (3, "invalid_transition")
