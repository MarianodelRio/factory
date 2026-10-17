# Software Factory

A CLI and four agent skills to develop with coding agents (Claude Code and Codex) on local
Orca: design and approve a change, implement each task in its
own Orca workspace, review it and publish it with evidence.

- Design: [`design_factory.md`](design_factory.md)
- Implementation plan and progress: [`implementation_factory.md`](implementation_factory.md)

Status: in development (v1).

## Development

Requires [uv](https://docs.astral.sh/uv/) (it provides Python 3.11+).

```bash
uv sync                 # create the environment with dev tools
uv run pytest -q        # tests
uv run ruff check .     # lint
uv run mypy src         # typecheck
uv tool install .       # install the `factory` command
```
