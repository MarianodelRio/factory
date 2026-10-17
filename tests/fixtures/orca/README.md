# Recorded Orca responses

Real `orca ... --json` outputs from Orca 1.4.229 (T-01 spike, 2026-10-17), used by the fake
`orca` in the tests. Personal paths and names are replaced by `/home/user` and `user`.

- `agent-context.json`: trimmed to `command`, `path`, `usage`, `flags`, `positionalArgs`.
- `worktree-current-not-found.json`: real error shape; only the path was replaced.
- `terminal-show-agent-exited.json`: the agent ran `/exit`; the terminal (shell) is still connected.
- `terminal-show-closed.json`: the terminal was closed (`orphaned`, `exitCause`).
- `worktree-set-unknown-status.json`: `--workspace-status blocked` (not a board column).
