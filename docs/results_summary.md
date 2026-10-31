# AuthPilot: results summary

AuthPilot is an AI agent that owns prior authorization end to end: it checks every payer policy
criterion against the chart with verbatim evidence, asks the clinic for what is missing, drafts the
letter, waits for one human approval, submits, and appeals denials.

Repository: https://github.com/AsmaI97/Humain_Hackthon

## Published results (live)

Agent model `claude-sonnet-5-5`, extraction model `claude-haiku-5-5`, 2026-10-31.
Source file: `results/eval/latest_dev_live.md`. These are five live cases, not a 60-case evaluation.
The sealed split has not been run.

| Case | Live outcome | Label |
| --- | --- | --- |
| `dev/case_035` | Approved after one human approval | Expected final: approved. Matched. |
| `dev/case_038` | Escalated. Red-flag screening was unclear, so it did not ask the clinic for the missing therapy note | Expected final: approved. The live model abstained. |
| `dev/case_036` | Asked the clinic for the red-flag note, then escalated because the criterion stayed unclear | Expected final: approved. The live model abstained. |
| `dev/case_040` | Denied, then approved on appeal | Expected final: approved. Matched. |
| `dev/case_002` | Escalated on contradictory methotrexate records | Expected final: escalated. Matched. |

## Offline pipeline check (not the published accuracy)

Source: `dev` split, 3 runs per case, mode `stub`, agent model `stub-heuristic-v1`, prompt `p3.0`, data seed 1001, eval seed 4004, run at 2026-10-30T19:09:24+00:00.

> These numbers come from the offline stub model, a keyword heuristic written alongside the case
> templates. They are not the published result.

## Headline results vs proposal targets

| Metric | Result | 95% CI | Target | Status |
| --- | --- | --- | --- | --- |
| Criteria-match accuracy | 99.2% | 97.9% to 100.0% | 90.0% | meets target |
| Final decision accuracy | 96.7% | 91.7% to 100.0% | 90.0% | meets target |
| Citation validity | 100.0% | - | 100.0% | meets target |
| Missing-evidence detection (gap recall) | 94.9% | 86.8% to 100.0% | 85.0% | meets target |
| Denial recovery | 60.0% | - | 70.0% | below target |
| Robustness drop (worst perturbation) | 20.8 points | - | 5 points or less | below target |
| Agent time per request | 23 ms | - | under 5 minutes | meets target |

## Does each part earn its place?

| Variant | Criterion acc | Final outcome acc | Denial recovery | Tokens per case |
| --- | --- | --- | --- | --- |
| agent | 99.2% | 96.7% | 60.0% | 5,093 |
| single prompt | 99.2% | - | - | 1,416 |
| keyword | 88.8% | - | - | 0 |
| no retrieval | 99.2% | 96.7% | 60.0% | 7,653 |
| no gap loop | 99.2% | 80.0% | 60.0% | 4,092 |
| no appeal loop | 99.2% | 91.7% | 0.0% | 4,950 |

Removing the evidence loop costs 16.7 points of final outcome accuracy; removing the appeal loop costs 5.0.

## Robustness and adaptation

| Perturbation | Criterion acc | Drop (points) | Notes |
| --- | --- | --- | --- |
| threshold 6 to 8 weeks | 100.0% | 0.0 | 9/9 affected verdicts flipped |
| reworded policy | 78.3% | 20.8 |  |
| noisy chart | 99.2% | 0.0 |  |
| removed evidence | 100.0% | 0.0 | no guesses on 50 removed criteria |
| unseen procedure | 0.0% | - | final states {'escalated': 10} |

## Safety under faults

- **payer down**: 100.0% of 60 runs ended safely ({'escalated': 21, 'queued': 39}).
- **corrupted output**: 100.0% of 60 runs ended safely ({'escalated': 60}).
- **empty retrieval**: 100.0% of 60 runs ended safely ({'approved': 37, 'escalated': 23}).
- Every submitted claim cites text found word for word in the chart; nothing reaches the payer without a human approving the exact letter.

## Next

- Run one live evaluation (`LLM_MODE=live make eval`) for real accuracy numbers.
- Run the sealed test split once, after tuning on dev is finished.
