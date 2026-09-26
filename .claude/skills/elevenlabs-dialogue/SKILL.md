---
name: elevenlabs-dialogue
description: How this project turns a two-host script into audio with ElevenLabs Text to Dialogue (eleven_v3), including chunking, voices, cost tracking and assembly. Use when writing or changing the TTS adapter, the voice or assemble stages, or voice settings.
---

# ElevenLabs in this project

Facts below come from ElevenLabs docs (Sept 2026); SDK call shapes confirmed live in phase 00
(`docs/DECISIONS.md` D-09). **This project's ElevenLabs key is a take-home-test account key with no
dashboard access and a restricted scope**: `text_to_speech` / `text_to_dialogue` work, but
`client.user.subscription.get()` and `client.voices.get_all()` both 401 ("missing the permission
user_read" / "voices_read"). So there is no API-based quota check and no way to browse the account's
actual voice library — voice selection falls back to ElevenLabs' classic premade voice IDs (Rachel,
Domi, Bella, Antoni, Elli, Josh, Arnold, Adam, Sam), each verified with a live 1-word
`text_to_speech` call before use. If a future key on this project has full scope, prefer
`client.voices.get_all()` for real voice selection.

## Facts that shape the design
- **Text to Dialogue** generates multi-speaker audio from a list of turns `{text, voice_id}`; it is only available on `eleven_v3`.
- Keep the total `inputs[].text` length **≤ 2,000 characters per request**; split longer scripts and concatenate the audio yourself.
- **Request stitching is not available for `eleven_v3`**, so chunk boundaries can shift prosody.
- Output is nondeterministic; a `seed` makes it more consistent, not identical.
- v3 reads emotional cues from text and accepts **audio tags** in square brackets, e.g. `[laughs]`, `[curious]`, `[sighs]`, `[excited]`. Dashes and ellipses shape interruptions and trailing speech.
- Public price reference: ~$0.10/minute for v3. Actual cost depends on the provided plan (characters).

## Endpoint and call

Raw HTTP:
```
POST https://api.elevenlabs.io/v1/text-to-dialogue?output_format=mp3_44100_128
xi-api-key: $ELEVENLABS_API_KEY
{"model_id": "eleven_v3",
 "inputs": [{"text": "Welcome back to the show!", "voice_id": "<host_a>"},
            {"text": "[laughs] Big week, Alex.", "voice_id": "<host_b>"}],
 "seed": 1234}
```

Python SDK, confirmed in phase 00 against `elevenlabs` SDK 2.69.0 — exactly the expected shape,
**except the client does not read `ELEVENLABS_API_KEY` from the environment automatically; `api_key`
must be passed explicitly** (an unauthenticated client raises 401 "Neither authorization header nor
xi-api-key received"). Use `with_raw_response`, not plain `.convert()` — see Adapter contract below
for why:
```python
from elevenlabs.client import ElevenLabs

client = ElevenLabs(api_key=settings.elevenlabs_api_key)   # required kwarg, not auto-read from env
with client.text_to_dialogue.with_raw_response.convert(
    inputs=[{"text": t.text, "voice_id": t.voice_id} for t in turns],
    model_id=settings.elevenlabs_model,
    output_format=settings.elevenlabs_output_format,
    seed=seed,
) as resp:
    headers = resp.headers                  # dict[str, str]; already a dict, no cast needed
    audio_bytes = b"".join(resp.data)
```
`with_raw_response.convert(...)` is `@contextlib.contextmanager`-decorated in this SDK version, so
the `with ... as resp:` form is required (not optional sugar).

## Chunking (pipeline, not adapter)
1. Walk script sections in order (intro, stories, outro).
2. Add whole sections to the current chunk while total characters ≤ 1,800.
3. A section that alone exceeds 1,800 characters is split at turn boundaries (never mid-turn).
4. Record for each chunk: section ids, character count, seed.
5. Chunks are saved to `data/chunks/{episode_id}/{n}.<ext>`; the voice stage skips chunks that already exist (resume without paying twice).

## Adapter contract
```python
class TTS(Protocol):
    def synthesize_chunk(self, turns: list[Turn], seed: int | None) -> tuple[bytes, Usage]: ...
```
Confirmed live in phase 00: a successful `text_to_dialogue` response carries a **`character-cost`**
response header equal to the exact number of characters billed (tags included — a 36-character
2-turn call returned `character-cost: 36`), plus a **`request-id`** header and a bonus
`tts-latency-ms`. The response body is only the audio, so this is the *only* way to get the
provider's own billed number rather than estimating it — use it:
- `Usage.units_in = int(headers["character-cost"])`, `usage_source="header"` on the `pipeline_steps` row.
- Store `headers["request-id"]` on the row too, for support/debugging.
- If the header is ever missing (defensive fallback only — it was present on every phase 00 call):
  `Usage.units_in = sum(len(t.text) for t in turns)` (tags included), `usage_source="estimated"`.
- Dollar cost either way = `units_in × ELEVENLABS_USD_PER_1K_CHARS / 1000` from `pricing.py`.
  `ELEVENLABS_USD_PER_1K_CHARS` (`.env.example`, default `0.11`) is an **estimate** derived from the
  public ~$0.10/minute v3 price at ~900 characters/spoken-minute (150 words × ~6 chars) — the actual
  per-character price isn't visible with this scoped test key (see Quota and guardrails). Set
  `cost_is_estimate=true` on the `pipeline_steps` row for every ElevenLabs call (Exa/OpenAI rows are
  `false` — their costs are exact); show it as an estimate anywhere it's displayed (dashboard,
  `solution.md`). See `docs/DECISIONS.md` D-12.

