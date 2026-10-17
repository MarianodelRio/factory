# End-to-end checklist (T-31)

Real run on this machine (Linux, Orca 1.4.229, Claude Code in Orca terminals), started 2026-10-17.
Sample project: `~/Desktop/factory-sample` (Python, pytest, ruff), remote: a local bare repository
(no GitHub, by the person's choice), so the PR step checks the "open the PR yourself" path.
Codex is not available: the role swap (Claude lead / Codex reviewer and vice versa) for A-04/A-05
is deferred (see plan §6).

| # | Step | Criteria | Result | Notes |
|---|---|---|---|---|
| 0 | `uv tool install .` and `factory install-skill` | — | pass | `factory 0.1.0`; `factory-init` in `~/.claude/skills/` and `~/.agents/skills/` |
| 1 | `/factory-init` in `factory-sample` (analysis, then apply) | A-01, A-02, A-03 | pass | Plan applied after one confirmation: 4 skills in `.claude/skills/` and `.agents/skills/` (with roles and templates), `AGENTS.md` (69 lines) and `docs/conventions.md` filled from the real code with unconfirmed points marked, `CLAUDE.md` = `@AGENTS.md`, `.factory/config.toml` with `pytest`, `ruff check .`, `mypy src` (all pass), `.gitignore` entry, `permissions.ask` for approve/reject, backup manifest; repo registered in Orca with base ref `origin/main`; nothing committed. A second `factory init --plan` proposes no file changes (A-02). Found: doctor kept warning about the missing `build` check after configuration (fixed: only warns before the first install); every plan re-runs `orca skills update` (harmless, kept). |
| 2 | Commit the installation | — | pass (with a finding) | The agent first committed on a new branch (`chore/factory-init`, its general habit); asked, it fast-forwarded `main` and pushed to the local remote. Fixed in the `factory-init` skill: the commit goes on the base branch. The global `orca skills update` failed in the person's environment (npx cache); the Factory reported it as a warning and went on, as designed. |
