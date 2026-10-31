# AuthPilot live cases

Run on 2026-10-31. Agent model `claude-sonnet-5-5`. Criterion extraction model `claude-haiku-5-5`.
Each case was run in live mode. `dev/case_040` was then replayed from the cache with no further API calls.
These are five live cases, not the 60-case dev evaluation. The sealed split has not been run.

| Case | What it tests | Status | Tool calls | Clinic requests | Appeals | Matches the label |
| --- | --- | --- | --- | --- | --- | --- |
| `dev/case_035` | All MRI criteria already in the chart | approved | 5 | 0 | 0 | Yes. Expected final status is approved. |
| `dev/case_038` | Missing physical-therapy note | escalated | 2 | 0 | 0 | No. The label expects approval after the clinic supplies the note. The model marked red-flag screening unclear (0.68) and abstained before asking the clinic. |
| `dev/case_036` | Missing red-flag screening | escalated | 4 | 1 | 0 | No. The agent asked the clinic. After the addendum, red-flag screening stayed unclear (0.72) and the safety gate escalated. The label expects approval. |
| `dev/case_040` | Biologic denied, then appealed | approved | 8 | 0 | 1 | Yes. First submission denied with `DAS28-SCORE`. Appeal approved by the payer. |
| `dev/case_002` | Contradictory methotrexate records | escalated | 2 | 0 | 0 | Yes. The consult and the medication history disagree, and the agent escalated instead of choosing one. |

`results/eval/latest_dev_stub.md` is an older offline pipeline check. It is not this result.
