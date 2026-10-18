"""Shared fixtures: temporary Git repositories and the fake `orca` and `gh` executables."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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
    """No real Orca session variables, a Git identity that does not depend on the machine, and the
    fake `orca` and `gh` first on PATH, so no test can reach the real tools (the fakes refuse to
    run unless their fixture is used)."""
    for name in list(os.environ):
        if name.startswith("ORCA_"):
            monkeypatch.delenv(name)
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\temail = person@example.com\n\tname = Person\n[init]\n\tdefaultBranch = main\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("PATH", f"{FAKES}{os.pathsep}{os.environ['PATH']}")
    # The fakes are Python scripts: run them with this Python, which also works on Windows.
    monkeypatch.setenv("SWFACTORY_ORCA", json.dumps([sys.executable, str(FAKES / "orca")]))
    monkeypatch.setenv("SWFACTORY_GH", json.dumps([sys.executable, str(FAKES / "gh")]))


def set_home(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    """Make `path` the home folder for this process and its children (HOME, or USERPROFILE on Windows)."""
    monkeypatch.setenv("HOME", str(path))
    monkeypatch.setenv("USERPROFILE", str(path))


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
    def respond(self, command: str, stdout: Any, exit: int = 0, target: str | None = None) -> None:
        """Replace the answer to `command` (e.g. "terminal show") with `stdout` and `exit`;
        `target` limits it to one --terminal/--worktree value."""
        self._write(command, {"exit": exit, "stdout": stdout}, target)

    def respond_sequence(
        self, command: str, answers: list[dict[str, Any]], target: str | None = None
    ) -> None:
        """Answer `command` with each {"exit", "stdout"} in turn, then with the default answer."""
        self._write(command, answers, target)

    def _write(self, command: str, spec: Any, target: str | None) -> None:
        responses = self.state / "responses"
        responses.mkdir(parents=True, exist_ok=True)
        name = command.replace(" ", "-") + (f"@{target}" if target else "")
        (responses / f"{name}.json").write_text(json.dumps(spec))

    def respond_fixture(self, command: str, fixture: str, exit: int = 0, target: str | None = None) -> None:
        self.respond(command, load_fixture(fixture), exit, target)

    def fail(self, command: str, code: str = "runtime_error", message: str = "fake failure") -> None:
        self.respond(command, orca_error(code, message), exit=1)


def orca_error(code: str, message: str) -> dict[str, Any]:
    return {"id": "fake", "ok": False, "error": {"code": code, "message": message}, "_meta": {}}


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
def fake_orca(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repo: Repo) -> FakeOrca:
    """Fake orca bound to the `repo` fixture: workspaces are worktrees of that repo."""
    state = tmp_path / "fake-orca"
    monkeypatch.setenv("FAKE_ORCA_DIR", str(state))
    monkeypatch.setenv("FAKE_ORCA_REPO", str(repo.root))
    return FakeOrca(state)


@pytest.fixture
def fake_gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeGh:
    state = tmp_path / "fake-gh"
    monkeypatch.setenv("FAKE_GH_DIR", str(state))
    return FakeGh(state)
