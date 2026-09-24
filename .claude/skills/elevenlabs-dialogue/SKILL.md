---
name: elevenlabs-dialogue
description: How this project turns a two-host script into audio with ElevenLabs Text to Dialogue (eleven_v3), including chunking, voices, cost tracking and assembly. Use when writing or changing the TTS adapter, the voice or assemble stages, or voice settings.
---

# ElevenLabs in this project

Facts below come from ElevenLabs docs (Sept 2026). SDK call shapes are **[VERIFY]** in phase 00.

## Facts that shape the design
- **Text to Dialogue** generates multi-speaker audio from a list of turns `{text, voice_id}`; it is only available on `eleven_v3`.
- Keep the total `inputs[].text` length **≤ 2,000 characters per request**; split longer scripts and concatenate the audio yourself.
- **Request stitching is not available for `eleven_v3`**, so chunk boundaries can shift prosody.
- Output is nondeterministic; a `seed` makes it more consistent, not identical.
- v3 reads emotional cues from text and accepts **audio tags** in square brackets, e.g. `[laughs]`, `[curious]`, `[sighs]`, `[excited]`. Dashes and ellipses shape interruptions and trailing speech.
- Public price reference: ~$0.10/minute for v3. Actual cost depends on the provided plan (characters).

## Endpoint and call [VERIFY]

Raw HTTP:
```
POST https://api.elevenlabs.io/v1/text-to-dialogue?output_format=mp3_44100_128
xi-api-key: $ELEVENLABS_API_KEY
{"model_id": "eleven_v3",
 "inputs": [{"text": "Welcome back to the show!", "voice_id": "<host_a>"},
            {"text": "[laughs] Big week, Alex.", "voice_id": "<host_b>"}],
 "seed": 1234}
```

Python SDK (expected shape):
```python
from elevenlabs.client import ElevenLabs

client = ElevenLabs(api_key=settings.elevenlabs_api_key)
audio_iter = client.text_to_dialogue.convert(
    inputs=[{"text": t.text, "voice_id": t.voice_id} for t in turns],
    model_id=settings.elevenlabs_model,
    output_format=settings.elevenlabs_output_format,
    seed=seed,
)
audio_bytes = b"".join(audio_iter)
```

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
`Usage.units_in` = characters sent (including tags). `FakeTTS` returns silence of ~(characters / 15) seconds so assembly and duration logic can be tested for free.

## Voices
- Phase 00 lists available voices and picks two that contrast clearly (e.g. warm lower voice for Alex, brighter voice for Sam) and sound natural on v3. Store IDs in `DEFAULT_VOICE_HOST_A/B`.
- `GET /voices` in our API returns a curated list of ~6 voices with names and preview URLs (from the ElevenLabs voices endpoint **[VERIFY]**), so users can choose.

## Assembly (ffmpeg)
- Decode each chunk, insert ~600 ms of silence between chunks (they start at section boundaries).
- Normalize: `-af loudnorm=I=-16:TP=-1.5:LRA=11` (podcast loudness), export MP3 128 kbps 44.1 kHz.
- If the plan allows PCM output (`pcm_44100`), request PCM and encode MP3 once at the end to avoid double lossy encoding.

## Quota and guardrails
- Phase 00 reads the account's character quota **[VERIFY]** `GET /v1/user/subscription` and records it.
- Never exceed `MAX_TTS_CHARS_PER_EPISODE`. Iterate with `--minutes 1` or `--tts fake`; save full-length runs for final takes.