`FakeTTS` returns silence of ~(characters / 15) seconds so assembly and duration logic can be tested for free; it can set `usage_source="fake"` and skip the header entirely.

## Voices
- Phase 00 picked two premade voices that contrast clearly and sound natural on v3: **Antoni** (`ErXwobaYiN019PkySvjV`, warm lower voice, host_a/Alex) and **Rachel** (`21m00Tcm4TlvDq8ikWAM`, calm voice, host_b/Sam). Stored in `DEFAULT_VOICE_HOST_A/B`. Chosen from the fallback premade pool since this key cannot list the account's own voices (see the scope note above).
- `GET /voices` in our API returns a curated list of ~6 voices with names and preview URLs. With a full-scope key this comes from `client.voices.get_all()`; with this project's restricted key it must instead be a small hardcoded list of verified premade voices (same set as the fallback pool) until/unless a wider-scope key is available.

## Assembly (ffmpeg)
- Decode each chunk, insert ~600 ms of silence between chunks (they start at section boundaries).
- Normalize: `-af loudnorm=I=-16:TP=-1.5:LRA=11` (podcast loudness), export MP3 128 kbps 44.1 kHz.
- Confirmed in phase 00: `output_format="pcm_44100"` is allowed on this plan. Request PCM per chunk and encode MP3 once at the end to avoid double lossy encoding.

## Quota and guardrails
- Phase 00 could not read the account's character quota: `client.user.subscription.get()` (`GET /v1/user/subscription`) 401s on this key ("missing the permission user_read"). No total-quota number is available for this test account.
- What *is* available: every call's own `character-cost` response header (see Adapter contract). Summing that column on `pipeline_steps` gives a running "characters used so far" total for this project — not the account's total quota, but the number that actually matters for `MAX_TTS_CHARS_PER_EPISODE`/`DAILY_SPEND_CAP_USD` enforcement.
- Never exceed `MAX_TTS_CHARS_PER_EPISODE`. Iterate with `--minutes 1` or `--tts fake`; save full-length runs for final takes.

## Concurrency and retries (D-56)
- ElevenLabs limits *concurrent requests* per plan (Free 2, Starter 3, Creator 5, Pro 10, Scale/Business 15), not requests per minute; over the limit is a 429 `too_many_concurrent_requests`. This key accepted 4 in flight, so it's Creator or above. `maximum-concurrent-requests` is **not** returned on `text-to-dialogue` with this key; only `current-concurrent-requests` is.
- The voice stage synthesizes missing chunks in a thread pool; the adapter holds a **process-wide** semaphore of `ELEVENLABS_MAX_CONCURRENCY` (default 4) around each request, so concurrent episodes can't burst past the account limit together.
- The SDK does **not** retry `text_to_dialogue` (it streams, and the SDK's `stream()` path has no retry loop), so the adapter retries 429/5xx/connect errors itself (`ELEVENLABS_MAX_ATTEMPTS`, backoff with jitter, honors `retry-after`). Don't retry 401/422 or read timeouts.
- Before sending a batch, the voice stage checks today's spend plus the batch's estimated cost fits `DAILY_SPEND_CAP_USD`.
