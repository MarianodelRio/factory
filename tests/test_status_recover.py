import json
from pathlib import Path

import pytest
from conftest import load_fixture
from test_claim_launch import TASK, orca_calls
from test_claim_launch import project as project  # noqa: F401

from factory.cli import main
from factory.state import TaskStore

TERMINAL = load_fixture("agent-launch")["result"]["outcome"]["handle"]


@pytest.fixture
def working(project, capsys):  # noqa: F811
    assert main(["task", "claim", TASK]) == 0
    assert main(["task", "launch", TASK, "--agent", "claude", "--reviewer", "claude"]) == 0
    capsys.readouterr()
    return project


@pytest.fixture
def store(working):
    return TaskStore(working.root / ".factory" / "state")


def cli(capsys, *argv):
    code = main([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


def status(capsys):
    code, out = cli(capsys, "status")
    assert code == 0, out
    return out["data"]


def task_in(data, task=TASK):
    return next(t for t in data["tasks"] if t["id"] == task)


def test_status_summary_and_task_details(working, store, capsys):
    cli(capsys, "task", "checkpoint", TASK, "--done", "model", "--next", "tests")
    data = status(capsys)
    assert data["summary"]["tasks"] == {"in_progress": 1, "pending": 1}
    assert data["summary"]["awaiting_approval"] == []
    task = task_in(data)
    assert task["agent"] == "claude"
    assert task["liveness"] == "alive"
    assert task["last_checkpoint"]["next"] == "tests"
    assert task["acceptance"] == {"verified": 0, "total": 2}
    assert task["next_step"] == "tests"
    assert task_in(data, "CHG-0012-02")["reason"] == "waiting for CHG-0012-01 to be done"


def test_finished_session_without_submit_is_interrupted(working, store, fake_orca, capsys):
    fake_orca.respond_fixture("terminal show", "terminal-show-closed", target=TERMINAL)
    data = status(capsys)
    assert task_in(data)["state"] == "interrupted"
    assert store.read_task(TASK)["state"] == "interrupted"
    assert any(TASK in a and "interrupted" in a for a in data["attention"])
    card = orca_calls(fake_orca, "worktree set")[-1]
    assert card[card.index("--comment") + 1] == "Interrupted: use /factory-status"


def test_unknown_liveness_is_never_dead(working, store, fake_orca, capsys):
    fake_orca.fail("terminal show", code="runtime_unavailable")
    data = status(capsys)
    assert task_in(data)["liveness"] == "unknown"
    assert store.read_task(TASK)["state"] == "in_progress"


def test_ten_minutes_without_checkpoint_is_only_a_warning(working, store, capsys):
    store.update_task(TASK, lambda s: {**s, "last_checkpoint": {"at": "2020-01-01T00:00:00Z", "done": ["x"],
                                                                "next": "y"}}, "old")
    data = status(capsys)
    assert task_in(data)["state"] == "in_progress"
    assert any("no checkpoint" in a and TASK in a for a in data["attention"])


def test_recent_checkpoint_gives_no_warning(working, capsys):
    cli(capsys, "task", "checkpoint", TASK, "--done", "a", "--next", "b")
    assert not any("no checkpoint" in a for a in status(capsys)["attention"])


def test_deleted_workspace_is_a_broken_link(working, store, fake_orca, capsys):
    fake_orca.respond_fixture("worktree show", "worktree-show-not-found", exit=1)
    data = status(capsys)
    assert task_in(data)["broken_link"] is True
    assert any("broken link" in a for a in data["attention"])


def test_status_without_orca_is_still_viewable(working, fake_orca, capsys, monkeypatch):
    monkeypatch.setenv("ORCA_ENVIRONMENT", "remote")
    data = status(capsys)
    assert task_in(data)["liveness"] == "unknown"
    assert task_in(data)["state"] == "in_progress"


def test_awaiting_approval_and_blocked_in_attention(working, capsys):
    cli(capsys, "task", "block", TASK, "--reason", "needs a decision")
    folder = working.root / ".factory/changes/CHG-0013"
    folder.mkdir()
    (folder / "design.md").write_text("# CHG-0013 — Next\n")
    data = status(capsys)
    assert data["summary"]["awaiting_approval"] == ["CHG-0013"]
    assert any("CHG-0013" in a for a in data["attention"])
    assert any(TASK in a and "needs a decision" in a for a in data["attention"])


def test_recover_inspects_without_changing_anything(working, store, fake_orca, capsys):
    workspace = Path(store.read_task(TASK)["workspace"]["orca_id"].split("::", 1)[1])
    (workspace / "wip.py").write_text("half done\n")
    fake_orca.respond_fixture("terminal show", "terminal-show-closed", target=TERMINAL)
    code, out = cli(capsys, "task", "recover", TASK)
    assert code == 0, out
    data = out["data"]
    assert data["liveness"] == "finished"
    assert "?? wip.py" in data["git_status"]
    assert data["missing_acceptance"] == ["AC-01", "AC-02"]
    assert "new agent" in data["proposal"]
    record = store.read_task(TASK)
    assert record["state"] == "interrupted"  # detected, but no new attempt without --confirm
    assert len(record["attempts"]) == 1


def test_recover_confirm_opens_a_new_attempt_and_keeps_files(working, store, fake_orca, capsys):
    workspace = Path(store.read_task(TASK)["workspace"]["orca_id"].split("::", 1)[1])
    (workspace / "wip.py").write_text("half done\n")
    fake_orca.respond_fixture("terminal show", "terminal-show-closed", target=TERMINAL)
    code, out = cli(capsys, "task", "recover", TASK, "--confirm")
    assert code == 0, out
    record = store.read_task(TASK)
    assert record["state"] == "in_progress"
    assert [a["id"] for a in record["attempts"]] == [1, 2]
    assert record["attempts"][0]["result"] == "interrupted"
    assert record["attempts"][0]["ended_at"]
    assert record["attempts"][1]["agent"] is None
    assert store.read_claim(TASK)["attempt"] == 2
    assert (workspace / "wip.py").read_text() == "half done\n"
    assert len(orca_calls(fake_orca, "agent launch")) == 1  # nothing relaunched
    assert "factory task launch" in out["data"]["next_step"]


def test_recover_with_a_live_session_only_proposes_continuing(working, capsys):
    _, out = cli(capsys, "task", "recover", TASK)
    assert "continue" in out["data"]["proposal"]
    code, out = cli(capsys, "task", "recover", TASK, "--confirm")
    assert (code, out["error"]["code"]) == (3, "session_alive")


def test_recover_with_unknown_liveness_needs_the_person(working, store, fake_orca, capsys):
    fake_orca.fail("terminal show", code="runtime_unavailable")
    _, out = cli(capsys, "task", "recover", TASK)
    assert out["data"]["liveness"] == "unknown"
    assert "cannot say" in out["data"]["proposal"]
    code, _ = cli(capsys, "task", "recover", TASK, "--confirm")
    assert code == 0
    assert [a["result"] for a in store.read_task(TASK)["attempts"]] == ["interrupted", None]


def test_recover_a_task_that_is_not_interrupted(working, capsys):
    cli(capsys, "task", "submit", TASK)
    code, out = cli(capsys, "task", "recover", TASK, "--confirm")
    assert (code, out["error"]["code"]) == (3, "invalid_transition")


def test_recover_with_a_broken_link(working, fake_orca, capsys):
    fake_orca.respond_fixture("terminal show", "terminal-show-closed", target=TERMINAL)
    fake_orca.respond_fixture("worktree show", "worktree-show-not-found", exit=1)
    _, out = cli(capsys, "task", "recover", TASK)
    assert out["data"]["broken_link"] is True
    code, out = cli(capsys, "task", "recover", TASK, "--confirm")
    assert (code, out["error"]["code"]) == (3, "workspace_missing")
