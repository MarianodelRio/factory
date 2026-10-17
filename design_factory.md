# design_factory.md — Software Factory Design

> **Version:** 1.4 — simplified design on top of Orca, pending final approval  
> **Reference date:** October 17, 2026  
> **Goal:** A simple, usable and powerful Factory to develop with agents (Claude Code and Codex) on **local Orca**, operated from the chat with four skills.  
> **Approach:** start with the minimum that adds value and iterate. What is not here will be added when real use justifies it.

## 0. Summary

### 0.1 What it is

A repository of skills, templates and a small CLI that prepares any Git repository to work with agents using a method: **design, approve, implement in an isolated workspace, review, publish a PR and remember what was learned**.

The Factory does not run agents or manage worktrees on its own: **Orca does that**. The Factory provides the method and keeps its state in readable files.

### 0.2 How it is used

The person works in the Orca agent chat or terminal and uses four skills:

| Skill | What for |
|---|---|
| `/factory-init` | Prepare or update the repo: analyzes it, proposes what to create, change and delete, and applies it after one confirmation. |
| `/factory-design` | Research and design a change, approve or reject it when the person says so, and generate its tasks. |
| `/factory-implement` | Implement an approved task in its own Orca workspace, with tests, reviews, memory and PR. |
| `/factory-status` | See how everything is going, leave notes or pause, recover interrupted tasks and review the memory. |

Under the hood, the skills use the `factory` CLI for everything that must be exact (claiming tasks, approving, recording state). The person does not need to use the CLI, but can.

### 0.3 Split between Orca and the Factory

| Orca | Factory |
|---|---|
| Workspaces (worktrees) and branches | Changes, designs and approval |
| Launching Claude/Codex agents with model and effort | Tasks, AC, dependencies and their state |
| Knowing whether an agent is still alive | Reviews, evidence and the definition of "done" |
| Workspace cards in the sidebar | What is shown on those cards |
| Browser, computer use, session search | Project memory and documentation |

### 0.4 Principles

- **Simple on the outside**: four skills and natural language. Any complexity stays inside.
- **Delegate to Orca before building**: if Orca does it, the Factory does not reimplement it.
- **Readable files**: all state is Markdown, YAML or JSON that can be opened and read.
- **One source of truth per datum**: Orca rules over workspaces and sessions; the Factory over designs, tasks and evidence.
- **Nothing without confirmation**: nothing is deleted, overwritten or approved unless the person sees it and accepts it.
- **Done means proven**: a task is done when every acceptance criterion has evidence, not when the agent says so.
- **Reviewed memory**: project memory changes only with human review: what tasks generate goes in their PR; what `/factory-init` and maintenance generate is shown as a diff and the person makes the commit.
- **Neutral between Claude and Codex**: any artifact can be continued by the other provider without the original chat.
- **Respect what exists**: the repo's rules, CI and protections always prevail.

### 0.5 Out of scope for now

These may be added later if needed: coordination of several tasks in parallel under an orchestrator; OpenSpec; GitHub Issues or another task manager; HTML dashboard; team profiles; remote Orca hosts; scheduled automations; automatic task retries; starting a task before its dependencies are integrated. Never part of it: automatic merge or deployment, or support for IDEs other than Orca.

---

## 1. Architecture and files

### 1.1 Components

```text
Person (chat / agent terminal in Orca)
            |
   4 Factory skills  ── query Orca directly (guides, browser, search)
            |
   factory CLI (Python, standard library + PyYAML)
     ├── Factory files (.factory/)
     ├── Orca client (operations that change state: workspaces, agents, cards)
     └── git / gh
```

- **Skills**: talk to the person, research, write and decide. They can use Orca directly to **query or interact** (load its guides with `orca skills get orca-cli`, browser, `orca search`), without copying its guides.
- **CLI**: exact, repeatable operations. It validates, claims, records and answers the skills in `--json`. It does not call models. It is the **only one that writes** Factory state.
- **Orca client**: part of the CLI and the only code that performs **Orca operations that change state** (create workspaces, launch agents, update cards). It always uses `--json` and checks that commands exist with `orca agent-context --json`.
- **Requirements**: Git, Orca (minimum version in config), Python 3.11+ (installed with `uv tool install`, which brings its own Python), PyYAML as the only runtime dependency, and at least Claude Code or Codex available in Orca. `gh` is optional (without it, PRs are not opened automatically).

### 1.2 Factory repository

```text
software-factory/
├── pyproject.toml           # installs the `factory` command (uv tool install)
├── src/factory/
│   ├── cli.py
│   ├── init.py              # analysis, plan, apply, backups
│   ├── design.py            # registration, digest, approval, tasks
│   ├── tasks.py             # state, claim, reviews, closing
│   ├── memory.py
│   ├── orca.py              # Orca client
│   └── git.py               # commits, push, PR
├── templates/
│   ├── skills/              # the 4 skills (for .claude/ and .agents/)
│   ├── roles/               # instructions for each role (§5.3)
│   ├── design/              # design template
│   └── docs/                # documentation and memory templates
└── tests/                   # includes a fake `orca` with recorded JSON responses
```

### 1.3 Files in a project

