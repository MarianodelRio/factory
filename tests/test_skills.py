import re
from importlib import resources

import pytest
import yaml

SKILLS = ["factory-init", "factory-design", "factory-implement", "factory-status"]
# Files that `factory init` copies into the skills when installing them (T-28).
INSTALLED = {"references/design-template.md", "references/adr-template.md"} | {
    f"references/roles/{r}.md"
    for r in ("designer", "design_critic", "lead", "planner", "quality_reviewer", "conformance_reviewer")
}


def skill_dir(name):
    return resources.files("factory").joinpath(f"templates/skills/{name}")


def frontmatter(text):
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "SKILL.md must start with YAML frontmatter"
    return yaml.safe_load(match.group(1))


@pytest.mark.parametrize("name", SKILLS)
def test_frontmatter(name):
    meta = frontmatter(skill_dir(name).joinpath("SKILL.md").read_text())
    assert meta["name"] == name
    assert 80 <= len(meta["description"]) <= 1024
    assert set(meta) == {"name", "description"}


@pytest.mark.parametrize("name", SKILLS)
def test_skill_is_short_and_marked(name):
    text = skill_dir(name).joinpath("SKILL.md").read_text()
    assert f"<!-- factory-template: skills/{name}@" in text
    assert len(text.splitlines()) <= 120


@pytest.mark.parametrize("name", SKILLS)
def test_references_exist(name):
    root = skill_dir(name)
    texts = [root.joinpath("SKILL.md").read_text()]
    refs = root.joinpath("references")
    if refs.is_dir():
        texts += [f.read_text() for f in refs.iterdir() if f.name.endswith(".md")]
    for text in texts:
        for ref in re.findall(r"`((?:references/)?(?:roles/)?[\w-]+\.md)`", text):
            if ref in ("AGENTS.md", "SKILL.md", "CLAUDE.md", "GEMINI.md") or ref.startswith(("docs/",)):
                continue
            path = ref if ref.startswith("references/") else f"references/{ref}"
            if path in INSTALLED:
                continue
            assert root.joinpath(path).is_file(), f"{name}: {ref} does not exist"


def test_every_cli_command_used_exists():
    from factory.cli import build_parser

    commands = set()
    for name in SKILLS:
        root = skill_dir(name)
        texts = [root.joinpath("SKILL.md").read_text()]
        if root.joinpath("references").is_dir():
            texts += [f.read_text() for f in root.joinpath("references").iterdir()]
        for text in texts:
            commands |= set(re.findall(r"factory (doctor|init|status|design \w+|task \w+|memory \w+)", text))
    parser = build_parser()
    for command in commands:
        with pytest.raises(SystemExit) as exc:
            parser.parse_args([*command.split(), "--help"])
        assert exc.value.code == 0, command
