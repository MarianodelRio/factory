<!-- factory-template: skills/factory-help/references/overview.md@1 -->
# The Software Factory in short

## Skills

| Skill | What for |
|---|---|
| `/factory-init` | Prepare or update the repository: one plan (create, modify, delete, respect, migrate from another workflow), applied after one confirmation, with backups. |
| `/factory-design <what>` | Design a change: an outline first, then the design with acceptance criteria and tasks. Approve it with "apruebo CHG-12". |
| `/factory-build <task>` | Build approved tasks: each in its own Orca workspace with a lead agent ("con claude opus 5.5, revisa codex"). Several at once: "12.1 12.2", "CHG-12", "todas las ready". |
| `/factory-quick <what>` | A small change without design or workspace: change, checks, commit, PR or merge. |
| `/factory-status` | How everything goes, what needs the person, notes and pauses, recovering or re-launching a task, merges, cleanup, memory. |
| `/factory-board` | The live kanban board in an Orca tab or the browser. |
| `/factory-help` | This help. |

## The flow

design → "apruebo CHG-12" → `/factory-build 12.1` (workspace, branch pushed, lead agent) → tests,
code, checkpoints → verify (checks and every criterion, with evidence) → reviews → memory →
finish (`to_merge`) → publish: a PR the person merges, or a merge right away (the task's
`integrate`) → `done` once merged → tasks that depended on it become `ready` → remove the workspace.

## Ids

A change is `CHG-12` (folder `.factory/changes/CHG-12-<slug>/`), its tasks `CHG-12.1`, `CHG-12.2`.
They can be typed short: `12`, `12.1`. Ids like `CHG-0012-01` from earlier versions still work.

## Task states

| State | Meaning | Next |
|---|---|---|
| `pending` | A dependency is not `done` yet, or the design awaits approval | Finish and merge the dependency |
| `ready` | Can start | `/factory-build <task>` |
| `in_progress` | The lead agent works | Watch, leave a note, wait |
| `in_review` | Reviews running | Wait |
| `blocked` | Paused, design changed, reviews not converging, a decision or a missing dependency | Resolve it, then unblock; or hand it to another agent |
| `interrupted` | The lead's terminal closed early | "recupera <task>" |
| `to_merge` | Finished; not merged yet | Publish; merge the PR |
| `done` | Merged into the base branch | Nothing (remove its workspace if offered) |

## What to say

- "apruebo CHG-12" / "rechaza CHG-12 porque …" — approve or reject a design (always explicit).
- "deja una nota en 12.1: …", "pausa 12.1" — talk to a running lead.
- "recupera 12.1", "relanza 12.1 con claude" — recover an interrupted task or change its agent.
- "12.1 ya está mergeada" — when the Factory cannot see a merge.
- "sincroniza" — fetch `origin` and update the base branch.
- "abre el tablero", "¿cómo va todo?", "¿cómo está la memoria?".

## Configuration (`.factory/config.toml`)

`[checks]` test, lint, typecheck, build commands · `[review]` quality and conformance
(`auto`/`always`/`never`), `max_rounds` · `[git]` `pr_on_done` (`offer`/`always`/`never`),
`integrate` (`pr`/`merge`), `cleanup` (`ask`/`always`/`never`) · `[agents]` default lead, reviewer,
their models and efforts · `[board]` port, idle minutes.

## Updating the Factory

`uv tool upgrade swfactory`, then `swfactory install-skill`, then `/factory-init` in each project:
it updates the skills (files you customized are shown as a diff, never overwritten). From 1.x:
`/factory-implement` became `/factory-build`, `done` now means merged (tasks finished before are
checked once and may go back to `to_merge`), and older ids keep working.
