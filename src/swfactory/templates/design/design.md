<!-- factory-template: design/design.md@2 -->
<!-- Replace CHG-N with the id reserved by `swfactory design register` (e.g. CHG-12; tasks CHG-12.1, CHG-12.2). Keep the design proportional
     to the change; delete these comments. Everything here is in English. -->
# CHG-N — Title

## Context
Verified current behaviour, with file references.

## Goal and scope
What changes. In scope / out of scope.

## Acceptance criteria
- AC-01: Given …, when …, then … — verified by: test/command
- AC-02: Given …, when …, then … — verified by: manual/visual step

## Approach
Chosen solution and alternatives considered, with trade-offs.
Decisions to record as ADR. Existing decisions respected or superseded.

## Implementation notes
Files and modules to touch, patterns to follow (with paths),
interfaces between tasks, known pitfalls.

## Tasks
```yaml
- id: CHG-N.1
  title: …
  depends_on: []
  complexity: normal
  review: [quality]
  scope: ["src/…/**"]          # optional
  integrate: pr                # optional: pr (the person merges) or merge; default git.integrate
  acceptance:
    AC-01: "pytest …"
    AC-02: manual
```

## Risks and open questions
Only what is unresolved, with its impact.
