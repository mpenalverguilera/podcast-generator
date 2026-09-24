# Phase 06 — Frontend

## Context
Read `CLAUDE.md`, `docs/ARCHITECTURE.md` §9–§10, and `docs/react-for-angular-devs.md` (the author knows
Angular, not React: keep patterns to the ones listed there so the code is easy to explain). Backend API from
phase 05 is the contract; read `/openapi.json`.

## Goal
A clean, simple SPA with four areas: login, interests & settings, episodes (with Generate now + focus request
and a player), admin dashboard shell (charts come in phase 07).

## Build
1. `frontend/` with Vite React-TS, Tailwind, React Router, TanStack Query, Recharts. `src/api/client.ts`
   typed fetch wrapper (base URL from `VITE_API_URL`, JWT header, 401 → logout). Types generated from
   OpenAPI with `openapi-typescript` into `src/api/types.ts`.
2. **Auth**: `AuthProvider` context (token + user), `RequireAuth` and `RequireAdmin` wrappers, `/login` page.
3. **Layout**: top nav (Episodes, Interests & settings, Dashboard if admin, logout). Neutral, readable design;
   one accent color; works at 375 px width.
4. **Interests & settings** (`/settings`)
   - Step 1 "Tell us what you follow": the guided questions as textareas → "Build my profile" calls
     `/profile/extract` and shows the result.
   - Step 2 profile editor: topic cards (name, description, include/exclude as tag inputs, depth toggle),
     add/remove topic, global "avoid" tags.
   - Podcast settings: length slider 3–12 min with estimate ("~6 min · ~5 stories"), tone select
     (conversational / focused / playful), host names, voice select with ▶ preview for each host, schedule
     (off / daily at HH:MM / weekdays at HH:MM) with timezone.
   - Save with `PUT /preferences`; unsaved-changes warning.
   - First login with an empty profile redirects here.
5. **Episodes** (`/`)
   - "New episode" card: optional focus textarea ("Anything specific you want covered this time?") +
     Generate now button (disabled while one is running).
   - List: title (or "Generating…"), date, duration, status badge; running episodes poll every 3 s and show
     the current stage as a small stepper.
   - Detail (`/episodes/:id`): audio player (native `<audio>` with custom rate buttons 1×/1.25×/1.5×), sends
     play events (start, progress every 15 s, completed); transcript with speaker names, story headings and
     source links under each story; 👍/👎; failed state shows the stage and a Retry button.
6. **Dashboard** (`/admin`): route, layout and empty chart cards only; data in phase 07.

## Acceptance
- `npm run build` passes with no TS errors; `npm run lint` clean.
- Manual walkthrough with the backend on fakes: login → onboarding → save → generate with focus → watch
  stages → play → rate → retry a forced failure. I do this walkthrough myself.
- Non-admin cannot see or open `/admin`.

## Out of scope
Charts, i18n, dark mode, component library.

## Cut first
Voice preview, playback-rate buttons, generated OpenAPI types (hand-write the few types instead).

## Finish
Decision entry: state management choice and polling vs SSE. Commit `phase 06: frontend`.
