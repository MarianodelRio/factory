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
| 3 | `/factory-design` (recurring bookings) and approval from the chat | A-06, A-07 | pass | Reserved `CHG-0001`, wrote the design in English (1 task, 7 AC), critic and `register` validation. "vale" did not approve: it asked "¿apruebas CHG-0001?". "apruebo CHG-0001" showed Claude's permission prompt for `factory design approve`; accepted → commit `Approve CHG-0001` on `main` with only the change folder; `approval.json` keeps the literal message. Finding (person's request): present a short outline and wait for OK before writing — added to §4.2 and the skill. |
| 4 | `/factory-implement CHG-0001-01` from main, lead in its workspace | A-10, A-12, A-14, A-16 | pass | Workspace `~/orca/workspaces/factory-sample/CHG-0001-01` on its own branch, lead and conformance reviewer launched in Orca (seen by the person); main session free. State: attempt 1 (claude / reviewer claude), checks pass, 7/7 AC verified with evidence, quality (subagent) and conformance (Orca agent) `pass` in round 1 on the reviewed commit `c5392d7`, `finish --memory none`, claim released. Agent behavior note: a single checkpoint and a single commit for the whole task (the flow asks for one per coherent step). |
| 5 | `factory task publish CHG-0001-01` (local remote, no GitHub) | A-15 | pass | Pushed only `MarianodelRio/CHG-0001-01` (at the reviewed `c5392d7`); remote `main` untouched, no tags; `gh` could not open a PR on a non-GitHub remote → reported, PR left to the person (§10.2). The agent did not offer to create a public GitHub repo without asking. |
| 6 | `/factory-init` again (update) | A-02 | pass (with a bug fixed) | Modified only the two changed skills (both folders) and the template hashes; committed on `main`. The plan also proposed product/architecture/working-agreements/decisions docs: the "small repo" count included the Factory's own installed files (fixed: they no longer count). The agent suggested not adding them; the person chose to keep them all. |
| 7 | `/factory-design` CHG-0002 depending on CHG-0001-01 | A-09 | pass | Showed the short outline first and waited for OK; approved with "apruebo CHG-0002" (commit `474af7f`, local). `CHG-0002-01` is `pending: waiting for CHG-0001-01 to be merged into main`. |
| 8 | Merge CHG-0001-01 into `main` (by the person, local merge commit) | A-09 | pass (with a fix) | `CHG-0002-01` moved from `pending` to `ready`. Verified that workspaces start from the local base branch (`baseRef: main`, including the unpushed approval commit), so no push of `main` is needed; the agent's advice to push came from a misleading line in the sample's `docs/conventions.md`. Fixed: `status` kept proposing `publish` for a done task whose branch was already pushed and merged; the next step now follows publish → PR or merge → "merged". |
| 9 | `/factory-implement CHG-0002-01`, then a note from the main session | A-20 | pass (interruption not tested) | Note left at 08:47:32, 23 s after launch; the agent read it at its checkpoint at 08:47:42 (`read: true`). The agent finished the whole task in about 2 minutes (launch 08:47:09 → `finish` 08:49:10, one checkpoint, one commit, both reviews `pass`), so there was no time to close its terminal while `in_progress`: A-21/A-22 need another task. Finding: liveness is only checked for `in_progress` (design §7.2), so `/factory-status` says nothing about an agent that dies while `in_review` (during reviews or before `finish`). Fixed: liveness is also checked in `in_review`; a closed terminal moves the task to `interrupted`, and `recover` returns it to `in_progress` keeping the reviews already recorded (the new lead submits again). |
| 10 | Interruption and recovery with the real tools | A-21, A-22 | not run (person's choice) | The person chose not to repeat the interruption by hand. Covered by the automated tests: `test_status_recover.py` (closed terminal → `interrupted` from `in_progress` and from `in_review`, unknown never dead, recover with confirmation keeps files and reviews) and `test_e2e.py::test_interruption_and_recovery`. The liveness check against the real Orca (`connected: false` after closing a terminal) was verified in the T-01 spike. |
| 11 | `/factory-design` + `/factory-implement CHG-0003-01` (JSON save/load, with an ADR) | A-16, A-19 | pass | Full flow in about 3 minutes: claim 09:06:29 → two checkpoints → verify (+ manual AC-06 with a grep evidence file) → submit → quality and conformance `pass` in round 1 on `1a8aafc` (only `minor` findings, kept for the PR) → `finish` 09:09:47. Two commits on the task branch: code + tests, then ADR 0001 (`Status: accepted`, listed in the decisions README) and updates to `docs/product.md` and `docs/architecture.md`, so the memory goes in the same PR (A-16). `--memory` records the summary. No working agreement came up, so A-18 is still to be checked. The `/factory-init` update (the two changed skills) was applied in the main checkout but not committed yet. |
| 12 | Change a decision (ADR superseded) and propose a working agreement | A-17, A-18 | not run (person's choice) | The person chose not to run them by hand. Both are skill rules (`factory-implement/references/memory.md`, rules 4 and 5); A-17 also has `test_memory.py::test_superseded_decision_still_cited`. |

## Result by criterion

| Criterion | Result | Where |
|---|---|---|
| A-01, A-02, A-03 | pass | Steps 1, 6 |
| A-04, A-05 | not verified | Codex not available on this machine (plan §6, deferred) |
| A-06, A-07 | pass | Step 3 (permission prompt seen) |
| A-09 | pass | Steps 7, 8 |
| A-10, A-12, A-14 | pass | Steps 4, 9, 11 |
| A-15 | pass | Step 5 (local remote; PR left to the person) |
| A-16 | pass | Step 11 |
| A-17, A-18 | not run (person's choice) | Step 12; automated test and skill rules |
| A-19 | pass | Every step: designs, commits, docs, ADR and cards in English while the conversation was in Spanish |
| A-20 | pass | Step 9 |
| A-21, A-22 | not run by hand (person's choice) | Step 10; automated tests |
| Others | automated | Plan §5 |

Findings fixed during the run: doctor build-check warning (step 1), commit on the base branch (step 2),
outline before writing a design (step 3), Factory files counted in the repo size (step 6), next step
of a done task (step 8), interruption while `in_review` not detected (step 9). Open: Codex
verification (A-04, A-05).
