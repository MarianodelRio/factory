# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The public interface covered by semantic versioning is: the `swfactory` commands and their `--json`
output, the files under `.factory/` (`schema_version`), and the skills' names and triggers.

## [Unreleased]

### Added
- `swfactory sync`: fetches `origin`, fast-forwards the base branch when the main checkout is on
  it, rebases and pushes local approval commits. It never merges, forces or touches uncommitted
  work; what it cannot do is a warning.

- A new task state, `to_merge`: `task finish` moves a task there, and it becomes `done` once its
  work is merged into the base branch. A pull request merged on GitHub counts, also squashed or
  rebased (`gh pr view`); without one, the branch's commits must be in the base. A pull request
  closed without merging needs the person. `swfactory task merged <task>` records a merge the
  Factory cannot see. The board has a *To merge* column and records merges once a minute.
- Each task chooses how it integrates: `integrate: pr` (the person merges the PR) or
  `integrate: merge` (`task publish` opens the PR and merges it right away with a merge commit).
  The default is `git.integrate` (`pr`); the designer asks in the outline.
- The task branch is pushed when the task is claimed (visible on GitHub from the start) and again
  when it is finished. The PR is linked to the Orca card.
- After a merge the remote branch is deleted, and `git.cleanup` (`ask`, `always`, `never`) decides
  whether the workspace and the local branch are removed. `swfactory task cleanup <task>` removes
  them (never with uncommitted files), `--keep` keeps them.

### Changed
- `done` now means merged: dependencies only wait for their tasks to be `done`, without git checks.
  Tasks finished with an earlier version are checked once and go back to `to_merge` if they are
  not merged.
- Claiming a task and approving or rejecting a design fetch `origin` first; `swfactory status`
  fetches at most once a minute. Merges done on GitHub are seen without pulling by hand.
- Task workspaces start from `origin/<base>` when the approval is there (the local base otherwise).
- Approving or rejecting pushes the base branch when the approval is all it would publish; the
  person's own unpushed commits are never pushed (a warning says so).

## [1.1.0] - 2026-10-18

### Added
- Windows support. The CI runs every test on Linux, macOS and Windows with Python 3.11-3.13.
- `SWFACTORY_ORCA` and `SWFACTORY_GH`: how to run Orca's or GitHub's CLI when it is not on `PATH`
  (a path, or a JSON list of a program and its arguments).

### Changed
- Task state locks work on every OS: writers take turns on a `.<task>.mutex` file next to the
  state, with `fcntl` on Linux and macOS and `msvcrt` on Windows.
- The board no longer inspects process ids: `swfactory board stop` asks the board to stop over
  HTTP with a token only its owner can read, and the board recognizes the server it launched.
- Repository files written by `/factory-init` and approvals always use LF line endings; paths
  recorded in state and plans always use `/`.
- Output of `git`, `orca`, `gh` and the check commands is read as UTF-8, and the CLI writes UTF-8.

### Fixed
- The board's `board.json` could be read half-written while the board started (an intermittent
  test failure); it is now written atomically.
- On Windows, a check command's backslashes are no longer eaten, and `orca.cmd` shims never get
  text that `cmd.exe` would reinterpret.

## [1.0.0] - 2026-10-18

First stable release, published as `swfactory` on PyPI.

### Added
- Five skills for Claude Code and Codex: `/factory-init`, `/factory-design`, `/factory-implement`,
  `/factory-status` and `/factory-board`.
- The `swfactory` CLI: designs with explicit approval, tasks in
  their own Orca workspace, verification with evidence, quality and conformance reviews, closing
  gates, publishing the task branch and PR, notes, pauses, interruption and recovery, project
  memory checks.
- `swfactory board`: a live, read-only kanban of the tasks in an Orca tab or any browser, with the
  agents, terminals and subagents running in each task.
- `/factory-init` installs a prompt rule for Codex (`.codex/rules/factory.rules`) so approving or
  rejecting a design asks the person, as Claude Code's `permissions.ask` does.
- A user guide (`docs/guide.md`).

### Changed
- The package, the module and the command are now `swfactory` (formerly `factory`).
- A lead agent that dies while its task is in review is now detected as interrupted, and recovery
  keeps the reviews already recorded.

### Verified
- End to end on Linux with Claude Code and Orca 1.4.229. The test suite passes on Linux and macOS
  with Python 3.11-3.13. Not yet verified on a real machine: Codex, and macOS with Orca. Windows
  is not supported.

## [0.1.0] - 2026-10-18

Initial development version (not published to a package registry).

[1.1.0]: https://github.com/MarianodelRio/swfactory/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/MarianodelRio/swfactory/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/MarianodelRio/swfactory/releases/tag/v0.1.0
