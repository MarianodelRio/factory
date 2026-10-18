# Updating memory when closing a task

Ask yourself:

| Question | Destination |
|---|---|
| Was a lasting decision made? | New ADR in `docs/decisions/` (or one that supersedes another) |
| Did the person or a reviewer correct something that will recur? | Working agreement (only if the person accepts it) |
| Did a repo pitfall appear? | "Known pitfalls" in `docs/conventions.md` |
| Did the structure, a flow or an integration change? | `docs/architecture.md` |
| Did the visible product or its scope change? | `docs/product.md` |
| Did commands or critical rules change? | `AGENTS.md` |

Rules:
1. Read before writing: edit or extend what exists; do not duplicate.
2. Minimal change with the why: each entry has its reason and origin.
3. One destination per entry; if none fits, do not write it.
4. ADRs use the template in `adr-template.md`, take the next number and get a line in the
   decisions README. An accepted ADR is immutable except its `Status` line: a changed decision is
   a new ADR that supersedes it (the old one only changes to `superseded by NNNN`). ADRs are for
   technologies, architecture patterns, public contracts, data models and security or performance
   trade-offs, not local details.
5. Working agreements are one line with date and origin, e.g.
   `- Ask before adding a new dependency. (2026-10-17, correction in CHG-0012-02)`; propose them
   and save them only if the person accepts.
6. No contradictions: if a new entry clashes with an old one, propose replacing the old one.
7. Contain the size: propose summarizing instead of adding when a document grows too much
   (`AGENTS.md` stays within 120 lines).
8. Everything in English, on the task branch, listed in the PR.

Pass the result to `swfactory task finish --memory "<summary>"`, or `none`.
