import re
from importlib import resources
from pathlib import Path

import pytest

DESIGN = (Path(__file__).parent.parent / "design_factory.md").read_text()
ROLES = {
    "designer": "Designer",
    "design_critic": "Design critic",
    "lead": "Lead (implementer)",
    "planner": "Planner",
    "quality_reviewer": "Quality reviewer",
    "conformance_reviewer": "Conformance reviewer",
}


def design_role(title):
    section = DESIGN[DESIGN.index("### 5.3"):DESIGN.index("### 5.4")]
    return re.search(rf"\*\*{re.escape(title)}\*\*\n> (.+?)\n", section).group(1)


@pytest.mark.parametrize(("name", "title"), ROLES.items())
def test_role_matches_the_design(name, title):
    text = resources.files("factory").joinpath(f"templates/roles/{name}.md").read_text()
    assert text.startswith(f"<!-- factory-template: roles/{name}@")
    assert design_role(title) in text


@pytest.mark.parametrize("name", ["quality_reviewer", "conformance_reviewer"])
def test_reviewers_carry_the_json_contract(name):
    text = resources.files("factory").joinpath(f"templates/roles/{name}.md").read_text()
    kind = name.removesuffix("_reviewer")
    assert f'{{"type": "{kind}", "commit": "<sha>", "verdict": "pass", "findings": [{{"severity": "major"' in text


DOCS = ["AGENTS.md", "CLAUDE.md", "product.md", "architecture.md", "conventions.md", "working-agreements.md",
        "decisions/README.md", "decisions/adr.md"]


def template(path):
    return resources.files("factory").joinpath(f"templates/{path}").read_text()


@pytest.mark.parametrize("name", DOCS)
def test_docs_templates_exist_with_mark(name):
    assert template(f"docs/{name}").startswith(f"<!-- factory-template: docs/{name}@")


def test_agents_md_size_and_factory_section():
    text = template("docs/AGENTS.md")
    assert 60 <= len(text.splitlines()) <= 120
    for needle in ("## Software Factory", "/factory-design", "/factory-implement", "/factory-status",
                   "/factory-init", "only way to change Factory state", "orca skills get orca-cli",
                   "evidence"):
        assert needle in text


def test_claude_md_imports_agents_md():
    lines = [line for line in template("docs/CLAUDE.md").splitlines() if not line.startswith("<!--")]
    assert lines == ["@AGENTS.md"]


def test_conventions_has_known_pitfalls():
    assert "## Known pitfalls" in template("docs/conventions.md")


def test_design_template_parses():
    from factory.design import parse_design

    text = template("design/design.md").replace("CHG-0000", "CHG-0042")
    parsed = parse_design(text, "CHG-0042", set())
    assert parsed["acceptance_criteria"] == ["AC-01", "AC-02"]
    assert parsed["tasks"][0]["id"] == "CHG-0042-01"
