"""Changes: digest, ids and the task block of `design.md` (design §1.4, §4.3).

Raises FactoryError with these codes:
- design_invalid (EXIT_PRECONDITION): the task block or the acceptance criteria are not valid;
  `details` lists every problem found.
- change_not_found (EXIT_PRECONDITION): the change folder or its `design.md` does not exist.
- change_rejected (EXIT_PRECONDITION): the change was rejected; a new change must be created.
- already_approved (EXIT_PRECONDITION): the current design is already approved.
- approval_not_explicit (EXIT_PRECONDITION): the approval message does not name the change.
- approval_not_confirmed (EXIT_PRECONDITION): the id typed in the terminal is not the change id.
- not_on_base_branch (EXIT_PRECONDITION): approve and reject only run on the base branch.
- git_identity_missing (EXIT_PRECONDITION): `git config user.email` is not set.
Plus the codes of factory.git (commit_failed, ...) and factory.orca (base branch).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from factory import git, orca, tasks
from factory.output import EXIT_PRECONDITION, FactoryError
from factory.state import TaskStore, now

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


def show(change_id: str, changes_dir: Path, store: TaskStore, main_changes_dir: Path) -> dict[str, Any]:
    """Change state (§1.5), digest, criteria, tasks with their stored state, approval or rejection.
    An invalid design is still shown, with its problems. Whether the design changed after its
    approval (§4.5) is decided on the main checkout's files, which own the shared task state."""
    folder = _folder(change_id, changes_dir)
    text = _design_text(folder)
    try:
        parsed = parse_design(text, change_id, known_tasks(changes_dir, exclude=change_id))
        problems: list[str] = []
    except FactoryError as exc:
        if exc.code != "design_invalid":
            raise
        parsed, problems = {"acceptance_criteria": [], "tasks": []}, exc.details

    approval = _read_json(folder / "approval.json")
    rejection = _read_json(folder / "rejection.json")
    current = digest(text)
    sync_with_main(change_id, main_changes_dir, store)

    task_list = []
    for task in parsed["tasks"]:
        stored = store.read_task(task["id"])
        task_list.append({**task, "state": stored["state"] if stored else None})
    if rejection is not None:
        state = "rejected"
    elif approval is None or approval.get("design_digest") != current:
        state = "awaiting_approval"
    elif task_list and all(t["state"] == "done" for t in task_list):
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
        "tasks": task_list,
        "approval": approval,
        "rejection": rejection,
        "problems": problems,
    }


def sync_with_main(change_id: str, main_changes_dir: Path, store: TaskStore) -> None:
    """Block or restore the change's tasks (§4.5) from the main checkout's design and approval."""
    folder = main_changes_dir / change_id
    approval = _read_json(folder / "approval.json")
    if approval is None or not (folder / "design.md").exists():
        return
    approved = approval.get("design_digest") == digest((folder / "design.md").read_text(encoding="utf-8"))
    tasks.sync_with_design(approved_task_ids(folder), approved, store)


def approved_task_ids(folder: Path) -> list[str]:
    """Task ids of the change's `tasks.yaml` (the last approved task list)."""
    path = folder / "tasks.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [str(t["id"]) for t in data.get("tasks", []) if isinstance(t, dict) and "id" in t]


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


