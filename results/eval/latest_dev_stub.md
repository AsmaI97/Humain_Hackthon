# AuthPilot evaluation: dev split

Run at 2026-10-30T19:09:24+00:00 | mode `stub` | agent model `stub-heuristic-v1` | prompt `p3.0` | data seed 1001 | eval seed 4004 | 3 runs per case | 79.0 s

> These numbers come from the offline stub model, a keyword heuristic written alongside the case
> templates. They show the evaluation pipeline works; they do not measure the agent's accuracy.

## Main results (95% bootstrap confidence intervals for the agent)

| Variant | Criterion acc | False-met | Citation validity | Gap recall | Decision acc | Final outcome acc | Denial recovery | Letter faithfulness | Tool calls | Tokens | Latency ms | Invalid output |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent | 0.992 [0.979, 1.000] | 0.051 | 1.000 | 0.949 [0.868, 1.000] | 0.967 [0.917, 1.000] | 0.967 [0.917, 1.000] | 0.600 | 1.000 | 4.770 | 5092.600 | 23.150 | 0.000 |
| single_prompt | 0.992 | 0.051 | 1.000 | 0.949 | 0.967 | - | - | - | - | 1416.100 | 0.860 | 0.000 |
| keyword | 0.887 | 0.692 | 1.000 | 0.308 | 0.600 | - | - | - | - | 0.000 | 0.160 | - |
| no_retrieval | 0.992 | 0.051 | 1.000 | 0.949 | 0.967 | 0.967 | 0.600 | 1.000 | 4.770 | 7652.700 | 18.410 | 0.000 |
| no_citation_check | 0.992 | 0.051 | 1.000 | 0.949 | 0.967 | 0.967 | 0.600 | 1.000 | 4.770 | 5082.900 | 22.850 | 0.000 |
| no_gap_loop | 0.992 | 0.051 | 1.000 | 0.949 | 0.967 | 0.800 | 0.600 | 1.000 | 3.980 | 4091.800 | 19.380 | 0.000 |
| no_appeal_loop | 0.992 | 0.051 | 1.000 | 0.949 | 0.967 | 0.917 | 0.000 | 1.000 | 4.450 | 4950.400 | 21.870 | 0.000 |

Agent spread across 3 runs: criterion accuracy std 0.0, final outcome accuracy std 0.0.

## Robustness and adaptation

| Perturbation | Cases | Criterion acc | Unperturbed | Drop (points) | Decision acc | Final outcome acc | Citation validity | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| threshold_6_to_8_weeks | 30 | 1.000 | 1.000 | 0.000 | 1.000 | 1.000 | 1.000 | 9/9 affected verdicts flipped; 21/21 unaffected unchanged |
| reworded_policy | 60 | 0.783 | 0.992 | 20.800 | 0.617 | 0.483 | 1.000 |  |
| noisy_chart | 60 | 0.992 | 0.992 | 0.000 | 0.967 | 0.967 | 1.000 |  |
| removed_evidence | 24 | 1.000 | 1.000 | 0.000 | 1.000 | 1.000 | 1.000 | no-guess rate 1.0 on 50 removed criteria |
| unseen_procedure | 10 | 0.000 | - | - | 0.500 | 0.500 | - | final: {'escalated': 10} |

## Fault injection

| Fault | Runs | Safe-failure rate | Final outcome acc | Final states |
| --- | --- | --- | --- | --- |
| payer_down | 60 | 1.000 | 0.350 | {'escalated': 21, 'queued': 39} |
| corrupted_output | 60 | 1.000 | 0.350 | {'escalated': 60} |
| empty_retrieval | 60 | 1.000 | 0.967 | {'approved': 37, 'escalated': 23} |

## Coverage vs accuracy (agent, initial verdicts)

| Confidence threshold | Coverage | Criterion acc on covered | Decision acc on covered |
| --- | --- | --- | --- |
| 0.0 | 0.700 | 0.988 | 0.952 |
| 0.3 | 0.700 | 0.988 | 0.952 |
| 0.5 | 0.700 | 0.988 | 0.952 |
| 0.6 | 0.700 | 0.988 | 0.952 |
| 0.7 | 0.700 | 0.988 | 0.952 |
| 0.8 | 0.700 | 0.988 | 0.952 |
| 0.9 | 0.483 | 0.983 | 0.931 |
| 0.95 | 0.000 | - | - |

## Regression check: pass

Compared with the run at 2026-10-30T18:53:07+00:00.
