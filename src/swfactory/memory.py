"""`swfactory memory check`: mechanical checks of the project memory. Read-only."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

AGENTS_MAX_LINES = 120
ADR_FILE = re.compile(r"^(\d{4})-.+\.md$")
SUPERSEDED = re.compile(r"^Status:\s*superseded", re.IGNORECASE | re.MULTILINE)
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def check(root: Path) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    agents = root / "AGENTS.md"
    if agents.exists():
        lines = len(agents.read_text(encoding="utf-8").splitlines())
        if lines > AGENTS_MAX_LINES:
            findings.append(_finding("agents_md_size", agents, root, f"{lines} lines (keep it within 120)"))

    decisions = root / "docs" / "decisions"
    adrs = sorted(p for p in decisions.glob("*.md") if ADR_FILE.match(p.name)) if decisions.is_dir() else []
    by_number: dict[str, list[str]] = {}
    for adr in adrs:
        by_number.setdefault(adr.name[:4], []).append(adr.name)
    for number, names in by_number.items():
        if len(names) > 1:
            findings.append(_finding("duplicated_adr_number", decisions, root, f"{number}: {', '.join(names)}"))
    superseded = {adr.name for adr in adrs if SUPERSEDED.search(adr.read_text(encoding="utf-8"))}

    for doc in _documents(root):
        for target in LINK.findall(doc.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            path = target.split("#", 1)[0]
            if not (doc.parent / path).exists():
                findings.append(_finding("missing_link", doc, root, f"links to {path}, which does not exist"))
            elif Path(path).name in superseded and doc.parent != decisions:
                findings.append(_finding("superseded_cited", doc, root, f"cites superseded decision {Path(path).name}"))
    return {"findings": findings}


def _documents(root: Path) -> list[Path]:
    docs = [root / name for name in ("AGENTS.md", "CLAUDE.md") if (root / name).exists()]
    if (root / "docs").is_dir():
        docs += sorted((root / "docs").rglob("*.md"))
    return docs


def _finding(kind: str, path: Path, root: Path, detail: str) -> dict[str, str]:
    return {"check": kind, "file": str(path.relative_to(root)), "detail": detail}
