# Handoff -- editorial scripting iteration (D-65), branch `claude/how-6j40vv`

Read `docs/DECISIONS.md` D-65 first (what changed and the first real run's results).

## Where we are
- D-65 is implemented and pushed: outline.v3 (`angle` = take, `tension`, `open_questions`, 3k chars of body),
  section_writer.v3, section_patch.v3, grounding_check.v4 (reason-first `GroundingChecks`), 6-20 min
  episodes (default 10) with depth-based selection in `rank.py` / `app/pipeline/budget.py`.
- First real rescript: the question->answer pattern is gone; three problems remain (see D-65).

## Next steps (agreed direction, not yet built)
1. Confirm the source mismatch: are articles 98/130 paywall stubs? Needs a real generate here (the
   user's local DB is not in this container), then inspect `articles.content` vs `highlights`.
   If confirmed: `_build_source` should always include highlights in the text the writer and
   grounder see, and a body under ~1,500 chars should count as thin.
2. New prompt versions (v3 is already recorded on an episode, so don't edit it):
   - section_writer.v4: no reflex "Exactly." / "Agreed." / "My take:"; a host who agrees adds
     something new; vary section endings (consequence, practical implication, or an open question
     only when it is the heart of the story).
   - outline.v4: `tension` / `open_questions` only when central -- not every story needs doubt.
3. Fresh `generate --minutes 10` to exercise the depth budget, then iterate with `rescript` on
   that same episode (identical articles). Audio only at the end.

## Environment in a cloud session
The provider keys arrive as environment variables. `.env` paths are sandbox-blocked, so don't create
one: settings fall back to env vars and code defaults (DATABASE_URL default matches the local Postgres).
Needs network access to api.openai.com, api.exa.ai (and api.elevenlabs.io for audio).
```bash
apt-get install -y ffmpeg            # if the setup script didn't
service postgresql start
su postgres -c "psql -c \"CREATE USER podcast WITH PASSWORD 'podcast' CREATEDB;\" -c \"CREATE DATABASE podcast OWNER podcast;\""
cd backend && uv sync && uv run alembic upgrade head
export DEFAULT_VOICE_HOST_A=ErXwobaYiN019PkySvjV DEFAULT_VOICE_HOST_B=21m00Tcm4TlvDq8ikWAM SCRIPT_TRACE_DIR=/tmp/scripts
uv run python -c "from app.db import SessionLocal; from app.users import create_user
with SessionLocal() as db: create_user(db, 'sample@example.com', 'sample'); db.commit()"
uv run python -m app.cli profile --user sample@example.com --answers ../eval/sample_profile.json --save
uv run python -m app.cli generate --user sample@example.com --minutes 10 --stop-after scripting \
  --focus "voice AI agents -- new launches, funding and real enterprise deployments"
uv run python -m app.cli rescript <id> --force          # each iteration, ~$0.18
uv run --project backend python eval/scripts_v2/export_review.py --episode-id <id>   # from repo root
```
