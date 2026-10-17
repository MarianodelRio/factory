"""Task lifecycle (design §1.5, §5, §7).

Raises FactoryError with these codes:
- invalid_transition (EXIT_PRECONDITION): the action is not allowed from the task's state.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import NoReturn

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
