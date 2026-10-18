# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The public interface covered by semantic versioning is: the `swfactory` commands and their `--json`
output, the files under `.factory/` (`schema_version`), and the skills' names and triggers.

## [1.0.0] - 2026-10-18

First stable release, published as `swfactory` on PyPI and npm.

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
- An npm launcher (`npx swfactory`) that runs the CLI through `uvx`.
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

[1.0.0]: https://github.com/MarianodelRio/factory/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/MarianodelRio/factory/releases/tag/v0.1.0
