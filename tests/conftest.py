"""Shared fixtures: temporary Git repositories and the fake `orca` and `gh` executables."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

FAKES = Path(__file__).parent / "fakes"


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


@dataclass
class Repo:
    """A main checkout cloned from a bare "remote", with helpers to add worktrees and commits."""

    root: Path
    remote: Path

    def add_worktree(self, name: str, base: str = "main") -> Path:
        path = self.root.parent / "worktrees" / name
        git("worktree", "add", "-b", name, str(path), base, cwd=self.root)
        return path

    def commit(self, path: str, content: str, message: str, cwd: Path | None = None) -> str:
        where = cwd or self.root
        file = where / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)
        git("add", path, cwd=where)
        git("commit", "-q", "-m", message, cwd=where)
        return git("rev-parse", "HEAD", cwd=where)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No real Orca session variables, and a Git identity that does not depend on the machine."""
    for name in list(os.environ):
        if name.startswith("ORCA_"):
            monkeypatch.delenv(name)
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\temail = person@example.com\n\tname = Person\n[init]\n\tdefaultBranch = main\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    remote = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    root = tmp_path / "project"
    root.mkdir()
    git("init", "-q", "-b", "main", cwd=root)
    git("remote", "add", "origin", str(remote), cwd=root)
    created = Repo(root=root, remote=remote)
    created.commit("README.md", "# project\n", "initial commit")
    git("push", "-q", "-u", "origin", "main", cwd=root)
    git("remote", "set-head", "origin", "main", cwd=root)
    return created


class FakeTool:
    def __init__(self, state: Path) -> None:
        self.state = state

    def calls(self) -> list[list[str]]:
        log = self.state / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line)["argv"] for line in log.read_text().splitlines()]


class FakeOrca(FakeTool):
    def respond(self, command: str, stdout: Any, exit: int = 0) -> None:
        """Replace the answer to `command` (e.g. "terminal show") with `stdout` and `exit`."""
        responses = self.state / "responses"
        responses.mkdir(parents=True, exist_ok=True)
        spec = {"exit": exit, "stdout": stdout}
        (responses / f"{command.replace(' ', '-')}.json").write_text(json.dumps(spec))

    def respond_fixture(self, command: str, fixture: str, exit: int = 0) -> None:
        self.respond(command, load_fixture(fixture), exit)

    def fail(self, command: str, code: str = "runtime_error", message: str = "fake failure") -> None:
        error = {"id": "fake", "ok": False, "error": {"code": code, "message": message}, "_meta": {}}
        self.respond(command, error, exit=1)


class FakeGh(FakeTool):
    def prs(self) -> list[dict[str, Any]]:
        file = self.state / "prs.json"
        return json.loads(file.read_text()) if file.exists() else []

    def fail(self, message: str = "gh: authentication required") -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "fail").write_text(message)


def load_fixture(name: str) -> Any:
    return json.loads((Path(__file__).parent / "fixtures" / "orca" / f"{name}.json").read_text())


@pytest.fixture
def fake_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", f"{FAKES}{os.pathsep}{os.environ['PATH']}")


@pytest.fixture
def fake_orca(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_tools: None) -> FakeOrca:
    state = tmp_path / "fake-orca"
    monkeypatch.setenv("FAKE_ORCA_DIR", str(state))
    return FakeOrca(state)


@pytest.fixture
def fake_gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_tools: None) -> FakeGh:
    state = tmp_path / "fake-gh"
    monkeypatch.setenv("FAKE_GH_DIR", str(state))
    return FakeGh(state)
