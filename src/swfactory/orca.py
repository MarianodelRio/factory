"""The only module that runs `orca`. Always with `--json` and argument lists.

Raises FactoryError (all EXIT_UNAVAILABLE) with these codes:
- orca_unavailable: `orca` is not installed or not on PATH.
- orca_failed: Orca answered with an error or with something that is not JSON (OrcaError, with
  Orca's own code in `orca_code`).
- orca_outdated: the Orca version is below `[orca] min_version`.
- orca_not_running: the Orca runtime cannot be reached.
- orca_not_local: a remote Orca was selected.
- orca_missing_command: a command or flag the Factory uses is not in `orca agent-context`.
- orca_repo_not_registered / orca_base_branch_unset: no base branch can be read for the repo.
- effort_needs_model (EXIT_USAGE): `--effort` was given without `--model`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from swfactory import system
from swfactory.output import EXIT_UNAVAILABLE, EXIT_USAGE, FactoryError, mask_secrets

TIMEOUT = 120

# Commands and flags the CLI uses; `check` verifies them against `orca agent-context`.
REQUIRED: dict[str, tuple[str, ...]] = {
    "status": (),
    "agent-context": (),
    "repo show": ("repo",),
    "worktree create": ("repo", "name", "base-branch", "no-parent"),
    "worktree show": ("worktree",),
    "worktree set": ("worktree", "display-name", "comment", "workspace-status", "unread", "read"),
    "agent launch": ("agent", "worktree", "prompt", "model", "effort", "retry-launch"),
    "terminal show": ("terminal",),
}
REMOTE_VARIABLES = ("ORCA_PAIRING_CODE", "ORCA_ENVIRONMENT")


class OrcaError(FactoryError):
    def __init__(
        self, message: str, orca_code: str | None = None, error: dict[str, Any] | None = None
    ) -> None:
        super().__init__("orca_failed", message, EXIT_UNAVAILABLE)
        self.orca_code = orca_code
        self.error = error or {}


def unavailable(code: str, message: str) -> FactoryError:
    return FactoryError(code, message, EXIT_UNAVAILABLE)


def _exec(args: list[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
    command = system.tool_command("orca", "SWFACTORY_ORCA")
    system.check_batch_arguments(command, args)
    try:
        return subprocess.run([*command, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=TIMEOUT)
    except FileNotFoundError as exc:
        message = "Orca is not installed or `orca` is not on PATH (or set SWFACTORY_ORCA)"
        raise unavailable("orca_unavailable", message) from exc
    except subprocess.TimeoutExpired as exc:
        raise OrcaError(f"orca {' '.join(args)} did not answer in {TIMEOUT}s") from exc


def run(args: list[str], cwd: Path | None = None) -> Any:
    """Run `orca <args> --json` against the local Orca and return its `result` (or the whole
    answer if it has none)."""
    require_local()
    done = _exec([*args, "--json"], cwd)
    command = " ".join(args[:2])
    try:
        answer = json.loads(done.stdout)
    except json.JSONDecodeError as exc:
        detail = (done.stderr or done.stdout).strip()[:300]
        raise OrcaError(f"orca {command} did not answer JSON: {detail}") from exc
    if not isinstance(answer, dict):
        raise OrcaError(f"orca {command} answered an unexpected value")
    if answer.get("ok") is False or done.returncode != 0:
        error = answer.get("error") or {}
        code = error.get("code")
        detail = error.get("message") or code or done.stderr.strip()
        raise OrcaError(f"orca {command} failed: {detail}", code, error)
    return answer.get("result", answer)


def run_plain(args: list[str], cwd: Path | None = None) -> str:
    """Run an `orca` command that must not get `--json` (e.g. `skills install`)."""
    require_local()
    done = _exec(args, cwd)
    if done.returncode != 0:
        raise OrcaError(f"orca {' '.join(args[:2])} failed: {(done.stderr or done.stdout).strip()[:300]}")
    return done.stdout.strip()


def version() -> str:
    done = _exec(["--version"], None)
    if done.returncode != 0:
        raise OrcaError(f"orca --version failed: {done.stderr.strip()}")
    return done.stdout.strip()


def _version_tuple(text: str) -> tuple[int, ...]:
    parts = [int(part) for part in re.findall(r"\d+", text)[:3]]
    return tuple(parts + [0] * (3 - len(parts)))


def check(min_version: str) -> dict[str, Any]:
    """Orca is installed, recent enough, running, local and has every command the CLI uses."""
    require_local()

    installed = version()
    if _version_tuple(installed) < _version_tuple(min_version):
        raise unavailable("orca_outdated", f"Orca {installed} is older than the required {min_version}")

    try:
        status = run(["status"])
    except OrcaError as exc:
        raise unavailable("orca_not_running", f"Orca is not running: {exc.message}. Open Orca.") from exc
    try:
        reachable = status["runtime"]["reachable"]
        local = status["target"]["kind"] == "local"
        context = run(["agent-context"])["commands"]
        commands = {c["command"]: set(c.get("flags", [])) for c in context}
    except (KeyError, TypeError, AttributeError) as exc:
        raise OrcaError(f"Orca answered in an unexpected format ({exc!r})") from exc
    if not reachable:
        raise unavailable("orca_not_running", "the Orca runtime is not reachable. Open Orca.")
    if not local:
        raise unavailable("orca_not_local", "Orca reports a host that is not local")

    for command, flags in REQUIRED.items():
        if command not in commands:
            raise unavailable("orca_missing_command", f"this Orca has no `orca {command}` command")
        missing = [f for f in flags if f not in commands[command]]
        if missing:
            flags_text = ", ".join(f"--{f}" for f in missing)
            raise unavailable("orca_missing_command", f"`orca {command}` lacks {flags_text}")
    return {"version": installed, "local": True}


def require_local() -> None:
    """Refuse a remote Orca selected through the environment."""
    for variable in REMOTE_VARIABLES:
        if os.environ.get(variable):
            raise unavailable("orca_not_local", f"{variable} is set: the Factory only works with local Orca")


def base_branch(main_checkout: Path) -> str:
    """The repo's base branch in Orca (`worktreeBaseRef`, set by `/factory-init`)."""
    try:
        repo = run(["repo", "show", "--repo", f"path:{main_checkout}"])["repo"]
    except OrcaError as exc:
        if exc.orca_code == "repo_not_found":
            message = f"{main_checkout} is not registered in Orca; run /factory-init"
            raise unavailable("orca_repo_not_registered", message) from exc
        raise
    ref = repo.get("worktreeBaseRef")
    if not ref:
        message = (
            "the repo has no base branch in Orca; run /factory-init or "
            f"`orca repo set-base-ref --repo path:{main_checkout} --ref origin/<branch>`"
        )
        raise unavailable("orca_base_branch_unset", message)
    return _branch_name(str(ref))


