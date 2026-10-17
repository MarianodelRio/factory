"""Task lifecycle (design §1.5, §5, §7).

Raises FactoryError with these codes:
- invalid_transition (EXIT_PRECONDITION): the action is not allowed from the task's state.
- task_not_found (EXIT_PRECONDITION): no approved change has a task with that id.
- task_not_ready (EXIT_PRECONDITION): claim of a task that is not `ready` (the reason is given).
- approval_not_on_base (EXIT_PRECONDITION): the approval commit is not on the base branch.
- task_claimed (EXIT_CONFLICT): the task is already claimed (from factory.state).
- already_launched (EXIT_CONFLICT): the current attempt already has a lead agent, or a launch
  whose result is unknown.
- launch_unconfirmed (EXIT_UNAVAILABLE): Orca did not answer a launch; an agent may have started.
- task_not_started (EXIT_PRECONDITION): the task has no state yet (it was never claimed).
- approval_not_valid (EXIT_PRECONDITION): unblock while the change's approval is not valid.
Plus the codes of factory.orca (Orca unavailable, not local, ...).
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

import yaml

from factory import config, design, git, orca
from factory.output import EXIT_CONFLICT, EXIT_PRECONDITION, EXIT_UNAVAILABLE, FactoryError
from factory.state import State, TaskStore, now

# Reasons for `blocked` that the CLI sets itself; any other text comes from `task block --reason`.
PAUSED = "paused"
DESIGN_CHANGED = "design_changed"
REVIEW_NOT_CONVERGING = "review_not_converging"

# (state, action) -> next state, design §1.5. `block` records the previous state in
# `blocked_from`; `unblock` and `reapprove` return to it. The callers check the conditions
# that are not about states: a valid approval for `unblock`, liveness for `recover`.
TRANSITIONS: dict[tuple[str, str], str] = {
    ("ready", "claim"): "in_progress",  # factory task claim
    ("interrupted", "recover"): "in_progress",  # factory task recover --confirm
    ("in_progress", "recover"): "in_progress",  # only when liveness is unknown (§7.4)
    ("in_progress", "submit"): "in_review",  # factory task submit
    ("in_progress", "finish"): "done",  # factory task finish (gates of §5.7)
    ("in_review", "finish"): "done",
    ("in_progress", "block"): "blocked",  # task block, a read pause note, a design change
    ("in_review", "block"): "blocked",  # also a review that does not converge
    ("interrupted", "block"): "blocked",  # a design change
    ("in_progress", "interrupt"): "interrupted",  # status/recover: the lead agent finished
}
RETURNS = {"unblock", "reapprove"}
# States that a design change blocks (design §4.5).
BLOCKED_BY_DESIGN_CHANGE = ("in_progress", "in_review", "interrupted")


def transition(task: State, action: str, current: str | None = None, reason: str | None = None) -> State:
    """Return a copy of `task` after `action`. `current` is the computed state (`pending` or
    `ready`) of a task that has no stored state yet; a stored state always wins."""
    state: str = task["state"] or current or ""
    result = copy.deepcopy(task)

    if action in RETURNS and state == "blocked":
        if action == "reapprove" and task["blocked_reason"] != DESIGN_CHANGED:
            _reject(task, action, f"it is blocked for '{task['blocked_reason']}', not by a design change")
        result.update(state=task["blocked_from"], blocked_reason=None, blocked_from=None)
        return result

    target = TRANSITIONS.get((state, action))
    if target is None:
        _reject(task, action, f"not allowed from '{state}'")
    if action == "block":
        if not reason:
            _reject(task, action, "a reason is required")
        result.update(blocked_reason=reason, blocked_from=state)
    result["state"] = target
    return result


def _reject(task: State, action: str, why: str) -> NoReturn:
    message = f"cannot {action} {task['task']}: {why}"
    raise FactoryError("invalid_transition", message, EXIT_PRECONDITION)


def sync_with_design(task_ids: list[str], approved: bool, store: TaskStore) -> None:
    """Apply design §4.5 to the approved tasks of a change: while the design does not match its
    approval, tasks in progress are blocked (`design_changed`); once it matches again (re-approval
    or a reverted edit), those tasks return to their previous state. `done` tasks are not touched."""
    for task_id in task_ids:
        stored = store.read_task(task_id)
        if stored is None:
            continue
        if not approved and stored["state"] in BLOCKED_BY_DESIGN_CHANGE:
            block = _if_state(BLOCKED_BY_DESIGN_CHANGE, "block", DESIGN_CHANGED)
            store.update_task(task_id, block, "design_changed")
        elif approved and stored["state"] == "blocked" and stored["blocked_reason"] == DESIGN_CHANGED:
            store.update_task(task_id, _if_state(("blocked",), "reapprove", None), "reapproved")


def _if_state(states: tuple[str, ...], action: str, reason: str | None) -> Callable[[State], State]:
    """A transition applied inside the task lock only if the state is still one of `states`."""

    def apply(task: State) -> State:
        if task["state"] not in states:
            return task
        if action == "reapprove" and task["blocked_reason"] != DESIGN_CHANGED:
            return task
        return transition(task, action, reason=reason)

    return apply


class Context:
    """What computing task states needs: the main checkout (owner of the approved changes and the
    shared state) and the base branch, read from Orca once and only when a dependency needs it."""

    def __init__(self, main_checkout: Path, store: TaskStore) -> None:
        self.main_checkout = main_checkout
        self.changes_dir = main_checkout / ".factory" / "changes"
        self.store = store
        self._base: str | None = None
        self._base_error: str | None = None

    def base(self) -> str | None:
        if self._base is None and self._base_error is None:
            try:
                self._base = orca.base_branch(self.main_checkout)
            except FactoryError as exc:
                self._base_error = exc.message
        return self._base

    def base_error(self) -> str:
        return self._base_error or ""


def catalog(ctx: Context) -> dict[str, dict[str, Any]]:
    """Every task of every approved, not rejected change: id -> task definition plus `change`
    and whether the change's approval is still valid. Applies §4.5 to each change first."""
    tasks: dict[str, dict[str, Any]] = {}
    for tasks_file in sorted(ctx.changes_dir.glob("CHG-*/tasks.yaml")):
        folder = tasks_file.parent
        if (folder / "rejection.json").exists():
            continue
        design.sync_with_main(folder.name, ctx.changes_dir, ctx.store)
        approval = design.approval_of(folder)
        current = design.digest((folder / "design.md").read_text(encoding="utf-8"))
        approved = approval is not None and approval.get("design_digest") == current
        data = yaml.safe_load(tasks_file.read_text(encoding="utf-8")) or {}
        for task in data.get("tasks", []):
            tasks[str(task["id"])] = {**task, "change": folder.name, "approved": approved}
    return tasks


