# Handoff -- editorial scripting iteration, branch `claude/handoff-docs-bwjlih`

Read `docs/DECISIONS.md` D-66 to D-70 first (what changed and each rescript's measured result).

## Where we are
- Current prompt versions (loaded automatically as the highest `vN`): outline.v6, section_writer.v7,
  section_patch.v3, frame.v5, grounding_check.v5.
- Writer and grounder see highlights first, then the body (D-66). The grounding check also grounds
  audio tags and fixes them by plain string replace (D-68). `tension` is set by a test, not a quota
  (D-68). The frame is never told about the listener's request (D-69). Short turns are a soft target
  and the cold-open hook is paid off once in story 1 (D-70).
- Last cloud rescript (episode 1, 10 min, 4 articles): 0 fact flags, 1,154 words, ~$0.16 scripting.
  Audio was cut off at chunk 4 of 5 by an ElevenLabs per-key quota (`quota_exceeded`).

## Open items (from D-70)
- Story 1 still refers to the top of the show ("those numbers we opened with").
- The hook fact comes back a third time in the outro.
- The preview hedges; the Sonnet section ends on a migration-setting detail.
- Left alone by choice: hedges when `tension` is null, the "distinction" tic.

## Run it locally
```bash
git fetch origin && git checkout claude/handoff-docs-bwjlih && git pull
python scripts/setup.py                 # uv, .env, deps, db, migrations
```
In `.env`: `ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128` on a free ElevenLabs plan (pcm needs a paid tier;
mp3 chunks are decoded and encoded once at assembly). A 10-minute episode is ~7,300 TTS characters;
on a 10k/month plan set `MAX_TTS_CHARS_PER_EPISODE=9500` so a too-long episode is refused up front.

```bash
cd backend
uv run python -m app.cli profile --user sample@example.com --answers ../eval/sample_profile.json --save
uv run python -m app.cli generate --user sample@example.com --minutes 10 --stop-after scripting \
  --focus "voice AI agents -- new launches, funding and real enterprise deployments"
uv run python -m app.cli transcript <id>             # read it; iterate with: rescript <id> --force
uv run python -m app.cli run <id>                    # audio: voicing + assembly
cd .. && uv run --project backend python scripts/export_sample.py --episode-id <id>
```
