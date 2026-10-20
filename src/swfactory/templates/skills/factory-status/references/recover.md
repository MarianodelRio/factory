# Recovering an interrupted task, or handing a task to another agent

Also for a `blocked` task whose agent cannot go on (out of quota, stuck) when the person wants
another agent or provider to take over ("relanza CHG-12.1 con claude opus"). A
`design_changed` block cannot be recovered: the design is approved again first.

1. `swfactory task recover <task> --json` (no changes): task, workspace, branch, `git_status`,
   commits, last checkpoint, `acceptance` (with evidence), `missing_acceptance`, `reviews`, `liveness`,
   `broken_link` and a `proposal`.
2. Compare the acceptance criteria with the evidence and summarize what is missing.
3. Decide with the person:
   - `liveness: alive` → propose continuing in that session (open it from the Orca sidebar). If the
     person says it is abandoned (out of quota, stuck, they want another agent), confirm with
     `--replace` in step 4 and tell them to close its terminal in Orca.
   - `liveness: finished` or the task is `interrupted` → propose launching a new agent in the same
     workspace.
   - `liveness: unknown` → say that Orca cannot tell; the person decides whether the previous
     session is gone.
   - `broken_link: true` → the workspace was deleted outside the Factory: ask the person what to do.
   - If more context is needed and Orca's session search is enabled, add excerpts with
     `orca search "<task>" --json`.
4. Only after the person confirms: `swfactory task recover <task> --confirm --json` (plus
   `--replace` when they said the live session is abandoned). It closes the previous attempt, opens
   a new one and reassigns the claim; a blocked task returns to `in_progress`. Uncommitted changes
   stay as they are. A task interrupted in review returns to `in_progress`: the new lead submits
   again and keeps the reviews already recorded.
5. Launch the lead for the new attempt: `swfactory task launch <task> --agent <agent> --reviewer <reviewer> --json`,
   with the agents the person chooses (suggest the previous attempt's, from `swfactory task show`),
   leaving out `--reviewer` when the task has no conformance review. It continues from the last
   checkpoint.