```text
my-repository/
├── AGENTS.md                         # short index, commands, critical rules
├── CLAUDE.md                         # minimal: @AGENTS.md
├── .claude/
│   ├── skills/factory-*/SKILL.md     # the 4 skills
│   └── settings.json                 # adds the "ask" rule for approve and reject (§4.4)
├── .agents/skills/factory-*/SKILL.md # the 4 skills for Codex
├── (Codex config)                    # equivalent approval rule; file to be confirmed (§10.3)
├── docs/
│   ├── product.md
│   ├── architecture.md
│   ├── conventions.md
│   ├── working-agreements.md
│   └── decisions/
│       ├── README.md
│       └── 0001-*.md
└── .factory/
    ├── config.toml                   # versioned
    ├── changes/                      # versioned
    │   └── CHG-0012/
    │       ├── design.md
    │       ├── tasks.yaml            # only after approval
    │       ├── approval.json         # only after approval
    │       └── rejection.json        # only if rejected
    └── state/                        # NOT versioned (.gitignore)
        ├── CHG-0012-01.json
        ├── CHG-0012-01.events.jsonl
        ├── CHG-0012-01.lock
        ├── evidence/CHG-0012-01/...
        └── backups/<YYYYMMDD-HHMMSS>/...
```

- **Versioned** (`.factory/config.toml`, `.factory/changes/`, `docs/`): what defines what is done and why. It is visible in Git and travels with the repo.
- **Live state** (`.factory/state/`): ignored by Git. It lives **in the main checkout** and all workspaces write there through the CLI, which locates it with `git worktree list --porcelain` (first worktree = main checkout). This way there is a single state, visible in the editor, without dirtying any branch.
- The structure of `docs/` adapts to the repo (§6.2): in a small one, `AGENTS.md` and `conventions.md` may be enough.

### 1.4 File formats

**Design digest**: SHA-256 of the content of `design.md` with line breaks normalized to LF. It is the only thing that is approved: the tasks are part of `design.md` (§4.3), and `tasks.yaml` is just a copy generated on approval. The CLI recalculates it whenever it needs to compare.

**IDs**: when registering a change, the CLI assigns it the next free number by looking at `.factory/changes/` (`CHG-0013`). Tasks are `<change>-NN` and their ids do not change if the change is approved again (a new task gets a new number). ADRs are numbered the same way when written. If two branches create the same id, the conflict shows up on integration and is resolved by hand.

`tasks.yaml` (versioned, copied from the design on approval):

```yaml
change: CHG-0012
design_digest: sha256:3f1c...
tasks:
  - id: CHG-0012-01
    title: Add recurrence model and validation
    depends_on: []
    complexity: normal              # trivial | normal | complex
    review: [quality]               # [] | [quality] | [conformance] | [quality, conformance]
    scope: ["src/bookings/**", "tests/bookings/**"]   # optional
    acceptance:
      AC-01: "pytest tests/bookings/test_recurrence.py::test_weekly"
      AC-02: manual                 # manual or visual evidence
  - id: CHG-0012-02
    title: Sync recurring bookings with calendar
    depends_on: [CHG-0012-01]
    complexity: complex
    review: [quality, conformance]
    acceptance:
      AC-03: "pytest tests/integration/test_calendar.py"
```

`approval.json` (versioned):

```json
{
  "change": "CHG-0012",
  "design_digest": "sha256:3f1c...",
  "approved_by": "user@example.com",
  "approved_at": "2026-10-17T10:42:00Z",
  "method": "chat",
  "message": "apruebo CHG-0012"
}
```

`approved_by` is the Git `user.email`. `method` is `chat` if it was approved from the skill and `terminal` if it was confirmed by typing the id. `message` stores the person's literal text, in the language they wrote it in (here, Spanish: "apruebo CHG-0012" means "approve CHG-0012"). `rejection.json` has the same format with `reason` instead of `message`.

`state/CHG-0012-01.json` (local):

```json
{
  "task": "CHG-0012-01",
  "state": "in_review",
  "blocked_reason": null,
  "workspace": {"orca_id": "repo-123::/home/me/orca/CHG-0012-01", "branch": "<assigned by Orca>"},
  "attempts": [
    {"id": 1, "agent": "codex", "model": null, "started_at": "...", "ended_at": null, "result": null}
  ],
  "last_checkpoint": {"at": "...", "done": ["Model and tests"], "next": "Run full suite"},
  "acceptance": {
    "AC-01": {"status": "verified", "evidence": "evidence/CHG-0012-01/AC-01.txt"},
    "AC-02": {"status": "pending", "evidence": null}
  },
  "checks": {"status": "passed", "at": "..."},
  "reviews": [
    {"type": "quality", "reviewer": "codex-subagent", "round": 1, "commit": "abc123", "verdict": "pass", "findings": []}
  ],
  "notes": [{"at": "...", "text": "...", "read": false}],
  "memory": null,
  "commits": ["abc123"],
  "pull_request": null
}
```

**State writing**:
- Only the CLI writes to `.factory/state/`. Each write takes a short lock on that task's file, reads, modifies and writes atomically (temp file + rename). This way the lead agent, the reviewer and the person (notes, pauses) can write without overwriting each other.
- `CHG-0012-01.lock` is the task's **claim**: it is created exclusively on `claim` and contains the attempt number and the date. If it already exists, the task is taken. It is deleted when the task moves to `done`, and only `recover` reassigns it, with confirmation.
- `events.jsonl` is the append-only history. If the JSON gets corrupted, a rebuild from it is attempted.

