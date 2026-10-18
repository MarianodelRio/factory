import json

import pytest
from conftest import git
from test_approve import CHANGE, DESIGN, FOLDER

from swfactory.cli import main
from swfactory.state import TaskStore


@pytest.fixture
def project(repo, fake_orca, monkeypatch, capsys):
    monkeypatch.chdir(repo.root)
    folder = repo.root / FOLDER
    folder.mkdir(parents=True)
    (folder / "design.md").write_text(DESIGN)
    assert main(["design", "approve", CHANGE, "--message", "apruebo CHG-0012"]) == 0
    capsys.readouterr()
    return repo


@pytest.fixture
def store(project):
    return TaskStore(project.root / ".factory" / "state")


def cli(capsys, *argv):
    code = main([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


def tasks_by_id(capsys):
    code, out = cli(capsys, "task", "list")
    assert code == 0, out
    return {t["id"]: t for t in out["data"]["tasks"]}


def finish_on_branch(project, store, task, merge):
    """Make `task` done with a commit on its own branch, merged into main or not."""
    path = project.add_worktree(f"user/{task}")
    commit = project.commit(f"{task}.txt", task, f"work on {task}", cwd=path)
    store.update_task(task, lambda s: {**s, "state": "done", "commits": [commit],
                                       "workspace": {"orca_id": f"r::{path}", "branch": f"user/{task}"}},
                      "finish")
    if merge:
        git("merge", "-q", "--no-ff", "-m", f"merge {task}", f"user/{task}", cwd=project.root)


def test_task_without_dependencies_is_ready(project, capsys):
    tasks = tasks_by_id(capsys)
    assert tasks["CHG-0012-01"]["state"] == "ready"
    assert tasks["CHG-0012-01"]["reason"] is None
    assert tasks["CHG-0012-01"]["change"] == CHANGE
    assert tasks["CHG-0012-01"]["title"] == "Add recurrence model and validation"


def test_dependency_not_done_is_pending(project, store, capsys):
    store.update_task("CHG-0012-01", lambda s: {**s, "state": "in_progress"}, "claim")
    task = tasks_by_id(capsys)["CHG-0012-02"]
    assert task["state"] == "pending"
    assert task["reason"] == "waiting for CHG-0012-01 to be done"


def test_dependency_done_but_not_merged_is_pending(project, store, capsys):
    finish_on_branch(project, store, "CHG-0012-01", merge=False)
    task = tasks_by_id(capsys)["CHG-0012-02"]
    assert task["state"] == "pending"
    assert task["reason"] == "waiting for CHG-0012-01 to be merged into main"


def test_dependency_done_and_merged_is_ready(project, store, capsys):
    finish_on_branch(project, store, "CHG-0012-01", merge=True)
    assert tasks_by_id(capsys)["CHG-0012-02"]["state"] == "ready"


def test_dependency_merged_into_origin_counts(project, store, capsys):
    finish_on_branch(project, store, "CHG-0012-01", merge=False)
    git("push", "-q", "origin", "user/CHG-0012-01:main", cwd=project.root)
    git("fetch", "-q", "origin", cwd=project.root)
    assert tasks_by_id(capsys)["CHG-0012-02"]["state"] == "ready"


def test_stored_state_wins(project, store, capsys):
    store.update_task("CHG-0012-01", lambda s: {**s, "state": "in_review"}, "submit")
    assert tasks_by_id(capsys)["CHG-0012-01"]["state"] == "in_review"


def test_unapproved_change_tasks_are_pending(project, capsys):
    path = project.root / FOLDER / "design.md"
    path.write_text(path.read_text() + "\nEdited.\n")
    task = tasks_by_id(capsys)["CHG-0012-01"]
    assert task["state"] == "pending"
    assert task["reason"] == f"{CHANGE} is awaiting approval"


def test_rejected_changes_are_not_listed(project, capsys):
    (project.root / FOLDER / "rejection.json").write_text("{}")
    assert tasks_by_id(capsys) == {}


def test_list_without_orca_is_still_viewable(project, store, capsys, fake_orca):
    fake_orca.fail("repo show", code="runtime_unavailable", message="Orca is closed")
    finish_on_branch(project, store, "CHG-0012-01", merge=True)
    tasks = tasks_by_id(capsys)
    assert tasks["CHG-0012-01"]["state"] == "done"
    assert tasks["CHG-0012-02"]["state"] == "pending"
    assert "Orca is closed" in tasks["CHG-0012-02"]["reason"]


def test_show(project, store, capsys):
    store.update_task("CHG-0012-01", lambda s: {**s, "state": "in_progress"}, "claim")
    code, out = cli(capsys, "task", "show", "CHG-0012-02")
    assert code == 0
    data = out["data"]
    assert data["id"] == "CHG-0012-02"
    assert data["state"] == "pending"
    assert data["reason"] == "waiting for CHG-0012-01 to be done"
    assert data["acceptance"] == {"AC-03": "pytest tests/integration/test_calendar.py"}
    assert data["review"] == ["quality", "conformance"]
    assert data["record"] is None
    code, out = cli(capsys, "task", "show", "CHG-0012-01")
    assert out["data"]["record"]["state"] == "in_progress"


def test_show_unknown_task(project, capsys):
    code, out = cli(capsys, "task", "show", "CHG-0012-09")
    assert code == 3
    assert out["error"]["code"] == "task_not_found"


def test_dependency_merged_and_branch_deleted_is_ready(project, store, capsys):
    finish_on_branch(project, store, "CHG-0012-01", merge=True)
    path = project.root.parent / "worktrees" / "user" / "CHG-0012-01"
    git("worktree", "remove", "--force", str(path), cwd=project.root)
    git("branch", "-D", "user/CHG-0012-01", cwd=project.root)
    assert tasks_by_id(capsys)["CHG-0012-02"]["state"] == "ready"
