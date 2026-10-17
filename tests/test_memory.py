import json

import pytest

from factory.cli import main


@pytest.fixture
def docs(repo, monkeypatch):
    monkeypatch.chdir(repo.root)
    (repo.root / "AGENTS.md").write_text("# AGENTS\n\nSee [conventions](docs/conventions.md).\n")
    (repo.root / "docs/decisions").mkdir(parents=True)
    (repo.root / "docs/conventions.md").write_text("# Conventions\n\nWe follow [0001](decisions/0001-use-x.md).\n")
    (repo.root / "docs/decisions/README.md").write_text(
        "# Decisions\n\n- [0001 — Use X](0001-use-x.md) — accepted\n")
    (repo.root / "docs/decisions/0001-use-x.md").write_text("# 0001 — Use X\n\nStatus: accepted\n")
    return repo


def check(capsys):
    code = main(["memory", "check", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0, out
    return out["data"]["findings"]


def test_clean_repo_has_no_findings(docs, capsys):
    assert check(capsys) == []


def test_agents_md_too_long(docs, capsys):
    (docs.root / "AGENTS.md").write_text("line\n" * 121)
    findings = check(capsys)
    assert [f["check"] for f in findings] == ["agents_md_size"]
    assert "121" in findings[0]["detail"]


def test_superseded_decision_still_cited(docs, capsys):
    (docs.root / "docs/decisions/0001-use-x.md").write_text("# 0001 — Use X\n\nStatus: superseded by 0002\n")
    (docs.root / "docs/decisions/0002-use-y.md").write_text("# 0002 — Use Y\n\nStatus: accepted\n")
    findings = check(capsys)
    assert [(f["check"], f["file"]) for f in findings] == [("superseded_cited", "docs/conventions.md")]


def test_duplicated_adr_numbers(docs, capsys):
    (docs.root / "docs/decisions/0001-use-z.md").write_text("# 0001 — Use Z\n\nStatus: accepted\n")
    findings = check(capsys)
    assert [f["check"] for f in findings] == ["duplicated_adr_number"]
    assert "0001" in findings[0]["detail"]


def test_link_to_missing_file(docs, capsys):
    (docs.root / "docs/architecture.md").write_text(
        "See [old](old-design.md), [web](https://example.com), [anchor](#top) and [ok](conventions.md#code).\n")
    findings = check(capsys)
    assert [(f["check"], f["file"]) for f in findings] == [("missing_link", "docs/architecture.md")]
    assert "old-design.md" in findings[0]["detail"]


def test_repo_without_docs(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo.root)
    assert check(capsys) == []
