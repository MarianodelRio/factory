import json

import pytest
from test_claim_launch import TASK, orca_calls
from test_claim_launch import project as project  # noqa: F401 - reuse the approved project fixture

from swfactory.cli import main
from swfactory.state import TaskStore


@pytest.fixture
def claimed(project, capsys):  # noqa: F811
    assert main(["task", "claim", TASK]) == 0
    capsys.readouterr()
    return project


@pytest.fixture
def store(claimed):
    return TaskStore(claimed.root / ".factory" / "state")


def cli(capsys, *argv):
    code = main([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


def test_checkpoint_saves_progress_and_updates_the_card(claimed, store, fake_orca, capsys):
    code, out = cli(capsys, "task", "checkpoint", TASK, "--done", "Model and tests", "--next", "Run full suite")
    assert code == 0
    checkpoint = store.read_task(TASK)["last_checkpoint"]
    assert checkpoint["done"] == ["Model and tests"]
    assert checkpoint["next"] == "Run full suite"
    assert checkpoint["at"].endswith("Z")
    assert out["data"]["notes"] == []
    card = orca_calls(fake_orca, "worktree set")[-1]
    assert card[card.index("--comment") + 1] == "Run full suite"


def test_note_from_another_worktree_is_read_at_the_next_checkpoint(claimed, store, capsys, monkeypatch):
    other = claimed.add_worktree("someone-else")
    monkeypatch.chdir(other)
    code, _ = cli(capsys, "task", "note", TASK, "--text", "Use UTC for dates")
    assert code == 0
    monkeypatch.chdir(claimed.root)
    _, out = cli(capsys, "task", "checkpoint", TASK, "--done", "a", "--next", "b")
    assert [n["text"] for n in out["data"]["notes"]] == ["Use UTC for dates"]
    assert all(n["read"] for n in store.read_task(TASK)["notes"])
    _, out = cli(capsys, "task", "checkpoint", TASK, "--done", "c", "--next", "d")
    assert out["data"]["notes"] == []


def test_pause_note_blocks_the_task_when_read(claimed, store, fake_orca, capsys):
    cli(capsys, "task", "note", TASK, "--text", "Wait for the API review", "--pause")
    assert store.read_task(TASK)["state"] == "in_progress"  # only when the agent reads it
    _, out = cli(capsys, "task", "checkpoint", TASK, "--done", "a", "--next", "b")
    assert out["data"]["paused"] is True
    record = store.read_task(TASK)
    assert (record["state"], record["blocked_reason"]) == ("blocked", "paused")
    card = orca_calls(fake_orca, "worktree set")[-1]
    assert "--unread" in card


def test_unblock_returns_to_the_previous_state(claimed, store, capsys):
    cli(capsys, "task", "note", TASK, "--text", "stop", "--pause")
    cli(capsys, "task", "checkpoint", TASK, "--done", "a", "--next", "b")
    code, out = cli(capsys, "task", "unblock", TASK)
    assert code == 0, out
    assert store.read_task(TASK)["state"] == "in_progress"


def test_block_with_reason(claimed, store, fake_orca, capsys):
    code, _ = cli(capsys, "task", "block", TASK, "--reason", "The design misses the timezone rule")
    assert code == 0
    record = store.read_task(TASK)
    assert record["blocked_reason"] == "The design misses the timezone rule"
    card = orca_calls(fake_orca, "worktree set")[-1]
    assert card[card.index("--comment") + 1] == "The design misses the timezone rule"


def test_unblock_needs_a_valid_approval(claimed, store, capsys):
    cli(capsys, "task", "block", TASK, "--reason", "question")
    design = claimed.root / ".factory/changes/CHG-0012/design.md"
    design.write_text(design.read_text() + "\nEdited.\n")
    code, out = cli(capsys, "task", "unblock", TASK)
    assert code == 3
    assert out["error"]["code"] == "approval_not_valid"
    assert store.read_task(TASK)["state"] == "blocked"


def test_unblock_a_task_that_is_not_blocked(claimed, capsys):
    code, out = cli(capsys, "task", "unblock", TASK)
    assert code == 3
    assert out["error"]["code"] == "invalid_transition"


def test_note_on_an_unclaimed_task(claimed, capsys):
    code, out = cli(capsys, "task", "note", "CHG-0012-02", "--text", "hi")
    assert code == 3
    assert out["error"]["code"] == "task_not_started"


def test_checkpoint_only_while_working(claimed, capsys):
    cli(capsys, "task", "block", TASK, "--reason", "x")
    code, out = cli(capsys, "task", "checkpoint", TASK, "--done", "a", "--next", "b")
    assert code == 3
    assert out["error"]["code"] == "invalid_transition"
