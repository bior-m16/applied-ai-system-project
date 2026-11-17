# Agent reliability evaluation

Run on 2026-11-16 23:13, model `n/a (offline)`, 2 trials per live scenario.

| ID | Scenario | Evaluation criteria | Passed | Avg seconds | Result | Failures |
|---|---|---|---|---|---|---|
| S7 | Empty request | Rejected gracefully, API never called | 1/1 | - | Pass | - |
| S8 | Oversized request | Rejected gracefully, API never called | 1/1 | - | Pass | - |

**Overall:** 2/2 trials passed (100%); 2/2 scenarios passed every trial (consistency).
