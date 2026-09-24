# Build phases — how to use these prompts

Each file is one Claude Code session's worth of work. Paste the whole file as the prompt (or say
"Do docs/phases/NN-name.md"). Claude Code reads `CLAUDE.md` automatically; each prompt tells it which
extra docs and skills to read.

## Recommended loop per phase
1. Start a fresh Claude Code session (or `/clear`) so context is clean.
2. Paste the phase prompt. Let it plan first (plan mode), read the plan, correct it if needed.
3. Let it build. Watch the acceptance checks run.
4. Listen to / look at the output yourself. Don't skip this for phases 03 and 08.
5. Read the new `docs/DECISIONS.md` entry and make sure you can explain it in your own words.
6. Commit (the prompt asks Claude Code to do it).

## Time plan

| Session | Phase | Budget | Must-have? |
|---|---|---|---|
| 1 | 00 Smoke test | 20 min | Yes |
| 1 | 01 Scaffold | 60 min | Yes |
| 1 | 02 Ingestion | 75 min | Yes |
| 1 | 03 Pipeline → first MP3 | 105 min | Yes |
| 1 | 04 Quality (grounding + classifier eval) | 40 min | Grounding yes, Jev optional |
| 2 | 05 API + scheduler | 60 min | Yes |
| 2 | 06 Frontend | 105 min | Yes |
| 2 | 07 Dashboard | 60 min | Yes |
| 2 | 08 Polish, sample.mp3, docs | 75 min | Yes |
| 3 | 09 Stretch | 5 h | Optional |

If a phase overruns by 50%, stop, cut scope (each prompt has a "cut first" line), and move on. A
working end-to-end product beats a perfect half.

## Before phase 00
- Keys in `.env`: OpenAI and ElevenLabs (provided), Exa (your account), optionally Jev.
- Docker, `uv`, Node 20+, ffmpeg installed locally.
- Empty git repo with these kit files committed as the first commit ("docs: architecture and build plan").
