---
name: factory-board
description: Open, close or check the Software Factory board — a live, read-only kanban of the repository's changes and tasks with every agent, terminal and subagent running in each task. Use for "/factory-board", "abre el tablero" / "open the board", "cierra el tablero" / "close the board", "¿está el tablero abierto?", "dame la URL del tablero", or "haz una foto del tablero" / "save a snapshot of the board".
---
<!-- factory-template: skills/factory-board@1 -->

# /factory-board

Reply in the person's language. Use only the `swfactory board` commands below, with `--json`, and
read each answer. The board never changes Factory state; nothing here needs confirmation.

- **Open** (the default for `/factory-board` with nothing else): `swfactory board open --json`. It
  starts the board in the background if needed and opens it in an Orca browser tab, or else in
  the system browser. Give the person the `url` from the answer (usually
  `http://127.0.0.1:8765/`; another port if that one is busy): it works in any browser on this
  machine. If `opened_in` is not `orca`, say so and mention any warning.
- **Close**: `swfactory board stop --json`. Without this it also stops by itself after
  `board.idle_minutes` (30 by default) with nobody looking.
- **Status / URL**: `swfactory board status --json` → whether it is running, its `url` and since when.
- **Snapshot** (a single HTML file to keep or share): `swfactory board snapshot <file.html> --json`.

What the person sees: columns *Needs you* (designs awaiting approval, blocked or interrupted tasks,
a closed lead terminal, a changed design), *Backlog*, *In progress*, *In review* and *Done*; on each
card the criteria verified, checks, reviews, notes, the next step and the agents and subagents of
the task; click a card for its details; the latest activity at the bottom. It refreshes itself
every few seconds while visible.

If it fails to start (`board_not_started`, `board_port_busy`, `board_unresponsive`), report the
message: the log is `.factory/state/board.log`. Recovering an interrupted task, notes and pauses
are `/factory-status`, not the board.
