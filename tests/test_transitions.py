import pytest

from factory.output import EXIT_PRECONDITION, FactoryError
from factory.state import empty_state
from factory.tasks import DESIGN_CHANGED, PAUSED, REVIEW_NOT_CONVERGING, transition


def task(state, **fields):
    data = empty_state("CHG-0001-01")
    data["state"] = state
    data.update(fields)
    return data


# One row per allowed transition of design §1.5: (from, action, to).
ALLOWED = [
    ("ready", "claim", "in_progress"),
    ("interrupted", "recover", "in_progress"),
    ("in_progress", "submit", "in_review"),
    ("in_progress", "finish", "done"),
    ("in_review", "finish", "done"),
    ("in_progress", "block", "blocked"),
    ("in_review", "block", "blocked"),
    ("in_progress", "interrupt", "interrupted"),
]


@pytest.mark.parametrize(("current", "action", "expected"), ALLOWED)
def test_allowed_transitions(current, action, expected):
    stored = None if current == "ready" else current
    result = transition(task(stored), action, current=current, reason="why")
    assert result["state"] == expected


@pytest.mark.parametrize("current", ["pending", "ready", "in_progress", "in_review", "done", "blocked",
                                     "interrupted"])
@pytest.mark.parametrize("action", ["claim", "recover", "submit", "finish", "block", "unblock",
                                    "reapprove", "interrupt"])
def test_illegal_transitions_are_rejected(current, action):
    allowed = {(c, a) for c, a, _ in ALLOWED} | {("blocked", "unblock"), ("blocked", "reapprove")}
    if (current, action) in allowed:
        return
    with pytest.raises(FactoryError) as exc:
        transition(task(current, blocked_reason="x", blocked_from="in_progress"), action, current=current,
                   reason="why")
    assert exc.value.code == "invalid_transition"
    assert exc.value.exit_code == EXIT_PRECONDITION


@pytest.mark.parametrize("reason", [PAUSED, DESIGN_CHANGED, REVIEW_NOT_CONVERGING, "needs a schema decision"])
@pytest.mark.parametrize("before", ["in_progress", "in_review"])
def test_block_records_reason_and_previous_state(reason, before):
    result = transition(task(before), "block", reason=reason)
    assert (result["state"], result["blocked_reason"], result["blocked_from"]) == ("blocked", reason, before)


def test_block_needs_a_reason():
    with pytest.raises(FactoryError) as exc:
        transition(task("in_progress"), "block")
    assert exc.value.code == "invalid_transition"


@pytest.mark.parametrize("before", ["in_progress", "in_review"])
def test_unblock_returns_to_previous_state(before):
    blocked = transition(task(before), "block", reason=PAUSED)
    result = transition(blocked, "unblock")
    assert (result["state"], result["blocked_reason"], result["blocked_from"]) == (before, None, None)


def test_unblock_does_not_release_a_design_change():
    blocked = transition(task("in_review"), "block", reason=DESIGN_CHANGED)
    with pytest.raises(FactoryError) as exc:
        transition(blocked, "unblock")
    assert exc.value.code == "invalid_transition"
    assert "approv" in exc.value.message


def test_reapproval_releases_only_design_changed_tasks():
    blocked = transition(task("in_review"), "block", reason=DESIGN_CHANGED)
    assert transition(blocked, "reapprove")["state"] == "in_review"
    paused = transition(task("in_progress"), "block", reason=PAUSED)
    with pytest.raises(FactoryError):
        transition(paused, "reapprove")


def test_transition_does_not_mutate_its_input():
    original = task("in_progress")
    transition(original, "submit")
    assert original["state"] == "in_progress"


def test_a_stored_state_wins_over_the_computed_one():
    with pytest.raises(FactoryError):
        transition(task("done"), "claim", current="ready")