def _branch_name(ref: str) -> str:
    for pattern in (r"^refs/remotes/[^/]+/", r"^refs/heads/", r"^origin/"):
        ref = re.sub(pattern, "", ref)
    return ref


def create_workspace(name: str, base: str, main_checkout: Path) -> dict[str, str]:
    """A new Orca workspace (Git worktree with its own branch) from `base`."""
    created = run(
        ["worktree", "create", "--repo", f"path:{main_checkout}", "--name", name, "--base-branch", base,
         "--no-parent"]
    )["worktree"]
    branch = str(created["branch"]).removeprefix("refs/heads/")
    return {"id": created["id"], "path": created["path"], "branch": branch}


def link_pull_request(workspace_id: str, number: int) -> list[str]:
    """Show the pull request on the workspace's card; a failure is only a warning."""
    try:
        run(["worktree", "set", "--worktree", f"id:{workspace_id}", "--pr", str(number)])
    except FactoryError as exc:
        return [f"the Orca card was not linked to PR #{number}: {exc.message}"]
    return []


def remove_workspace(workspace_id: str) -> None:
    """Remove a workspace (its worktree folder) from Orca; never forced."""
    run(["worktree", "rm", "--worktree", f"id:{workspace_id}"])


def workspace_exists(workspace_id: str) -> bool:
    try:
        run(["worktree", "show", "--worktree", f"id:{workspace_id}"])
    except OrcaError as exc:
        if exc.orca_code == "selector_not_found":
            return False
        raise
    return True


