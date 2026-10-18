# Lead agent flow

Your role: `roles/lead.md`. You own the task end to end, inside its workspace.

## Before writing code

- `swfactory task show <task> --json`: acceptance criteria, `complexity`, `review`, `scope`, state,
  last checkpoint and unread notes. If there is a previous checkpoint, continue from it.
- If this is a recovered attempt and the task already has reviews, verify and submit again, then run
  only the reviews whose latest verdict is not `pass` on the current commit.
- Read the approved design `.factory/changes/<change>/design.md`, `docs/conventions.md` and
  `docs/working-agreements.md`, and the decisions it cites.

## Work by complexity

| Complexity | Flow |
|---|---|
| `trivial` | Implement → checks |
| `normal` | Short plan → tests first → implement → checks → reviews |
| `complex` | Plan with a Planner subagent (`roles/planner.md`) → small steps with checkpoints → checks → reviews |

- **Checkpoint** after each significant step: `swfactory task checkpoint <task> --done "..." --next "..." --json`.
  Read the `notes` it returns. If `paused` is true, stop immediately and say so.
- **Commit** each coherent step on the task branch with a clear message.
- If something forces a design change (new requirement, architecture), stop:
  `swfactory task block <task> --reason "..." --json`. Do not improvise architecture.

## Verify and submit

1. `swfactory task verify <task> --json` runs the project checks and each AC command in this
   workspace. For a `manual` AC, produce real evidence (a note, `orca screenshot`, `orca snapshot`)
   and record it: `swfactory task verify <task> --manual AC-NN --evidence <file> --json`. Use
   computer use only when there is no programmatic way. Never record a secret file as evidence.
2. Re-read your whole diff (`git diff <base>...HEAD`).
3. If the task needs no reviews (`review: []` and none forced by the config or asked by the person),
   skip `submit` and go to "Memory, finish and publish". Otherwise run
   `swfactory task submit <task> --json`: it hands over pending notes first (stop if `paused`) and
   lists the reviews the task needs.

## Reviews

- **Quality** (if required): start a read-only subagent with `roles/quality_reviewer.md` on the
  diff. If your client has no subagents, run `swfactory task review <task> --type quality --agent <agent> --json`
  with the conformance reviewer's provider (or your own if there is none).
- **Conformance** (if required): `swfactory task review <task> --type conformance --json` (add
  `--agent <claude|codex>` if no reviewer was chosen at launch). Orca opens the reviewer in this
  workspace.
- For a reviewer launched in Orca, read its terminal (the `terminal` in the answer) with
  `orca terminal read --terminal <terminal>` until its final JSON appears; `orca terminal wait`
  can return before the agent has finished, so never take its output as the answer by itself.
- Each reviewer ends with JSON (`type`, `commit`, `verdict`, `findings`). Save it to a file outside
  the repo (so it is not committed) and record it: `swfactory task review <task> --record <file> --json`.
- Fix `blocker` and `major` findings, verify again and repeat that review. After two rounds
  without `pass` the CLI blocks the task with the findings saved: stop and tell the person.
  `minor` findings do not block; they go to the PR.
- Reviewers never edit files or approve anything.

## Memory, finish and publish

1. Ask the questions of `memory.md`, write what applies on this branch and commit it (it goes in
   the same PR).
2. `swfactory task finish <task> --memory "<summary of what you proposed>" --json` (or
   `--memory none`). It hands over pending notes first: stop if `paused`. If it answers
   `gates_not_met`, fix each item in `error.details`. Mention any "changed outside the task scope"
   warning to the person; the conformance review decides whether it is a deviation.
3. Publishing follows `git.pr_on_done` in `.factory/config.toml`: `offer` (default) → offer
   "push the branch and open the PR?"; `always` → do it; `never` → do not. If the person asks,
   do it directly: `swfactory task publish <task> --json`. Running it again pushes later commits to
   the same PR. If `gh` is missing or the push is rejected, report it: the branch stays intact and
   the PR is left to the person. Never merge, force push, or delete branches or workspaces.
