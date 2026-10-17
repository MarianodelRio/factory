"""Task state files in `.factory/state/` (design §1.4): the only code that writes them.

Per task: `<task>.json` (current state, replaced atomically), `<task>.events.jsonl` (append-only
history; each event carries the resulting state, so a corrupted JSON is rebuilt from the last
readable event) and `<task>.lock` (the claim). Writers serialize on an `flock` of the events
file, which is never replaced.

Raises FactoryError with these codes:
- task_claimed (EXIT_CONFLICT): the claim file already exists.
- not_claimed (EXIT_PRECONDITION): reassigning a claim that does not exist.
- state_corrupted (EXIT_ERROR): the JSON is unreadable and no event can rebuild it.
"""

from __future__ import annotations

import copy
import fcntl
import json
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from factory.output import EXIT_CONFLICT, EXIT_ERROR, EXIT_PRECONDITION, FactoryError

State = dict[str, Any]


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def empty_state(task_id: str) -> State:
    """A task state with every field of design §1.4 and nothing recorded yet."""
    return {
        "task": task_id,
        "state": None,
        "blocked_reason": None,
        "workspace": None,
        "attempts": [],
        "last_checkpoint": None,
        "acceptance": {},
        "checks": None,
        "reviews": [],
        "notes": [],
        "memory": None,
        "commits": [],
        "pull_request": None,
    }


class TaskStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _json(self, task_id: str) -> Path:
        return self.root / f"{task_id}.json"

    def _events(self, task_id: str) -> Path:
        return self.root / f"{task_id}.events.jsonl"

    def _claim(self, task_id: str) -> Path:
        return self.root / f"{task_id}.lock"

    def read_task(self, task_id: str) -> State | None:
        """The current state, rebuilt from the events if the JSON is corrupted; None if absent."""
        path = self._json(task_id)
        if not path.exists():
            return None
        try:
            state: State = json.loads(path.read_text(encoding="utf-8"))
            return state
        except json.JSONDecodeError:
            with self._locked(task_id):
                state = self.rebuild_from_events(task_id)
                self._write_json(task_id, state)
            return state

    def update_task(self, task_id: str, fn: Callable[[State], State], event: str) -> State:
        """Lock, read, apply `fn`, write atomically and log `event`. If `fn` raises, nothing changes."""
        with self._locked(task_id) as log:
            current = self._load(task_id)
            updated = fn(copy.deepcopy(current))
            self._write_json(task_id, updated)
            log.write(json.dumps({"at": now(), "event": event, "state": updated}) + "\n")
            log.flush()
            os.fsync(log.fileno())
        return updated

    def rebuild_from_events(self, task_id: str) -> State:
        path = self._events(task_id)
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        for line in reversed(lines):
            try:
                state: State = json.loads(line)["state"]
                return state
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        message = f"{self._json(task_id)} is unreadable and has no events to rebuild it"
        raise FactoryError("state_corrupted", message, EXIT_ERROR)

    def create_claim(self, task_id: str, attempt: int) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self._claim(task_id), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError as exc:
            raise FactoryError("task_claimed", f"{task_id} is already claimed", EXIT_CONFLICT) from exc
        with os.fdopen(fd, "w") as file:
            json.dump({"attempt": attempt, "at": now()}, file)

    def read_claim(self, task_id: str) -> dict[str, Any] | None:
        try:
            claim: dict[str, Any] = json.loads(self._claim(task_id).read_text(encoding="utf-8"))
            return claim
        except FileNotFoundError:
            return None

    def release_claim(self, task_id: str) -> None:
        self._claim(task_id).unlink(missing_ok=True)

    def reassign_claim(self, task_id: str, attempt: int) -> None:
        """Give an existing claim to a new attempt (only `recover` does this)."""
        if not self._claim(task_id).exists():
            raise FactoryError("not_claimed", f"{task_id} has no claim to reassign", EXIT_PRECONDITION)
        self._atomic_write(self._claim(task_id), json.dumps({"attempt": attempt, "at": now()}))

    def _load(self, task_id: str) -> State:
        path = self._json(task_id)
        if not path.exists():
            return empty_state(task_id)
        try:
            state: State = json.loads(path.read_text(encoding="utf-8"))
            return state
        except json.JSONDecodeError:
            return self.rebuild_from_events(task_id)

    def _write_json(self, task_id: str, state: State) -> None:
        self._atomic_write(self._json(task_id), json.dumps(state, indent=2, ensure_ascii=False) + "\n")

    def _atomic_write(self, path: Path, text: str) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.root, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(text)
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _locked(self, task_id: str) -> _EventsLock:
        self.root.mkdir(parents=True, exist_ok=True)
        return _EventsLock(self._events(task_id))


class _EventsLock:
    """Exclusive flock on the append-only events file; yields it open for appending."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> Any:
        self.file = self.path.open("a", encoding="utf-8")
        fcntl.flock(self.file, fcntl.LOCK_EX)
        return self.file

    def __exit__(self, *exc: object) -> None:
        fcntl.flock(self.file, fcntl.LOCK_UN)
        self.file.close()