def view(task: dict[str, Any], ctx: Context) -> dict[str, Any]:
    """The task with its state and the reason it is not ready (design §1.5, §5.1)."""
    record = ctx.store.read_task(task["id"])
    state, reason = (record["state"], record.get("blocked_reason")) if record else _computed(task, ctx)
    workspace = (record or {}).get("workspace") or {}
    return {
        "id": task["id"],
        "title": task["title"],
        "change": task["change"],
        "state": state,
        "reason": reason,
        "depends_on": task.get("depends_on", []),
        "workspace": workspace.get("orca_id"),
        "branch": workspace.get("branch"),
    }


def _computed(task: dict[str, Any], ctx: Context) -> tuple[str, str | None]:
    """`pending` or `ready` for a task without a state file: approval valid and every dependency
    `done` and merged into the base branch."""
    if not task["approved"]:
        return "pending", f"{task['change']} is awaiting approval"
    for dep in task.get("depends_on", []):
        record = ctx.store.read_task(dep)
        if record is None or record["state"] != "done":
            return "pending", f"waiting for {dep} to be done"
        base = ctx.base()
        if base is None:
            return "pending", f"cannot check that {dep} is merged: {ctx.base_error()}"
        if not _merged(record, base, ctx.main_checkout):
            return "pending", f"waiting for {dep} to be merged into {base}"
    return "ready", None


def _merged(record: State, base: str, cwd: Path) -> bool:
    branch = (record.get("workspace") or {}).get("branch")
    tip = branch if branch and git.ref_exists(branch, cwd) else (record.get("commits") or [None])[-1]
    if not tip:
        return False
    targets = [ref for ref in (base, f"origin/{base}") if git.ref_exists(ref, cwd)]
    return any(git.is_ancestor(tip, ref, cwd) for ref in targets)


def list_tasks(ctx: Context) -> dict[str, Any]:
    all_tasks = catalog(ctx)
    return {"tasks": [view(task, ctx) for task in all_tasks.values()]}


def _task(task_id: str, ctx: Context) -> dict[str, Any]:
    all_tasks = catalog(ctx)
    if task_id not in all_tasks:
        raise FactoryError("task_not_found", f"no approved change has a task {task_id}", EXIT_PRECONDITION)
    return all_tasks[task_id]


def show_task(task_id: str, ctx: Context) -> dict[str, Any]:
    task = _task(task_id, ctx)
    shown = view(task, ctx)
    definition = {k: v for k, v in task.items() if k not in ("change", "approved")}
    return {**definition, **shown, "record": ctx.store.read_task(task_id)}


