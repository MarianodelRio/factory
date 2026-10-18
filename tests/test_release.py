"""The version that a release publishes agrees with the changelog."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_changelog_has_a_section_for_the_version():
    assert f"## [{VERSION}] - " in (ROOT / "CHANGELOG.md").read_text()
