# swfactory

[![PyPI](https://img.shields.io/pypi/v/swfactory)](https://pypi.org/project/swfactory/)
[![npm](https://img.shields.io/npm/v/swfactory)](https://www.npmjs.com/package/swfactory)
[![CI](https://github.com/MarianodelRio/swfactory/actions/workflows/ci.yml/badge.svg)](https://github.com/MarianodelRio/swfactory/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/MarianodelRio/swfactory/blob/main/LICENSE)

A method, five agent skills and a CLI to build software with coding agents (Claude Code and Codex)
on local Orca: design and approve a change, implement each task in its own Orca workspace, review
it and publish it with evidence, follow everything on a live board, and keep what was learned in
the project's memory.

Orca runs the agents and the workspaces; the Factory brings the method and keeps its state in
readable files under `.factory/`. You talk to the agent in natural language (Spanish or English);
everything it writes to the repository is in English.

The [user guide](https://github.com/MarianodelRio/swfactory/blob/main/docs/guide.md) explains every
step in detail: what each skill does, what you decide, task states, notes and recovery, configuration and what to do when something goes wrong.

## Requirements

- Linux or macOS with Git (Windows is not supported).
- Orca **1.4.229** or later, running locally (remote hosts are
  refused), with its `orca` CLI on your `PATH`.
- [Claude Code](https://claude.com/claude-code) and/or Codex, available as agents in Orca.
- [uv](https://docs.astral.sh/uv/) (it provides Python 3.11+), with `~/.local/bin` on your `PATH`
  (`uv tool update-shell` adds it). Installing through npm also needs Node 18+.
- Optional: [`gh`](https://cli.github.com/), authenticated, to open pull requests. Without it the
  Factory pushes the task branch and leaves the PR to you.

## Install

Once per machine, with uv (recommended):

```bash
uv tool install swfactory   # the `swfactory` command, in ~/.local/bin
swfactory install-skill     # copies /factory-init to ~/.claude/skills/ and ~/.agents/skills/
```

Or with npm, which runs the same package through uv:

```bash
npm install -g swfactory
swfactory install-skill
```

The skills call `swfactory`, so it has to be installed, not only run once. To try it without
installing: `uvx swfactory --version` or `npx swfactory --version`.

**Upgrade:** `uv tool upgrade swfactory` (or `npm update -g swfactory`), then
`swfactory install-skill`, then `/factory-init` in each project to update its skills.

## The five skills

| Skill | What for |
|---|---|
| `/factory-init` | Prepare or update a repository: it analyzes it, proposes one plan (create, modify, delete with reason, respect, Orca actions) and applies it after a single confirmation, with backups. "solo el análisis" shows the plan only. |
| `/factory-design` | Design a change: it shows a short outline first, writes the design with its acceptance criteria and tasks, and has it critiqued. You approve it by saying "apruebo CHG-NNNN" (Claude asks for permission before the approval commit). |
| `/factory-implement` | Implement an approved task: from the main checkout it claims the task, creates its Orca workspace and launches the lead agent there. The lead writes tests and code, checkpoints, verifies every criterion with evidence, runs the reviews, updates the memory and finishes. |
| `/factory-board` | The live kanban board: opens it in an Orca tab (or your browser), closes it, gives its URL or saves a snapshot. |
| `/factory-status` | How everything is going, what needs you, notes and pauses for a running agent ("deja una nota en CHG-…", "pausa CHG-…"), recovering an interrupted task and memory maintenance. |

The skills call the `swfactory` CLI for everything that must be exact. You do not need to use it,
but you can: `swfactory --help` lists every command.

## Five-minute walkthrough

In a Claude Code (or Codex) terminal in Orca, at the root of your repository:

1. **Prepare the repo.**
   ```
   /factory-init
   ```
   Read the plan and confirm it. It registers the repo in Orca with its base branch, installs the
   five skills in the repo, writes `AGENTS.md`, `docs/` and `.factory/config.toml` with your test, lint
   and typecheck commands, and leaves everything uncommitted. Review the diff and commit it on the
   base branch (or ask the agent to).

2. **Design a change.**
   ```
   /factory-design add weekly recurrence to bookings
   ```
   Say OK to the outline; it writes `.factory/changes/CHG-0001/design.md` and `tasks.yaml`.
   Read it and approve it:
   ```
   apruebo CHG-0001
   ```
   Accept the permission prompt. "vale" or "ok" is not an approval.

3. **Implement a task.**
   ```
   /factory-implement CHG-0001-01 con claude, revisa claude
   ```
   ("with claude, review claude": the lead agent and the conformance reviewer.) A new workspace
   appears in Orca's sidebar with its agent; your main session is free. Open the workspace to watch
   it or talk to the agent.

4. **Follow it.**
   ```
   /factory-status
   /factory-board
   ```
   You see each task's state, acceptance criteria verified, reviews and the next step. The board
   is a live kanban in an Orca tab (and in your browser, at the address `swfactory board status`
   prints) with every agent and subagent running in each task. When the
   task is `done`, the lead offers to push the branch and open the PR.

5. **Integrate.** Review the PR and merge it yourself; the Factory never merges. Tasks that depend
   on it move from `pending` to `ready` once it is on the base branch.

## Good to know

- Approving or rejecting a design always needs your explicit message. Claude Code and Codex also
  ask for permission before running it (`.claude/settings.json` and `.codex/rules/factory.rules`;
  Codex reads project rules only if you trust the project in Codex).
- A task is `done` only when every acceptance criterion has evidence, the checks pass and the
  required reviews passed on the final commit.
- The Factory only pushes the task branch: no force push, merge or branch deletion.
- Orca may launch Claude with `--dangerously-skip-permissions` (its `agentDefaultArgs` setting).
  The approval rule still asks in that mode. `swfactory doctor` warns when Claude's own settings
  skip permission prompts (`bypassPermissions`); it cannot read Orca's setting.
- Orca does not say whether the agent inside a terminal is still running: `/factory-status` marks
  a task `interrupted` only when its terminal is closed. An agent that exited in an open terminal
  looks alive; more than 10 minutes without a checkpoint only gives a warning.
- Orca does not report the model an agent used; the Factory records the `--model` it passed.
- **Verified:** end to end on Linux with Claude Code and Orca 1.4.229. **Implemented, not yet
  verified on a real machine:** Codex (skills in `.agents/skills/`, the approval rule, reviews) and
  macOS (the CI runs the tests there). **Not supported:** Windows.

## Development

```bash
git clone https://github.com/MarianodelRio/swfactory && cd factory
uv sync                 # create the environment with dev tools
uv run pytest -q        # tests
uv run ruff check .     # lint
uv run mypy src         # typecheck
uv tool install .       # install the `swfactory` command from this checkout
```

Changes are listed in [CHANGELOG.md](https://github.com/MarianodelRio/swfactory/blob/main/CHANGELOG.md); how to publish a version is in
[docs/releasing.md](https://github.com/MarianodelRio/swfactory/blob/main/docs/releasing.md). License: [MIT](https://github.com/MarianodelRio/swfactory/blob/main/LICENSE).
