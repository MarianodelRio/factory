# Choosing complexity and reviews for each task

`complexity` decides how the lead agent works:

| Complexity | Flow |
|---|---|
| `trivial` | Implement → checks |
| `normal` | Short plan → tests first → implement → checks → reviews |
| `complex` | Plan with a Planner subagent → small steps with checkpoints → checks → reviews |

`review` lists the reviews the task needs:

| Task | `review` |
|---|---|
| Trivial | `[]` |
| Normal without new visible behavior | `[quality]` |
| Changes visible behavior or has several AC | `[quality, conformance]` |
| Complex or risky (security, data, public interfaces) | `[quality, conformance]` |

The config can force (`always`) or disable (`never`) a review type for every task.
