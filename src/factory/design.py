"""Changes: digest, ids and the task block of `design.md` (design §1.4, §4.3).

Raises FactoryError with these codes:
- design_invalid (EXIT_PRECONDITION): the task block or the acceptance criteria are not valid;
  `details` lists every problem found.
- change_not_found (EXIT_PRECONDITION): the change folder or its `design.md` does not exist.
- change_rejected (EXIT_PRECONDITION): the change was rejected; a new change must be created.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from factory.output import EXIT_PRECONDITION, FactoryError
from factory.state import TaskStore

CHANGE_ID = re.compile(r"^CHG-(\d{4})$")
TITLE = re.compile(r"^# (?:CHG-\d{4}\s*[—-]\s*)?(.+)$", re.MULTILINE)
AC_ID = re.compile(r"^AC-\d{2,}$")
AC_LINE = re.compile(r"^\s*-\s*(AC-\d{2,})\s*:")
FENCE = re.compile(r"^```yaml\s*\n(.*?)^```\s*$", re.MULTILINE | re.DOTALL)

REQUIRED = ("id", "title", "depends_on", "complexity", "review", "acceptance")
OPTIONAL = ("scope",)
COMPLEXITIES = ("trivial", "normal", "complex")
REVIEW_TYPES = ("quality", "conformance")


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def digest(design_md: str) -> str:
    """SHA-256 of `design.md` with line breaks normalized to LF."""
    return "sha256:" + hashlib.sha256(normalize(design_md).encode("utf-8")).hexdigest()


def next_change_id(changes_dir: Path) -> str:
    """The next free `CHG-NNNN` after the highest change folder."""
    numbers = [0]
    if changes_dir.is_dir():
        for entry in changes_dir.iterdir():
            match = CHANGE_ID.match(entry.name)
            if match and entry.is_dir():
                numbers.append(int(match.group(1)))
    return f"CHG-{max(numbers) + 1:04d}"


def section(text: str, title: str) -> str | None:
    """Body of the `## <title>` section, or None if there is none."""
    match = re.search(rf"^## {re.escape(title)}[ \t]*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else None


def parse_design(design_md: str, change_id: str, known_tasks: set[str]) -> dict[str, Any]:
    """Validate the acceptance criteria and the task block of a change and return both.

    `known_tasks` are task ids of other changes that `depends_on` may refer to.
    """
    text = normalize(design_md)
    errors: list[str] = []

    criteria_body = section(text, "Acceptance criteria")
    criteria: list[str] = []
    if criteria_body is None:
        errors.append("missing section '## Acceptance criteria'")
    else:
        criteria = [m.group(1) for line in criteria_body.splitlines() if (m := AC_LINE.match(line))]

    tasks = _task_block(text, errors)
    if tasks is not None:
        _validate_tasks(tasks, change_id, known_tasks, criteria, errors)

    if errors:
        message = f"the design of {change_id} has {len(errors)} problem(s)"
        raise FactoryError("design_invalid", message, EXIT_PRECONDITION, errors)
    assert tasks is not None
    return {"acceptance_criteria": criteria, "tasks": tasks}


def _task_block(text: str, errors: list[str]) -> list[dict[str, Any]] | None:
    body = section(text, "Tasks")
    if body is None:
        errors.append("missing section '## Tasks'")
        return None
    fence = FENCE.search(body)
    if fence is None:
        errors.append("the '## Tasks' section has no ```yaml block")
        return None
    try:
        tasks = yaml.safe_load(fence.group(1))
    except yaml.YAMLError as exc:
        errors.append(f"the task block is not valid YAML: {exc}")
        return None
    if not isinstance(tasks, list) or not tasks or not all(isinstance(t, dict) for t in tasks):
        errors.append("the task block must be a non-empty list of tasks")
        return None
    return tasks


def _validate_tasks(
    tasks: list[dict[str, Any]],
    change_id: str,
    known_tasks: set[str],
    criteria: list[str],
    errors: list[str],
) -> None:
    id_pattern = re.compile(rf"^{re.escape(change_id)}-\d{{2,}}$")
    ids = [str(t.get("id")) for t in tasks]
    own = set(ids)
    covered: set[str] = set()

    for position, task in enumerate(tasks, start=1):
        name = str(task.get("id", f"task #{position}"))
        for field in REQUIRED:
            if field not in task:
                errors.append(f"{name}: missing field '{field}'")
        for field in task:
            if field not in REQUIRED + OPTIONAL:
                errors.append(f"{name}: unknown field '{field}'")

        if "id" in task and not id_pattern.match(str(task["id"])):
            errors.append(f"{name}: id must be {change_id}-NN")
        if "id" in task and ids.count(str(task["id"])) > 1:
            errors.append(f"{name}: duplicated task id")
        if "title" in task and (not isinstance(task["title"], str) or not task["title"].strip()):
            errors.append(f"{name}: title must be a non-empty text")
        if "complexity" in task and task["complexity"] not in COMPLEXITIES:
            allowed = ", ".join(COMPLEXITIES)
            errors.append(f"{name}: complexity '{task['complexity']}' must be one of {allowed}")

        review = task.get("review")
        if "review" in task:
            if not isinstance(review, list) or any(r not in REVIEW_TYPES for r in review):
                errors.append(f"{name}: review {review!r} must be a list of {', '.join(REVIEW_TYPES)}")
            elif len(set(review)) != len(review):
                errors.append(f"{name}: review {review!r} has a duplicated type")

        if "scope" in task and (
            not isinstance(task["scope"], list) or not all(isinstance(g, str) and g for g in task["scope"])
        ):
            errors.append(f"{name}: scope must be a list of path globs")

        depends = task.get("depends_on")
        if "depends_on" in task:
            if not isinstance(depends, list):
                errors.append(f"{name}: depends_on must be a list of task ids")
            else:
                for dep in depends:
                    if str(dep) not in own and str(dep) not in known_tasks:
                        errors.append(f"{name}: depends on unknown task '{dep}'")

        acceptance = task.get("acceptance")
        if "acceptance" in task:
            if not isinstance(acceptance, dict) or not acceptance:
                errors.append(f"{name}: acceptance must map each AC to a command or 'manual'")
            else:
                for ac, how in acceptance.items():
                    if not AC_ID.match(str(ac)):
                        errors.append(f"{name}: '{ac}' is not an AC id (AC-NN)")
                    elif ac not in criteria:
                        errors.append(f"{name}: {ac} is not in '## Acceptance criteria'")
                    if not isinstance(how, str) or not how.strip():
                        errors.append(f"{name}: {ac} needs a command or 'manual'")
                    covered.add(str(ac))

    for ac in criteria:
        if ac not in covered:
            errors.append(f"{ac} is covered by no task")

    cycle = _find_cycle(tasks, own)
    if cycle:
        errors.append(f"dependency cycle: {' -> '.join(cycle)}")


def _find_cycle(tasks: list[dict[str, Any]], own: set[str]) -> list[str] | None:
    graph = {
        str(t.get("id")): [str(d) for d in t.get("depends_on") or [] if str(d) in own]
        for t in tasks
        if isinstance(t.get("depends_on", []), list)
    }
    visiting: list[str] = []
    done: set[str] = set()

    def visit(node: str) -> list[str] | None:
        if node in visiting:
            return visiting[visiting.index(node) :] + [node]
        if node in done:
            return None
        visiting.append(node)
        for dep in graph.get(node, []):
            found = visit(dep)
            if found:
                return found
        visiting.pop()
        done.add(node)
        return None

    for node in graph:
        found = visit(node)
        if found:
            return found
    return None


def reserve_change(changes_dir: Path) -> dict[str, Any]:
    """Create the folder of the next free change id; two sessions never get the same one."""
    changes_dir.mkdir(parents=True, exist_ok=True)
    while True:
        change_id = next_change_id(changes_dir)
        try:
            (changes_dir / change_id).mkdir()
        except FileExistsError:
            continue
        return {"change": change_id, "design": str(changes_dir / change_id / "design.md")}


def register(change_id: str, changes_dir: Path) -> dict[str, Any]:
    """Validate the `design.md` of a reserved change."""
    folder = _folder(change_id, changes_dir)
    if (folder / "rejection.json").exists():
        message = f"{change_id} was rejected; create a new change to take it up again"
        raise FactoryError("change_rejected", message, EXIT_PRECONDITION)
    text = _design_text(folder)
    parsed = parse_design(text, change_id, known_tasks(changes_dir, exclude=change_id))
    return {"change": change_id, "digest": digest(text), **parsed}


def show(change_id: str, changes_dir: Path, store: TaskStore) -> dict[str, Any]:
    """Change state (§1.5), digest, criteria, tasks with their stored state, approval or rejection.
    An invalid design is still shown, with its problems."""
    folder = _folder(change_id, changes_dir)
    text = _design_text(folder)
    try:
        parsed = parse_design(text, change_id, known_tasks(changes_dir, exclude=change_id))
        problems: list[str] = []
    except FactoryError as exc:
        if exc.code != "design_invalid":
            raise
        parsed, problems = {"acceptance_criteria": [], "tasks": []}, exc.details

    tasks = []
    for task in parsed["tasks"]:
        stored = store.read_task(task["id"])
        tasks.append({**task, "state": stored["state"] if stored else None})

    approval = _read_json(folder / "approval.json")
    rejection = _read_json(folder / "rejection.json")
    current = digest(text)
    if rejection is not None:
        state = "rejected"
    elif approval is None or approval.get("design_digest") != current:
        state = "awaiting_approval"
    elif tasks and all(t["state"] == "done" for t in tasks):
        state = "done"
    else:
        state = "approved"

    title = TITLE.search(normalize(text))
    return {
        "change": change_id,
        "title": title.group(1).strip() if title else None,
        "state": state,
        "digest": current,
        "acceptance_criteria": parsed["acceptance_criteria"],
        "tasks": tasks,
        "approval": approval,
        "rejection": rejection,
        "problems": problems,
    }


def known_tasks(changes_dir: Path, exclude: str) -> set[str]:
    """Ids of approved tasks of other changes (their `tasks.yaml`)."""
    ids: set[str] = set()
    for tasks_file in sorted(changes_dir.glob("CHG-*/tasks.yaml")):
        if tasks_file.parent.name == exclude:
            continue
        data = yaml.safe_load(tasks_file.read_text(encoding="utf-8")) or {}
        ids.update(str(t["id"]) for t in data.get("tasks", []) if isinstance(t, dict) and "id" in t)
    return ids


def _folder(change_id: str, changes_dir: Path) -> Path:
    folder = changes_dir / change_id
    if not folder.is_dir():
        message = f"{change_id} does not exist in {changes_dir}"
        raise FactoryError("change_not_found", message, EXIT_PRECONDITION)
    return folder


def _design_text(folder: Path) -> str:
    path = folder / "design.md"
    if not path.exists():
        raise FactoryError("change_not_found", f"{path} does not exist yet", EXIT_PRECONDITION)
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data
