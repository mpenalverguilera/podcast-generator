# Phase 09 — Stretch (optional, session 3)

Pick items in order of value; each is independent. Read `CLAUDE.md` and the relevant docs first; one commit
per item; a decision entry for each.

## A. Niche tuning with curated RSS (best value for episode quality)
- New `SearchSource` implementation `RssSource`: curated feed list per niche in config, `feedparser` to list
  items in the window, keyword prefilter against the profile, `trafilatura` for full text of survivors only.
- Fetch stage merges Exa and RSS candidates (dedupe by `url_hash` already handles overlap).
- Niche-specific additions to the script prompt (vocabulary, pronunciation of names and acronyms) as
  `script_writer.v3.md`, activated per profile.
- Extend the eval set with niche articles; re-run phase 04 eval; record the difference.

## B. Episode memory
- Store a 3-sentence "what we said" summary per story. The planner avoids repeats; the script can say
  "Last week we covered X; here's what changed" when a story continues. Needs a classifier question
  "continues a previous story? which one?".

## C. Hosted deployment
- Frontend on GitHub Pages (Vite `base`, SPA 404 fallback). API on AWS (App Runner or a small EC2 with
  Docker), managed Postgres (RDS free tier) or the same box, audio on S3 with presigned URLs, HTTPS, CORS,
  secrets in SSM/Secrets Manager. Budget 2–3 h; stop if blocked and document instead.

## D. Live status via SSE
- `GET /episodes/{id}/events` server-sent events for stage changes; frontend replaces polling.

## E. Evals in CI
- GitHub Actions: lint, tests (fakes), and a nightly job running the classifier eval on the fixture set.
