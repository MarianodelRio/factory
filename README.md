# Software Factory

A CLI and four agent skills to develop with coding agents (Claude Code and Codex) on local
Orca: design and approve a change, implement each task in its
own Orca workspace, review it and publish it with evidence, and keep what was learned in the
project's memory.

Orca runs the agents and the workspaces; the Factory brings the method and keeps its state in
readable files under `.factory/`. You talk to the agent in natural language (Spanish or English);
everything it writes to the repository is in English.

- Design (the contract): [`design_factory.md`](design_factory.md)
- Implementation plan and progress: [`implementation_factory.md`](implementation_factory.md)
- Real-run checklist: [`docs/e2e-checklist.md`](docs/e2e-checklist.md)

## Requirements

- Linux or macOS with Git.
- Orca **1.4.229** or later, running locally (remote hosts are
  refused), with its `orca` CLI on your `PATH`.
- [Claude Code](https://claude.com/claude-code) and/or Codex, available as agents in Orca.
- [uv](https://docs.astral.sh/uv/) (it provides Python 3.11+), with `~/.local/bin` on your `PATH`
  (`uv tool update-shell` adds it).
- Optional: [`gh`](https://cli.github.com/), authenticated, to open pull requests. Without it the
  Factory pushes the task branch and leaves the PR to you.

## Install

Once per machine:

```bash
git clone https://github.com/MarianodelRio/factory
cd factory
uv tool install .          # the `factory` command, in ~/.local/bin
factory install-skill      # copies /factory-init to ~/.claude/skills/ and ~/.agents/skills/
```

To upgrade later: `git pull && uv tool install --reinstall . && factory install-skill`, then run
`/factory-init` again in each project to update its skills.

## The four skills

| Skill | What for |
|---|---|
| `/factory-init` | Prepare or update a repository: it analyzes it, proposes one plan (create, modify, delete with reason, respect, Orca actions) and applies it after a single confirmation, with backups. "solo el análisis" shows the plan only. |
| `/factory-design` | Design a change: it shows a short outline first, writes the design with its acceptance criteria and tasks, and has it critiqued. You approve it by saying "apruebo CHG-NNNN" (Claude asks for permission before the approval commit). |
| `/factory-implement` | Implement an approved task: from the main checkout it claims the task, creates its Orca workspace and launches the lead agent there. The lead writes tests and code, checkpoints, verifies every criterion with evidence, runs the reviews, updates the memory and finishes. |
| `/factory-status` | How everything is going, what needs you, notes and pauses for a running agent ("deja una nota en CHG-…", "pausa CHG-…"), recovering an interrupted task and memory maintenance. |

The skills call the `factory` CLI for everything that must be exact. You do not need to use it,
but you can: `factory --help`, and the full list in [design §9](design_factory.md#9-cli).

## Five-minute walkthrough

In a Claude Code (or Codex) terminal in Orca, at the root of your repository:

1. **Prepare the repo.**
   ```
   /factory-init
   ```
   Read the plan and confirm it. It registers the repo in Orca with its base branch, installs the
   four skills in the repo, writes `AGENTS.md`, `docs/` and `.factory/config.toml` with your test, lint
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
   ```
   You see each task's state, acceptance criteria verified, reviews and the next step. When the
   task is `done`, the lead offers to push the branch and open the PR.

5. **Integrate.** Review the PR and merge it yourself; the Factory never merges. Tasks that depend
   on it move from `pending` to `ready` once it is on the base branch.

## Good to know

- Approving or rejecting a design always needs your explicit message. In Claude Code it also asks
  for permission before running the approval; Codex has no equivalent rule yet.
- A task is `done` only when every acceptance criterion has evidence, the checks pass and the
  required reviews passed on the final commit.
- The Factory only pushes the task branch: no force push, merge or branch deletion.
- Orca may launch Claude with `--dangerously-skip-permissions` (its `agentDefaultArgs` setting).
  The approval rule still asks in that mode. `factory doctor` warns when Claude's own settings
  skip permission prompts (`bypassPermissions`); it cannot read Orca's setting.
- v0.1.0 is verified with Claude Code only. Codex support follows the design but has not been
  checked on a real machine yet (see [`docs/spike-results.md`](docs/spike-results.md)).

## Development

```bash
uv sync                 # create the environment with dev tools
uv run pytest -q        # tests
uv run ruff check .     # lint
uv run mypy src         # typecheck
uv tool install .       # install the `factory` command
```