def new_attempt(number: int) -> dict[str, Any]:
    return {
        "id": number,
        "agent": None,
        "reviewer": None,
        "model": None,
        "operation_id": None,
        "terminal": None,
        "started_at": now(),
        "ended_at": None,
        "result": None,
    }


def claim(task_id: str, ctx: Context) -> tuple[dict[str, Any], list[str]]:
    """Claim a ready task and create its Orca workspace from the base branch (design §5.1)."""
    task = _task(task_id, ctx)
    if ctx.store.read_claim(task_id) is not None:
        raise FactoryError("task_claimed", f"{task_id} is already claimed", EXIT_CONFLICT)
    shown = view(task, ctx)
    if shown["state"] != "ready":
        raise FactoryError("task_not_ready", f"{task_id} is {shown['state']}: {shown['reason']}", EXIT_PRECONDITION)
    orca.check(_min_version(ctx))
    base = orca.base_branch(ctx.main_checkout)
    _require_approval_on_base(task["change"], base, ctx)

    ctx.store.create_claim(task_id, 1)
    try:
        workspace = orca.create_workspace(task_id, base, ctx.main_checkout)
    except FactoryError:
        ctx.store.release_claim(task_id)
        raise

    def start(state: State) -> State:
        state = transition(state, "claim", current="ready")
        state["workspace"] = {"orca_id": workspace["id"], "branch": workspace["branch"]}
        state["attempts"] = [new_attempt(1)]
        return state

    ctx.store.update_task(task_id, start, "claim")
    next_action = f"launch the lead agent (factory task launch {task_id})"
    warnings = orca.update_card(workspace["id"], task_id, task["title"], "in_progress", next_action)
    data = {"task": task_id, "state": "in_progress", "workspace": workspace["id"], "path": workspace["path"],
            "branch": workspace["branch"], "attempt": 1}
    return data, warnings


def launch(
    task_id: str, agent: str, reviewer: str | None, model: str | None, effort: str | None, ctx: Context
) -> tuple[dict[str, Any], list[str]]:
    """Open the lead agent in the task's workspace with the brief `/factory-implement <id>`."""
    task = _task(task_id, ctx)
    record = ctx.store.read_task(task_id)
    if record is None or record["state"] != "in_progress":
        state = record["state"] if record else view(task, ctx)["state"]
        _reject({"task": task_id}, "launch", f"it is {state}; claim it first")
    if record["attempts"][-1]["agent"] is not None:
        message = f"attempt {record['attempts'][-1]['id']} of {task_id} already has a lead agent"
        raise FactoryError("already_launched", message, EXIT_CONFLICT)
    if effort and not model:
        raise FactoryError("effort_needs_model", "--effort requires --model", 2)
    orca.check(_min_version(ctx))

    _set_attempt(ctx, task_id, {"agent": agent, "reviewer": reviewer, "model": model}, "launch")
    prompt = f"/factory-implement {task_id}" + (f" --reviewer {reviewer}" if reviewer else "")
    workspace_id = record["workspace"]["orca_id"]
    try:
        launched = orca.launch_agent(workspace_id, agent, prompt, model, effort)
    except orca.OrcaError as exc:
        if exc.orca_code is None:
            message = (f"Orca did not confirm the launch ({exc.message}); an agent may have started. "
                       f"Check the workspace in Orca; if no agent is there, use factory task recover {task_id}")
            raise FactoryError("launch_unconfirmed", message, EXIT_UNAVAILABLE) from exc
        _set_attempt(ctx, task_id, {"agent": None, "reviewer": None, "model": None}, "launch_failed")
        raise
    except FactoryError:
        _set_attempt(ctx, task_id, {"agent": None, "reviewer": None, "model": None}, "launch_failed")
        raise
    _set_attempt(ctx, task_id, {"operation_id": launched["operation_id"], "terminal": launched["terminal"]},
                 "launched")
    warnings = orca.update_card(workspace_id, task_id, task["title"], "in_progress", f"lead agent {agent} working")
    data = {"task": task_id, "agent": agent, "reviewer": reviewer, "model": model,
            "operation_id": launched["operation_id"], "terminal": launched["terminal"],
            "message": f"{task_id} launched; open it from the Orca sidebar"}
    return data, warnings


def _set_attempt(ctx: Context, task_id: str, fields: dict[str, Any], event: str) -> None:
    def apply(state: State) -> State:
        state["attempts"][-1].update(fields)
        return state

    ctx.store.update_task(task_id, apply, event)


