# End-to-end checklist (T-31)

Real run on this machine (Linux, Orca 1.4.229, Claude Code in Orca terminals), started 2026-10-17.
Sample project: `~/Desktop/factory-sample` (Python, pytest, ruff), remote: a local bare repository
(no GitHub, by the person's choice), so the PR step checks the "open the PR yourself" path.
Codex is not available: the role swap (Claude lead / Codex reviewer and vice versa) for A-04/A-05
is deferred (see plan §6).

| # | Step | Criteria | Result | Notes |
|---|---|---|---|---|
| 0 | `uv tool install .` and `factory install-skill` | — | pass | `factory 0.1.0`; `factory-init` in `~/.claude/skills/` and `~/.agents/skills/` |
