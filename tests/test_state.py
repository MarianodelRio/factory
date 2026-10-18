import json
import multiprocessing
from pathlib import Path

import pytest

from swfactory.output import FactoryError
from swfactory.state import TaskStore, empty_state

TASK = "CHG-0001-01"


def _increment(root: str, times: int) -> None:
    store = TaskStore(Path(root))
    for _ in range(times):
        def bump(state):
            state["counter"] = state.get("counter", 0) + 1
            return state

        store.update_task(TASK, bump, "bump")


def _claim(root: str, attempt: int, results) -> None:
    try:
        TaskStore(Path(root)).create_claim(TASK, attempt)
        results.put(("won", attempt))
    except FactoryError as exc:
        results.put((exc.code, attempt))


def test_empty_state_has_the_design_shape():
    state = empty_state(TASK)
    assert state["task"] == TASK
    for key in ("state", "blocked_reason", "blocked_from", "workspace", "attempts", "last_checkpoint",
                "acceptance", "checks", "reviews", "notes", "memory", "commits", "pull_request"):
        assert key in state


def test_read_missing_task_is_none(tmp_path):
    assert TaskStore(tmp_path).read_task(TASK) is None


def test_update_creates_writes_and_logs_an_event(tmp_path):
    store = TaskStore(tmp_path)

    def start(state):
        state["state"] = "in_progress"
        return state

    result = store.update_task(TASK, start, "claim")
    assert result["state"] == "in_progress"
    assert store.read_task(TASK)["state"] == "in_progress"
    assert json.loads((tmp_path / f"{TASK}.json").read_text())["task"] == TASK
    events = [json.loads(line) for line in (tmp_path / f"{TASK}.events.jsonl").read_text().splitlines()]
    assert [e["event"] for e in events] == ["claim"]
    assert events[0]["state"]["state"] == "in_progress"
    assert "at" in events[0]
    assert not list(tmp_path.glob("*.tmp"))


def test_failing_update_changes_nothing(tmp_path):
    store = TaskStore(tmp_path)
    store.update_task(TASK, lambda s: s, "create")

    def boom(state):
        state["state"] = "done"
        raise FactoryError("invalid_transition", "no")

    with pytest.raises(FactoryError):
        store.update_task(TASK, boom, "finish")
    assert store.read_task(TASK)["state"] is None
    assert len((tmp_path / f"{TASK}.events.jsonl").read_text().splitlines()) == 1


def test_concurrent_updates_lose_no_write(tmp_path):
    processes = [multiprocessing.Process(target=_increment, args=(str(tmp_path), 25)) for _ in range(4)]
    for p in processes:
        p.start()
    for p in processes:
        p.join()
    assert TaskStore(tmp_path).read_task(TASK)["counter"] == 100
    assert len((tmp_path / f"{TASK}.events.jsonl").read_text().splitlines()) == 100


def test_concurrent_claims_exactly_one_wins(tmp_path):
    results = multiprocessing.Queue()
    processes = [multiprocessing.Process(target=_claim, args=(str(tmp_path), n, results)) for n in range(8)]
    for p in processes:
        p.start()
    for p in processes:
        p.join()
    outcomes = [results.get() for _ in processes]
    winners = [a for code, a in outcomes if code == "won"]
    assert len(winners) == 1
    assert sorted(code for code, _ in outcomes if code != "won") == ["task_claimed"] * 7
    assert TaskStore(tmp_path).read_claim(TASK)["attempt"] == winners[0]


def test_release_and_reassign_claim(tmp_path):
    store = TaskStore(tmp_path)
    store.create_claim(TASK, 1)
    store.reassign_claim(TASK, 2)
    assert store.read_claim(TASK)["attempt"] == 2
    store.release_claim(TASK)
    assert store.read_claim(TASK) is None
    store.release_claim(TASK)  # releasing twice is harmless
    store.create_claim(TASK, 3)
    assert store.read_claim(TASK)["attempt"] == 3


def test_reassign_without_claim_fails(tmp_path):
    with pytest.raises(FactoryError) as exc:
        TaskStore(tmp_path).reassign_claim(TASK, 2)
    assert exc.value.code == "not_claimed"


def test_corrupted_json_is_rebuilt_from_events(tmp_path):
    store = TaskStore(tmp_path)

    def step(value):
        def apply(state):
            state["state"] = value
            return state

        return apply

    store.update_task(TASK, step("in_progress"), "claim")
    store.update_task(TASK, step("in_review"), "submit")
    (tmp_path / f"{TASK}.json").write_text("{not json")
    assert store.read_task(TASK)["state"] == "in_review"
    assert json.loads((tmp_path / f"{TASK}.json").read_text())["state"] == "in_review"


def test_corrupted_json_without_events_is_an_error(tmp_path):
    (tmp_path / f"{TASK}.json").write_text("{not json")
    with pytest.raises(FactoryError) as exc:
        TaskStore(tmp_path).read_task(TASK)
    assert exc.value.code == "state_corrupted"


def test_rebuild_skips_a_truncated_last_event(tmp_path):
    store = TaskStore(tmp_path)
    store.update_task(TASK, lambda s: {**s, "state": "in_progress"}, "claim")
    with (tmp_path / f"{TASK}.events.jsonl").open("a") as log:
        log.write('{"event": "submit", "sta')
    assert store.rebuild_from_events(TASK)["state"] == "in_progress"


def test_missing_json_with_events_is_rebuilt(tmp_path):
    store = TaskStore(tmp_path)
    store.update_task(TASK, lambda s: {**s, "state": "in_progress"}, "claim")
    (tmp_path / f"{TASK}.json").unlink()
    assert store.read_task(TASK)["state"] == "in_progress"
    (tmp_path / f"{TASK}.json").unlink()
    store.update_task(TASK, lambda s: {**s, "counter": 1}, "touch")
    assert store.read_task(TASK)["state"] == "in_progress"


def test_claim_is_never_seen_empty(tmp_path):
    store = TaskStore(tmp_path)
    store.create_claim(TASK, 1)
    assert store.read_claim(TASK)["attempt"] == 1
    assert not list(tmp_path.glob(".*.tmp"))


def test_released_claim_leaves_no_state(tmp_path):
    store = TaskStore(tmp_path)
    store.create_claim(TASK, 1)
    store.release_claim(TASK)
    assert store.read_task(TASK) is None
