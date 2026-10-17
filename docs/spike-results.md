# Spike results (T-01)

Machine: Linux, Orca 1.4.229, Claude Code 2.1.302 in Orca terminals. Codex is not installed
(the person has no licence). Checked on 2026-10-17 with the person.
Raw outputs are recorded, with personal paths and names redacted, in `tests/fixtures/orca/`
(see the README there).

## Answers to design §10.3

| # | Question | Answer | Evidence |
|---|---|---|---|
| 1 | All Orca workspaces are worktrees of the same clone | **Yes** | A fresh `orca worktree create` and an older workspace both appear in `git worktree list --porcelain` of the main checkout; the first entry is the main checkout. |
| 2 | Orca chat and agent terminal load the repo skills (Claude, Codex) | **Claude terminal: yes. Chat: not verified (not used). Codex: not verified.** | `agent launch --prompt "factory probe"` → `Skill(factory-probe)` loaded; `--prompt "/factory-probe CHG-0001-01"` also invokes the skill, so the brief `/factory-implement <id>` works as a prompt. The person works only with Claude in terminals. |
| 3 | Claude "ask" rule applies to approve/reject in the usual modes; Codex equivalent | **Claude: yes**, even with `--dangerously-skip-permissions`. **Codex: not verified.** | Probe repo with `permissions.ask: ["Bash(echo factory-ask-probe:*)"]`: Claude asked before running the command in bypass mode (person). |
| 4 | How Codex offers subagents | **Not verified** (no Codex). Claude has subagents (Agent tool). | — |
| 5 | Lead and reviewer agents coexist in one workspace | **Yes (Claude + Claude)** | Two `agent launch` calls in `spike-a` → two terminals with `agentIdentity: "claude"`, both working. |
| 6 | Card states, model reported, non-local host | **Cards: `todo`, `in-progress`, `in-review`, `completed`** (+ comment, unread, display name). **Model: not reported** in any JSON. **Local: `status.result.target.kind == "local"`**, `hostId`/`executionHostId == "local"`. | `worktree set` fixtures; unknown status → warning `UNKNOWN_WORKSPACE_STATUS`, saved, shown as `in-progress`. |
| 7 | Real `--json` responses | **Recorded** | `tests/fixtures/orca/*.json`. Not recordable here: a lost launch reply (error with `operationId`) and a non-local host. |

## Design changes (copied to plan §6; 1–4 approved by the person and applied in design v1.5)

1. **Liveness (§7.2).** Orca does not report whether a terminal agent is still running: after
   the agent exits, its terminal stays `connected: true` with `agentIdentity` (the shell
   remains); `worktree ps` / `reference find` return `agents: []`. Only a closed terminal is
   visible (`connected: false`, `orphaned: true`, `exitCause`). The attempt must store Orca's
   terminal handle (`result.outcome.handle`) to query it.
2. **Base branch (§8, T-13).** `orca repo show` returns `worktreeBaseRef` only after
   `orca repo set-base-ref`; otherwise there is no field (Orca still picks
   `refs/remotes/origin/main` for new worktrees, and `origin/HEAD` is not set in this clone).
3. **Model (§1.4 attempts).** Orca does not report the model; the Factory can only record the
   `--model` it passed (`null` = agent default).
4. **Permissions (§10.1).** Orca's own setting `agentDefaultArgs` launches Claude with
   `--dangerously-skip-permissions` (and bypass flags for other agents). The Factory does not
   add those flags, and the "ask" rule still holds, but the agents do run without sandbox or
   prompts. Proposal: `factory doctor` reports it as the "client permission mode" warning it
   already plans (§3.1 step 1); no change to the launch.
5. **Codex** items (2, 3, 4, 5 for Codex) stay not verified until Codex is available.

Notes that need no design change:
- `orca worktree create` runs the repo's Orca setup hook by default (repo policy); the Factory
  follows the repo policy and passes no `--setup` flag.
- `orca agent launch` returns `result.operationId` on success; `--retry-launch <operationId>` is
  documented for a lost reply.
- `terminal wait --for tui-idle` can return before the agent finishes; the Factory does not use it.
- `orca search` is off on this machine (`kind: "unavailable", reason: "disabled"`); the person
  keeps it off for now. Recovery works without it.

## Findings collected without the person (read-only commands)

- `git worktree list --porcelain` in the main checkout lists the Orca workspace
  `~/orca/workspaces/factory/test` (branch `MarianodelRio/test`): Orca workspaces are Git
  worktrees of the same clone; the first entry is the main checkout.
- `orca status --json` → `result.target.kind = "local"`, `result.runtime.reachable`,
  `result.runtime.appVersion`. No model information.
