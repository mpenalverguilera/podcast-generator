# Phase 05 — API and scheduler

## Context
Read `CLAUDE.md`, `docs/ARCHITECTURE.md` §7–§9. The pipeline already works from the CLI; this phase exposes
it over HTTP and on a schedule.

## Build
1. **Auth**: `POST /auth/login` (email + password, bcrypt) → JWT (HS256, 12 h). Dependencies
   `current_user` and `admin_user`. CORS for `http://localhost:5173`.
2. **Profile and preferences**
   - `GET /profile/questions` → the guided questions.
   - `POST /profile/extract` {answers} → proposed `InterestProfile` (not saved).
   - `GET /preferences`, `PUT /preferences` (profile + target_minutes 3–12 + tone + host names/voices + schedule
     + timezone). Validate ranges. Emits `profile_updated` / `settings_changed` events.
   - `GET /voices` → curated list (ids from config plus a few more picked in phase 00) with preview URLs;
     cache in memory for 1 h.
3. **Episodes**
   - `POST /episodes/generate` {focus_request?} → creates episode, starts the runner in a background thread,
     returns id. 409 if the user already has one in progress. Emits `generate_clicked`.
   - `GET /episodes` (own episodes, newest first, status, title, duration, created_at).
   - `GET /episodes/{id}`: status, failed_stage, error, title, summary, transcript (tags stripped, speaker
     names resolved), sources per story (title, outlet, url), steps summary (per-stage latency and cost).
   - `POST /episodes/{id}/retry` for failed episodes.
   - `GET /episodes/{id}/audio`: MP3 with HTTP range support (confirm Starlette `FileResponse` handles `Range`;
     if not, implement a small ranged response). Owner or admin only.
4. **Events**: `POST /events` {type, episode_id?, payload} for play_started, play_progress (every 15 s with
   position), play_completed, episode_rated (+1/−1).
5. **Scheduler** `app/scheduler.py`: APScheduler `BackgroundScheduler` started in FastAPI lifespan; one cron
   job per user from `schedule_cron` + timezone; re-sync on preferences update; per-user in-progress guard;
   scheduled runs pass `trigger="schedule"`.
6. **Startup recovery**: on boot, episodes stuck in a running status for > 30 min are marked failed with
   `error="interrupted"` so they can be retried.

## Acceptance
- OpenAPI docs at `/docs` show every route. A `backend/tests/api/` suite covers login, auth guards, generate
  (with fakes) → poll until ready → download audio with a `Range` header (206), retry, events.
- Manual: set a user's schedule to every 2 minutes with fakes, see an episode appear, then set it back.
- `uv run pytest -q` passes; lint clean.

## Out of scope
Admin metrics (phase 07), frontend.

## Cut first
Startup recovery, voices endpoint (use two fixed voices).

## Finish
Decision entries: JWT storage/expiry, background execution model and its limits. Commit
`phase 05: REST API, auth, scheduler`.
