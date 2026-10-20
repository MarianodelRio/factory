import json
from pathlib import Path

import pytest
from conftest import git, load_fixture, worktree_paths
from test_approve import CHANGE, DESIGN, FOLDER

from swfactory.cli import main
from swfactory.state import TaskStore

TASK = "CHG-0012-01"


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


def orca_calls(fake_orca, command):
    return [c for c in fake_orca.calls() if " ".join(c[: len(command.split())]) == command]


def test_claim_creates_workspace_state_claim_and_card(project, store, fake_orca, capsys):
    code, out = cli(capsys, "task", "claim", TASK)
    assert code == 0, out
    record = store.read_task(TASK)
    assert record["state"] == "in_progress"
    assert record["workspace"]["branch"] == f"user/{TASK}"
    assert record["workspace"]["orca_id"] == out["data"]["workspace"]
    assert [a["id"] for a in record["attempts"]] == [1]
    assert record["attempts"][0]["agent"] is None
    assert store.read_claim(TASK)["attempt"] == 1
    create = orca_calls(fake_orca, "worktree create")[0]
    assert create[create.index("--base-branch") + 1] == "origin/main"
    assert out["data"]["base"] == "origin/main"
    card = orca_calls(fake_orca, "worktree set")[-1]
    assert card[card.index("--workspace-status") + 1] == "in-progress"
    assert Path(out["data"]["path"]).resolve() in worktree_paths(project.root)


def test_second_claim_is_a_conflict(project, capsys):
    cli(capsys, "task", "claim", TASK)
    code, out = cli(capsys, "task", "claim", TASK)
    assert code == 4
    assert out["error"]["code"] == "task_claimed"


def test_pending_task_cannot_be_claimed(project, capsys):
    code, out = cli(capsys, "task", "claim", "CHG-0012-02")
    assert code == 3
    assert out["error"]["code"] == "task_not_ready"
    assert "CHG-0012-01" in out["error"]["message"]


def test_approval_must_be_on_the_base_branch(project, capsys):
    git("reset", "-q", "--soft", "HEAD~1", cwd=project.root)  # approval no longer committed
    git("push", "-q", "-f", "origin", "HEAD:main", cwd=project.root)
    code, out = cli(capsys, "task", "claim", TASK)
    assert code == 3
    assert out["error"]["code"] == "approval_not_on_base"


def test_workspace_failure_releases_the_claim(project, store, fake_orca, capsys):
    fake_orca.fail("worktree create", code="worktree_create_failed", message="disk full")
    code, out = cli(capsys, "task", "claim", TASK)
    assert code == 5
    assert "disk full" in out["error"]["message"]
    assert store.read_claim(TASK) is None
    assert store.read_task(TASK) is None
    _, listed = cli(capsys, "task", "show", TASK)
    assert listed["data"]["state"] == "ready"


@pytest.mark.parametrize("break_orca", ["closed", "remote"])
def test_orca_unavailable_claims_nothing(project, store, fake_orca, capsys, monkeypatch, break_orca):
    if break_orca == "closed":
        fake_orca.fail("status", code="runtime_unavailable", message="Orca is not running")
    else:
        monkeypatch.setenv("ORCA_PAIRING_CODE", "orca://pair?x")
    code, _ = cli(capsys, "task", "claim", TASK)
    assert code == 5
    assert store.read_claim(TASK) is None
    assert orca_calls(fake_orca, "worktree create") == []
    monkeypatch.delenv("ORCA_PAIRING_CODE", raising=False)
    _, listed = cli(capsys, "task", "list")
    assert listed["ok"] is True  # the state is still viewable


def test_card_failure_does_not_fail_the_claim(project, store, fake_orca, capsys):
    fake_orca.fail("worktree set", message="card service down")
    code, out = cli(capsys, "task", "claim", TASK)
    assert code == 0
    assert any("card service down" in w for w in out["warnings"])
    assert store.read_task(TASK)["state"] == "in_progress"


