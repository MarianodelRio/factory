"""`swfactory board`: a local, read-only kanban of the repository's changes and tasks, with what
runs in each task. A small HTTP server (standard library only, 127.0.0.1) serves one page that
polls `/api/board`; it runs in the background and stops by itself when nobody looks at it."""

from __future__ import annotations

import collections
import contextlib
import fcntl
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any

from swfactory import activity, config, design, orca, tasks
from swfactory.output import EXIT_CONFLICT, EXIT_ERROR, EXIT_UNAVAILABLE, FactoryError, mask_secrets
from swfactory.state import TaskStore, now

CACHE_SECONDS = 2.0
ACTIVITY_LIMIT = 40
START_TIMEOUT = 10.0
IDLE_CHECK_SECONDS = 15.0
DONE_STEP_SECONDS = 60.0  # a done task's next step (merged? PR?) costs git calls: reuse it this long
INFO_FILE = "board.json"
LOCK_FILE = "board.lock"
LOG_FILE = "board.log"
COLUMNS = ("needs_you", "backlog", "in_progress", "in_review", "done")


# --- What the page shows --------------------------------------------------------------------------


def collect(ctx: tasks.Context, home: Path) -> dict[str, Any]:
    """The whole board as JSON. Reads only: it never changes a task's state, not even to mark it
    interrupted (`/factory-status` does that)."""
    cfg = config.load_config(ctx.main_checkout / ".factory" / "config.toml")
    view = activity.orca_view()
    hooks = activity.orca_hooks(home)
    rows = []
    for task in tasks.catalog(ctx, sync=False).values():
        record = ctx.store.read_task(task["id"])
        working = record is not None and record["state"] in tasks.WORKING
        active = record is not None and record["state"] in tasks.ACTIVE
        live = activity.liveness(record, view) if working and record else None
        missing = activity.workspace_missing(record, view) if active and record else False
        done_step = _cached_done_step(ctx, task["id"]) if record and record["state"] == "done" else None
        row = tasks.task_row(task, record, live, missing, cfg, ctx, next_step=done_step)
        if record and record["state"] == "done" and done_step is None:
            _remember_done_step(ctx, task["id"], row["next_step"])
        row.update(_details(task, record))
        row["design_changed"] = active and not task["approved"]
        row["runs"] = activity.runs(tasks.workspace_path(record), record, view, hooks, home) if record else []
        row["column"] = _column(row)
        rows.append(row)

    changes = _changes(ctx, rows)
    counts = collections.Counter(row["column"] for row in rows)
    counts["needs_you"] += sum(1 for c in changes if c["state"] == "awaiting_approval")
    return {
        "repo": ctx.main_checkout.name,
        "path": str(ctx.main_checkout),
        "base": ctx.base(),
        "generated_at": now(),
        "sources": {"orca": "ok" if view["ok"] else "unavailable",
                    "hooks": "ok" if hooks["ok"] else "unavailable",
                    "claude": "ok" if (home / ".claude" / "projects").is_dir() else "unavailable",
                    "codex": "unverified" if (home / ".codex" / "sessions").is_dir() else "unavailable"},
        "orca_error": view["error"],
        "counts": {column: counts.get(column, 0) for column in COLUMNS},
        "changes": changes,
        "tasks": rows,
        "activity": _activity(ctx.store, rows, hooks),
    }


_done_steps: dict[str, tuple[float, float, str]] = {}


def _state_mtime(ctx: tasks.Context, task_id: str) -> float:
    try:
        return (ctx.store.root / f"{task_id}.json").stat().st_mtime
    except OSError:
        return 0.0


def _cached_done_step(ctx: tasks.Context, task_id: str) -> str | None:
    cached = _done_steps.get(task_id)
    fresh = cached and cached[0] == _state_mtime(ctx, task_id) and time.monotonic() - cached[1] < DONE_STEP_SECONDS
    return cached[2] if cached and fresh else None


def _remember_done_step(ctx: tasks.Context, task_id: str, step: str) -> None:
    _done_steps[task_id] = (_state_mtime(ctx, task_id), time.monotonic(), step)


def _column(row: dict[str, Any]) -> str:
    state = row["state"]
    if (state in ("blocked", "interrupted") or row["broken_link"] or row["liveness"] == "finished"
            or row["design_changed"]):
        return "needs_you"
    if state in ("pending", "ready"):
        return "backlog"
    return state if state in COLUMNS else "backlog"


