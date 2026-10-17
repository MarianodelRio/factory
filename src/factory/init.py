"""`factory doctor` and `factory init` (design §3): analysis, plan, apply, backups and restore.

`doctor` only reads: it never writes to the repository or to Orca.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
import tomllib
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

from factory import config, git, orca
from factory.output import EXIT_PRECONDITION, FactoryError, is_secret_file

CHECK_KINDS = ("test", "lint", "typecheck", "build")
OTHER_INSTRUCTIONS = (".cursorrules", ".cursor/rules", ".windsurfrules", "GEMINI.md", ".github/copilot-instructions.md")


def doctor(root: Path, main_checkout: Path) -> dict[str, Any]:
    """Everything `/factory-init` needs to propose a plan (design §3.1 step 1), without changes."""
    problems: list[str] = []
    warnings: list[str] = []
    configured = config.load_config(root / ".factory" / "config.toml") if (root / ".factory").is_dir() else None

    report: dict[str, Any] = {
        "git": {
            "root": str(root),
            "branch": git.current_branch(root),
            "pending_changes": len(git.run(["status", "--porcelain"], root).splitlines()),
            "worktrees": [str(p) for p in git.worktree_paths(root)],
        },
        "orca": _orca(main_checkout, configured, problems),
        "agents": _agents(),
        "gh": _gh(root),
        "stack": _stack(root),
        "checks": _checks(root, configured),
        "ci": sorted(str(p.relative_to(root)) for p in (root / ".github" / "workflows").glob("*.y*ml")),
        "instructions": _instructions(root),
        "factory": {"installed": configured is not None},
    }
    if any(v == "ask" for v in report["checks"].values()):
        warnings.append("some check commands were not found: ask the person for them")
    warnings += _permission_warnings(root)
    report["problems"] = problems
    report["warnings"] = warnings
    return report


def _orca(main_checkout: Path, configured: dict[str, Any] | None, problems: list[str]) -> dict[str, Any]:
    min_version = (configured or config.DEFAULTS)["orca"]["min_version"]
    try:
        info = orca.check(min_version)
    except FactoryError as exc:
        problems.append(f"Orca: {exc.message}")
        return {"ok": False, "problem": exc.message}
    result: dict[str, Any] = {"ok": True, "version": info["version"]}
    try:
        orca.run(["repo", "show", "--repo", f"path:{main_checkout}"])
        result["repo_registered"] = True
    except FactoryError:
        result["repo_registered"] = False
    try:
        result["base_branch"] = orca.base_branch(main_checkout)
    except FactoryError:
        result["base_branch"] = None
    try:
        skills = orca.run(["skills", "installed"])["skills"]
        result["orca_skills_installed"] = any(s.get("name") == "orca-cli" for s in skills)
    except (FactoryError, KeyError, TypeError):
        result["orca_skills_installed"] = None
    return result


def _agents() -> dict[str, bool | None]:
    try:
        statuses = {s["agent"]: s["state"] for s in orca.run(["agent", "hooks", "status"])["statuses"]}
    except (FactoryError, KeyError, TypeError):
        return {"claude": None, "codex": None}
    return {agent: statuses.get(agent) == "installed" for agent in ("claude", "codex")}


def _gh(root: Path) -> dict[str, bool]:
    try:
        git.gh_version(root)
    except FactoryError:
        return {"installed": False, "authenticated": False}
    return {"installed": True, "authenticated": git.gh_authenticated(root)}


def _stack(root: Path) -> list[str]:
    markers = {"python": ("pyproject.toml", "setup.py", "requirements.txt"), "node": ("package.json",),
               "go": ("go.mod",), "rust": ("Cargo.toml",)}
    return [name for name, files in markers.items() if any((root / f).exists() for f in files)]


def _checks(root: Path, configured: dict[str, Any] | None) -> dict[str, str]:
    """Check commands from the config, package.json, pyproject.toml or the Makefile; "ask" if
    there is no evidence."""
    sources = [dict((configured or {}).get("checks", {})), _node_checks(root), _python_checks(root),
               _make_checks(root)]
    return {kind: next((s[kind] for s in sources if kind in s), "ask") for kind in CHECK_KINDS}


def _node_checks(root: Path) -> dict[str, str]:
    path = root / "package.json"
    if not path.exists():
        return {}
    scripts = json.loads(path.read_text(encoding="utf-8")).get("scripts", {})
    runner = "pnpm" if (root / "pnpm-lock.yaml").exists() else "yarn" if (root / "yarn.lock").exists() else "npm"
    return {kind: f"{runner} run {kind}" for kind in CHECK_KINDS if kind in scripts}


def _python_checks(root: Path) -> dict[str, str]:
    path = root / "pyproject.toml"
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    tools = data.get("tool", {})
    found = {}
    if "pytest" in tools:
        found["test"] = "pytest"
    if "ruff" in tools:
        found["lint"] = "ruff check ."
    if "mypy" in tools:
        found["typecheck"] = "mypy src" if (root / "src").is_dir() else "mypy ."
    return found


def _make_checks(root: Path) -> dict[str, str]:
    path = root / "Makefile"
    if not path.exists():
        return {}
    targets = set(re.findall(r"^([A-Za-z][\w-]*):", path.read_text(encoding="utf-8"), re.MULTILINE))
    return {kind: f"make {kind}" for kind in CHECK_KINDS if kind in targets}


def _instructions(root: Path) -> dict[str, Any]:
    skills = []
    for base in (".claude/skills", ".agents/skills"):
        if (root / base).is_dir():
            skills += sorted(str(p.relative_to(root)) for p in (root / base).iterdir() if p.is_dir())
    return {
        "agents_md": (root / "AGENTS.md").exists(),
        "claude_md": (root / "CLAUDE.md").exists(),
        "readme": any((root / name).exists() for name in ("README.md", "README.rst", "README")),
        "docs": sorted(str(p.relative_to(root)) for p in (root / "docs").rglob("*.md")) if (root / "docs").is_dir()
        else [],
        "skills": skills,
        "other": [name for name in OTHER_INSTRUCTIONS if (root / name).exists()],
    }


def _permission_warnings(root: Path) -> list[str]:
    """Claude Code settings that skip permission prompts (then approval rests on the skills' rules)."""
    warnings = []
    for path in (root / ".claude/settings.json", root / ".claude/settings.local.json",
                 Path.home() / ".claude/settings.json"):
        try:
            mode = json.loads(path.read_text(encoding="utf-8")).get("permissions", {}).get("defaultMode")
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
        if mode == "bypassPermissions":
            warnings.append(f"{path} skips permission prompts: approving then rests only on the skills' rules")
    return warnings


# --- init: plan, apply, restore (design §3.1, §3.2) -------------------------------------------------

SKILL_BASES = (".claude/skills", ".agents/skills")
ASK_RULES = ["Bash(factory design approve:*)", "Bash(factory design reject:*)"]
GITIGNORE_LINE = ".factory/state/"
SMALL_REPO_FILES = 30
DOCS_SMALL = ("conventions.md",)
DOCS_NORMAL = ("product.md", "architecture.md", "conventions.md", "working-agreements.md", "decisions/README.md")
DELETABLE_SUFFIXES = (".md", ".mdc", ".txt", ".rst")
MARK = re.compile(r"<!-- factory-template: ([\w./-]+)@(\d+) -->")


def _template(path: str) -> str:
    return resources.files("factory").joinpath(f"templates/{path}").read_text(encoding="utf-8")


def _skill_files() -> dict[str, str]:
    """Relative path inside a skills folder -> content, for the four skills and what they reference."""
    files: dict[str, str] = {}
    base = resources.files("factory").joinpath("templates/skills")
    for skill in sorted(p.name for p in base.iterdir() if p.is_dir()):
        stack = [(base.joinpath(skill), skill)]
        while stack:
            folder, rel = stack.pop()
            for entry in folder.iterdir():
                if entry.is_dir():
                    stack.append((entry, f"{rel}/{entry.name}"))
                elif entry.name.endswith(".md"):
                    files[f"{rel}/{entry.name}"] = entry.read_text(encoding="utf-8")
    roles = resources.files("factory").joinpath("templates/roles")
    for skill in ("factory-design", "factory-implement"):
        for role in roles.iterdir():
            files[f"{skill}/references/roles/{role.name}"] = role.read_text(encoding="utf-8")
    files["factory-design/references/design-template.md"] = _template("design/design.md")
    files["factory-implement/references/adr-template.md"] = _template("docs/decisions/adr.md")
    return dict(sorted(files.items()))


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _diff(path: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{path}", f"b/{path}"))


def _read(root: Path, path: str) -> str | None:
    file = root / path
    return file.read_text(encoding="utf-8") if file.is_file() else None


class Plan:
    """The four lists, the Orca actions and the exact content each write will have."""

    def __init__(self) -> None:
        self.create: list[dict[str, str]] = []
        self.modify: list[dict[str, str]] = []
        self.delete: list[dict[str, str]] = []
        self.respect: list[dict[str, str]] = []
        self.customized: list[dict[str, str]] = []
        self.orca: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.writes: dict[str, str] = {}
        self.tracked: dict[str, str] = {}  # skill files whose installed hash goes to [templates]

    def write(self, root: Path, path: str, new: str, reason: str) -> None:
        old = _read(root, path)
        if old == new:
            return
        self.writes[path] = new
        if old is None:
            self.create.append({"path": path})
        else:
            self.modify.append({"path": path, "reason": reason, "diff": _diff(path, old, new)})

    def data(self) -> dict[str, Any]:
        body = {"create": self.create, "modify": self.modify, "delete": self.delete, "respect": self.respect,
                "customized": self.customized, "orca": self.orca, "warnings": self.warnings}
        fingerprint = json.dumps([body, self.writes, self.tracked], sort_keys=True)
        return {"plan_id": hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:12], **body}


def build_plan(root: Path, main_checkout: Path, deletes: list[tuple[str, str]]) -> Plan:
    """What `/factory-init` would do in this repo, without changing anything."""
    report = doctor(root, main_checkout)
    configured = config.load_config(root / ".factory" / "config.toml") if (root / ".factory").is_dir() else None
    recorded: dict[str, str] = dict((configured or {}).get("templates", {}))
    plan = Plan()
    plan.warnings = report["warnings"]

    for rel, content in _skill_files().items():
        for base in SKILL_BASES:
            path = f"{base}/{rel}"
            current = _read(root, path)
            if current is None or current == content or recorded.get(path) == _sha(current):
                plan.write(root, path, content, "update to the current Factory template")
                plan.tracked[path] = _sha(content)
            else:
                plan.customized.append({"path": path, "diff": _diff(path, current, content)})

    _docs(root, plan)
    _deletions(root, plan, deletes)
    _settings(root, plan)
    gitignore = _read(root, ".gitignore")
    if gitignore is None or GITIGNORE_LINE not in gitignore.splitlines():
        text = (gitignore or "") + ("" if not gitignore or gitignore.endswith("\n") else "\n") + GITIGNORE_LINE + "\n"
        plan.write(root, ".gitignore", text, "ignore the Factory's local state")
    plan.write(root, ".factory/config.toml", _config_text(root, report, plan.tracked), "record template hashes")
    plan.orca = _orca_actions(root, main_checkout, report, plan)
    return plan


def _docs(root: Path, plan: Plan) -> None:
    agents = _read(root, "AGENTS.md")
    if agents is None:
        plan.write(root, "AGENTS.md", _template("docs/AGENTS.md"), "")
    elif "## Software Factory" not in agents:
        section = _template("docs/AGENTS.md").split("## Software Factory", 1)[1]
        plan.write(root, "AGENTS.md", agents.rstrip("\n") + "\n\n## Software Factory" + section,
                   "add the Factory section")
    claude = _read(root, "CLAUDE.md")
    if claude is None:
        plan.write(root, "CLAUDE.md", _template("docs/CLAUDE.md"), "")
    elif "@AGENTS.md" not in claude.splitlines():
        plan.write(root, "CLAUDE.md", claude.rstrip("\n") + "\n\n@AGENTS.md\n", "import AGENTS.md")
    tracked = len(git.run(["ls-files"], root).splitlines())
    for doc in DOCS_SMALL if tracked < SMALL_REPO_FILES else DOCS_NORMAL:
        path = f"docs/{doc}"
        if _read(root, path) is None:
            plan.write(root, path, _template(path), "")
    for path in _existing_docs(root):
        if path not in plan.writes:
            plan.respect.append({"path": path, "reason": "existing documentation is kept and linked"})
    for path in OTHER_INSTRUCTIONS:
        if (root / path).is_file():
            plan.respect.append({"path": path, "reason": "review: may duplicate or contradict AGENTS.md"})


def _existing_docs(root: Path) -> list[str]:
    docs = sorted(str(p.relative_to(root)) for p in (root / "docs").rglob("*.md")) if (root / "docs").is_dir() else []
    return [p for p in docs if (root / p).read_text(encoding="utf-8").strip()]


def _deletions(root: Path, plan: Plan, deletes: list[tuple[str, str]]) -> None:
    proposed: dict[str, str] = {}
    current_skills = {rel.split("/", 1)[0] for rel in _skill_files()}
    for base in SKILL_BASES:
        folder = root / base
        if not folder.is_dir():
            continue
        for skill in folder.iterdir():
            if skill.name.startswith("factory-") and skill.name not in current_skills:
                for file in sorted(skill.rglob("*")):
                    if file.is_file() and MARK.search(file.read_text(encoding="utf-8", errors="ignore")):
                        proposed[str(file.relative_to(root))] = "leftover from an earlier Factory version"
    if (root / "docs").is_dir():
        for file in sorted((root / "docs").rglob("*.md")):
            if not file.read_text(encoding="utf-8").strip():
                proposed[str(file.relative_to(root))] = "empty document"
    for path, reason in deletes:
        _check_deletable(root, path)
        proposed[path] = reason
    plan.delete = [{"path": p, "reason": r} for p, r in sorted(proposed.items())]


def _check_deletable(root: Path, path: str) -> None:
    """Only documentation and instruction files may be deleted; never code, tests, CI or secrets."""
    file = root / path
    parts = Path(path).parts
    allowed = (
        file.is_file()
        and not is_secret_file(path)
        and not ({"tests", "test"} & set(parts))
        and not path.startswith((".github/workflows/", ".gitlab-ci", ".circleci/"))
        and (file.suffix in DELETABLE_SUFFIXES or path in OTHER_INSTRUCTIONS)
    )
    if not allowed:
        message = f"{path} cannot be deleted by /factory-init (missing, code, tests, CI or a secret)"
        raise FactoryError("delete_not_allowed", message, EXIT_PRECONDITION)


def _settings(root: Path, plan: Plan) -> None:
    """`permissions.ask` for approve and reject in Claude Code, merged into existing settings."""
    current = _read(root, ".claude/settings.json")
    settings = json.loads(current) if current else {}
    ask = settings.setdefault("permissions", {}).setdefault("ask", [])
    ask.extend(rule for rule in ASK_RULES if rule not in ask)
    plan.write(root, ".claude/settings.json", json.dumps(settings, indent=2) + "\n", "always ask before approve/reject")


def _config_text(root: Path, report: dict[str, Any], tracked: dict[str, str]) -> str:
    """`.factory/config.toml`: created from the defaults and detected checks; an existing one keeps
    everything and only its `[templates]` section is replaced."""
    current = _read(root, ".factory/config.toml")
    if current is None:
        checks = {k: v for k, v in report["checks"].items() if v != "ask"}
        d = config.DEFAULTS
        lines = [
            f"schema_version = {d['schema_version']}", "",
            "[orca]", f"min_version = {json.dumps(d['orca']['min_version'])}", "",
            "[checks]", *[f"{k} = {json.dumps(v)}" for k, v in checks.items()], "",
            "[review]", *[f"{k} = {json.dumps(v)}" for k, v in d["review"].items()], "",
            "[git]", f"pr_on_done = {json.dumps(d['git']['pr_on_done'])}", "",
            "[language]", f"artifacts = {json.dumps(d['language']['artifacts'])}", "",
        ]
        current = "\n".join(lines)
    body = re.sub(r"^\[templates\]\n(?:(?!\[).*\n?)*", "", current, flags=re.MULTILINE).rstrip("\n")
    table = "\n".join(f"{json.dumps(path)} = {json.dumps(sha)}" for path, sha in sorted(tracked.items()))
    return f"{body}\n\n[templates]\n{table}\n"


def _orca_actions(root: Path, main_checkout: Path, report: dict[str, Any], plan: Plan) -> list[dict[str, Any]]:
    info = report["orca"]
    if not info.get("ok"):
        plan.warnings.append(f"Orca actions skipped: {info.get('problem')}")
        return []
    actions: list[dict[str, Any]] = []
    if not info.get("repo_registered"):
        actions.append({"id": "repo-add", "command": ["repo", "add", "--path", str(main_checkout)]})
    if not info.get("base_branch"):
        ref = f"origin/{_default_branch(root)}"
        actions.append({"id": "set-base-ref",
                        "command": ["repo", "set-base-ref", "--repo", f"path:{main_checkout}", "--ref", ref]})
    verb = "update" if info.get("orca_skills_installed") else "install"
    actions.append({"id": f"skills-{verb}", "command": ["skills", verb, "--skill", "orca-cli"], "global": True})
    return actions


def _default_branch(root: Path) -> str:
    try:
        return git.run(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], root).removeprefix("origin/")
    except FactoryError:
        return git.current_branch(root) or "main"


