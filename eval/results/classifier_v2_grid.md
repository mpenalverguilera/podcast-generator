# Classifier v2 grid (D-61)

Prompt `classifier.v2`; 76 rows (60 original D-44 rows for quality, all rows for staleness). Rules fixed in advance in `docs/DECISIONS.md` D-61. Per-episode figures assume 60 candidates (median of real episodes).

**Chosen: none passed -- keep sol/none**

## Quality (D-44 rows) and the D-61 gates, vs sol/none

| config | keep AUC | keep P | keep R | news AUC | rel AUC | sel. prec | discordant net | stale FPs | passes |
|---|---|---|---|---|---|---|---|---|---|
| sol/none | 1.000 | 0.95 | 1.00 | 0.999 | 0.818 | 1.000 | 0 | 6/61 | no: zero_fp |
| luna/none | 0.943 | 0.85 | 1.00 | 0.948 | 0.685 | 0.750 | 5 | 3/61 | no: keep_auc, news_auc, discordant, selection, zero_fp |
| luna/low | 0.932 | 0.89 | 1.00 | 0.931 | 0.717 | 0.750 | 3 | 4/61 | no: keep_auc, news_auc, selection, zero_fp |
| luna/medium | 0.938 | 0.88 | 0.97 | 0.937 | 0.671 | 0.750 | 4 | 9/61 | no: keep_auc, news_auc, discordant, selection, zero_fp |

## Stale recall (hits / stale rows)

| config | real easy | real medium | synthetic easy | synthetic medium | synthetic hard | false positives (article ids) |
|---|---|---|---|---|---|---|
| sol/none | 2/3 | 2/2 | 3/3 | 4/4 | 2/3 | [249, 212, 197, 205, 177, 247] |
| luna/none | 3/3 | 0/2 | 3/3 | 1/4 | 0/3 | [265, 197, 177] |
| luna/low | 3/3 | 1/2 | 3/3 | 2/4 | 0/3 | [265, 209, 177, 247] |
| luna/medium | 2/3 | 1/2 | 3/3 | 1/4 | 1/3 | [265, 249, 212, 201, 208, 209, 205, 177, 247] |

## Cost and latency

| config | $/100 calls | $/episode | p50 ms | p95 ms | ~episode wait s | avg output tokens |
|---|---|---|---|---|---|---|
| sol/none | $0.3052 | $0.1831 | 1797 | 2608 | 14.2 | 56 |
| luna/none | $0.0152 | $0.0091 | 1233 | 1468 | 9.5 | 56 |
| luna/low | $0.0183 | $0.0110 | 1858 | 2750 | 14.1 | 118 |
| luna/medium | $0.0217 | $0.0130 | 2000 | 5000 | 17.2 | 186 |

## v1 vs v2 on the same model (D-44 rows)

| model | keep AUC v1 -> v2 | news AUC v1 -> v2 | rel AUC v1 -> v2 | sel. prec v1 -> v2 | keep-gate discordant net (v1 - v2) |
|---|---|---|---|---|---|
| sol/none | 0.993 -> 1.000 | 0.993 -> 0.999 | 0.781 -> 0.818 | 0.875 -> 1.000 | -2 |
| luna/none | 0.907 -> 0.943 | 0.894 -> 0.948 | 0.761 -> 0.685 | 0.875 -> 0.750 | 0 |

Selection precision uses the current `select_stories` (topic coverage, stale skip) for both v1 and v2, so the v1 numbers differ from `latest.md`'s.
