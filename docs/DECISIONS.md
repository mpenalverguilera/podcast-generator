# Decision log

One entry per non-trivial decision. Newest at the bottom. This file is the raw material for `solution.md`.

Format:
```
## D-NN — Title (YYYY-MM-DD, phase NN)
Context: what forced the decision.
Decision: what we chose.
Alternatives: what we didn't choose and why.
Consequences: what this costs us / what to watch.
```

---

## D-01 — Mirror Prosper's stack (2026-09-24, planning)
Context: Assignment for a team running FastAPI + PostgreSQL + React/TS.
Decision: FastAPI, PostgreSQL, React + TypeScript.
Alternatives: Django, Next.js full-stack. Rejected: less relevant to the role.
Consequences: React is new to the author; see `docs/react-for-angular-devs.md`.

## D-02 — Single process, in-process scheduler (2026-09-24, planning)
Context: 10–15 hours of build time; one user base, low volume.
Decision: API, APScheduler and pipeline in one FastAPI process; audio on local disk.
Alternatives: Celery/RQ + Redis workers; Exa Monitors for scheduled search (needs a public webhook).
Consequences: Jobs would double-run with two instances. Fix path: DB advisory lock or a queue + worker.

## D-03 — Two-host dialogue, English, tunable length (2026-09-24, planning)
Context: Episode quality is the main judged output.
Decision: Two hosts (Alex anchor, Sam co-host), English, 3–12 minutes (default 6), user-tunable.
Alternatives: Solo narrator (simpler, less engaging).
Consequences: More prompt and voice-tuning work; chunking must respect turn and story boundaries.

## D-04 — ElevenLabs Text to Dialogue on eleven_v3, chunked at story boundaries (2026-09-24, planning)
Context: ElevenLabs recommends ≤ 2,000 characters per dialogue request; v3 has no request stitching.
Decision: Pack whole script sections into ≤ ~1,800-char chunks; one request per chunk; fixed seed; concatenate with ffmpeg and loudness-normalize to −16 LUFS.
Alternatives: One call per episode (too large); one call per line (loses turn-taking prosody); GenFM Create Podcast API (black box over script, grounding and personalization).
Consequences: Chunk boundaries are the main audio risk; they land on topic changes where a pause is natural.

## D-05 — OpenAI GPT-6 family, split by task (2026-09-24, planning)
Context: Different steps need different cost/quality.
Decision: Luna (reasoning none) for query planning, classification and grounding checks; Sol (reasoning medium) for profile extraction and scripting; Astra only as a quality ceiling experiment for `sample.mp3`.
Alternatives: One model for everything.
Consequences: TTS (~$0.60/episode) dominates cost; LLM steps are ~$0.10. Savings come from shorter TTS input, not cheaper LLMs. Model IDs to be confirmed in phase 00.

## D-06 — Exa as the only v1 news source (2026-09-24, planning)
Context: Brief requires news via APIs or scraping; users can type any interest.
Decision: Exa `/search` driven by LLM-planned queries; curated RSS for a niche is a later step. Hacker News, Reddit and X dropped.
Alternatives: NewsAPI.org (dev-only free plan, no full text, ~24h delay), other aggregators (snippet-only free tiers), Reddit (2–4 week approval queue), X (pay per read, low signal).
Consequences: Coverage depends on Exa's index; very fresh or niche pages may be missed.

## D-07 — Exa request shape follows Exa's official guidance (2026-09-24, planning)
Context: Exa's `build-with-exa` skill documents over-specification as the most common mistake.
Decision: `/search` with `query`, `type: "auto"`, `contents.highlights: true` and `startPublishedDate` for the episode window (a stated window we must enforce). No `category`, `numResults`, domain filters or `maxAgeHours`. Retry once without the date filter if a query returns < 3 results. Full text only for selected URLs via `/contents` (`text: true`), checking per-URL `statuses`.
Alternatives: `category: "news"` (Exa advises against inferring categories); full text for every result (pays for text we never use).
Consequences: Classification runs on highlights, scripting on full text. Exa's `costDollars` gives exact search cost.

## D-08 — Interest profile via guided interview + per-episode focus request (2026-09-24, planning)
Context: Search needs concrete queries; users describe interests loosely.
Decision: LLM extracts an editable structured profile once; each episode an LLM plans queries from the profile, an optional focus request and recent headlines.
Alternatives: Plain topic tags (weak queries); full chat interview (time-expensive).
Consequences: Planned queries are stored on the episode, so every selection is traceable.