def _details(task: dict[str, Any], record: dict[str, Any] | None) -> dict[str, Any]:
    record = record or {}
    stored = record.get("acceptance") or {}
    attempt = record["attempts"][-1] if record.get("attempts") else {}
    notes = record.get("notes") or []
    return {
        "criteria": [{"id": ac, "how": how, "status": (stored.get(ac) or {}).get("status", "pending"),
                      "evidence": (stored.get(ac) or {}).get("evidence")}
                     for ac, how in task["acceptance"].items()],
        "checks": (record.get("checks") or {}).get("status"),
        "review_details": [{"type": r["type"], "round": r["round"], "verdict": r["verdict"],
                            "reviewer": r.get("reviewer"), "commit": r["commit"][:8],
                            "findings": [{"severity": f.get("severity"), "file": f.get("file"),
                                          "problem": mask_secrets(str(f.get("problem", "")))}
                                         for f in r.get("findings", [])]}
                           for r in record.get("reviews", [])],
        "required_reviews": task.get("review", []),
        "complexity": task.get("complexity"),
        "model": attempt.get("model"),
        "attempts": len(record.get("attempts") or []),
        "started_at": attempt.get("started_at"),
        "notes": [{"at": n["at"], "text": n["text"], "pause": n.get("pause", False), "read": n["read"]}
                  for n in notes[-5:]],
        "unread_notes": sum(1 for n in notes if not n["read"]),
    }