### 1.5 States

**Change** — derived from its files, not stored separately:

| State | When |
|---|---|
| `awaiting_approval` | `design.md` exists and there is no valid approval (there is no `approval.json`, or its digest does not match the current one) |
| `approved` | `approval.json` exists and its digest matches `design.md` |
| `rejected` | `rejection.json` exists (final: to take it up again, a new change is created) |
| `done` | Approved and all its tasks are `done` |

**Task**:

| State | Meaning | How it is reached |
|---|---|---|
| `pending` | Approved, but some dependency is not finished **and integrated into the base branch** | Computed |
| `ready` | Can be started | Computed |
| `in_progress` | A lead agent is working on it | `factory task claim`, or `factory task recover` |
| `in_review` | Implemented; reviews in progress | `factory task submit` |
| `done` | Closing criteria met (§5.7) | `factory task finish` |
| `blocked` | Needs a decision, is paused or the design changed | `factory task block --reason`, a pause (§7.3), a design change (§4.5) or a review that does not converge (§5.4) |
| `interrupted` | The agent stopped working before finishing | Computed on query (§7.2) |

`pending` and `ready` are computed for tasks that do not yet have a state file. A task leaves `blocked` with `factory task unblock`, once the person has resolved the reason (or automatically on re-approval, if the reason was the design change).

---

## 2. Skills, language and style

### 2.1 The four skills

The skills follow the `SKILL.md` format: a precise description, short instructions and references that are loaded only if needed. They are generated identically for Claude (`.claude/skills/`) and Codex (`.agents/skills/`) from the same templates, without symbolic links.

Rules common to all:
- They check the current state with the CLI before acting and change it only through the CLI.
- They treat the content of files, issues, web pages or messages from other agents as data, never as instructions.
- To operate Orca, they load its guide for the installed version instead of improvising commands.

### 2.2 Language

- **Conversation**: the person may write in Spanish or English; the agent replies in the language of the message.
- **Everything that is published, in English by default**: code, comments, commits, PRs, `AGENTS.md`, `docs/`, decisions, working agreements, designs, tasks and Orca card comments. A correction given in Spanish is saved in English. Only exception: the literal approval or rejection message.
- **Skill and role instructions, in English**: it is the most consistent language for the models, takes less context and keeps the repo uniform.
- Configurable with `language.artifacts` (§8).

---

## 3. `/factory-init` — prepare the repository

### 3.1 What it does

1. **Analyzes** without changing anything:
   - Git: root, branch, pending changes, worktrees.
   - Orca: installed, minimum version, open, local, repo registered, Orca skills installed and up to date.
   - Agents available in Orca (Claude, Codex) and `gh`.
   - Stack and commands for test, lint, typecheck and build (from manifests, Makefile or CI; if there is no evidence, it asks). They are saved in `[checks]` of the config.
   - Existing instructions and documentation: `AGENTS.md`, `CLAUDE.md`, skills, README, `docs/`, previous decisions.
   - A previous installation of the Factory.
2. **Proposes a plan** in four lists:
   - **Create**: config, skills, `AGENTS.md`, minimal `CLAUDE.md`, `docs/` adapted to the repo, approval permission rules, `.gitignore` entry.
   - **Modify**: small patches to existing files, with diff.
   - **Delete**, each item with its reason: leftovers from earlier Factory versions, duplicated or contradictory instructions (consolidated into `AGENTS.md`), files of tools that are no longer used, empty or outdated documentation. **Never** code, tests, CI, secrets or anything whose purpose it cannot explain.
   - **Respect**: what is left untouched and why.

   And the actions in Orca: register the repo and install or update its skills (global installation, stated clearly).
3. The person **confirms once** or excludes items ("todo menos borrar X", or "everything except deleting X").
4. **Applies**: saves a copy of everything it deletes or modifies in `.factory/state/backups/<YYYYMMDD-HHMMSS>/`, writes the files, generates the initial documentation from evidence (marking what it could not confirm) and validates that everything works.
5. **Summarizes** what was done, what remains to be completed in `docs/` and how to start. It leaves the changes uncommitted: the person reviews the diff and makes the commit (or asks the agent to).

### 3.2 Rules

- **Idempotent**: repeating it does not duplicate anything.
- **Update without overwriting**: each file installed from a template carries a `factory-template: <name>@<version>` mark, and the config stores the hash of what was installed. If a file no longer matches that hash, it is considered customized: the diff is shown and it is not overwritten without confirmation. Approved designs, decisions and working agreements are never touched.
- If Git or Orca is missing, it stops and explains what is needed.
- Asking for "only the analysis" ("solo el análisis") shows the plan without applying anything.
- What was deleted can be restored from the backup.
- It does not install hooks in Claude or Codex: Orca already installs its own.

---

## 4. `/factory-design` — design and approve

### 4.1 Change and tasks

A **change** (`CHG-0012`) is what is researched, designed and approved. Its design includes one or more **tasks** (`CHG-0012-01`), which are what gets implemented. The design does not modify product code.

For truly trivial changes the Factory is not needed: just ask an agent directly.

### 4.2 How the skill works

