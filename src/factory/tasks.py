"""Task lifecycle (design §1.5, §5, §7).

Raises FactoryError with these codes:
- invalid_transition (EXIT_PRECONDITION): the action is not allowed from the task's state.
- task_not_found (EXIT_PRECONDITION): no approved change has a task with that id.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

import yaml

from factory import design, git, orca
from factory.output import EXIT_PRECONDITION, FactoryError
from factory.state import State, TaskStore

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


def show_task(task_id: str, ctx: Context) -> dict[str, Any]:
    all_tasks = catalog(ctx)
    if task_id not in all_tasks:
        raise FactoryError("task_not_found", f"no approved change has a task {task_id}", EXIT_PRECONDITION)
    task = all_tasks[task_id]
    shown = view(task, ctx)
    definition = {k: v for k, v in task.items() if k not in ("change", "approved")}
    return {**definition, **shown, "record": ctx.store.read_task(task_id)}
