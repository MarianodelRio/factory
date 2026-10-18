# swfactory

The npm launcher for **[swfactory](https://github.com/MarianodelRio/factory)**: a method and a
CLI to build software with coding agents (Claude Code, Codex) on Orca — design, approve, implement
in isolated workspaces, review and publish with evidence.

This package contains no Python: its `swfactory` command runs the
[`swfactory`](https://pypi.org/project/swfactory/) package of the same version through
[uv](https://docs.astral.sh/uv/), which downloads Python and the package the first time.

## Install

You need [uv](https://docs.astral.sh/uv/) and Node 18+.

```bash
npm install -g swfactory   # puts `swfactory` on your PATH (the skills call it)
swfactory install-skill              # once per machine: /factory-init for Claude Code and Codex
```

To try a command without installing: `npx swfactory --version`.

Prefer Python tooling? `uv tool install swfactory` gives the same `swfactory` command.

See the [README](https://github.com/MarianodelRio/factory#readme) and the
[user guide](https://github.com/MarianodelRio/factory/blob/main/docs/guide.md).