def _min_version(ctx: Context) -> str:
    cfg = config.load_config(ctx.main_checkout / ".factory" / "config.toml")
    return str(cfg["orca"]["min_version"])


def _require_approval_on_base(change_id: str, base: str, ctx: Context) -> None:
    folder = ctx.changes_dir / change_id
    approval = design.approval_of(folder) or {}
    on_base = git.show_file(base, f".factory/changes/{change_id}/approval.json", ctx.main_checkout)
    if on_base is None or json.loads(on_base).get("design_digest") != approval.get("design_digest"):
        message = f"the approval of {change_id} is not committed on {base}"
        raise FactoryError("approval_not_on_base", message, EXIT_PRECONDITION)


def _started(task_id: str, ctx: Context) -> tuple[dict[str, Any], State]:
    task = _task(task_id, ctx)
    record = ctx.store.read_task(task_id)
    if record is None:
        raise FactoryError("task_not_started", f"{task_id} has not been claimed yet", EXIT_PRECONDITION)
    return task, record


def card_detail(record: State) -> str | None:
    """The card comment for the task's state (design §7.5)."""
    state = record["state"]
    if state == "in_progress":
        checkpoint = record.get("last_checkpoint") or {}
        return checkpoint.get("next") or "lead agent working"
    if state == "in_review":
        return "reviews in progress"
    if state == "blocked":
        return str(record["blocked_reason"])
    if state == "done":
        acceptance = record.get("acceptance") or {}
        verified = sum(1 for ac in acceptance.values() if ac.get("status") == "verified")
        pr = (record.get("pull_request") or {}).get("number")
        return orca.done_comment(verified, len(acceptance), pr)
    return None


def _card(task: dict[str, Any], record: State) -> list[str]:
    workspace = (record.get("workspace") or {}).get("orca_id")
    if not workspace:
        return []
    return orca.update_card(workspace, task["id"], task["title"], record["state"], card_detail(record))


def checkpoint(task_id: str, done: str, next_step: str, ctx: Context) -> tuple[dict[str, Any], list[str]]:
    """Record progress and hand over the person's unread notes, marking them read. A pause note
    moves the task to `blocked` (`paused`) (design §5.2, §7.3)."""
    task, _ = _started(task_id, ctx)
    delivered: list[dict[str, Any]] = []

    def apply(state: State) -> State:
        if state["state"] not in ("in_progress", "in_review"):
            _reject(state, "checkpoint", f"it is {state['state']}")
        state["last_checkpoint"] = {"at": now(), "done": [done], "next": next_step}
        delivered.extend(_read_notes(state))
        if any(n.get("pause") for n in delivered):
            state = transition(state, "block", reason=PAUSED)
        return state

    record = ctx.store.update_task(task_id, apply, "checkpoint")
    paused = record["state"] == "blocked"
    data = {"task": task_id, "state": record["state"], "notes": delivered, "paused": paused}
    if paused:
        data["message"] = "paused by the person: stop here; they continue with factory task unblock"
    return data, _card(task, record)


def _read_notes(state: State) -> list[dict[str, Any]]:
    unread = [n for n in state["notes"] if not n["read"]]
    for note in unread:
        note["read"] = True
    return [dict(n) for n in unread]


def note(task_id: str, text: str, pause: bool, ctx: Context) -> tuple[dict[str, Any], list[str]]:
    """Leave a note (or a pause) for the lead agent; it reads it at its next checkpoint or before
    `submit` (design §7.3)."""
    _started(task_id, ctx)

    def apply(state: State) -> State:
        state["notes"].append({"at": now(), "text": text, "pause": pause, "read": False})
        return state

    ctx.store.update_task(task_id, apply, "pause_note" if pause else "note")
    return {"task": task_id, "note": text, "pause": pause}, []


def block(task_id: str, reason: str, ctx: Context) -> tuple[dict[str, Any], list[str]]:
    task, _ = _started(task_id, ctx)
    record = ctx.store.update_task(task_id, lambda s: transition(s, "block", reason=reason), "block")
    return {"task": task_id, "state": "blocked", "reason": reason}, _card(task, record)


def unblock(task_id: str, ctx: Context) -> tuple[dict[str, Any], list[str]]:
    """Return a blocked task to its previous state, only while the change's approval is valid."""
    task, _ = _started(task_id, ctx)
    if not task["approved"]:
        message = f"{task['change']} is awaiting approval: approve the design again before unblocking"
        raise FactoryError("approval_not_valid", message, EXIT_PRECONDITION)
    record = ctx.store.update_task(task_id, lambda s: transition(s, "unblock"), "unblock")
    return {"task": task_id, "state": record["state"]}, _card(task, record)
