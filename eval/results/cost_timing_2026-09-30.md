Produced on 2026-09-30 by `uv run --project backend python scripts/measure_costs.py run`: 4 fresh real 10-minute episodes (ids 13747–13750), stopped after scripting; ElevenLabs was NOT called, so voicing cost and time are estimated from exact character counts × $0.11 per 1,000 characters and ~40 chars/s per chunk (up to 4 chunks in parallel).

```
ElevenLabs rate: $0.11/1k chars (estimate). 'est' = voicing not run, estimated.
    ep min words chars        plann        fetch        ranki        extra        scrip        voici        assem          TOTAL
 13747  10  1209  7714    $0.000/4s   $0.070/10s    $0.310/4s    $0.005/1s  $0.221/220s   $0.849/44s   $0.000/15s $1.45/297s est
 13748  10  1066  6538    $0.000/4s   $0.042/6s    $0.179/2s    $0.006/1s  $0.233/247s   $0.719/44s   $0.000/15s $1.18/319s est
 13749  10  1048  6353    $0.000/3s   $0.056/7s    $0.262/5s    $0.004/1s  $0.158/658s   $0.699/42s   $0.000/15s $1.18/729s est
 13750  10  1028  6466    $0.000/3s   $0.070/9s    $0.296/5s    $0.005/1s  $0.202/412s   $0.711/44s   $0.000/15s $1.29/489s est
Median over 4 episodes:
  planning    $0.000 (  0%)       4s (  1%)
  fetching    $0.063 (  5%)       8s (  2%)
  ranking     $0.279 ( 22%)       4s (  1%)
  extracting  $0.005 (  0%)       1s (  0%)
  scripting   $0.212 ( 17%)     330s ( 81%)
  voicing     $0.715 ( 56%)      44s ( 11%)
  assembling  $0.000 (  0%)      15s (  4%)
  total       $1.27            404s
  ElevenLabs (est)  $0.715 (56%)
  OpenAI            $0.491 (39%)
  Exa               $0.068 (5%)
```

Notes: `scripting` includes the grounding fact-check. Scripts came out at 1,028–1,209 words against a 1,350-word budget (about 7.6–9 minutes of audio), the "shorter than asked" behaviour described in `solution.md` section 3.7. Episode 13749's scripting took 658 s because one section-draft call stalled for about 9 minutes; the median is robust to it.
