# Recovering an interrupted task

1. `swfactory task recover <task> --json` (no changes): task, workspace, branch, `git_status`,
   commits, last checkpoint, `acceptance` (with evidence), `missing_acceptance`, `reviews`, `liveness`,
   `broken_link` and a `proposal`.
2. Compare the acceptance criteria with the evidence and summarize what is missing.
3. Decide with the person:
   - `liveness: alive` → only propose continuing in that session (open it from the Orca sidebar).
   - `liveness: finished` or the task is `interrupted` → propose launching a new agent in the same
     workspace.
   - `liveness: unknown` → say that Orca cannot tell; the person decides whether the previous
     session is gone.
   - `broken_link: true` → the workspace was deleted outside the Factory: ask the person what to do.
   - If more context is needed and Orca's session search is enabled, add excerpts with
     `orca search "<task>" --json`.
4. Only after the person confirms: `swfactory task recover <task> --confirm --json`. It closes the
   previous attempt as interrupted, opens a new one and reassigns the claim. Uncommitted changes
   stay as they are. A task interrupted in review returns to `in_progress`: the new lead submits
   again and keeps the reviews already recorded.
5. Launch the lead for the new attempt: `swfactory task launch <task> --agent <agent> --reviewer <reviewer> --json`,
   with the agents the person chooses (suggest the previous attempt's, from `swfactory task show`),
   leaving out `--reviewer` when the task has no conformance review. It continues from the last
   checkpoint.
