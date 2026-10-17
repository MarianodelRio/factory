# Recorded Orca responses

Real `orca ... --json` outputs from Orca 1.4.229 (T-01 spike, 2026-10-17), used by the fake
`orca` in the tests. Personal paths and names are replaced by `/home/user` and `user`.

- `agent-context.json`: trimmed to `command`, `path`, `usage`, `flags`, `positionalArgs`.
- `worktree-current-not-found.json`: real error shape; only the path was replaced.
- `terminal-show-agent-exited.json`: the agent ran `/exit`; the terminal (shell) is still connected.
- `terminal-show-closed.json`: the terminal was closed (`orphaned`, `exitCause`).
- `worktree-set-unknown-status.json`: `--workspace-status blocked` (not a board column).

Not recorded (could not be produced on this machine; the fake builds them from the envelope
shape `{"id", "ok": false, "error": {"code", "message"}, "_meta"}` of the real errors):
a lost `agent launch` reply carrying an `operationId`, a non-local host, and `orca search` with
results (search is disabled here).
- `repo-show-not-found.json`: `repo show --repo path:<unregistered>` (exit 1).
- `terminal-show-stale.json`: `terminal show` with a handle Orca does not know (exit 1).
- `worktree-show-not-found.json`: `worktree show` of a workspace that does not exist (exit 1).
- `agent-hooks-status.json`: `orca agent hooks status` (which agents Orca finds: claude installed, codex not).
- `skills-installed.json`: `orca skills installed`, trimmed to id, name, providers and source.
