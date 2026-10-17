import json

import pytest
import yaml
from test_approve import CHANGE, DESIGN, FOLDER

from factory.cli import main
from factory.state import TaskStore
from factory.tasks import DESIGN_CHANGED, PAUSED, transition

NEW_TASK = """- id: CHG-0012-03
  title: Notify users
  depends_on: [CHG-0012-02]
  complexity: trivial
  review: []
  acceptance:
    AC-03: "pytest tests/test_notify.py"
```"""


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


def set_state(store, task, state, **fields):
    store.update_task(task, lambda s: {**s, "state": state, **fields}, "test")


def show(capsys):
    assert main(["design", "show", CHANGE, "--json"]) == 0
    return json.loads(capsys.readouterr().out)["data"]


def edit(project, old="Weekly recurrence.", new="Weekly recurrence, with a typo fixed."):
    path = project.root / FOLDER / "design.md"
    path.write_text(path.read_text().replace(old, new))


def test_edit_after_approval_blocks_tasks_in_progress(project, store, capsys):
    set_state(store, "CHG-0012-01", "in_progress")
    set_state(store, "CHG-0012-02", "in_review")
    edit(project)
    data = show(capsys)
    assert data["state"] == "awaiting_approval"
    for task in ("CHG-0012-01", "CHG-0012-02"):
        stored = store.read_task(task)
        assert stored["state"] == "blocked"
        assert stored["blocked_reason"] == DESIGN_CHANGED
    assert [t["state"] for t in data["tasks"]] == ["blocked", "blocked"]


def test_interrupted_tasks_are_blocked_too(project, store, capsys):
    set_state(store, "CHG-0012-01", "interrupted")
    edit(project)
    show(capsys)
    assert store.read_task("CHG-0012-01")["blocked_from"] == "interrupted"


def test_done_and_paused_tasks_are_not_touched(project, store, capsys):
    set_state(store, "CHG-0012-01", "done")
    paused = transition({**store.read_task("CHG-0012-01"), "task": "CHG-0012-02", "state": "in_progress"},
                        "block", reason=PAUSED)
    store.update_task("CHG-0012-02", lambda s: paused, "pause")
    edit(project)
    show(capsys)
    assert store.read_task("CHG-0012-01")["state"] == "done"
    assert store.read_task("CHG-0012-02")["blocked_reason"] == PAUSED


def test_reapproval_restores_previous_states(project, store, capsys):
    set_state(store, "CHG-0012-01", "in_progress")
    set_state(store, "CHG-0012-02", "in_review")
    edit(project)
    show(capsys)
    assert main(["design", "approve", CHANGE, "--message", "apruebo CHG-0012"]) == 0
    capsys.readouterr()
    assert store.read_task("CHG-0012-01")["state"] == "in_progress"
    assert store.read_task("CHG-0012-02")["state"] == "in_review"
    assert store.read_task("CHG-0012-01")["blocked_reason"] is None


def test_reverting_the_edit_restores_previous_states(project, store, capsys):
    set_state(store, "CHG-0012-01", "in_progress")
    edit(project)
    show(capsys)
    edit(project, "Weekly recurrence, with a typo fixed.", "Weekly recurrence.")
    data = show(capsys)
    assert data["state"] == "approved"
    assert store.read_task("CHG-0012-01")["state"] == "in_progress"


def test_reapproval_keeps_ids_and_adds_new_tasks(project, store, capsys):
    set_state(store, "CHG-0012-01", "done")
    edit(project, "    AC-03: \"pytest tests/integration/test_calendar.py\"\n```",
         "    AC-03: \"pytest tests/integration/test_calendar.py\"\n" + NEW_TASK)
    assert main(["design", "approve", CHANGE, "--message", "apruebo CHG-0012"]) == 0
    capsys.readouterr()
    tasks = yaml.safe_load((project.root / FOLDER / "tasks.yaml").read_text())["tasks"]
    assert [t["id"] for t in tasks] == ["CHG-0012-01", "CHG-0012-02", "CHG-0012-03"]
    assert store.read_task("CHG-0012-01")["state"] == "done"


def test_reapproval_cannot_remove_an_approved_task(project, capsys):
    path = project.root / FOLDER / "design.md"
    text = path.read_text()
    start = text.index("- id: CHG-0012-02")
    end = text.index("```", start)
    path.write_text(text[:start] + text[end:])
    code = main(["design", "approve", CHANGE, "--message", "apruebo CHG-0012", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 3
    assert any("CHG-0012-02" in d for d in out["error"]["details"])