def launch_agent(
    workspace_id: str, agent: str, prompt: str, model: str | None, effort: str | None
) -> dict[str, str | None]:
    """Start `agent` in the workspace. If Orca's reply is lost, the same operation is re-issued
    once with `--retry-launch <operationId>`; it is never launched again as a new agent."""
    if effort and not model:
        raise FactoryError("effort_needs_model", "--effort requires --model", EXIT_USAGE)
    args = ["agent", "launch", "--agent", agent, "--worktree", f"id:{workspace_id}", "--prompt", prompt]
    if model:
        args += ["--model", model]
    if effort:
        args += ["--effort", effort]
    operation_id = None
    try:
        result = run(args)
    except OrcaError as exc:
        operation_id = _operation_id(exc)
        if operation_id is None:
            raise
        result = run([*args, "--retry-launch", operation_id])
    outcome = result.get("outcome", {})
    return {
        "operation_id": result.get("operationId") or operation_id,
        "terminal": outcome.get("handle") or None,
        "kind": outcome.get("kind", "terminal"),
    }


def _operation_id(exc: OrcaError) -> str | None:
    """The operationId Orca gives in a lost-launch error, if any. The exact error shape was not
    recorded in the spike, so the id is looked for in the error fields and in its message."""
    data = exc.error.get("data") or {}
    found = exc.error.get("operationId") or (data.get("operationId") if isinstance(data, dict) else None)
    if found:
        return str(found)
    match = re.search(r"--retry-launch\s+(\S+)", str(exc.error.get("message", "")))
    return match.group(1) if match else None


def session_liveness(terminal: str | None) -> str:
    """`alive` if the agent's terminal is connected, `finished` if it is closed or gone, `unknown`
    when Orca cannot say. An agent that exited inside an open terminal looks alive."""
    if not terminal:
        return "unknown"
    try:
        shown = run(["terminal", "show", "--terminal", terminal])["terminal"]
    except OrcaError as exc:
        return "finished" if exc.orca_code == "terminal_handle_stale" else "unknown"
    except (FactoryError, KeyError, TypeError):
        return "unknown"
    return "alive" if shown.get("connected") else "finished"


# Task state -> (card status, fixed comment or None to use the detail, unread notice).
# "No notice" leaves Orca's unread flag as it is.
CARDS: dict[str, tuple[str, str | None, bool]] = {
    "in_progress": ("in-progress", None, False),  # detail: next action
    "in_review": ("in-review", None, False),  # detail: pending reviews
    "to_merge": ("in-review", None, False),  # detail: done_comment()
    "done": ("completed", None, False),  # detail: done_comment()
    "blocked": ("in-progress", None, True),  # detail: reason for the block
    "interrupted": ("in-progress", "Interrupted: use /factory-status", True),
}


def done_comment(verified: int, total: int, pr_number: int | None, merged: bool = False) -> str:
    text = f"{verified}/{total} AC verified" + (f" · PR #{pr_number}" if pr_number else "")
    return f"{text} · merged" if merged else f"{text} · to merge"


def update_card(workspace_id: str, task_id: str, title: str, state: str, detail: str | None) -> list[str]:
    """Update the workspace card for the task's state. Never raises: a failure only gives a
    warning, and if Orca refuses some value the comment alone is updated."""
    status, fixed, unread = CARDS[state]
    comment = mask_secrets(fixed or detail or "")
    selector = ["worktree", "set", "--worktree", f"id:{workspace_id}"]
    shown = task_id.removeprefix("CHG-") if "." in task_id else task_id  # `12.1`; ids before 1.2 in full
    full = [*selector, "--display-name", f"{shown} · {title}", "--workspace-status", status,
            "--comment", comment, *(["--unread"] if unread else [])]
    try:
        result = run(full)
        return [str(w.get("message", w)) for w in result.get("warnings", [])]
    except OrcaError as exc:
        first = exc.message
    except FactoryError as exc:
        return [f"the Orca card was not updated: {exc.message}"]
    try:
        run([*selector, "--comment", comment])
        return [f"the Orca card only got its comment ({first})"]
    except FactoryError as exc:
        return [f"the Orca card was not updated: {exc.message}"]
