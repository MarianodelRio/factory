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
    assert f'{{"type": "{kind}", "verdict": "pass", "findings": [{{"severity": "major"' in text