def approve(
    change_id: str, changes_dir: Path, message: str, method: str, main_checkout: Path, store: TaskStore
) -> dict[str, Any]:
    """Approve the current design (design §4.4): on the base branch, with an explicit message
    (`chat`) or the typed id (`terminal`); commit only the change folder. On re-approval the task
    ids are kept and tasks blocked by the design change return to their state (§4.5)."""
    folder = _folder(change_id, changes_dir)
    _refuse_rejected(change_id, folder)
    text = _design_text(folder)
    removed = _removed_tasks(text, folder)
    try:
        parsed = parse_design(text, change_id, known_tasks(changes_dir, exclude=change_id))
    except FactoryError as exc:
        exc.details += removed
        raise
    if removed:
        message = f"the design of {change_id} removes approved tasks"
        raise FactoryError("design_invalid", message, EXIT_PRECONDITION, removed)
    current = digest(text)
    previous = _read_json(folder / "approval.json")
    if previous and previous.get("design_digest") == current:
        raise FactoryError("already_approved", f"{change_id} is already approved", EXIT_PRECONDITION)
    if method == "terminal" and message.strip() != change_id:
        message = f"typed '{message.strip()}', expected {change_id}: not approved"
        raise FactoryError("approval_not_confirmed", message, EXIT_PRECONDITION)
    if method == "chat" and not re.search(rf"\b{re.escape(change_id)}\b", message, re.IGNORECASE):
        message = f"the approval message must name {change_id} explicitly (e.g. 'approve {change_id}')"
        raise FactoryError("approval_not_explicit", message, EXIT_PRECONDITION)
    email = _ready_to_commit(folder, main_checkout)

    approval = {
        "change": change_id,
        "design_digest": current,
        "approved_by": email,
        "approved_at": now(),
        "method": method,
        "message": message,
    }
    tasks_yaml = {"change": change_id, "design_digest": current, "tasks": parsed["tasks"]}
    files = {
        "approval.json": json.dumps(approval, indent=2, ensure_ascii=False) + "\n",
        "tasks.yaml": yaml.safe_dump(tasks_yaml, sort_keys=False, allow_unicode=True),
    }
    commit = _write_and_commit(folder, files, f"Approve {change_id}")
    tasks.sync_with_design(approved_task_ids(folder), True, store)
    return {"change": change_id, "digest": current, "commit": commit, "tasks": parsed["tasks"]}


def reject(change_id: str, changes_dir: Path, reason: str, main_checkout: Path) -> dict[str, Any]:
    """Reject a change (final): write `rejection.json` on the base branch and commit it."""
    folder = _folder(change_id, changes_dir)
    _refuse_rejected(change_id, folder)
    text = _design_text(folder)
    email = _ready_to_commit(folder, main_checkout)
    rejection = {
        "change": change_id,
        "design_digest": digest(text),
        "rejected_by": email,
        "rejected_at": now(),
        "method": "chat",
        "reason": reason,
    }
    files = {"rejection.json": json.dumps(rejection, indent=2, ensure_ascii=False) + "\n"}
    commit = _write_and_commit(folder, files, f"Reject {change_id}")
    return {"change": change_id, "commit": commit}


def _removed_tasks(text: str, folder: Path) -> list[str]:
    """Problems for approved task ids missing from the design: nothing is deleted (§4.5)."""
    block = _task_block(normalize(text), []) or []
    ids = {str(t.get("id")) for t in block}
    missing = [i for i in approved_task_ids(folder) if i not in ids]
    return [f"{i} was approved before and cannot be removed" for i in missing]


def _refuse_rejected(change_id: str, folder: Path) -> None:
    if (folder / "rejection.json").exists():
        message = f"{change_id} was rejected; create a new change to take it up again"
        raise FactoryError("change_rejected", message, EXIT_PRECONDITION)


def _ready_to_commit(folder: Path, main_checkout: Path) -> str:
    """The session is on the base branch and has a Git identity; return its email."""
    base = orca.base_branch(main_checkout)
    branch = git.current_branch(folder)
    if branch != base:
        where = branch or "a detached HEAD"
        message = f"this session is on '{where}', not on the base branch '{base}'; run `git switch {base}`"
        raise FactoryError("not_on_base_branch", message, EXIT_PRECONDITION)
    email = git.config_value("user.email", folder)
    if not email:
        raise FactoryError("git_identity_missing", "set `git config user.email` first", EXIT_PRECONDITION)
    return email


def _write_and_commit(folder: Path, files: dict[str, str], message: str) -> str:
    """Write `files` in the change folder and commit only that folder; undo the writes if the
    commit fails."""
    previous = {name: (folder / name).read_text(encoding="utf-8") if (folder / name).exists() else None
                for name in files}
    for name, content in files.items():
        (folder / name).write_text(content, encoding="utf-8")
    root = git.toplevel(folder)
    try:
        return git.commit_paths([str(folder.relative_to(root))], message, root)
    except FactoryError:
        for name, before in previous.items():
            if before is None:
                (folder / name).unlink(missing_ok=True)
            else:
                (folder / name).write_text(before, encoding="utf-8")
        raise
