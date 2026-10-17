# implementation_factory.md — Software Factory v1 Implementation Plan

> **Source of truth:** `design_factory.md` (v1.5). This file says **in what order** to build it and **how to know each step is done**. It does not redefine behavior: when in doubt, the design wins.
> **Audience:** a Claude Code session (with subagents) that implements the Factory in this repository.
> **Status:** M0 done; M1 next.

---

## 1. How to use this file

### 1.1 Session protocol

At the **start of every session**:
1. Read §1–§3 of this file and the **Progress log** (§7).
2. Run `git log --oneline -15` and `git status`.
3. Run the test suite (`pytest -q`). If it is red, fix that first.
4. Pick the **first unchecked task** whose dependencies are all checked. Read only the design sections that task cites.

For **each task**:
1. Write the tests first (from the task's "Done when"), watch them fail, then implement.
2. Keep the change inside the task's files. If you need to touch something else, say why in the commit.
3. Run `pytest -q`, `ruff check .` and `mypy src` until green.
4. Commit with `T-NN: <what>` (one or more commits per task).
5. Tick the task's checkbox and add one line to the Progress log.

At the **end of every session**: make sure everything is committed and the Progress log says what comes next.

### 1.2 Rules

- **The design is the contract.** Do not add features, options or states that are not in `design_factory.md`. If the design is wrong, incomplete or contradictory, write it in §6 (Open questions) and stop that task: do not invent behavior.
- **Simplicity first.** The smallest code that meets the design. No frameworks, no plugin systems, no premature abstractions.
- **Never claim done without evidence.** A task is done when its "Done when" checks pass, not before.
- **Do not run destructive Git commands** (`reset --hard`, `push --force`, branch deletion) on this repository.
- **No real network or real Orca in unit/integration tests.** Use the fakes from T-04. Real tools are only used in the spike (M0) and the end-to-end checks (M8).
- **Everything in English**: code, comments, commits, docs, templates.

### 1.3 Using subagents

- **Explore subagents**: to read design sections or search the code without filling the main context.
- **Parallel implementation subagents**: only for tasks marked **[P]** in the same milestone, whose files do not overlap. Give each subagent: the task text, the design sections it cites, the module contracts from §3, and the rule "tests first, do not touch files outside your task". The main session reviews, runs the full suite and commits.
- **Review subagent at the end of each milestone** (fresh context): give it the milestone's tasks, the cited design sections and `git diff <milestone-start>..HEAD`. Ask for (a) behavior that contradicts the design, (b) acceptance criteria (A-xx) claimed but not tested, (c) unnecessary complexity. Fix blockers before starting the next milestone.
- Architecture decisions and integration stay in the main session.

### 1.4 Task format

```text
- [ ] T-NN [P] Title
  Depends: T-.. · Design: §x.y · Acceptance: A-xx
  Files: ...
  Do: what to build.
  Done when: concrete, testable checks.
```

`[P]` = can run in parallel with the other `[P]` tasks of the same milestone. `[HUMAN]` = needs the person (real tools, permission prompts or a decision).

---

## 2. Decisions before starting

These resolve gaps between the design and the real environment. D-01 and D-02 were confirmed by the person on 2026-10-17; the rest are defaults.

| ID | Decision | Default | Why |
|---|---|---|---|
| D-01 | YAML parsing (`tasks.yaml`, task block in `design.md`) | **Confirmed: PyYAML** as the only runtime dependency (`yaml.safe_load` / `safe_dump`) | The standard library has no YAML. Writing our own parser is more code and more risk than one mature dependency. Design §1.1 updated. |
| D-02 | Python version and installer | **Confirmed: Python ≥ 3.11** (for `tomllib`), installed with **`uv tool install .`** | The local machine has Python 3.10 and no `pipx`. `uv` provides its own Python 3.11+ and installs CLI tools, so it removes both problems. |
| D-03 | Where templates live | Inside the package: `src/factory/templates/` (loaded with `importlib.resources`) | Design §1.2 shows `templates/` at the repo root; it must be package data for an installed CLI to find it. Same content, different path. |
| D-04 | Repository layout | Build in this repository's root (`src/factory/`, `tests/`). | The design calls it `software-factory/`; the name does not matter. |
| D-05 | Extra modules | Allowed: `config.py`, `paths.py`, `state.py`, `output.py` besides the design's modules. | Design §1.2 is indicative; small focused modules keep each file readable. |
| D-06 | File locking | `fcntl.flock` (Linux/macOS). Windows is out of scope. | Simple and in the standard library. |
| D-07 | Dev tools | `pytest`, `ruff`, `mypy` as dev dependencies only. | Standard, fast, no runtime cost. |

---

## 3. Fixed contracts (defined in M1, used everywhere)

Keep these stable; tasks and subagents depend on them.

**CLI output.** Every command prints human text by default and, with `--json`, exactly one JSON object:

```json
{"ok": true, "data": { }, "warnings": []}
{"ok": false, "error": {"code": "not_approved", "message": "CHG-0012 is not approved"}, "warnings": []}
```

**Exit codes.** `0` ok · `1` unexpected error · `2` usage error · `3` precondition failed (not approved, not on base branch, dependency pending, gate not met) · `4` conflict (task already claimed) · `5` external tool unavailable (Orca, gh, git).

**Error codes** are short snake_case strings; each module documents the ones it raises. When there are several problems (e.g. design validation), `error.details` lists one per line.

**Paths** (`paths.py`): `repo_root()`, `main_checkout()` (first entry of `git worktree list --porcelain`), `state_dir()` = `<main_checkout>/.factory/state`, `changes_dir()` = `<repo_root>/.factory/changes`.

**Module responsibilities.**

| Module | Owns |
|---|---|
| `cli.py` | `argparse` subcommands, output formatting, exit codes. No logic. |
| `output.py` | JSON envelope and human formatting. |
| `config.py` | Load and validate `.factory/config.toml` with defaults (design §8). |
| `paths.py` | Path resolution above. |
| `state.py` | Task state files: lock, atomic read-modify-write, events log, claim lock, rebuild from events (design §1.4). |
| `design.py` | Digest, id assignment, task-block parsing and validation, register, show, approve, reject, change state (design §1.4, §1.5, §4). |
| `tasks.py` | Task lifecycle: computed states, claim, launch, checkpoint, note, block, verify, submit, review, finish, publish, recover, status (design §1.5, §5, §7). |
| `memory.py` | `memory check` (design §6.6). |
| `orca.py` | The only module that runs `orca`. Capability check, local-only check, workspace, launch, card, liveness (design §1.1, §7.5, §10). |
| `git.py` | The only module that runs `git` and `gh`. |
| `init.py` | Analysis, plan, apply, backups, restore, template marks and hashes (design §3). |

All subprocess calls use argument lists (never `shell=True`) and go through `orca.py` or `git.py` (design §10.1).

---

## 4. Milestones and tasks

Order: **M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8**, but the `Depends` field is what counts: T-13 (M4) is needed by T-11 (M3), so do T-13 right after M2. M6 (templates) can start in parallel once M1 is done, because it only depends on the CLI command names in design §9.

### M0 — Spike: verify the real tools

Goal: answer design §10.3 with evidence and record real outputs for the fakes. No product code.

- [x] T-01 [HUMAN] Verify Orca, Claude Code and Codex behavior
  Depends: — · Design: §10.3
  Files: `docs/spike-results.md`, `tests/fixtures/orca/*.json`
  Do: with the person, check each of the 7 items in design §10.3 on this machine (Orca 1.4.229). Note that `codex` is not on PATH here: find how Orca runs it. Record the real `--json` output of every `orca` command the design uses (`status`, `agent-context`, `repo show`, `worktree create/show/set/list`, `agent launch`, `terminal list/show`, `search`). Redact paths and ids that are personal.
  Done when: `docs/spike-results.md` answers the 7 items (yes/no + evidence), lists any design change needed (copied to §6), and the fixtures exist.

- [x] T-02 [HUMAN] Confirm D-01 and D-02
  Depends: — · Design: §1.1
  Done when: the person has confirmed or changed D-01/D-02, and the decision is written in §2. If D-01 is accepted, update design §1.1 in the same commit.

### M1 — Skeleton and contracts

- [x] T-03 Project skeleton
  Depends: T-02 · Design: §1.2
  Files: `pyproject.toml`, `src/factory/__init__.py`, `src/factory/cli.py`, `src/factory/output.py`, `README.md`, `.gitignore`
  Do: package with entry point `factory`, Python ≥ 3.11, PyYAML runtime dependency, dev dependencies (pytest, ruff, mypy). `factory --version` and `factory --help` with all subcommands of design §9 registered (bodies may raise "not implemented" with exit 1). JSON envelope and exit codes of §3.
  Done when: `uv tool install .` works; `factory --help` lists every command of design §9; `factory status --json` prints a valid envelope; `pytest`, `ruff check .`, `mypy src` pass.

- [x] T-04 Test harness: temp repos and fake tools
  Depends: T-03, T-01 · Design: §1.2 (tests)
  Files: `tests/conftest.py`, `tests/fakes/orca`, `tests/fakes/gh`
  Do: fixtures that create a temporary Git repo with a main checkout, a bare "remote" and extra worktrees. A fake `orca` executable (Python script put first on `PATH`) that answers from the recorded fixtures, records every call to a log file, and can be told to fail or return "unknown" liveness. A fake `gh` that records PR creation.
  Done when: a sample test can create a repo, call the fake `orca`, and assert on the recorded calls.

- [x] T-05 [P] Config loading
  Depends: T-03 · Design: §8
  Files: `src/factory/config.py`, `tests/test_config.py`
  Do: read `.factory/config.toml` with `tomllib`, apply the defaults of design §8, validate known values (`auto|always|never`, `offer|always|never`), reject unknown `schema_version`.
  Done when: tests cover defaults, valid values, invalid values (clear error) and a missing file (defaults).

- [x] T-06 [P] Path resolution
  Depends: T-04 · Design: §1.3
  Files: `src/factory/paths.py`, `tests/test_paths.py`
  Do: functions of §3. Must work when called from the main checkout and from any worktree of the same clone.
  Done when: tests from main and from a worktree return the same `state_dir()`.

### M2 — State core

- [x] T-07 Task state storage
  Depends: T-06 · Design: §1.4 (state writing)
  Files: `src/factory/state.py`, `tests/test_state.py`
  Do: `update_task(task_id, fn)` = flock on the task file → read → apply `fn` → write temp + rename → append event to `<task>.events.jsonl`. `read_task`. `rebuild_from_events`. Claim lock: `create_claim(task_id, attempt)` with exclusive create (fails with conflict if it exists), `release_claim`, `reassign_claim`. JSON shape of design §1.4.
  Done when: tests show (a) two processes updating the same task concurrently lose no write, (b) two concurrent claims → exactly one wins (A-11), (c) a corrupted JSON is rebuilt from events.

- [x] T-08 State machine
  Depends: T-07 · Design: §1.5
  Files: `src/factory/tasks.py` (transition table only), `tests/test_transitions.py`
  Do: a pure table of allowed transitions and the command that triggers each (design §1.5), plus `blocked_reason` handling (`paused`, `design_changed`, review not converging, free text). Illegal transitions raise `invalid_transition`.
  Done when: every row of the design's task-state table has a test, and illegal transitions are rejected.

### M3 — Design and approval

- [x] T-09 Digest, ids and task-block parsing
  Depends: T-07 · Design: §1.4, §4.3
  Files: `src/factory/design.py`, `tests/test_design_parse.py`
  Do: `digest(design_md)` = SHA-256 with LF normalization. `next_change_id()` from `.factory/changes/`. Extract the YAML block under `## Tasks` and validate it: required fields, allowed values, ids `<change>-NN`, `depends_on` refers to tasks of the same change or existing ones, no cycles, every `AC-xx` in "Acceptance criteria" is covered by some task, every task AC exists.
  Done when: tests cover a valid design, each validation error (A-06), CRLF vs LF giving the same digest.

- [x] T-10 `design register` and `design show`
  Depends: T-09 · Design: §4.2 (step 6), §1.5
  Files: `src/factory/design.py`, `src/factory/cli.py`, `tests/test_design_cli.py`
  Do: `register` without id reserves the next id and creates its folder (exclusive, safe against two sessions); `register <CHG>` validates its `design.md` (dependencies may point to tasks in other changes' `tasks.yaml`; a rejected change cannot be registered again). `show` returns change state (derived, design §1.5), digest, AC, tasks and the approval if any.
  Done when: tests for register (ok, invalid → exit 3 with details) and show in each change state.

- [x] T-11 `design approve` and `design reject`
  Depends: T-10, T-13 · Design: §4.4, §1.4 · Acceptance: A-07
  Files: `src/factory/design.py`, `src/factory/git.py`, `tests/test_approve.py`
  Do: check current branch == base branch (`orca.base_branch()` from T-13). Without `--message`: interactive, the person must type the change id. Write `approval.json` (fields of design §1.4, `approved_by` = `git config user.email`) and `tasks.yaml`, then commit **only** `.factory/changes/<id>/`. If the commit fails, remove what was written. `reject --reason` writes `rejection.json` and commits.
  Done when: tests: approve on base branch commits only the change folder (other staged and unstaged files untouched); approve on another branch → exit 3; failing pre-commit hook → nothing approved; interactive mode rejects a wrong id; reject works.

- [x] T-12 Design changed after approval
  Depends: T-11, T-08 · Design: §4.5 · Acceptance: A-08
  Files: `src/factory/design.py`, `src/factory/tasks.py`, `tests/test_design_change.py`
  Do: whenever the CLI reads a change, compare digests. On mismatch: change is `awaiting_approval`; `in_progress`/`in_review`/`interrupted` tasks move to `blocked` (`design_changed`); `done` untouched. On re-approval: keep task ids, new tasks get new numbers, tasks blocked by `design_changed` return to their previous state.
  Done when: tests for each of those rules.

### M4 — Orca client

- [x] T-13 Orca client base
  Depends: T-04 · Design: §1.1, §10.1, §10.2 · Acceptance: A-24
  Files: `src/factory/orca.py`, `tests/test_orca.py`
  Do: `run(args)` always with `--json`, parse output, map failures to exit code 5 with a clear message. `check()`: installed, version ≥ `min_version`, runtime reachable (`orca status`), required commands present in `orca agent-context`, local only (reject if `ORCA_PAIRING_CODE`/`ORCA_ENVIRONMENT` set or `orca status` → `result.target.kind` is not `local`). `base_branch()` from `worktreeBaseRef` of `orca repo show` (strip `origin/`, `refs/remotes/origin/`); missing → clear error saying how to set it.
  Done when: tests with the fake: each failure case gives the right error; capability check fails cleanly when a command is missing.

- [x] T-14 [P] Workspaces and agents
  Depends: T-13 · Design: §5.1, §10.2
  Files: `src/factory/orca.py`, `tests/test_orca_workspace.py`
  Do: `create_workspace(name, base)`, `workspace_exists(id)`, `launch_agent(workspace, agent, prompt, model, effort)` storing Orca's `operationId` and agent handle (`result.outcome.handle`); on a lost response, resend with `--retry-launch <operationId>` (never a new launch). `session_liveness(terminal)` → `alive` (terminal `connected`) `| finished` (terminal closed or missing) `| unknown` (Orca error), per design §7.2.
  Done when: tests: lost response resends with the same operationId and only one agent is recorded; liveness maps each fake answer correctly.

- [x] T-15 [P] Cards
  Depends: T-13 · Design: §7.5 · Acceptance: A-23
  Files: `src/factory/orca.py`, `tests/test_cards.py`
  Do: `update_card(workspace, task_state, ...)` following the table of design §7.5 (name, status, comment, unread). Unsupported values → comment only. Failures are logged as warnings, never raised.
  Done when: one test per row of the table, plus "Orca fails → task operation still succeeds".

### M5 — Task lifecycle

- [x] T-16 Computed states, `task list`, `task show`
  Depends: T-12, T-13 · Design: §1.5, §5.1 · Acceptance: A-09
  Files: `src/factory/tasks.py`, `tests/test_task_states.py`
  Do: for tasks without a state file, compute `pending`/`ready`: approval valid and every dependency `done` **and** its branch merged into the base branch (`git merge-base --is-ancestor`). `list` and `show` with reasons (e.g. "waiting for CHG-0012-01 to be merged").
  Done when: tests: dependency not done → pending; done but not merged → pending with reason; done and merged → ready.

- [ ] T-17 `task claim` and `task launch`
  Depends: T-16, T-14, T-15 · Design: §5.1, §10.2 · Acceptance: A-10, A-11
  Files: `src/factory/tasks.py`, `tests/test_claim_launch.py`
  Do: `claim`: check ready + approval commit on base → create claim lock → create workspace from base branch → write state (`in_progress`, attempt 1) → card. If workspace creation fails, release the claim (task back to `ready`). `launch --agent`: launch the lead agent with the brief `/factory-implement <id>` plus the review agent name; record the attempt's agent, model (as passed), `operation_id` and `terminal` (design §1.4).
  Done when: tests: happy path; second claim → exit 4; workspace failure → claim released; launch records operationId and attempt.

- [ ] T-18 [P] `checkpoint`, `note`, `block`, `unblock`
  Depends: T-17 · Design: §5.2, §7.3 · Acceptance: A-20
  Files: `src/factory/tasks.py`, `tests/test_notes.py`
  Do: `checkpoint` saves done/next and returns unread notes (marking them read). `note --text` and `note --pause` from any session. A read pause note moves the task to `blocked` (`paused`). `block --reason`, `unblock` (only while the change's approval is valid, design §1.5). Cards updated.
  Done when: tests: a note written from another worktree is returned by the next checkpoint; pause → blocked; unblock → previous state.

- [ ] T-19 [P] `task verify`
  Depends: T-17 · Design: §5.5
  Files: `src/factory/tasks.py`, `tests/test_verify.py`
  Do: run the config `[checks]` and each AC command inside the task workspace; save stdout/stderr/exit code under `evidence/<task>/`; mark `verified` only on exit 0; commands that cannot run → `not_run`. `--manual AC --evidence <file>` copies the file into evidence and marks the AC verified.
  Done when: tests for pass, fail, not runnable, and manual evidence.

- [ ] T-20 `task submit` and `task review`
  Depends: T-19 · Design: §5.3, §5.4 · Acceptance: A-12, A-13
  Files: `src/factory/tasks.py`, `tests/test_review.py`
  Do: `submit` → `in_review`. `review --type conformance --agent X` launches an Orca agent in the same workspace with the conformance role and the task context (quality runs as a subagent of the lead and needs no launch, unless T-01 says the client has none). Effective review types = task `review` field adjusted by config `always|never`. `review --record <file.json>`: validate the reviewer JSON of design §5.3, compute verdict (`pass` if no blocker/major), store with round number and current HEAD commit. If the second round of a type is not `pass` (config `max_rounds`) → `blocked`, findings kept.
  Done when: tests: effective types for each config combination; verdict computation; round limit → blocked with findings kept.

- [ ] T-21 `task finish`
  Depends: T-20 · Design: §5.7 · Acceptance: A-14
  Files: `src/factory/tasks.py`, `tests/test_finish.py`
  Do: check all gates of design §5.7 (AC verified, checks passed, required reviews `pass` on the last commit that changed files outside `docs/` and `.factory/`, `--memory` given, approval valid). `scope` warning for files outside the globs (excluding `docs/`, `.factory/`), stored in state. On success: `done`, release claim, card `completed`.
  Done when: one failing test per gate, the scope warning test, and the happy path.

- [ ] T-22 [P] `task publish`
  Depends: T-21 · Design: §5.6 · Acceptance: A-15
  Files: `src/factory/git.py`, `src/factory/tasks.py`, `tests/test_publish.py`
  Do: push **only** the task branch (no `--force`); open a PR against the base branch with `gh` and a description built from the task (change, AC + evidence, reviews incl. minor findings, memory summary, pending items). Second publish → push only, same PR. No `gh` or push rejected → clear message, branch intact.
  Done when: tests with the bare remote and fake `gh`: branch pushed, PR body contains each section, re-publish does not create a second PR, no other refs pushed.

- [ ] T-23 [P] `status` and `task recover`
  Depends: T-21 · Design: §7.1, §7.2, §7.4 · Acceptance: A-21, A-22, A-25
  Files: `src/factory/tasks.py`, `tests/test_status_recover.py`
  Do: `status`: summary, per task, attention list (design §7.1). For `in_progress` tasks ask Orca liveness: `finished` without submit → `interrupted`; `unknown` → shown as unknown; >10 min without checkpoint → warning only. Missing workspace → broken link. `recover`: gather context (git status, commits, last checkpoint, evidence); if the session is alive, propose continuing only; if it is `unknown`, say so and let the person decide; otherwise (or after the person decides) `recover --confirm` (called by the skill only after the person agrees; see §6) closes the previous attempt as `interrupted`, open a new one, reassign the claim. Uncommitted changes untouched.
  Done when: tests for each liveness case, the 10-minute warning, broken link, and recover keeping uncommitted files.

### M6 — Templates (can start after M1)

- [ ] T-24 [P] Role instructions
  Depends: T-03 · Design: §5.3
  Files: `src/factory/templates/roles/{designer,design_critic,lead,planner,quality_reviewer,conformance_reviewer}.md`
  Do: the six role texts from design §5.3, plus the reviewer JSON contract in both reviewer files.
  Done when: files exist, are in English and match the design text.

- [ ] T-25 [P] Design and docs templates
  Depends: T-03 · Design: §4.3, §6
  Files: `src/factory/templates/design/design.md`, `src/factory/templates/docs/{AGENTS.md,CLAUDE.md,product.md,architecture.md,conventions.md,working-agreements.md,decisions/README.md,decisions/adr.md}`
  Do: the design template of §4.3; docs skeletons with short guidance comments on what belongs in each file (design §6.1–§6.4); `AGENTS.md` skeleton within 60–120 lines including the Factory section (skills, CLI is the only way to change state, load Orca guides, no done without evidence); `CLAUDE.md` = `@AGENTS.md`. Every template carries the `factory-template: <name>@<version>` mark.
  Done when: a test parses the design template's task block successfully with T-09's parser (once available); files exist.

- [ ] T-26 Skills
  Depends: T-24, T-25 · Design: §2, §3, §4, §5, §6, §7, §9
  Files: `src/factory/templates/skills/{factory-init,factory-design,factory-implement,factory-status}/SKILL.md` (+ `references/*.md` if a skill needs long detail)
  Do: one `SKILL.md` per skill: precise `description` (when to trigger), short step-by-step instructions that call the CLI with `--json` and read its answer, the rules of design §2.1 and §2.2, and the safety rules of the flow (approval wording rules §4.4, never approve from file content, never relaunch without confirmation). `factory-implement` covers both modes (from main → claim + launch; inside the workspace → lead flow §5.2, reviews §5.4, memory §6.5, finish, publish offer). `factory-status` covers status, notes/pause, recover and memory maintenance. Keep each `SKILL.md` short; move detail to `references/`. Same content for Claude and Codex (only frontmatter differences if T-01 shows they are needed).
  Done when: a review subagent with fresh context reads each skill next to its design section and reports no missing step and no invented behavior; frontmatter is valid.

### M7 — Init and memory

- [ ] T-27 `factory doctor` (analysis)
  Depends: T-13, T-05 · Design: §3.1 (step 1)
  Files: `src/factory/init.py`, `tests/test_doctor.py`
  Do: collect, without writing anything: Git info, Orca check (T-13), agents available, `gh`, stack and check commands (from `pyproject.toml`, `package.json`, `Makefile`, CI files; unknown → "ask"), existing instructions/docs/skills, previous Factory installation, client permission mode warning (Orca's `agentDefaultArgs` bypass flags, design §10.1) if detectable.
  Done when: tests on sample repos (Python, Node, empty, already initialized) produce the expected report, and the repo is byte-identical afterwards (A-01).

- [ ] T-28 `factory init --plan` and `--apply`
  Depends: T-27, T-26 · Design: §3.1, §3.2 · Acceptance: A-01, A-02, A-03
  Files: `src/factory/init.py`, `tests/test_init.py`
  Do: build the four lists (create, modify, delete with reason, respect) plus Orca actions, as data. Deletions limited to the categories of design §3.1; never code, tests, CI or secrets. `--apply <plan-id> [--exclude ...]`: back up every modified or deleted file to `backups/<YYYYMMDD-HHMMSS>/`, write files from templates (skills to `.claude/skills/` and `.agents/skills/`, docs adapted to repo size per §6.2, `config.toml` with detected `[checks]`, `.gitignore` entry for `.factory/state/`, `permissions.ask` for `factory design approve`/`reject` in `.claude/settings.json` merged without losing existing settings, Codex equivalent per T-01), record template hashes, register the repo in Orca, set its base branch (`orca repo set-base-ref`) and install/update Orca skills. Nothing committed. Customized files (hash mismatch) → shown as diff, not overwritten. `--restore <backup>`.
  Done when: tests: plan is stable; apply twice = same tree (A-02); customized file kept; deleted file restorable (A-03); existing `.claude/settings.json` keys preserved.

- [ ] T-29 [P] `factory memory check`
  Depends: T-03 · Design: §6.6
  Files: `src/factory/memory.py`, `tests/test_memory.py`
  Do: `AGENTS.md` > 120 lines; ADRs with status `superseded` still referenced; duplicated ADR numbers; links to missing files.
  Done when: one test per check, plus a clean repo → no findings.

### M8 — End to end

- [ ] T-30 Automated end-to-end flow
  Depends: T-23, T-28, T-29 · Acceptance: A-01…A-26 (automatable ones)
  Files: `tests/test_e2e.py`
  Do: on a temp repo with fakes: init → register a design → approve → claim → launch → checkpoint → verify → submit → record reviews → finish → publish → status; plus design change after approval, two tasks in parallel, interruption and recover.
  Done when: the test passes and the traceability table (§5) has every automatable criterion linked to a test.

- [ ] T-31 [HUMAN] Real run on a sample project
  Depends: T-30, T-01
  Files: `docs/e2e-checklist.md`
  Do: install with `uv tool install .`, create a small sample repo, register it in Orca, and walk the full flow with the real tools: `/factory-init`, `/factory-design`, approve from chat (check the permission prompt appears), `/factory-implement ... con codex, revisa claude` from main, watch the workspace, reviews, finish, PR, `/factory-status`, an interruption and recovery. Repeat the key steps with the roles swapped (Claude lead, Codex reviewer) for A-04/A-05.
  Done when: `docs/e2e-checklist.md` lists each step and acceptance criterion with pass/fail and notes; failures become tasks or open questions.

- [ ] T-32 [HUMAN] Release v1
  Depends: T-31
  Files: `README.md`
  Do: README with install (`uv tool install`), requirements, the four skills and a 5-minute walkthrough. Tag `v0.1.0`.
  Done when: the person can follow the README on a fresh repo without help.

---

## 5. Acceptance traceability

Fill the "Test" column as tasks are completed. "Manual" criteria are checked in T-31.

| Criterion | Task(s) | Test | Manual |
|---|---|---|---|
| A-01 | T-27, T-28 | | |
| A-02 | T-28 | | |
| A-03 | T-28 | | |
| A-04 | T-26, T-31 | | ✔ |
| A-05 | T-31 | | ✔ |
| A-06 | T-09, T-10 | `test_design_parse.py` (each validation error), `test_design_cli.py::test_register_invalid_design_lists_problems` | |
| A-07 | T-11 (+ skill rules in T-26) | `test_approve.py` (commits only the folder, other branch, "vale"/other id refused, hook failure, typed id, piped stdin refused); file content cannot approve by construction (only `--message` or a typed id are read) | ✔ (permission prompt) |
| A-08 | T-12 | `test_design_change.py` | |
| A-09 | T-16 | `test_task_states.py` (not done → pending; done not merged → pending with reason; merged → ready) | |
| A-10 | T-17, T-26 | | ✔ |
| A-11 | T-07, T-17 | `test_state.py::test_concurrent_claims_exactly_one_wins` | |
| A-12 | T-20 | | |
| A-13 | T-20 | | |
| A-14 | T-21 | | |
| A-15 | T-22 | | |
| A-16 | T-21, T-26 | | ✔ |
| A-17 | T-26, T-29 | | ✔ |
| A-18 | T-26 | | ✔ |
| A-19 | T-24, T-25, T-26 | | ✔ |
| A-20 | T-18 | | |
| A-21 | T-23 | | |
| A-22 | T-23 | | |
| A-23 | T-15 | `test_cards.py::test_card_follows_the_table` (one case per row) | |
| A-24 | T-13 | `test_orca.py` (closed, unreachable, remote variables, non-local host); claim/launch refusal in T-17 | |
| A-25 | T-23 | | |
| A-26 | T-07, T-22, T-23 (no secrets written) | | |

---

## 6. Open questions and design deviations

Write here anything the design does not answer or that reality contradicts. Each entry: date, task, question or deviation, proposed resolution, status (`open` / `resolved: <how>`). Do not implement an unresolved item.

| Date | Task | Question / deviation | Proposal | Status |
|---|---|---|---|---|
| 2026-10-17 | T-02 | Design §1.1 says "standard library" but YAML needs a dependency (D-01). | Accept PyYAML and update §1.1. | resolved: confirmed, design §1.1 updated |
| 2026-10-17 | T-02 | Local Python is 3.10; design requires 3.11+; no pipx (D-02). | Use `uv tool install`. | resolved: confirmed, design §1.1–§1.2 updated |
| 2026-10-17 | T-01 | Codex is not available on this machine (no licence), so §10.3 items 2–5 cannot be verified for Codex. | Keep Codex support exactly as designed; mark Codex items "not verified" in `docs/spike-results.md`; verify them (and A-04/A-05) when Codex is available. | open (deferred) |
| 2026-10-17 | T-01 | Liveness (§7.2): Orca does not say whether a terminal agent is still running. After the agent exits, its terminal stays `connected: true`; only a closed terminal shows `connected: false` / `orphaned`. | Store Orca's terminal handle in the attempt (`terminal`, from `result.outcome.handle`, plus `operation_id`). Liveness: terminal missing or `connected: false` → `finished`; `connected: true` → `alive`; Orca error → `unknown`. Known limit: an agent that exited inside a still-open terminal shows as `alive`; the 10-minute no-checkpoint warning covers it. Update design §1.4 and §7.2. | resolved: approved by the person; design §1.4 and §7.2 updated |
| 2026-10-17 | T-01 | Base branch (§8, T-13): `orca repo show` returns `worktreeBaseRef` only after `orca repo set-base-ref`; otherwise no field. | `base_branch()` reads `worktreeBaseRef` (strip `origin/` / `refs/remotes/origin/`). If missing → exit 5 with "set the base branch in Orca". `factory init` adds `orca repo set-base-ref` to its Orca actions (with the detected default branch, confirmed in the plan). Update design §3.1 and §8. | resolved: approved by the person; design §3.1 and §8 updated |
| 2026-10-17 | T-01 | Model (§1.4): Orca does not report the model used. | `attempts[].model` = the `--model` passed, or `null` (agent default). Clarify in design §1.4. | resolved: approved by the person; design §1.4 updated |
| 2026-10-17 | T-01 | Permissions (§10.1): Orca's `agentDefaultArgs` launches Claude with `--dangerously-skip-permissions`. The "ask" rule still holds (verified). | No launch change (the Factory adds no flags). `factory doctor` reports it as the permission-mode warning of §3.1. Note it in design §10.1. | resolved: approved by the person; design §10.1 updated |
| 2026-10-17 | T-08 | §1.5 does not say from which states `finish` is allowed (a trivial task has no reviews). | From `in_progress` and `in_review`; the §5.7 gates decide. | resolved: confirmed by the person; design §1.5 updated |
| 2026-10-17 | T-08 | `unblock` and re-approval return the task to "its previous state", but the §1.4 JSON does not store it. | Add `blocked_from` to the task state. | resolved: confirmed by the person; design §1.4 updated |
| 2026-10-17 | M2 review | §4.5 blocks tasks "in progress" on a design change, but an `interrupted` task could not be blocked, and a paused task could be unblocked on an unapproved design. | `interrupted` tasks are also blocked (`design_changed`) and return on re-approval; `unblock` works only while the approval is valid, whatever the reason (replaces T-08's "unblock does not release design_changed"). | resolved: confirmed by the person; design §1.5 and §4.5 updated |
| 2026-10-17 | M2 review | With liveness `unknown` (§7.2) a task stays `in_progress` and could never be recovered. | `task recover` also works from `in_progress` when liveness is `unknown`: it says so, and `--confirm` (after the person decides) closes the attempt as interrupted and opens a new one. | resolved: confirmed by the person; design §1.5 and §7.4 updated |
| 2026-10-17 | T-10 | §9 `design register <CHG>` vs §4.2 "the CLI assigns it an id"; task ids need the change id before the task block is written. | Two steps: `register` (no id) reserves the next id and creates the folder; `register <CHG>` validates. Update design §4.2 and §9. | resolved: confirmed by the person; design §4.2 and §9 updated |
| 2026-10-17 | T-11 | The CLI also refuses an approval `--message` that does not name the change id (code `approval_not_explicit`). | Enforces §4.4 rule 1 ("explicit approval that names the change") in the CLI as a second line of defence; it adds no new behavior for valid approvals. | resolved: follows design §4.4 |
| 2026-10-17 | T-12 | Re-approval of a design that drops a previously approved task id is refused (`design_invalid`). | Follows §4.5 "keeping the ids … Nothing is deleted". | resolved: follows design §4.5 |
| 2026-10-17 | M3 review | §4.5 restores `design_changed` tasks "on re-approval"; the CLI also restores them when an edit is reverted (the digest matches the existing approval again). | Equivalent: the approval is valid again for that exact design, so nothing new is approved. | resolved: follows design §1.5 ("approved" = digest matches) |
| 2026-10-17 | T-16 | "Integrated into the base branch" is checked with `git merge-base --is-ancestor` (branch tip, or last recorded commit, against `<base>` or `origin/<base>`, no fetch). A squash or rebase merge on GitHub rewrites the commits, so the dependency would stay `pending` forever. | Ask the person whether their repos use squash/rebase merges; if so, also accept a merged PR (`gh pr view --json state`) as integration. | open |
| 2026-10-17 | T-23 | Design §7.4 says recover acts "after the person confirms", but §9 has a single `task recover`. | `task recover <id>` only inspects; `task recover <id> --confirm` acts (the skill calls it after asking). Add to design §9. | resolved: design §9 updated |

---

## 7. Progress log

One line per completed task or session: date, task, what was done, what comes next.

| Date | Task | Done | Next |
|---|---|---|---|
| 2026-10-17 | T-02 | D-01 (PyYAML) and D-02 (Python 3.11+, uv) confirmed; design updated. | T-01 spike with the person, then T-03. |
| 2026-10-17 | T-01 | Spike with the person: §10.3 answered in `docs/spike-results.md` (Claude terminal verified; Codex and Orca chat not verified), 21 Orca fixtures recorded, 4 design changes approved and applied (design v1.5). The spike's sandbox repo and workspace were removed from Orca. M0 review: no blockers; fixes applied. | T-03 project skeleton. |
| 2026-10-17 | T-03 | Package skeleton (uv_build, Python 3.11 pinned for dev, PyYAML), `factory` CLI with every design §9 command registered (not implemented → exit 1), JSON envelope and exit codes of §3, README. `uv` reinstalled on the machine (link was broken). 52 tests, ruff, mypy green. | T-04 test harness (fake orca/gh), then T-05/T-06. |
| 2026-10-17 | T-04 | `tests/conftest.py` (isolated Git identity, no ORCA_* vars, temp repo with bare remote and worktrees), fake `orca` (fixtures, call log, per-command overrides, real `git worktree add` on `worktree create`) and fake `gh` (PR create/list, failure switch). 59 tests green. | T-05 and T-06 in parallel. |
| 2026-10-17 | T-05 | `config.load_config(path)`: §8 defaults deep-merged per section, `config_invalid` (exit 3) for bad TOML, schema_version, choices, max_rounds, checks; unknown keys kept. (Subagent, reviewed.) The name of the template-hash section is left to T-28. | T-06. |
| 2026-10-17 | T-06 | `paths.py` (repo_root, main_checkout, state_dir, changes_dir; same state_dir from main and worktrees) on a minimal `git.py` (`run`, `toplevel`, `worktree_paths`; git_unavailable / not_a_git_repo / git_failed). (Subagent, reviewed.) 92 tests green. M1 done. | M1 review, then T-07. |
| 2026-10-17 | M1 review | No blockers. Fixed the harness: fakes always first on PATH and refuse to run without their fixture (the real orca/gh are never reached), fake orca creates worktrees in `$FAKE_ORCA_REPO` (not the cwd), answer sequences, per-terminal answers, `--retry-launch` echo; fake gh `--version` survives the fail switch. Left as minor: static `worktree list`, config without `schema_version` accepted as 1. 97 tests green. | T-07 state storage. |
| 2026-10-17 | T-07 | `state.TaskStore`: flock on the append-only events file, atomic JSON replace, each event carries the resulting state (rebuild = last readable event), exclusive claim file with release/reassign; `empty_state` with the §1.4 fields. 109 tests green. | T-08 state machine. |
| 2026-10-17 | T-08 | Transition table in `tasks.py` (design §1.5 + finish from in_progress/in_review), `block` records reason and `blocked_from`, `unblock`/`reapprove` return to it; manual `unblock` refuses `design_changed` (only re-approval releases it, §4.5). Design §1.4/§1.5 updated with the person's two answers. 187 tests green. M2 done. | M2 review, then T-09. |
| 2026-10-17 | M2 review | No blockers. Minor fixes to state storage (event before JSON, rebuild a missing JSON, claim written in one step, locked release/reassign). Two gaps decided by the person: interrupted tasks are blocked by a design change and `unblock` needs a valid approval; `recover` also from `in_progress` when liveness is unknown. Design §1.5, §4.5, §7.4 updated. 197 tests green. | T-09 digest, ids and task-block parsing. |
| 2026-10-17 | T-09 | `design.py`: `digest` (LF-normalized SHA-256), `next_change_id`, `parse_design` (AC list + YAML task block: fields, values, ids, dependencies incl. other changes, cycles, AC coverage both ways), all problems reported at once in `error.details` (added to the §3 envelope). 223 tests green. | T-10 register/show. |
| 2026-10-17 | T-10 | `design register` (no id: reserve the next id + folder, exclusive; with id: validate, deps from other changes' `tasks.yaml`, rejected → `change_rejected`) and `design show` (derived change state, digest, AC, tasks with stored state, approval/rejection, problems of an invalid design); change ids validated by the CLI. Design §4.2/§9 updated with the person's choice. 235 tests green. | T-13 Orca client base (needed by T-11), then T-11. |
| 2026-10-17 | T-13 | `orca.py`: `run` (always `--json`, Orca errors → `OrcaError` with Orca's code, exit 5), `version`, `check` (installed, min version numerically, running, local by env vars and `status.target.kind`, required commands and flags in `agent-context`), `base_branch` from `worktreeBaseRef` of `repo show --repo path:<main checkout>` with clear errors when unregistered or unset. New fixture `repo-show-not-found.json`. 256 tests green. | T-11 approve/reject. |
| 2026-10-17 | T-11 | `design approve` (valid design, not already approved or rejected, message names the change or typed id, base branch from Orca, `approval.json` + `tasks.yaml`, commit of only the change folder; a refused commit restores the files and the index) and `design reject` (same checks, `rejection.json`). `git.py`: `current_branch`, `config_value`, `commit_paths`. 273 tests green. | T-12 design changed after approval. |
| 2026-10-17 | T-12 | `tasks.sync_with_design`: while the digest differs from the approval, in_progress/in_review/interrupted tasks are blocked (`design_changed`); when it matches again (re-approval or reverted edit) they return to `blocked_from`; done/paused untouched. Called by `design show` and `design approve`. Re-approval keeps ids, accepts new tasks, refuses removing approved ones. 280 tests green. M3 done. | M3 review, then M4 (T-14, T-15). |
| 2026-10-17 | M3 review | No blockers. Fixed: §4.5 sync decided on the main checkout's files (a worktree's `design show` can no longer lift a block); approval commit uses `git add -N` + `commit --only`, so a refused commit leaves the person's staged changes intact; interactive approve needs a real terminal and prompts on stderr; approve/reject refuse remote Orca variables; version padding; unexpected Orca shapes → exit 5. 286 tests green. | M4: T-14 and T-15 in parallel. |
| 2026-10-17 | T-14 | `orca.create_workspace` (worktree create from the base branch, repo by path, no agent, repo setup policy), `workspace_exists` (selector_not_found → False), `launch_agent` (model/effort, effort needs model, one `--retry-launch <operationId>` re-issue when the reply is lost, never a fresh relaunch; returns operation_id + terminal), `session_liveness` (connected → alive, closed/stale → finished, Orca failure or no terminal → unknown). Done sequentially with T-15: both edit `orca.py`. New fixtures for a stale terminal and a missing worktree. 304 tests green. | T-15 cards. |
| 2026-10-17 | T-15 | `orca.update_card` from the §7.5 table (display name = id + title, status, comment, unread/read), `done_comment`; never raises: failures become warnings, a refused value falls back to a comment-only update, Orca's own warnings are passed on. M4 done. | M4 review, then T-16. |
| 2026-10-17 | M4 review | No blockers. Fixed: local-only check moved into `orca.run` (every command; liveness under a remote selection is `unknown`); workspaces created with `--no-parent` (independent, as in the spike); cards no longer force `--read` ("no notice" leaves Orca's flag alone); unknown card state → warning; launch returns `terminal: null` for non-terminal launches and keeps the resent operationId. Carried to T-17: a launch that times out has no operationId and must not lead to a second agent. 319 tests green. | T-16 computed states, task list/show. |
| 2026-10-17 | T-16 | `tasks.Context`/`catalog`/`view`: tasks of approved, not rejected changes from the main checkout (after §4.5 sync); computed `pending`/`ready` with reasons (awaiting approval, dependency not done, not merged into base or origin/base, Orca unavailable for the base branch — still viewable); `task list` and `task show` (definition + state + full record). Open question in §6 about squash merges. 330 tests green. | T-17 claim and launch. |
