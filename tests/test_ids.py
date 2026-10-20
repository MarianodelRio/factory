"""Short, descriptive ids: `CHG-12` in a `CHG-12-<slug>` folder, tasks `CHG-12.1`, typed as `12.1`."""

import json

import pytest
from conftest import git
from test_design_parse import VALID

from swfactory.cli import main

DESIGN = (VALID.replace("CHG-0012-01", "CHG-12.1").replace("CHG-0012-02", "CHG-12.2").replace("CHG-0012", "CHG-12")
          .replace("depends_on: [CHG-12.1, CHG-0007-03]", "depends_on: [CHG-12.1]"))


def cli(capsys, *argv):
    code = main([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


@pytest.fixture
def approved(repo, fake_orca, monkeypatch, capsys):
    monkeypatch.chdir(repo.root)
    (repo.root / ".factory/changes").mkdir(parents=True)
    for n in range(1, 12):  # changes 1..11 exist, so CHG-12 sorts after CHG-2 by number, not by text
        (repo.root / f".factory/changes/CHG-{n}").mkdir()
    code, out = cli(capsys, "design", "register", "--slug", "weekly-recurrence")
    assert (code, out["data"]["change"]) == (0, "CHG-12"), out
    (repo.root / ".factory/changes/CHG-12-weekly-recurrence/design.md").write_text(DESIGN)
    assert cli(capsys, "design", "register", "12")[0] == 0
    code, out = cli(capsys, "design", "approve", "CHG-12", "--message", "apruebo CHG-12")
    assert code == 0, out
    return repo


def test_a_change_with_a_slug_folder_goes_end_to_end(approved, capsys):
    tasks = {t["id"]: t for t in cli(capsys, "task", "list")[1]["data"]["tasks"]}
    assert (tasks["CHG-12.1"]["state"], tasks["CHG-12.2"]["state"]) == ("ready", "pending")
    code, out = cli(capsys, "task", "claim", "12.1")  # typed short
    assert code == 0, out
    assert out["data"]["branch"] == "user/chg-12.1-add-recurrence-model-validation"
    shown = cli(capsys, "task", "show", "chg-12.1")[1]["data"]
    assert shown["design"] == ".factory/changes/CHG-12-weekly-recurrence/design.md"
    assert git("show", "origin/main:.factory/changes/CHG-12-weekly-recurrence/approval.json", cwd=approved.root)


def test_the_orca_card_shows_the_short_id(approved, fake_orca, capsys):
    cli(capsys, "task", "claim", "12.1")
    card = [c for c in fake_orca.calls() if c[:2] == ["worktree", "set"]][-1]
    assert card[card.index("--display-name") + 1] == "12.1 · Add recurrence model and validation"


def test_design_show_by_number(approved, capsys):
    code, out = cli(capsys, "design", "show", "12")
    assert (code, out["data"]["change"], out["data"]["state"]) == (0, "CHG-12", "approved")
