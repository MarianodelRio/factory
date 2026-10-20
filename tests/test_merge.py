"""A finished task waits in `to_merge` until its work reaches the base branch, then it is `done`."""

import json

import pytest
from conftest import git
from test_claim_launch import TASK
from test_finish import ready_to_finish as ready_to_finish  # noqa: F401
from test_publish import done as finished  # noqa: F401

from swfactory.cli import main

DEPENDENT = "CHG-0012-02"


def cli(capsys, *argv):
    code = main([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


def row(capsys, task):
    code, out = cli(capsys, "status")
    assert code == 0, out
    return next(t for t in out["data"]["tasks"] if t["id"] == task), out["data"]


def test_finished_task_waits_to_be_merged(finished, capsys):  # noqa: F811
    task, _ = row(capsys, TASK)
    assert task["state"] == "to_merge"
    assert task["next_step"] == f"swfactory task publish {TASK}"
    dependent, _ = row(capsys, DEPENDENT)
    assert (dependent["state"], dependent["reason"]) == ("pending", f"waiting for {TASK} to be merged into main")


def test_a_merge_into_the_base_makes_it_done(finished, capsys):  # noqa: F811
    repo, store = finished["repo"], finished["store"]
    branch = store.read_task(TASK)["workspace"]["branch"]
    git("merge", "-q", "--no-ff", "-m", "merge", branch, cwd=repo.root)
    task, _ = row(capsys, TASK)
    assert task["state"] == "done"
    assert task["next_step"].startswith("merged: remove its workspace?")
    assert store.read_task(TASK)["merged_at"].endswith("Z")
    assert row(capsys, DEPENDENT)[0]["state"] == "ready"


def test_a_squashed_pull_request_counts_as_merged(finished, fake_gh, capsys):  # noqa: F811
    assert cli(capsys, "task", "publish", TASK)[0] == 0
    fake_gh.set_pr(1, state="MERGED", mergedAt="2026-10-20T10:00:00Z")
    assert row(capsys, TASK)[0]["state"] == "done"
    assert finished["store"].read_task(TASK)["merged_at"] == "2026-10-20T10:00:00Z"


def test_a_closed_pull_request_needs_the_person(finished, fake_gh, capsys):  # noqa: F811
    assert cli(capsys, "task", "publish", TASK)[0] == 0
    fake_gh.set_pr(1, state="CLOSED")
    task, data = row(capsys, TASK)
    assert task["state"] == "to_merge"
    assert "closed without merging" in task["next_step"]
    assert f"{TASK}: its PR was closed without merging" in data["attention"]


def test_the_person_can_say_it_is_merged(finished, capsys):  # noqa: F811
    code, out = cli(capsys, "task", "merged", TASK)
    assert code == 0, out
    assert finished["store"].read_task(TASK)["state"] == "done"
    code, out = cli(capsys, "task", "merged", TASK)
    assert (code, out["error"]["code"]) == (3, "not_merged")


def test_only_a_finished_task_is_published(finished, capsys):  # noqa: F811
    assert cli(capsys, "task", "merged", TASK)[0] == 0
    code, out = cli(capsys, "task", "publish", TASK)
    assert (code, out["error"]["code"]) == (3, "invalid_transition")


@pytest.mark.parametrize("merged", [True, False])
def test_tasks_done_before_to_merge_existed(finished, capsys, merged):  # noqa: F811
    repo, store = finished["repo"], finished["store"]
    store.update_task(TASK, lambda s: {**{k: v for k, v in s.items() if k != "merged_at"}, "state": "done"}, "x")
    if merged:
        git("merge", "-q", "--no-ff", "-m", "merge", store.read_task(TASK)["workspace"]["branch"], cwd=repo.root)
    assert row(capsys, TASK)[0]["state"] == ("done" if merged else "to_merge")