- `orca host list --json` → hosts with `kind` (`local`, `ssh`); worktrees and terminals carry
  `hostId` / `executionHostId` (`"local"`).
- `orca repo show --json` has **no base ref field** when none was set; each worktree in
  `orca worktree list --json` carries `baseRef` (e.g. `refs/remotes/origin/main`).
  `orca repo set-base-ref` exists.
- Card statuses (`orca worktree set --workspace-status`): defaults `todo`, `in-progress`,
  `in-review`, `completed`; custom ids allowed. `--comment`, `--unread|--read`, `--display-name`.
- `orca agent launch` supports `--model`, `--effort` (requires `--model`), `--retry-launch
  <operationId>`; result in `result.outcome` (`kind` structured|terminal, `handle`) and `result.operationId`
  (`orca worktree create --agent` nests the same data under `result.launch`).
- `orca terminal list --json` → per terminal `agentIdentity` (`claude`), `connected`,
  `worktreeId`, `lastOutputAt`, `preview`. `orca reference find` reports agent `liveness`
  (`live`, `unverifiable`, `exited`).
- Claude agents in Orca terminals were started as `claude --dangerously-skip-permissions`
  (terminal preview) — relevant for item 3.
- The repo's Orca setup hook (`pnpm install`, policy `run-by-default`) runs on
  `worktree create` unless `--setup skip`.
- Codex: no `codex` binary on the machine, no `~/.codex`; `orca account list` reports
  "Codex not signed in".
- `orca search --index-status` answers; search itself is disabled on this machine (see below).
- Orca setting `agentDefaultArgs` (profile state) adds `claude: --dangerously-skip-permissions`
  (and the equivalent bypass flags for other agents) to every agent Orca launches.

## Decisions taken with the person

- 2026-10-17: the person has no Codex licence. Codex items stay **not verified**; the Factory
  keeps Codex support as designed (skills in `.agents/skills/`, `--agent codex`) so it works
  once Codex is available.
- 2026-10-17, item 3 (Claude): with `.claude/settings.json` `permissions.ask:
  ["Bash(echo factory-ask-probe:*)"]`, `claude --dangerously-skip-permissions` **still asked**
  before running the command (checked by the person). The default mode was not tested: it
  prompts for any command not explicitly allowed, and "ask" rules take precedence over allow
  rules.

## Sandbox run (2026-10-17, repo `factory-spike` registered in Orca with the person's consent)

- `orca worktree create --repo id:<repo> --name spike-a --no-parent --setup skip` → new Git
  worktree under `~/orca/workspaces/factory-spike/spike-a`, branch `<gitUser>/spike-a`,
  `baseRef: refs/remotes/origin/main`, listed by `git worktree list --porcelain` of the main
  checkout (item 1 confirmed on a fresh workspace). Default card status: `in-progress`.
- `orca agent launch --agent claude --worktree id:<repo>::<path> --prompt "factory probe"` →
  `result.operationId`, `result.outcome.kind = "terminal"`, `result.outcome.handle =
  term_...`, `receipt.reason = "user_default"`. Orca ran
  `claude '--dangerously-skip-permissions' 'factory probe'` (prompt passed as CLI argument).
  The repo skill loaded (`Skill(factory-probe)` → expected reply). Item 2 (Claude, terminal): yes.
- A second `agent launch` in the same workspace (with `--model claude-sonnet-5-5 --effort low`)
  started a second Claude terminal next to the first. Item 5 (Claude): yes.
- Model: no launch, terminal or worktree JSON reports the model. It is only visible in the
  terminal banner ("Sonnet 5.5 with low effort"). The Factory can only record the model it
  passed with `--model`.
- Liveness: after the agent exits (`/exit`), its terminal stays `connected: true` with
  `agentIdentity: "claude"` (the shell remains); `worktree ps` and `reference find` return
  `agents: []` for terminal-launched agents. After the terminal is closed, `terminal show`
  returns `connected: false`, `orphaned: true`, `exitCause: {kind: ...}`.
- Cards: `worktree set --display-name --workspace-status in-review --comment --unread` all
  applied. Unknown status (`blocked`) → `ok: true`, value saved, warning
  `UNKNOWN_WORKSPACE_STATUS`, board shows `in-progress`.
- `orca search ... --json` → `result: {kind: "unavailable", reason: "disabled"}` (Agent Session
  History is off in Orca settings).
- 2026-10-17, item 2 (chat): the person tried from the Orca UI; a terminal agent opened (new
  terminal `agentIdentity: claude`) and loaded the skill again. The person will always work
  with Claude in terminals and does not want Orca's Chat UI: chat is **not verified** and not
  needed for v1.
