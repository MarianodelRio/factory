import pytest
from conftest import load_fixture, orca_error

from factory import orca
from factory.output import EXIT_UNAVAILABLE, EXIT_USAGE, FactoryError


def test_create_workspace(repo, fake_orca):
    workspace = orca.create_workspace("CHG-0012-01", "main", repo.root)
    assert workspace["branch"] == "user/CHG-0012-01"
    assert workspace["path"].endswith("/CHG-0012-01")
    assert workspace["id"].endswith("::" + workspace["path"])
    call = fake_orca.calls()[-1]
    assert call[:2] == ["worktree", "create"]
    assert call[call.index("--repo") + 1] == f"path:{repo.root}"
    assert call[call.index("--name") + 1] == "CHG-0012-01"
    assert call[call.index("--base-branch") + 1] == "main"
    assert "--agent" not in call
    assert "--no-parent" in call


def test_create_workspace_failure(repo, fake_orca):
    fake_orca.fail("worktree create", code="worktree_create_failed")
    with pytest.raises(FactoryError) as exc:
        orca.create_workspace("CHG-0012-01", "main", repo.root)
    assert exc.value.exit_code == EXIT_UNAVAILABLE


def test_workspace_exists(repo, fake_orca):
    workspace = orca.create_workspace("CHG-0012-01", "main", repo.root)
    assert orca.workspace_exists(workspace["id"]) is True
    fake_orca.respond_fixture("worktree show", "worktree-show-not-found", exit=1)
    assert orca.workspace_exists(workspace["id"]) is False


def test_workspace_exists_other_errors_propagate(repo, fake_orca):
    fake_orca.fail("worktree show", code="runtime_unavailable")
    with pytest.raises(FactoryError):
        orca.workspace_exists("repo::/x")


def test_launch_agent(repo, fake_orca):
    launched = orca.launch_agent("repo::/w", "claude", "/factory-implement CHG-0012-01", None, None)
    body = load_fixture("agent-launch")["result"]
    assert launched == {"operation_id": body["operationId"], "terminal": body["outcome"]["handle"],
                        "kind": "terminal"}
    assert fake_orca.calls()[-1] == ["agent", "launch", "--agent", "claude", "--worktree", "id:repo::/w",
                                     "--prompt", "/factory-implement CHG-0012-01", "--json"]


def test_launch_agent_with_model_and_effort(repo, fake_orca):
    orca.launch_agent("repo::/w", "codex", "brief", "gpt-x", "high")
    call = fake_orca.calls()[-1]
    assert call[call.index("--model") + 1] == "gpt-x"
    assert call[call.index("--effort") + 1] == "high"


def test_effort_needs_model(repo, fake_orca):
    with pytest.raises(FactoryError) as exc:
        orca.launch_agent("repo::/w", "claude", "brief", None, "high")
    assert exc.value.exit_code == EXIT_USAGE
    assert fake_orca.calls() == []


def lost(operation_id="op-7"):
    error = orca_error("launch_reply_lost", f"reply lost; re-issue with --retry-launch {operation_id}")
    return {"exit": 1, "stdout": error}


def test_lost_reply_is_retried_with_the_same_operation(repo, fake_orca):
    fake_orca.respond_sequence("agent launch", [lost("op-7")])
    launched = orca.launch_agent("repo::/w", "claude", "brief", None, None)
    assert launched["operation_id"] == "op-7"
    launches = [c for c in fake_orca.calls() if c[:2] == ["agent", "launch"]]
    assert len(launches) == 2
    assert "--retry-launch" not in launches[0]
    assert launches[1][launches[1].index("--retry-launch") + 1] == "op-7"
    assert launches[1][:-3] == launches[0][:-1]  # same command, only --retry-launch added


def test_structured_launch_has_no_terminal(repo, fake_orca):
    body = load_fixture("agent-launch")
    body["result"]["outcome"] = {"kind": "structured", "handle": None}
    fake_orca.respond("agent launch", body)
    launched = orca.launch_agent("repo::/w", "claude", "brief", None, None)
    assert launched["terminal"] is None
    assert launched["kind"] == "structured"


def test_retry_answer_without_operation_id_keeps_the_resent_one(repo, fake_orca):
    body = load_fixture("agent-launch")
    del body["result"]["operationId"]
    fake_orca.respond_sequence("agent launch", [lost("op-7"), {"exit": 0, "stdout": body}])
    assert orca.launch_agent("repo::/w", "claude", "brief", None, None)["operation_id"] == "op-7"


def test_operation_id_in_error_data(repo, fake_orca):
    error = orca_error("launch_reply_lost", "lost")
    error["error"]["data"] = {"operationId": "op-9"}
    fake_orca.respond_sequence("agent launch", [{"exit": 1, "stdout": error}])
    assert orca.launch_agent("repo::/w", "claude", "brief", None, None)["operation_id"] == "op-9"


def test_retry_failure_is_not_relaunched_again(repo, fake_orca):
    fake_orca.respond_sequence("agent launch", [lost("op-7"), lost("op-7")])
    with pytest.raises(FactoryError):
        orca.launch_agent("repo::/w", "claude", "brief", None, None)
    assert len([c for c in fake_orca.calls() if c[:2] == ["agent", "launch"]]) == 2


def test_failure_without_operation_id_is_never_retried(repo, fake_orca):
    fake_orca.fail("agent launch", code="agent_unavailable", message="codex is not installed")
    with pytest.raises(FactoryError) as exc:
        orca.launch_agent("repo::/w", "codex", "brief", None, None)
    assert "codex is not installed" in exc.value.message
    assert len(fake_orca.calls()) == 1


@pytest.mark.parametrize(("fixture", "exit", "expected"), [
    ("terminal-show-alive", 0, "alive"),
    ("terminal-show-agent-exited", 0, "alive"),  # Orca cannot tell
    ("terminal-show-closed", 0, "finished"),
    ("terminal-show-stale", 1, "finished"),
])
def test_session_liveness(repo, fake_orca, fixture, exit, expected):
    fake_orca.respond_fixture("terminal show", fixture, exit=exit)
    assert orca.session_liveness("term_1") == expected


def test_session_liveness_unknown_when_orca_fails(repo, fake_orca):
    fake_orca.fail("terminal show", code="runtime_unavailable")
    assert orca.session_liveness("term_1") == "unknown"


def test_session_liveness_without_terminal(repo, fake_orca):
    assert orca.session_liveness(None) == "unknown"
    assert fake_orca.calls() == []


def test_session_liveness_orca_missing(repo, monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert orca.session_liveness("term_1") == "unknown"
