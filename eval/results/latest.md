# Classifier eval results

Default classifier: **sol** -- selection agreement is 0.33 (< 0.7) and Sol gains +0.25 on selection_precision (>= 0.1) -- worth ~20x the cost.

Oracle selection precision (best possible on this label set): 1.00

| classifier | n | keep P | keep R | keep ROC-AUC | rel. acc | rel. ROC-AUC | news ROC-AUC | sel. prec. | p50 ms | p95 ms | $/100 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| luna | 60 | 0.85 | 1.00 | 0.91 | 0.87 | 0.76 | 0.89 | 0.75 | 1875 | 4109 | $0.014 |
| luna_rerun | 60 | 0.83 | 1.00 | 0.89 | 0.87 | 0.59 | 0.90 | 0.75 | 1952 | 3655 | $0.014 |
| sol | 60 | 0.91 | 1.00 | 0.99 | 0.87 | 0.78 | 0.99 | 1.00 | 2547 | 3656 | $0.286 |
| jev | 60 | 0.97 | 1.00 | 1.00 | 0.97 | 1.00 | 1.00 | 1.00 | 482 | 9571 | $0.007 |
| jev_v1 | 60 | 0.97 | 0.87 | 0.96 | 0.83 | 0.71 | 0.99 | 1.00 | 403 | 978 | $0.006 |

Selection agreement (Jaccard vs Luna, target_minutes=10 -> 8 stories): luna_rerun=0.60, sol=0.33, jev=0.60, jev_v1=0.14

`jev` = jev.v2 (graded score questions, D-42), the decision candidate. `jev_v1` = the phase-04 choice/boolean questions (D-40), frozen scores shown for comparison only.

Relevance scores exactly 0 or 1: luna=32%, luna_rerun=32%, sol=32%, jev=7%, jev_v1=80%

Jev HTTP responses this run: 0 (429: 0, 5xx: 0)

## Jev non-inferiority conditions
Quality (conditions 1-4): pass. Availability: 356/413 responses were 429/5xx over 6 runs.

Luna-vs-Luna rerun keep-gate disagreement (noise floor): 3/60

| condition | value | threshold | pass |
|---|---|---|---|
| keep_gate_auc_delta | 0.0891 | -0.05 | yes |
| keep_gate_discordant_net | -6 | 3 | yes |
| selection_precision_gap | 0.25 | -0.125 | yes |
| cost_and_latency | 0.00669 | 0.0143 | yes |
| availability | 0.862 | 0.05 | no |

Bootstrap 95% CI on keep-gate AUC gap (informational, not gating): +0.089 [+0.000, +0.214]