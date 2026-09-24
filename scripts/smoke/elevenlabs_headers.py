"""Phase 00 smoke test: ElevenLabs response headers.

`text_to_dialogue.convert()`'s response body *is* the audio, so there's nowhere in the normal
return value for a per-call cost number. This checks whether ElevenLabs puts one (and a
request-id) in the response **headers** instead, via the SDK's `with_raw_response` pattern --
the only lever left for cost tracking since this project's key can't read
`user.subscription.get()` (see elevenlabs_check.py / DECISIONS.md D-09).

Run (from repo root): uv run --project backend python scripts/smoke/elevenlabs_headers.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

OUT_DIR = ROOT / "data" / "smoke"


def main() -> int:
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    voice_a = os.environ["DEFAULT_VOICE_HOST_A"]
    voice_b = os.environ["DEFAULT_VOICE_HOST_B"]

    inputs = [
        {"text": "Quick header test.", "voice_id": voice_a},
        {"text": "[laughs] Sure, go.", "voice_id": voice_b},
    ]
    total_chars = sum(len(t["text"]) for t in inputs)
    print(f"Calling text_to_dialogue.with_raw_response.convert ({total_chars} chars)...")

    with client.text_to_dialogue.with_raw_response.convert(
        inputs=inputs,
        model_id="eleven_v3",
    ) as resp:
        headers = dict(resp.headers)
        audio = b"".join(resp.data)

    print(f"\nstatus_code: {resp.status_code}")
    print(f"audio bytes: {len(audio)}")
    print(f"\nfull headers ({len(headers)}):")
    for key, value in sorted(headers.items()):
        print(f"  {key}: {value}")

    cost_like = {k: v for k, v in headers.items() if "cost" in k.lower() or "character" in k.lower()}
    id_like = {k: v for k, v in headers.items() if "request" in k.lower() or "history" in k.lower()}
    print(f"\ncost/character-like headers: {cost_like or 'NONE FOUND'}")
    print(f"request/history-id-like headers: {id_like or 'NONE FOUND'}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "headers_test.mp3"
    out_path.write_bytes(audio)
    print(f"\nSaved audio to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