1. **Reads the project context**: `AGENTS.md` and whatever applies from `docs/` (product, architecture, conventions, current decisions, working agreements).
2. **Researches the real code**: locates the files that will be touched, the existing patterns worth imitating and the current tests. It distinguishes what was verified from what was assumed.
3. **Clarifies** what is ambiguous: it first researches and proposes options; it asks only what changes the design.
4. **Writes the design** with the template (§4.3), proportional to the size of the change. For each task it decides its complexity and reviews, using the table in §5.4 as a guide.
5. **Self-reviews** with a critical subagent (*Design critic* role, §5.3) that answers one question: *could another agent implement this correctly without having seen this conversation?* The agent fixes issues before presenting.
6. **Registers** the change (`factory design register`): the CLI assigns it an id and validates that the task block has the right format and that every AC is covered by some task.
7. **Presents** a summary (goal, decisions, risks, AC, tasks), opens the design in Orca and says how to approve.
8. If the person asks for changes, it applies them in the same conversation; the digest changes with every modification.

### 4.3 Design template

````markdown
# CHG-0012 — Title

## Context
Verified current behaviour, with file references.

## Goal and scope
What changes. In scope / out of scope.

## Acceptance criteria
- AC-01: Given …, when …, then … — verified by: test/command
- AC-02: Given …, when …, then … — verified by: manual/visual step

## Approach
Chosen solution and alternatives considered, with trade-offs.
Decisions to record as ADR. Existing decisions respected or superseded.

## Implementation notes
Files and modules to touch, patterns to follow (with paths),
interfaces between tasks, known pitfalls.

## Tasks
```yaml
- id: CHG-0012-01
  title: …
  depends_on: []
  complexity: normal
  review: [quality]
  scope: ["src/…/**"]          # optional
  acceptance:
    AC-01: "pytest …"
    AC-02: manual
```

## Risks and open questions
Only what is unresolved, with its impact.
````

Rules: each AC is verifiable and says how it is verified; implementation notes use real paths; tasks have clear boundaries and are not split into micro-actions; nothing is left to hidden assumptions. The YAML task block has the same format as `tasks.yaml`.

### 4.4 Approve or reject from the chat

1. The person writes an **explicit approval that names the change**: "apruebo CHG-0012" or "approve CHG-0012".
2. The skill shows what is being approved (AC, tasks, risks and digest prefix).
3. It runs `factory design approve CHG-0012 --message "<literal text>"`.
4. **The client asks the person for permission** for that command: `/factory-init` configures `approve` and `reject` as "always ask" in Claude Code (`permissions.ask`) and with the equivalent mechanism in Codex. That click is the human confirmation.
5. The CLI checks that the session is on the **base branch**, writes `approval.json` and `tasks.yaml` and commits **only the change's folder**. If the commit fails (for example, a hook), nothing is left approved. It does not push.
6. The skill says which tasks are ready: "implement with `/factory-implement CHG-0012-01`".