def plan_init(root: Path, main_checkout: Path, deletes: list[tuple[str, str]]) -> dict[str, Any]:
    return build_plan(root, main_checkout, deletes).data()


def apply_init(
    root: Path, main_checkout: Path, state_dir: Path, plan_id: str, deletes: list[tuple[str, str]], excludes: list[str]
) -> tuple[dict[str, Any], list[str]]:
    """Apply exactly the confirmed plan (same id), minus the excluded items, with backups. Nothing
    is committed."""
    plan = build_plan(root, main_checkout, deletes)
    data = plan.data()
    if data["plan_id"] != plan_id:
        message = "the repository changed since that plan was shown (or the --delete options differ): plan again"
        raise FactoryError("plan_changed", message, EXIT_PRECONDITION)

    def excluded(path: str) -> bool:
        return any(path == ex.rstrip("/") or path.startswith(ex.rstrip("/") + "/") for ex in excludes)

    created = [i["path"] for i in plan.create if not excluded(i["path"])]
    modified = [i["path"] for i in plan.modify if not excluded(i["path"])]
    deleted = [i["path"] for i in plan.delete if not excluded(i["path"])]
    backup = _backup_dir(state_dir)
    for path in modified + deleted:
        target = backup / "files" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / path, target)
    (backup / "manifest.json").write_text(json.dumps({"created": created, "modified": modified,
                                                      "deleted": deleted}, indent=2) + "\n")

    tracked = {p: h for p, h in plan.tracked.items() if not excluded(p) or (root / p).exists()}
    plan.writes[".factory/config.toml"] = _config_text(root, doctor(root, main_checkout), tracked)
    for path in created + modified:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(plan.writes[path], encoding="utf-8")
    if ".factory/config.toml" not in created + modified and not excluded(".factory/config.toml"):
        (root / ".factory/config.toml").write_text(plan.writes[".factory/config.toml"], encoding="utf-8")
    for path in deleted:
        (root / path).unlink()

    results = []
    warnings = list(plan.warnings)
    for action in plan.orca:
        if excluded(action["id"]):
            continue
        try:
            command = action["command"]
            orca.run_plain(command) if command[0] == "skills" else orca.run(command)
            results.append({"id": action["id"], "ok": True})
        except FactoryError as exc:
            results.append({"id": action["id"], "ok": False, "error": exc.message})
            warnings.append(f"Orca action {action['id']} failed: {exc.message}")
    data = {"backup": backup.name, "created": created, "modified": modified, "deleted": deleted,
            "customized": [c["path"] for c in plan.customized], "orca": results}
    return data, warnings


def _backup_dir(state_dir: Path) -> Path:
    base = state_dir / "backups" / datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate, n = base, 1
    while candidate.exists():
        candidate, n = base.with_name(f"{base.name}-{n}"), n + 1
    candidate.mkdir(parents=True)
    return candidate


def restore(root: Path, state_dir: Path, name: str) -> dict[str, Any]:
    """Put back every file a run of `init --apply` modified or deleted."""
    backup = state_dir / "backups" / name
    manifest_file = backup / "manifest.json"
    if not manifest_file.is_file():
        raise FactoryError("backup_not_found", f"no backup named {name} in {state_dir / 'backups'}", EXIT_PRECONDITION)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    restored = []
    for path in manifest["modified"] + manifest["deleted"]:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup / "files" / path, root / path)
        restored.append(path)
    return {"backup": name, "restored": restored, "created_left": manifest["created"]}