def test_launch_records_the_attempt(project, store, fake_orca, capsys):
    cli(capsys, "task", "claim", TASK)
    code, out = cli(capsys, "task", "launch", TASK, "--agent", "codex", "--reviewer", "claude",
                    "--model", "gpt-x", "--effort", "high")
    assert code == 0, out
    attempt = store.read_task(TASK)["attempts"][0]
    body = load_fixture("agent-launch")["result"]
    assert attempt["agent"] == "codex"
    assert attempt["reviewer"] == "claude"
    assert attempt["model"] == "gpt-x"
    assert attempt["operation_id"] == body["operationId"]
    assert attempt["terminal"] == body["outcome"]["handle"]
    launch = orca_calls(fake_orca, "agent launch")[0]
    assert launch[launch.index("--prompt") + 1] == f"/factory-implement {TASK} --reviewer claude"
    assert launch[launch.index("--worktree") + 1] == f"id:{store.read_task(TASK)['workspace']['orca_id']}"
    assert out["data"]["message"].startswith(f"{TASK} launched")


def test_launch_without_reviewer_and_model(project, store, fake_orca, capsys):
    cli(capsys, "task", "claim", TASK)
    cli(capsys, "task", "launch", TASK, "--agent", "claude")
    launch = orca_calls(fake_orca, "agent launch")[0]
    assert launch[launch.index("--prompt") + 1] == f"/factory-implement {TASK}"
    assert "--model" not in launch
    assert store.read_task(TASK)["attempts"][0]["model"] is None


def test_launch_twice_is_refused(project, fake_orca, capsys):
    cli(capsys, "task", "claim", TASK)
    cli(capsys, "task", "launch", TASK, "--agent", "claude")
    code, out = cli(capsys, "task", "launch", TASK, "--agent", "claude")
    assert code == 4
    assert out["error"]["code"] == "already_launched"
    assert len(orca_calls(fake_orca, "agent launch")) == 1


def test_launch_before_claim_is_refused(project, capsys):
    code, out = cli(capsys, "task", "launch", TASK, "--agent", "claude")
    assert code == 3
    assert out["error"]["code"] == "invalid_transition"


def test_lost_reply_records_one_agent(project, store, fake_orca, capsys):
    cli(capsys, "task", "claim", TASK)
    lost = {"id": "x", "ok": False, "error": {"code": "launch_reply_lost", "message": "lost",
                                             "operationId": "op-3"}}
    fake_orca.respond_sequence("agent launch", [{"exit": 1, "stdout": lost}])
    code, _ = cli(capsys, "task", "launch", TASK, "--agent", "claude")
    assert code == 0
    attempts = store.read_task(TASK)["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["operation_id"] == "op-3"


def test_launch_refused_by_orca_can_be_retried(project, store, fake_orca, capsys):
    cli(capsys, "task", "claim", TASK)
    refused = {"code": "agent_unavailable", "message": "codex is not installed"}
    fake_orca.respond_sequence("agent launch", [{"exit": 1, "stdout": {"id": "x", "ok": False, "error": refused}}])
    code, out = cli(capsys, "task", "launch", TASK, "--agent", "codex")
    assert code == 5
    assert "codex is not installed" in out["error"]["message"]
    assert store.read_task(TASK)["attempts"][0]["agent"] is None
    code, _ = cli(capsys, "task", "launch", TASK, "--agent", "claude")
    assert code == 0


def test_launch_without_an_answer_is_not_repeated(project, store, fake_orca, capsys):
    cli(capsys, "task", "claim", TASK)
    fake_orca.respond_sequence("agent launch", [{"exit": 0, "stdout": "connection reset"}])
    code, out = cli(capsys, "task", "launch", TASK, "--agent", "claude")
    assert code == 5
    assert "recover" in out["error"]["message"]
    code, out = cli(capsys, "task", "launch", TASK, "--agent", "claude")
    assert code == 4
    assert len(orca_calls(fake_orca, "agent launch")) == 1


def test_effort_without_model_is_a_usage_error(project, fake_orca, capsys):
    cli(capsys, "task", "claim", TASK)
    code, out = cli(capsys, "task", "launch", TASK, "--agent", "claude", "--effort", "high")
    assert code == 2
    assert orca_calls(fake_orca, "agent launch") == []


def _launch(root, results):
    import os
    os.chdir(root)
    results.put(main(["task", "launch", TASK, "--agent", "claude", "--json"]))


def test_concurrent_launches_start_one_agent(project, store, fake_orca, capsys):
    import multiprocessing
    cli(capsys, "task", "claim", TASK)
    results = multiprocessing.Queue()
    procs = [multiprocessing.Process(target=_launch, args=(str(project.root), results)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    codes = sorted(results.get() for _ in procs)
    assert codes == [0, 4, 4, 4]
    assert len(orca_calls(fake_orca, "agent launch")) == 1
