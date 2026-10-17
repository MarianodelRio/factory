"""`factory doctor` and `factory init` (design §3): analysis, plan, apply, backups and restore.

`doctor` only reads: it never writes to the repository or to Orca.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from factory import config, git, orca
from factory.output import FactoryError

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
