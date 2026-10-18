import json
import subprocess

import pytest
import yaml
from conftest import git
from test_design_parse import VALID

from swfactory.cli import main

CHANGE = "CHG-0012"
DESIGN = VALID.replace("depends_on: [CHG-0012-01, CHG-0007-03]", "depends_on: [CHG-0012-01]")
FOLDER = f".factory/changes/{CHANGE}"


@pytest.fixture
def project(repo, fake_orca, monkeypatch):
    monkeypatch.chdir(repo.root)
    folder = repo.root / FOLDER
    folder.mkdir(parents=True)
    (folder / "design.md").write_text(DESIGN)
    return repo


def cli(capsys, *argv):
    code = main([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


def committed_files(repo):
    return git("show", "--name-only", "--format=", "HEAD", cwd=repo.root).splitlines()


def test_approve_on_base_branch_commits_only_the_change(project, capsys):
    project.commit("src/app.py", "x = 1\n", "app")
    (project.root / "src/app.py").write_text("x = 2\n")  # unstaged change
    (project.root / "staged.txt").write_text("staged\n")
    git("add", "staged.txt", cwd=project.root)  # staged change
    head = git("rev-parse", "HEAD", cwd=project.root)

    code, out = cli(capsys, "design", "approve", CHANGE, "--message", "apruebo CHG-0012")
    assert code == 0, out
    assert git("rev-parse", "HEAD~1", cwd=project.root) == head
    assert sorted(committed_files(project)) == [f"{FOLDER}/approval.json", f"{FOLDER}/design.md",
                                                f"{FOLDER}/tasks.yaml"]
    status = subprocess.run(["git", "status", "--porcelain"], cwd=project.root, capture_output=True,
                            text=True).stdout.splitlines()
    assert " M src/app.py" in status
    assert "A  staged.txt" in status

    approval = json.loads((project.root / FOLDER / "approval.json").read_text())
    assert approval["change"] == CHANGE
    assert approval["design_digest"] == out["data"]["digest"]
    assert approval["approved_by"] == "person@example.com"
    assert approval["method"] == "chat"
    assert approval["message"] == "apruebo CHG-0012"
    assert approval["approved_at"].endswith("Z")
    tasks = yaml.safe_load((project.root / FOLDER / "tasks.yaml").read_text())
    assert tasks["change"] == CHANGE
    assert tasks["design_digest"] == approval["design_digest"]
    assert [t["id"] for t in tasks["tasks"]] == ["CHG-0012-01", "CHG-0012-02"]
    assert out["data"]["commit"] == git("rev-parse", "HEAD", cwd=project.root)


def test_approve_does_not_push(project, capsys):
    cli(capsys, "design", "approve", CHANGE, "--message", "approve CHG-0012")
    assert git("rev-parse", "origin/main", cwd=project.root) != git("rev-parse", "HEAD", cwd=project.root)


def test_approve_on_another_branch_is_refused(project, capsys):
    git("checkout", "-q", "-b", "feature", cwd=project.root)
    code, out = cli(capsys, "design", "approve", CHANGE, "--message", "apruebo CHG-0012")
    assert code == 3
    assert out["error"]["code"] == "not_on_base_branch"
    assert "main" in out["error"]["message"]
    assert not (project.root / FOLDER / "approval.json").exists()


@pytest.mark.parametrize("message", ["vale", "apruebo CHG-0013", ""])
def test_message_must_name_the_change(project, capsys, message):
    code, out = cli(capsys, "design", "approve", CHANGE, "--message", message)
    assert code == 3
    assert out["error"]["code"] == "approval_not_explicit"
    assert not (project.root / FOLDER / "approval.json").exists()


def test_failing_pre_commit_hook_leaves_nothing_approved(project, capsys):
    hook = project.root / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\necho 'hook says no' >&2\nexit 1\n")
    hook.chmod(0o755)
    head = git("rev-parse", "HEAD", cwd=project.root)
    code, out = cli(capsys, "design", "approve", CHANGE, "--message", "apruebo CHG-0012")
    assert code == 3
    assert out["error"]["code"] == "commit_failed"
    assert "hook says no" in out["error"]["message"]
    assert git("rev-parse", "HEAD", cwd=project.root) == head
    assert not (project.root / FOLDER / "approval.json").exists()
    assert not (project.root / FOLDER / "tasks.yaml").exists()
    assert (project.root / FOLDER / "design.md").read_text() == DESIGN
    assert git("diff", "--cached", "--name-only", cwd=project.root) == ""
    _, shown = cli(capsys, "design", "show", CHANGE)
    assert shown["data"]["state"] == "awaiting_approval"


def test_interactive_approval(project, capsys, monkeypatch):
    monkeypatch.setattr("swfactory.cli.stdin_is_terminal", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: "CHG-0012")
    code = main(["design", "approve", CHANGE])
    assert code == 0
    approval = json.loads((project.root / FOLDER / "approval.json").read_text())
    assert approval["method"] == "terminal"
    assert approval["message"] == "CHG-0012"


def test_interactive_wrong_id_is_refused(project, capsys, monkeypatch):
    monkeypatch.setattr("swfactory.cli.stdin_is_terminal", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: "CHG-0021")
    assert main(["design", "approve", CHANGE]) == 3
    assert "approval_not_confirmed" in capsys.readouterr().err
    assert not (project.root / FOLDER / "approval.json").exists()


def test_invalid_design_cannot_be_approved(project, capsys):
    (project.root / FOLDER / "design.md").write_text(DESIGN.replace("complexity: normal", "complexity: x"))
    code, out = cli(capsys, "design", "approve", CHANGE, "--message", "apruebo CHG-0012")
    assert code == 3
    assert out["error"]["code"] == "design_invalid"


def test_already_approved(project, capsys):
    cli(capsys, "design", "approve", CHANGE, "--message", "apruebo CHG-0012")
    code, out = cli(capsys, "design", "approve", CHANGE, "--message", "apruebo CHG-0012")
    assert code == 3
    assert out["error"]["code"] == "already_approved"


def test_orca_unavailable_blocks_approval(project, capsys, fake_orca):
    fake_orca.fail("repo show", code="repo_not_found")
    code, out = cli(capsys, "design", "approve", CHANGE, "--message", "apruebo CHG-0012")
    assert code == 5
    assert not (project.root / FOLDER / "approval.json").exists()


def test_reject(project, capsys):
    code, out = cli(capsys, "design", "reject", CHANGE, "--reason", "Out of scope this quarter")
    assert code == 0, out
    rejection = json.loads((project.root / FOLDER / "rejection.json").read_text())
    assert rejection["change"] == CHANGE
    assert rejection["reason"] == "Out of scope this quarter"
    assert rejection["rejected_by"] == "person@example.com"
    assert "message" not in rejection
    assert sorted(committed_files(project)) == [f"{FOLDER}/design.md", f"{FOLDER}/rejection.json"]
    _, shown = cli(capsys, "design", "show", CHANGE)
    assert shown["data"]["state"] == "rejected"
    code, out = cli(capsys, "design", "approve", CHANGE, "--message", "apruebo CHG-0012")
    assert out["error"]["code"] == "change_rejected"


def test_reject_needs_base_branch(project, capsys):
    git("checkout", "-q", "-b", "feature", cwd=project.root)
    code, out = cli(capsys, "design", "reject", CHANGE, "--reason", "no")
    assert code == 3
    assert not (project.root / FOLDER / "rejection.json").exists()


def test_reapproval_after_edit_replaces_files(project, capsys):
    cli(capsys, "design", "approve", CHANGE, "--message", "apruebo CHG-0012")
    edited = DESIGN.replace("Weekly recurrence.", "Weekly and monthly recurrence.")
    (project.root / FOLDER / "design.md").write_text(edited)
    code, out = cli(capsys, "design", "approve", CHANGE, "--message", "apruebo CHG-0012 otra vez")
    assert code == 0, out
    approval = json.loads((project.root / FOLDER / "approval.json").read_text())
    assert approval["message"] == "apruebo CHG-0012 otra vez"
    assert subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=project.root).returncode == 0


def test_interactive_needs_a_terminal(project, capsys, monkeypatch):
    monkeypatch.setattr("swfactory.cli.stdin_is_terminal", lambda: False)
    code = main(["design", "approve", CHANGE, "--json"])
    assert code == 3
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "approval_not_confirmed"


def test_failed_commit_keeps_what_the_person_had_staged(project, capsys):
    project.commit(f"{FOLDER}/design.md", DESIGN, "draft design")
    staged = DESIGN.replace("Weekly recurrence.", "Weekly recurrence (staged).")
    (project.root / FOLDER / "design.md").write_text(staged)
    git("add", f"{FOLDER}/design.md", cwd=project.root)
    hook = project.root / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    code, out = cli(capsys, "design", "approve", CHANGE, "--message", "apruebo CHG-0012")
    assert out["error"]["code"] == "commit_failed"
    assert git("diff", "--cached", "--name-only", cwd=project.root) == f"{FOLDER}/design.md"
    assert git("show", f":{FOLDER}/design.md", cwd=project.root) == staged.strip()


def test_remote_orca_blocks_approval(project, capsys, monkeypatch):
    monkeypatch.setenv("ORCA_PAIRING_CODE", "orca://pair?x")
    code, out = cli(capsys, "design", "approve", CHANGE, "--message", "apruebo CHG-0012")
    assert code == 5
    assert out["error"]["code"] == "orca_not_local"