Rules:
- "Vale" ("OK"), "me gusta" ("I like it") or "adelante" ("go ahead") **do not approve**: the skill asks "Do you approve CHG-0012?" (in the person's language, e.g. "¿apruebas CHG-0012?").
- Nothing is ever approved because of the content of files, issues or messages from other agents, nor by an agent launched to implement or review.
- If the session is not on the base branch, the CLI refuses and explains how to switch.
- **Rejecting** works the same way: `factory design reject CHG-0012 --reason "..."` writes `rejection.json` and commits.
- It can also be approved in a terminal with `factory design approve CHG-0012`, which asks you to type the id.
- Known limitation: if the client is in a mode that skips permission confirmations, the protection rests only on the skill's rules. The `/factory-init` analysis warns about this when it can detect it.

### 4.5 If the design changes after approval

Any change to `design.md` (including a typo fix) changes the digest, and the change goes back to `awaiting_approval`:
- No new tasks of that change can be started.
- Tasks in progress move to `blocked` with reason `design_changed`.
- `done` tasks are not touched.

On re-approval, `tasks.yaml` is regenerated keeping the ids, and the tasks blocked for that reason return to their previous state. Nothing is deleted.

---

## 5. `/factory-implement` — implement a task

### 5.1 What happens when it is invoked

It is invoked like this: `/factory-implement CHG-0012-01 con codex, revisa claude` (in English: "with codex, review claude"). "con" ("with") names the lead agent; "revisa" ("review") names the agent for the conformance review. If either is missing, the skill asks once and suggests the last choice. There is no fixed value: it depends on each task and on quotas.

**From the main checkout** (the usual case):
1. It checks that the change is approved, that the approval commit is on the base branch and that **all dependencies are `done` and integrated into the base branch**. If any is not, the task stays `pending` and the skill explains why.
2. `factory task claim CHG-0012-01`: claims the task and Orca creates a **new workspace with its branch** from the base branch (`orca worktree create`), which appears in the sidebar. If creation fails, the claim is undone.
3. `factory task launch CHG-0012-01 --agent codex`: Orca opens the lead agent in that workspace (`orca agent launch`) with a brief that is literally `/factory-implement CHG-0012-01` and the chosen review agent.
4. The main session does not move: it reports "CHG-0012-01 launched; open it from the sidebar" and is free.

**Inside the task's workspace** (the skill detects it with Git): the session acts directly as the lead agent and does not launch another.

Uncommitted changes in the main checkout do not carry over to the workspace, because it starts from a commit of the base branch.

The person can enter the workspace whenever they want: watch the agent work, write to it, correct it or work on the branch themselves.

### 5.2 Lead agent flow

While working, the lead agent is the one who writes in the workspace (the person can also do so if they enter). It adapts the flow to the complexity:

| Complexity | Flow |
|---|---|
| `trivial` | Implement → checks |
| `normal` | Short plan → tests first → implement → checks → reviews (§5.4) |
| `complex` | Plan with a *Planner* subagent → small steps with checkpoints → checks → reviews |

During the work:
- **Checkpoints** (`factory task checkpoint`) after each significant step: what is done and what comes next. At each checkpoint, and always before `submit`, it reads the person's pending notes.
- Frequent **commits** on the task branch, one per coherent step.
- If something forces a design change, it stops and moves the task to `blocked` with the reason (`factory task block`): it does not improvise architecture.
- When the implementation is finished: `factory task verify` (checks and AC), `factory task submit` (moves to `in_review`) and the reviews that apply.

### 5.3 Instructions for each role

Short, professional instructions, in English, in `templates/roles/`. Each one is complemented by the project's `docs/conventions.md` and `docs/working-agreements.md`.

**Designer**
> You are a senior software architect. Ground every statement in the actual code: read the files you will touch and the patterns already in use. Prefer the smallest design that fully meets the goal. Write acceptance criteria that a test can prove. Give implementers concrete file paths, the patterns to follow and the pitfalls to avoid. Separate verified facts from assumptions.

**Design critic**
> You review a design before a human approves it. Ask one question: could another engineer implement this correctly without the original conversation? Flag acceptance criteria that cannot be verified, missing information, contradictions with accepted decisions and badly bounded tasks. Be concrete and brief.

**Lead (implementer)**
> You are a senior engineer who owns this task end to end. Read the approved design, its acceptance criteria, the conventions and the working agreements before writing code. Find and follow existing patterns. Work in small steps: write a failing test for each acceptance criterion where it makes sense, make it pass with the simplest code, then refactor with tests green. Keep the change within scope; no drive-by edits. Handle errors explicitly. Run the full checks before submitting. Commit each coherent step with a clear message. Re-read your whole diff before asking for review. Never claim something works without evidence.

**Planner**
> You plan a complex task before any code is written. Break it into small, verifiable steps in a sensible order, each with the test that proves it. Point out risks and the existing code each step depends on. Do not write code.

**Quality reviewer**
> You are a meticulous code reviewer. Review only the diff, for maintainability: readability, naming, structure, duplication, unnecessary complexity, error handling, adherence to the project conventions and meaningful tests. Ignore formatting and anything linters already check. Report only concrete defects. Do not edit files.

**Conformance reviewer**
> You verify that the implementation matches the approved design. For every acceptance criterion, confirm it is implemented and that real evidence proves it. Flag anything out of scope, any deviation from the design and any violated decision record. Do not judge style. Do not edit files.

Both reviewers finish with this JSON, which the lead agent records with `factory task review --record`:

```json
{"verdict": "pass", "findings": [{"severity": "major", "file": "src/x.py", "line": 42, "problem": "...", "fix": "..."}]}
```

### 5.4 Reviews

Two types, independent. Syntax and formatting are always covered by the checks (linters, typecheck, tests).

| Type | Question | Who does it |
|---|---|---|
| **Quality** | Is the code well written? | A subagent of the lead agent, read-only. If its client has no subagents, an Orca agent from the same provider as the reviewer. |
| **Conformance** | Was what was approved done, with evidence? | An Orca agent in the same workspace, from the provider given with "revisa" ("review") (ideally the other one), read-only. It appears as another session in the workspace. |

**Which reviews each task gets** is set by the designer in the `review` field, with this guide:

| Task | Reviews |
|---|---|
| Trivial | none |
| Normal without new visible behavior | quality |
| Changes visible behavior or has several AC | quality and conformance |
| Complex or risky (security, data, public interfaces) | quality and conformance |

The config can force a type (`always`) or disable it (`never`), and the person can ask for more when invoking ("revisa también conformidad", or "also review conformance").

**Verdict and rounds**:
- `pass` if there are no `blocker` or `major` findings. `minor` findings do not block and are listed in the PR.
- Each review stores the commit it reviewed.
- If there are blocking findings, the lead agent fixes them and that review is repeated. At most **two rounds** per type: if the second one is not `pass` either, the task moves to `blocked` and the card raises a notice.
- Reviewers never edit or approve.

### 5.5 Verification and evidence

- `factory task verify` runs the project's **checks** (`[checks]` in the config) and each AC's command. It marks the AC `verified` only if its command finishes successfully, and saves the output in `.factory/state/evidence/<task>/`.
- A `manual` AC is recorded with `factory task verify --manual AC-02 --evidence <file>` (a note, a capture from the Orca browser with `orca screenshot`, a snapshot with `orca snapshot`…). Computer use only when there is no programmatic way.
- A command that could not be run is recorded as not run, never as passed.

### 5.6 Commits, push and PR

- The agent makes commits on the task branch while it works.
- After `finish`, `factory task publish` **pushes the task branch** and opens the **PR** with `gh` against the base branch. According to `git.pr_on_done`, the agent offers it (`offer`, the default), always does it (`always`) or never does (`never`). If the person asks for it, it does it directly.
- If there are more commits on the branch afterwards, `publish` pushes them again to the same PR.
- The PR description is generated from the task: change, AC with their evidence, reviews (with the `minor` findings), memory changes and what remains pending.
- It does not `push --force`, push to other branches, merge, or delete branches or workspaces. The person decides that.
- The repo's branch protections and CI rule. If CI fails, it is shown on the card and in the status.

### 5.7 When a task is done

`factory task finish CHG-0012-01 --memory "<summary>|none"` moves the task to `done` only if:
1. every AC of the task is `verified`;
2. the project checks pass;
3. the reviews in the `review` field have a `pass` verdict **on the last commit with code** (if afterwards only `docs/` or `.factory/` changed, it still holds);
4. memory has been evaluated (the `--memory` argument is mandatory, §6.5);
5. the approval is still valid.

If the task has `scope`, the CLI warns about files changed outside it (except `docs/` and `.factory/`); it does not block, but the warning stays in the state and in the PR, and the conformance review decides whether it is a deviation.

The PR is not a requirement for `done`, but its status is shown next to the task.

---

## 6. Memory and documentation

### 6.1 What is stored and where

| What | Where | When agents read it |
|---|---|---|
| Index, commands and critical rules | `AGENTS.md` (60–120 lines) | Always |
| What the product is, who it is for and what it is not | `docs/product.md` | When designing |
| Modules, flows, stack and integrations | `docs/architecture.md` | When designing and implementing in that area |
| How we write code and tests, and **known pitfalls** | `docs/conventions.md` | When implementing and reviewing |
| How we want agents to work | `docs/working-agreements.md` | When implementing and reviewing |
| Why the system is the way it is | `docs/decisions/NNNN-*.md` | When designing and in the conformance review |
| State of each task | `.factory/state/` | When working on or resuming that task |

Everything in `docs/` and `AGENTS.md` is in English and versioned, and changes only with human review (§0.4). `CLAUDE.md` is limited to importing `AGENTS.md`.

### 6.2 Adapting to the repository

- **Small repo**: `AGENTS.md` and `conventions.md`; the rest when there is content.
- **Normal repo**: the full structure.
- **Monorepo**: a root `AGENTS.md` as index and a short one per package or area, without repeating what is common.
- **Existing documentation**: it is linked and completed; never duplicated.

What gets written is what is **not easily deduced from the code**, with real paths and principles instead of exhaustive lists that go stale.

### 6.3 Decisions (ADR)

```markdown
# 0007 — Use per-task JSON files for local state

Status: accepted            # accepted | superseded by 0012
Date: 2026-10-17
Change: CHG-0012

## Context
## Options considered
## Decision
## Consequences
```

- One decision per file, sequential numbering and a one-line index entry per decision in `docs/decisions/README.md`.
- **Immutable except the `Status` line**: if a decision changes, another one is written that supersedes it, and in the old one only its status changes to `superseded by NNNN`.
- The design points out the lasting decisions; the lead agent writes them during implementation, on the task branch.
- ADRs are warranted for: technologies, architecture patterns, public contracts, data models and security or performance trade-offs. Not for local implementation details.

### 6.4 Working agreements and pitfalls

**Working agreements** (`working-agreements.md`): rules about how to work, grouped by topic (process, code, tests, communication). One line per agreement, with date and origin:

```markdown
- Ask before adding a new dependency. (2026-10-17, correction in CHG-0012-02)
```

They can arise from the person's corrections during a session, from review findings that repeat, or from instructions like "from now on…" ("a partir de ahora…"). In all cases they are proposed and **only saved if the person accepts** (in the conversation or when reviewing the PR).

**Known pitfalls** (final section of `conventions.md`): repo quirks that have caused errors ("test X is flaky", "never edit files under `gen/` by hand").

### 6.5 How memory is updated

When closing each task, the lead agent asks itself these questions:

| Question | Destination |
|---|---|
| Was a lasting decision made? | New ADR (or one that supersedes another) |
| Did the person or a reviewer correct something that will recur? | Working agreement |
| Did a repo pitfall appear? | Known pitfalls |
| Did the structure, a flow or an integration change? | `architecture.md` |
| Did the visible product or its scope change? | `product.md` |
| Did commands or critical rules change? | `AGENTS.md` |

Rules when writing:
1. **Read before writing**: if something similar already exists, edit or extend it; do not duplicate.
2. **Minimal change with the why**: each entry includes its reason and its origin.
3. **One destination per entry**: if it fits none in the table, it is not written.
4. **Fixed template** for ADRs and agreements; the decisions index is updated.
5. **No contradictions**: if a new entry clashes with an existing one, it proposes replacing the old one.
6. **Contain the size**: if a document grows too much, it proposes summarizing instead of adding.
7. **Everything on the task branch and listed in the PR**: the person reviews it alongside the code.

The result is passed to `finish` with `--memory`: a summary of what was proposed, or `none` if there was nothing to add. There is no separate memory agent.

### 6.6 Maintenance

When the person asks ("¿cómo está la memoria?", or "how is the memory?"), `/factory-status` runs `factory memory check`, which reviews:
- `AGENTS.md` above 120 lines;
- superseded decisions that are still cited, and repeated ADR numbers;
- links to files that no longer exist.

With that and its own reading (contradictory agreements, outdated documents), the skill proposes concrete changes. They are shown as a diff and the person commits if they agree.

---

## 7. `/factory-status` — tracking and recovery

### 7.1 Viewing the state

It is asked in natural language ("¿cómo va todo?", "¿qué está bloqueado?", "¿cómo va CHG-0012-01?", or in English: "how is everything going?", "what is blocked?", "how is CHG-0012-01 going?"). The skill answers from the state files and what Orca reports at that moment:

- **Summary**: changes awaiting approval and tasks by state.
- **Per task**: state (and reason if blocked), agent, workspace and branch, last checkpoint and its age, AC verified / total, reviews, PR and next step.
- **Attention**: pending approvals, blocked or interrupted tasks, reviews that do not converge, `pending` tasks waiting for a dependency to be integrated, agents with no checkpoint for more than 10 minutes.

### 7.2 Whether an agent is alive

On query, the CLI asks Orca about the session of the lead agent of each `in_progress` task:
- **Alive**: shown as active.
- **Finished without `submit`**: the task moves to `interrupted` at that moment.
- **No information**: shown as "unknown", never as dead.

`interrupted` is only detected when querying the state or when recovering. More than 10 minutes without a checkpoint only produces a warning, and is never interpreted as a crash.

### 7.3 Notes and pauses

The most direct way is to enter the workspace and talk to the agent. From any session you can also ask:
- "deja una nota en CHG-0012-01: …" ("leave a note on CHG-0012-01: …") (`factory task note`): the agent reads it at its next checkpoint or before `submit`;
- "pausa CHG-0012-01" ("pause CHG-0012-01") (`factory task note --pause`): when the agent reads it, it moves the task to `blocked` with reason `paused` and stops. To continue, `factory task unblock`.

If a note changes requirements or architecture, the agent blocks the task; the design is adjusted and approved again.

### 7.4 Recovering an interrupted task

1. `factory task recover CHG-0012-01` gathers the task, workspace, branch, `git status`, commits, last checkpoint and evidence. If needed, the skill adds excerpts from the previous session (`orca search`).
2. It compares the AC with the evidence and summarizes what is missing.
3. If the previous session is still alive, it only proposes continuing in it. If not, it proposes launching a new agent in the same workspace.
4. After the person confirms, it closes the previous attempt (`result: interrupted`), records a new one, reassigns the claim and the agent continues from the last checkpoint. Uncommitted changes from the previous attempt are kept as they are.

The Factory never relaunches anything without confirmation.

### 7.5 Orca cards

On each state change, the CLI updates the workspace card (`orca worktree set`):

| Task state | Card state | Comment | Unread notice |
|---|---|---|---|
| `in_progress` | `in-progress` | Next action | no |
| `in_review` | `in-review` | Pending reviews | no |
| `done` | `completed` | "N/N AC verified · PR #123" | no |
| `blocked` | `in-progress` | Reason for the block | yes |
| `interrupted` | `in-progress` | "Interrupted: use /factory-status" | yes |

The card name is the task's id and title. If Orca does not support a value, only the comment is updated. If the update fails, the task is not affected.

---

## 8. Configuration

`.factory/config.toml`, with few fields and good defaults:

```toml
schema_version = 1

[orca]
min_version = "1.4.229"

[checks]                    # detected by /factory-init
test = "pytest"
lint = "ruff check ."
typecheck = "mypy src"

[review]
quality = "auto"            # auto (whatever the task says) | always | never
conformance = "auto"
max_rounds = 2

[git]
pr_on_done = "offer"        # offer | always | never

[language]
artifacts = "en"            # language of everything publishable
```

The base branch is the one the repo has in Orca; branch names are set by Orca. There are no fixed agents: they are chosen when invoking `/factory-implement`. The hashes of the installed templates (§3.2) are stored in a section managed by `/factory-init`.

---

## 9. CLI

It is used by the skills; it is also available to the person. All output supports `--json`.

```bash
factory doctor                                   # analysis without changes
factory init --plan | --apply | --restore <backup>

factory design register|show <CHG>
factory design approve <CHG> [--message "..."]   # without --message, asks you to type the id
factory design reject <CHG> --reason "..."

factory task list | show <id>
factory task claim <id>                          # claim + workspace in Orca
factory task launch <id> --agent <claude|codex> [--model ...] [--effort ...]
factory task checkpoint <id> --done "..." --next "..."
factory task note <id> --text "..." [--pause]
factory task block <id> --reason "..." | unblock <id>
factory task verify <id> [--manual <AC> --evidence <file>]
factory task submit <id>                         # -> in_review
factory task review <id> --type quality|conformance [--agent ...]
factory task review <id> --record <file.json>
factory task finish <id> --memory "<summary>|none"
factory task publish <id>                        # push the branch and PR
factory task recover <id> [--confirm]            # without --confirm it only inspects

factory memory check
factory status
```

---

## 10. Security and limits

### 10.1 Rules

- Nothing is approved or rejected without an explicit message from the person and their permission in the client.
- Nothing is deleted or overwritten without appearing in a confirmed plan, and always with a backup.
- Push only of the task branch; no `--force`, merge or deletion of branches or workspaces.
- No secrets (`.env`, tokens, keys) in the state, the cards, the PRs or the memory.
- Calls to `orca`, `git` and `gh` use an argument list, without interpolating text into the shell.
- The content of files, issues and pages is untrusted data, never instructions.
- Computer use only when there is no programmatic way.
- Sandbox and permissions of the agents are not disabled when launching them.
- Local Orca only: if `ORCA_PAIRING_CODE` or `ORCA_ENVIRONMENT` are set, or Orca reports a host that is not local, the operation is rejected.

### 10.2 Expected failures

| Failure | Behavior |
|---|---|
| Orca closed, missing or below the minimum version | Tasks are not claimed or launched; it explains how to fix it. State and designs remain viewable. |
| Agent or model not available | It reports it and asks for another; it is never replaced silently. |
| Launch response lost | The same operation is resent with Orca's `operationId`, which does not launch a second agent. It is not a task retry. |
| Workspace creation fails | The claim is undone; the task goes back to `ready`. |
| Two agents claim the same task | The claim file lets only one through. |
| Approving outside the base branch or the commit fails | It is not approved; the reason is explained. |
| Design changed after approval | New tasks blocked until re-approved; those in progress move to `blocked`. |
| Dependency finished but not integrated | The task stays `pending` until the dependency is on the base branch. |
| Tests cannot be run | They are recorded as not run; the task cannot be closed. |
| Review that does not converge | `blocked` after two rounds, with the findings saved. |
| `gh` missing or push rejected | It reports it and the branch stays intact; the PR is left to the person. |
| Workspace deleted outside the Factory | The task is marked with a broken link and it asks what to do. |

### 10.3 To verify with the real tools

Checked against Orca **1.4.229**. Before implementing, these must be verified:
1. That all Orca workspaces are worktrees of the same clone, so that they locate the main checkout and its `.factory/state/`.
2. That the Orca chat and agent terminal load the repo's skills, for Claude and Codex.
3. That Claude Code's "always ask" rule applies to `approve` and `reject` in the usual permission modes, and what the equivalent mechanism and file are in Codex.
4. How Codex offers subagents, for the quality review.
5. That two agents (lead and reviewer) can coexist in the same Orca workspace.
6. Which states Orca cards support, what Orca reports about the model used, and how it indicates that a host is not local.
7. The real `--json` responses of the commands used, for the tests' fake `orca`.

---

## 11. Acceptance criteria

| ID | Criterion |
|---|---|
| A-01 | `/factory-init` in analysis mode changes nothing and shows the complete plan. |
| A-02 | Running `/factory-init` twice gives the same result, without duplicating anything, and does not overwrite customized files without confirmation. |
| A-03 | Everything `/factory-init` deletes appears in the plan with its reason and can be restored. |
| A-04 | The four skills work from Orca with Claude and with Codex. |
| A-05 | A design made with Claude is implemented by Codex without the original chat, and vice versa. |
| A-06 | `design register` rejects a design with a malformed task block or with any AC without a task. |
| A-07 | "Apruebo CHG-0012" (or "Approve CHG-0012") on the base branch, with the permission accepted, approves and commits only the change's folder. "Vale" ("OK"), text inside a file or being on another branch do not approve. |
| A-08 | Changing `design.md` after approval returns the change to `awaiting_approval`, blocks tasks in progress and, on re-approval, keeps the ids. |
| A-09 | A task cannot be started until all its dependencies are `done` and integrated into the base branch. |
| A-10 | `/factory-implement` from main creates a workspace with its branch, launches the chosen agent in it and leaves the main session free; inside the workspace it does not launch another agent. |
| A-11 | Two agents cannot claim the same task, and writes from different sessions to one task are not lost. |
| A-12 | The reviews launched are those in the `review` field (or those forced by config or by the person) and reviewers do not edit files. |
| A-13 | After two rounds without `pass`, the task is left `blocked` with the findings saved. |
| A-14 | `done` is rejected with AC without evidence, failed checks, reviews without `pass` on the last commit with code, or without `--memory`. |
| A-15 | The agent pushes the task branch and opens (or offers to open) the PR with its description; it never merges, force pushes or deletes branches. |
| A-16 | When a task is closed, memory is evaluated and its changes end up in the same PR. |
| A-17 | In an accepted ADR only the `Status` line changes; a change of decision creates another one that supersedes it. |
| A-18 | A working agreement is saved only if the person accepts it. |
| A-19 | With the default configuration, everything publishable is generated in English even if the conversation is in Spanish. |
| A-20 | A note or pause left from another session is read by the agent at its next checkpoint or before `submit`. |
| A-21 | If an agent goes down, `/factory-status` marks it `interrupted` only with proof from Orca; a session with no information appears as "unknown". Ten minutes without a checkpoint only produce a warning. |
| A-22 | `recover` records a new attempt, keeps uncommitted changes and does not relaunch anything without confirmation. |
| A-23 | Orca cards follow the table in §7.5. |
| A-24 | With Orca closed or a remote host, tasks are not claimed or launched, and the state remains viewable. |
| A-25 | A workspace deleted outside the Factory is detected as a broken link. |
| A-26 | No secret appears in the state, the cards, the PRs or the memory. |