def _changes(ctx: tasks.Context, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    awaiting = set(tasks.awaiting_approval(ctx))
    found = []
    for folder in sorted(ctx.changes_dir.glob("CHG-*")):
        path = folder / "design.md"
        if not path.exists():
            continue
        match = design.TITLE.search(design.normalize(path.read_text(encoding="utf-8")))
        own = [r for r in rows if r["change"] == folder.name]
        if (folder / "rejection.json").exists():
            state = "rejected"
        elif folder.name in awaiting:
            state = "awaiting_approval"
        elif own and all(r["state"] == "done" for r in own):
            state = "done"
        else:
            state = "approved"
        found.append({"id": folder.name, "title": match.group(1).strip() if match else folder.name,
                      "state": state, "tasks": len(own)})
    return found


def _event_text(name: str, state: dict[str, Any]) -> str | None:
    attempt = state["attempts"][-1] if state.get("attempts") else {}
    checkpoint = state.get("last_checkpoint") or {}
    notes = state.get("notes") or []
    reviews = state.get("reviews") or []
    acceptance = state.get("acceptance") or {}
    texts = {
        "claim": "claimed; Orca workspace created",
        "launched": f"lead {attempt.get('agent')} launched"
                    + (f", reviewer {attempt['reviewer']}" if attempt.get("reviewer") else ""),
        "checkpoint": (checkpoint.get("done") or [""])[0],
        "note": (("pause: " if notes and notes[-1].get("pause") else "note: ") + notes[-1]["text"]) if notes else None,
        "verify": f"verified {sum(1 for a in acceptance.values() if a.get('status') == 'verified')}"
                  f"/{len(acceptance)} AC, checks {(state.get('checks') or {}).get('status')}",
        "verify_manual": "manual evidence recorded",
        "submit": "submitted for review",
        "review": (f"{reviews[-1]['type']} review round {reviews[-1]['round']}: {reviews[-1]['verdict']}"
                   if reviews else None),
        "finish": "done",
        "publish": "branch pushed" + (f", PR #{state['pull_request']['number']}" if state.get("pull_request") else ""),
        "interrupted": "interrupted: the lead's terminal is closed",
        "recover": f"recovered: attempt {attempt.get('id')}",
        "design_changed": "blocked: the design changed",
        "unblock": "unblocked",
        "launch_failed": "launch failed",
    }
    return texts.get(name)


_events_cache: dict[Path, tuple[float, int, list[dict[str, Any]]]] = {}


def _task_events(path: Path) -> list[dict[str, Any]]:
    """The last events of one task as feed items, cached while its log does not change."""
    try:
        stat = path.stat()
        cached = _events_cache.get(path)
        if cached and cached[:2] == (stat.st_mtime, stat.st_size):
            return cached[2]
        with path.open(encoding="utf-8") as handle:
            lines = collections.deque(handle, maxlen=ACTIVITY_LIMIT)
    except OSError:
        return []
    task, items = path.name.removesuffix(".events.jsonl"), []
    for line in lines:
        try:
            event = json.loads(line)
            at, text = event["at"], _event_text(event["event"], event["state"])
        except (ValueError, KeyError, TypeError, IndexError, AttributeError):
            continue
        if text and isinstance(at, str):
            items.append({"at": at, "task": task, "event": event["event"], "text": mask_secrets(text)})
    _events_cache[path] = (stat.st_mtime, stat.st_size, items)
    return items


def _activity(store: TaskStore, rows: list[dict[str, Any]], hooks: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(store.root.glob("*.events.jsonl")):
        items += _task_events(path)
    by_workspace = {r["workspace"].split("::", 1)[1]: r["id"] for r in rows if r.get("workspace")}
    for event in hooks["subagents"]:
        owner = by_workspace.get(event["cwd"] or "")
        if owner and event["at"]:
            verb = "started" if event["event"] == "SubagentStart" else "finished"
            items.append({"at": event["at"], "task": owner, "event": "subagent",
                          "text": f"{event['provider'] or 'agent'} subagent {event['type'] or ''} {verb}".strip()})
    # Newest first; events of the same second keep the order they were written in.
    order = {id(item): n for n, item in enumerate(items)}
    return sorted(items, key=lambda i: (i["at"], order[id(i)]), reverse=True)[:ACTIVITY_LIMIT]


def page(data: dict[str, Any] | None = None) -> str:
    """The board page; with `data` the board is embedded (a snapshot) and does not poll."""
    html = resources.files("swfactory").joinpath("templates/board/board.html").read_text(encoding="utf-8")
    embedded = "null"
    if data is not None:  # safe inside <script>: no "<", ">" or "&" can end it or start a comment
        embedded = json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return html.replace("__BOARD_DATA__", embedded)


def snapshot(ctx: tasks.Context, home: Path, out: Path) -> dict[str, Any]:
    out.write_text(page(collect(ctx, home)), encoding="utf-8")
    return {"snapshot": str(out)}


# --- The server -----------------------------------------------------------------------------------


class _Server(ThreadingHTTPServer):
    daemon_threads = True


def serve(main_checkout: Path, state_dir: Path, port: int, idle_minutes: float, home: Path) -> None:
    """Serve the board in the foreground until stopped or idle for `idle_minutes`."""
    other = running(main_checkout, state_dir)
    if other and other.get("pid") != os.getpid():
        raise FactoryError("board_running", f"a board is already running at {other['url']}", EXIT_CONFLICT)
    lock = threading.Lock()
    cache: dict[str, Any] = {"at": 0.0, "body": b""}
    last_seen = [time.monotonic()]

    def board_body() -> bytes:
        with lock:
            if time.monotonic() - cache["at"] > CACHE_SECONDS:
                ctx = tasks.Context(main_checkout, TaskStore(state_dir))  # fresh: Orca may have recovered
                cache["body"] = json.dumps(collect(ctx, home)).encode("utf-8")
                cache["at"] = time.monotonic()
            return bytes(cache["body"])

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            bound = self.server.server_port  # type: ignore[attr-defined]
            if self.headers.get("Host") not in (f"127.0.0.1:{bound}", f"localhost:{bound}"):
                return self._send(403, "text/plain", b"forbidden")  # another site through DNS rebinding
            path = self.path.split("?", 1)[0]
            if path == "/health":
                health = {"factory_board": True, "pid": os.getpid(), "repo": str(main_checkout)}
                return self._send(200, "application/json", json.dumps(health).encode("utf-8"))
            last_seen[0] = time.monotonic()
            if path == "/":
                return self._send(200, "text/html; charset=utf-8", page().encode("utf-8"))
            if path == "/api/board":
                try:
                    return self._send(200, "application/json", board_body())
                except Exception as exc:  # the page shows it and keeps polling
                    error = {"error": f"{type(exc).__name__}: {exc}"}
                    return self._send(500, "application/json", json.dumps(error).encode("utf-8"))
            self._send(404, "text/plain", b"not found")

        def _send(self, status: int, kind: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    try:
        server = _Server(("127.0.0.1", port), Handler)
    except OSError as exc:
        raise FactoryError("board_port_busy", f"cannot listen on 127.0.0.1:{port}: {exc}", EXIT_UNAVAILABLE) from exc
    bound = server.server_address[1]
    info_path = state_dir / INFO_FILE
    info_path.write_text(json.dumps({"pid": os.getpid(), "port": bound, "url": f"http://127.0.0.1:{bound}/",
                                     "started_at": now(), "repo": str(main_checkout)}) + "\n")
    stopped = threading.Event()

    def stop(*_: Any) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    def watch_idle() -> None:
        while not stopped.wait(IDLE_CHECK_SECONDS):
            if time.monotonic() - last_seen[0] > idle_minutes * 60:
                stop()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, stop)
    threading.Thread(target=watch_idle, daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stopped.set()
        server.server_close()
        if _read_info(state_dir).get("pid") == os.getpid():
            info_path.unlink(missing_ok=True)


# --- Background process: start, status, stop, open ------------------------------------------------


def _read_info(state_dir: Path) -> dict[str, Any]:
    try:
        info = json.loads((state_dir / INFO_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return info if isinstance(info, dict) else {}


def _health(info: dict[str, Any]) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{int(info['port'])}/health", timeout=2) as reply:
            health = json.loads(reply.read())
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return health if isinstance(health, dict) and health.get("factory_board") else None


def _is_board_process(pid: Any) -> bool:
    """True if `pid` is alive and, where the system says it, runs `swfactory board serve`."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return True  # no /proc (macOS): an alive pid is the best evidence there is
    return b"factory" in command and b"board\x00serve" in command


def running(main_checkout: Path, state_dir: Path) -> dict[str, Any] | None:
    """The board serving this repository and answering, or None. The info file is removed only
    when its process is gone."""
    info = _read_info(state_dir)
    if not info:
        return None
    health = _health(info)
    if health and health.get("pid") == info.get("pid") and health.get("repo") == str(main_checkout):
        return info
    if not _is_board_process(info.get("pid")):
        (state_dir / INFO_FILE).unlink(missing_ok=True)
    return None


@contextlib.contextmanager
def _start_lock(state_dir: Path) -> Iterator[None]:
    """One `start` at a time, so two quick `board open` never launch two servers."""
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / LOCK_FILE).open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _free_port(preferred: int) -> int:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            return 0  # the server picks a free one


def _wait_healthy(state_dir: Path, pid: int | None, deadline: float) -> dict[str, Any] | None:
    while time.monotonic() < deadline:
        info = _read_info(state_dir)
        if info and (pid is None or info.get("pid") == pid) and _health(info):
            return info
        time.sleep(0.1)
    return None


def start(main_checkout: Path, state_dir: Path, port: int | None) -> dict[str, Any]:
    """Start the board in the background, or return the one already running."""
    with _start_lock(state_dir):
        current = running(main_checkout, state_dir)
        if current:
            return {**current, "running": True, "started": False}
        slow = _read_info(state_dir)
        if slow:  # its process is alive but did not answer: give it a moment before giving up
            current = _wait_healthy(state_dir, slow.get("pid"), time.monotonic() + START_TIMEOUT)
            if current:
                return {**current, "running": True, "started": False}
            message = f"a board process ({slow.get('pid')}) is not answering: stop it or remove {state_dir / INFO_FILE}"
            raise FactoryError("board_unresponsive", message, EXIT_ERROR)
        cfg = config.load_config(main_checkout / ".factory" / "config.toml")
        chosen = _free_port(port or cfg["board"]["port"])
        with (state_dir / LOG_FILE).open("a", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "swfactory", "board", "serve", "--port", str(chosen)],
                cwd=main_checkout, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline and process.poll() is None:
            info = _wait_healthy(state_dir, process.pid, min(deadline, time.monotonic() + 0.5))
            if info:
                return {**info, "running": True, "started": True}
        if process.poll() is None:
            process.terminate()
    raise FactoryError("board_not_started", f"the board did not start; see {state_dir / LOG_FILE}", EXIT_ERROR)


def status(main_checkout: Path, state_dir: Path) -> dict[str, Any]:
    current = running(main_checkout, state_dir)
    return {**current, "running": True} if current else {"running": False}


def stop(main_checkout: Path, state_dir: Path) -> dict[str, Any]:
    """Stop this repository's board: only a process that answers as it, or runs `board serve`."""
    info = running(main_checkout, state_dir) or _read_info(state_dir)
    pid = info.get("pid")
    if not info or not (_health(info) or _is_board_process(pid)):
        (state_dir / INFO_FILE).unlink(missing_ok=True)
        return {"running": False, "stopped": False}
    assert isinstance(pid, int)
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _is_board_process(pid):
        time.sleep(0.1)
    if _is_board_process(pid):
        os.kill(pid, signal.SIGKILL)
    (state_dir / INFO_FILE).unlink(missing_ok=True)
    return {"running": False, "stopped": True, "pid": pid}


def open_board(main_checkout: Path, state_dir: Path, port: int | None) -> tuple[dict[str, Any], list[str]]:
    """Start the board if needed and open it in an Orca browser tab, or else in the system browser."""
    info = start(main_checkout, state_dir, port)
    warnings: list[str] = []
    opened: str | None
    try:
        orca.run(["tab", "create", "--url", info["url"], "--worktree", f"path:{main_checkout}"])
        opened = "orca"
    except FactoryError as exc:
        warnings.append(f"could not open an Orca tab ({exc.message}); opening the system browser")
        opened = "browser" if webbrowser.open(info["url"]) else None
    return {**info, "opened_in": opened}, warnings
