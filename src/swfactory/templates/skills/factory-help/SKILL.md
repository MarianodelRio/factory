---
name: factory-help
description: Explain the Software Factory to the person — what each skill does, how a change goes from design to merge, task states, what to say to the agent, configuration — and what to do next in this repository. Use for "/factory-help", "/factory-help <topic>", "¿cómo funciona la factory?", "¿qué skills hay?", "¿qué significa to_merge?", "what should I do next?".
---
<!-- factory-template: skills/factory-help@1 -->

# /factory-help

Reply in the person's language, briefly. You only explain: change nothing, run nothing that writes.

1. Read `references/overview.md`: skills, the flow, task states, phrases and configuration.
2. Answer what was asked, from that reference; for a topic it does not cover, read the matching
   skill's `SKILL.md` in `.claude/skills/` or `.agents/skills/`. Without a topic, give the
   overview in a few lines: the skills table and the flow.
3. Make it concrete for this repository: `swfactory status --json` (it may fetch `origin`) and say
   what the next step is, with the exact phrase to use (for example "CHG-12 is awaiting approval:
   `apruebo CHG-12`", "12.1 is ready: `/factory-build 12.1 con claude`"). If the Factory is not
   installed here (no `.factory/`), say that `/factory-init` comes first.
