import pytest

from swfactory import orca

WS = "repo::/w/CHG-0012-01"


def set_call(fake_orca):
    calls = [c for c in fake_orca.calls() if c[:2] == ["worktree", "set"]]
    return calls[-1]


def value(call, flag):
    return call[call.index(flag) + 1] if flag in call else None


# One row per line of the card table (orca.CARDS): state, detail, status, comment, unread.
ROWS = [
    ("in_progress", "Write the migration", "in-progress", "Write the migration", False),
    ("in_review", "Pending reviews: conformance", "in-review", "Pending reviews: conformance", False),
    ("to_merge", orca.done_comment(3, 3, 123), "in-review", "3/3 AC verified · PR #123 · to merge", False),
    ("done", orca.done_comment(3, 3, 123, merged=True), "completed", "3/3 AC verified · PR #123 · merged", False),
    ("blocked", "paused", "in-progress", "paused", True),
    ("interrupted", None, "in-progress", "Interrupted: use /factory-status", True),
]


@pytest.mark.parametrize(("state", "detail", "status", "comment", "unread"), ROWS)
def test_card_follows_the_table(repo, fake_orca, state, detail, status, comment, unread):
    warnings = orca.update_card(WS, "CHG-0012-01", "Add recurrence model", state, detail)
    assert warnings == []
    call = set_call(fake_orca)
    assert value(call, "--worktree") == f"id:{WS}"
    assert value(call, "--display-name") == "CHG-0012-01 Add recurrence model"
    assert value(call, "--workspace-status") == status
    assert value(call, "--comment") == comment
    assert ("--unread" in call) is unread
    assert "--read" not in call


def test_done_comment_without_pr():
    assert orca.done_comment(2, 3, None) == "2/3 AC verified · to merge"


def test_orca_failure_is_only_a_warning(repo, fake_orca):
    fake_orca.fail("worktree set", code="runtime_unavailable", message="Orca is closed")
    warnings = orca.update_card(WS, "CHG-0012-01", "T", "in_progress", "next")
    assert len(warnings) == 1
    assert "Orca is closed" in warnings[0]


def test_orca_missing_is_only_a_warning(repo, monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert len(orca.update_card(WS, "CHG-0012-01", "T", "in_progress", "next")) == 1


def test_unsupported_values_fall_back_to_the_comment(repo, fake_orca):
    error = {"id": "x", "ok": False, "error": {"code": "invalid_argument", "message": "unknown flag"}}
    fake_orca.respond_sequence("worktree set", [{"exit": 1, "stdout": error}])
    warnings = orca.update_card(WS, "CHG-0012-01", "T", "blocked", "needs a decision")
    calls = [c for c in fake_orca.calls() if c[:2] == ["worktree", "set"]]
    assert len(calls) == 2
    assert value(calls[1], "--comment") == "needs a decision"
    assert "--workspace-status" not in calls[1]
    assert warnings and "comment" in warnings[0]


def test_orca_warnings_are_passed_on(repo, fake_orca):
    fake_orca.respond_fixture("worktree set", "worktree-set-unknown-status")
    warnings = orca.update_card(WS, "CHG-0012-01", "T", "in_progress", "next")
    assert any("Unknown workspace status" in w for w in warnings)


def test_remote_orca_is_never_called(repo, fake_orca, monkeypatch):
    monkeypatch.setenv("ORCA_ENVIRONMENT", "build-server")
    assert orca.update_card(WS, "CHG-0012-01", "T", "in_progress", "next")
    assert orca.session_liveness("term_1") == "unknown"
    assert fake_orca.calls() == []
