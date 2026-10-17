import json
import tomllib

import pytest
from conftest import git, load_fixture
from test_doctor import snapshot

from factory.cli import main

SKILLS = ["factory-init", "factory-design", "factory-implement", "factory-status"]


@pytest.fixture
def project(repo, fake_orca, fake_gh, monkeypatch):
    monkeypatch.chdir(repo.root)
    (repo.root / "pyproject.toml").write_text('[project]\nname = "x"\n[tool.pytest.ini_options]\n[tool.ruff]\n')
    return repo


def cli(capsys, *argv):
    code = main([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


def plan(capsys, *extra):
    code, out = cli(capsys, "init", "--plan", *extra)
    assert code == 0, out
    return out["data"]


def apply(capsys, plan_id, *extra):
    code, out = cli(capsys, "init", "--apply", plan_id, *extra)
    assert code == 0, out
    return out["data"]


def paths(items):
    return {item["path"] for item in items}


def test_plan_lists_everything_and_changes_nothing(project, capsys):
    before = snapshot(project.root)
    data = plan(capsys)
    assert snapshot(project.root) == before
    created = paths(data["create"])
    for path in ("AGENTS.md", "CLAUDE.md", "docs/conventions.md", ".factory/config.toml", ".gitignore",
                 ".claude/settings.json"):
        assert path in created
    for skill in SKILLS:
        assert f".claude/skills/{skill}/SKILL.md" in created
        assert f".agents/skills/{skill}/SKILL.md" in created
    assert ".claude/skills/factory-implement/references/roles/lead.md" in created
    assert ".claude/skills/factory-design/references/design-template.md" in created
    assert "docs/product.md" not in created  # small repo: AGENTS.md and conventions.md only
    assert data["delete"] == []
    assert [a["id"] for a in data["orca"]] == ["skills-update"]
    assert data["plan_id"]


def test_plan_is_stable(project, capsys):
    assert plan(capsys)["plan_id"] == plan(capsys)["plan_id"]


def test_apply_installs_without_committing(project, capsys):
    head = git("rev-parse", "HEAD", cwd=project.root)
    data = plan(capsys)
    result = apply(capsys, data["plan_id"])
    root = project.root
    assert git("rev-parse", "HEAD", cwd=root) == head
    cfg = tomllib.loads((root / ".factory/config.toml").read_text())
    assert cfg["checks"] == {"test": "pytest", "lint": "ruff check ."}
    assert cfg["templates"][".claude/skills/factory-init/SKILL.md"].startswith("sha256:")
    assert "AGENTS.md" not in cfg["templates"]  # docs are filled by the agent: created once, then kept
    assert ".factory/state/" in (root / ".gitignore").read_text().splitlines()
    settings = json.loads((root / ".claude/settings.json").read_text())
    assert settings["permissions"]["ask"] == ["Bash(factory design approve:*)", "Bash(factory design reject:*)"]
    assert (root / "CLAUDE.md").read_text().splitlines()[-1] == "@AGENTS.md"
    for skill in SKILLS:
        claude, codex = root / f".claude/skills/{skill}/SKILL.md", root / f".agents/skills/{skill}/SKILL.md"
        assert codex.read_text() == claude.read_text()
    assert (root / ".claude/skills/factory-implement/references/adr-template.md").exists()
    assert result["orca"] == [{"id": "skills-update", "ok": True}]


def test_apply_twice_gives_the_same_tree(project, capsys):
    apply(capsys, plan(capsys)["plan_id"])
    first = snapshot(project.root)
    second_plan = plan(capsys)
    assert second_plan["create"] == [] and second_plan["modify"] == [] and second_plan["delete"] == []
    apply(capsys, second_plan["plan_id"])
    assert {k: v for k, v in snapshot(project.root).items() if "backups" not in k} == \
        {k: v for k, v in first.items() if "backups" not in k}


def test_changed_repo_refuses_an_old_plan(project, capsys):
    data = plan(capsys)
    (project.root / "AGENTS.md").write_text("# mine\n")
    code, out = cli(capsys, "init", "--apply", data["plan_id"])
    assert (code, out["error"]["code"]) == (3, "plan_changed")
    assert (project.root / "AGENTS.md").read_text() == "# mine\n"


def test_customized_file_is_kept_and_shown_as_diff(project, capsys):
    apply(capsys, plan(capsys)["plan_id"])
    path = project.root / ".claude/skills/factory-status/SKILL.md"
    path.write_text(path.read_text() + "\nMy own rule.\n")
    data = plan(capsys)
    customized = {c["path"]: c for c in data["customized"]}
    assert ".claude/skills/factory-status/SKILL.md" in customized
    assert "My own rule." in customized[".claude/skills/factory-status/SKILL.md"]["diff"]
    apply(capsys, data["plan_id"])
    assert "My own rule." in path.read_text()


def test_existing_settings_are_preserved(project, capsys):
    (project.root / ".claude").mkdir()
    (project.root / ".claude/settings.json").write_text(json.dumps(
        {"model": "opus", "permissions": {"allow": ["Bash(npm test)"], "ask": ["Bash(rm:*)"]}}))
    data = plan(capsys)
    assert ".claude/settings.json" in paths(data["modify"])
    apply(capsys, data["plan_id"])
    settings = json.loads((project.root / ".claude/settings.json").read_text())
    assert settings["model"] == "opus"
    assert settings["permissions"]["allow"] == ["Bash(npm test)"]
    assert settings["permissions"]["ask"] == ["Bash(rm:*)", "Bash(factory design approve:*)",
                                              "Bash(factory design reject:*)"]


def test_existing_agents_md_gets_the_factory_section_and_can_be_restored(project, capsys):
    (project.root / "AGENTS.md").write_text("# Our agents\n\nRun `make test`.\n")
    data = plan(capsys)
    modify = {m["path"]: m for m in data["modify"]}
    assert "## Software Factory" in modify["AGENTS.md"]["diff"]
    result = apply(capsys, data["plan_id"])
    text = (project.root / "AGENTS.md").read_text()
    assert text.startswith("# Our agents") and "## Software Factory" in text
    code, out = cli(capsys, "init", "--restore", result["backup"])
    assert code == 0, out
    assert (project.root / "AGENTS.md").read_text() == "# Our agents\n\nRun `make test`.\n"


def test_other_instruction_files_are_respected_for_review(project, capsys):
    (project.root / "GEMINI.md").write_text("Use tabs.\n")
    respect = {r["path"]: r["reason"] for r in plan(capsys)["respect"]}
    assert "review" in respect["GEMINI.md"]


def test_skill_proposed_deletion_is_applied_with_backup_and_restorable(project, capsys):
    (project.root / "GEMINI.md").write_text("Use tabs.\n")
    data = plan(capsys, "--delete", "GEMINI.md", "--reason", "duplicates AGENTS.md")
    assert data["delete"] == [{"path": "GEMINI.md", "reason": "duplicates AGENTS.md"}]
    code, out = cli(capsys, "init", "--apply", data["plan_id"])
    assert code == 3  # the same --delete must be passed again to get the same plan id
    result = apply(capsys, data["plan_id"], "--delete", "GEMINI.md", "--reason", "duplicates AGENTS.md")
    assert not (project.root / "GEMINI.md").exists()
    cli(capsys, "init", "--restore", result["backup"])
    assert (project.root / "GEMINI.md").read_text() == "Use tabs.\n"


@pytest.mark.parametrize("path", ["src/app.py", "tests/notes.md", ".github/workflows/ci.yml", ".env", "missing.md"])
def test_deleting_code_tests_ci_or_secrets_is_refused(project, capsys, path):
    target = project.root / path
    if path != "missing.md":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n")
    code, out = cli(capsys, "init", "--plan", "--delete", path, "--reason", "unused")
    assert (code, out["error"]["code"]) == (3, "delete_not_allowed")


def test_empty_docs_are_proposed_for_deletion(project, capsys):
    (project.root / "docs").mkdir()
    (project.root / "docs/old.md").write_text("\n  \n")
    deletes = {d["path"]: d["reason"] for d in plan(capsys)["delete"]}
    assert "empty" in deletes["docs/old.md"]


def test_factory_leftovers_are_proposed_for_deletion(project, capsys):
    (project.root / ".claude/skills/factory-old").mkdir(parents=True)
    mark = "<!-- factory-template: skills/factory-old@1 -->\n"
    (project.root / ".claude/skills/factory-old/SKILL.md").write_text(mark)
    deletes = {d["path"] for d in plan(capsys)["delete"]}
    assert ".claude/skills/factory-old/SKILL.md" in deletes


def test_exclude_skips_items(project, capsys):
    data = plan(capsys)
    apply(capsys, data["plan_id"], "--exclude", ".gitignore", "--exclude", ".agents/skills")
    assert not (project.root / ".gitignore").exists()
    assert not (project.root / ".agents").exists()
    assert (project.root / ".claude/skills/factory-init/SKILL.md").exists()


def test_normal_repo_gets_the_full_docs(project, capsys):
    for n in range(30):
        project.commit(f"src/m{n}.py", "x = 1\n", f"m{n}")
    created = paths(plan(capsys)["create"])
    for doc in ("docs/product.md", "docs/architecture.md", "docs/conventions.md", "docs/working-agreements.md",
                "docs/decisions/README.md"):
        assert doc in created


def test_orca_actions_when_the_repo_is_new(project, fake_orca, capsys):
    fake_orca.respond_fixture("repo show", "repo-show-not-found", exit=1)
    skills = load_fixture("skills-installed")
    skills["result"]["skills"] = [s for s in skills["result"]["skills"] if s["name"] != "orca-cli"]
    fake_orca.respond("skills installed", skills)
    data = plan(capsys)
    assert [a["id"] for a in data["orca"]] == ["repo-add", "set-base-ref", "skills-install"]
    apply(capsys, data["plan_id"])
    calls = [c for c in fake_orca.calls() if c[0] in ("repo", "skills") and c[1] in ("add", "set-base-ref", "install")]
    assert calls[0][:4] == ["repo", "add", "--path", str(project.root)]
    assert calls[1][:5] == ["repo", "set-base-ref", "--repo", f"path:{project.root}", "--ref"]
    assert calls[1][5] == "origin/main"
    assert calls[2][:4] == ["skills", "install", "--skill", "orca-cli"]
