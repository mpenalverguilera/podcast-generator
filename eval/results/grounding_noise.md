# Fact-checker noise (D-61)

`grounding_check.v2`, gpt-6-luna, 12 story sections from episodes 15708, 15709, 15710 (84 turns), 3 runs per reasoning level. A turn *flips* when it is flagged in some runs and not in others.

| reasoning | flipping turns | sections with a flip | avg flags / section | $ / check | p50 ms | max ms |
|---|---|---|---|---|---|---|
| low | 8/84 | 7/12 | 1.22 | $0.00044 | 3562 | 6344 |
| medium | 7/84 | 6/12 | 1.33 | $0.00056 | 4233 | 10687 |

medium vs low: flips cut by 12%, cost x1.26. Rule (D-61): medium if flips drop by at least a third at under 2x the cost. **Chosen: low.**
