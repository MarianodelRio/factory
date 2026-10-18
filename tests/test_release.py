"""The versions and files that a release publishes agree with each other."""

import json
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_npm_launcher_has_the_same_version_and_license():
    package = json.loads((ROOT / "npm/package.json").read_text())
    assert package["version"] == VERSION
    assert (ROOT / "npm/LICENSE").read_text() == (ROOT / "LICENSE").read_text()
    assert set(package["bin"]) == {"swfactory"}


def test_changelog_has_a_section_for_the_version():
    assert f"## [{VERSION}] - " in (ROOT / "CHANGELOG.md").read_text()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_npm_launcher_is_valid_javascript():
    subprocess.run(["node", "--check", str(ROOT / "npm/bin/swfactory.js")], check=True)
