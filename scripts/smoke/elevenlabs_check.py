"""Phase 00 smoke test: ElevenLabs.

Confirms:
- account character quota/usage (best effort; this key is scoped down, see below)
- voice list (best effort; falls back to classic premade voices, verified live against this key)
- Text to Dialogue (eleven_v3) 2-turn sample for 3 candidate voice pairs -> data/smoke/pair_*.mp3
- whether output_format="pcm_44100" is allowed on this plan

This project's ElevenLabs key is a take-home-test account: no dashboard access, and the key is
scoped to text_to_speech/text_to_dialogue only (`user.subscription.get()` and `voices.get_all()`
both 401 with "missing the permission {user_read,voices_read}"). So voice selection falls back to
ElevenLabs' classic premade voices, each verified live below with a 1-word `text_to_speech` call
before being offered as a dialogue-pair candidate.

Run (from repo root): uv run --project backend python scripts/smoke/elevenlabs_check.py
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

SAMPLE_TURNS = [
    "Welcome back to the show! [laughs] Big week for AI voice agents.",
    "It really was, I've been reading about this nonstop.",
]

# Classic ElevenLabs premade voices, used only as a fallback because this key cannot list
# the account's actual voice library (see module docstring).
PREMADE_CANDIDATES = {
    "Rachel": "21m00Tcm4TlvDq8ikWAM",
    "Domi": "AZnzlk1XvdvUeBnXmlld",
    "Bella": "EXAVITQu4vr4xnSDxMaL",
    "Antoni": "ErXwobaYiN019PkySvjV",
    "Elli": "MF3mGyEYCl7XYWbV9V6O",
    "Josh": "TxGEqnHWrfWFTfGW9XjX",
    "Arnold": "VR6AewLTigWG4xSOukaG",
    "Adam": "pNInz6obpgDQGcFmaJgB",
    "Sam": "yoZ06aMxZJJ28mfd3POQ",
}

# Contrasting pairs: one lower/warmer voice, one brighter voice, as ARCHITECTURE.md §5.6 suggests.
CANDIDATE_PAIRS = [
    ("Adam", "Elli"),
    ("Arnold", "Domi"),
    ("Antoni", "Rachel"),
]


def try_list_voices(client: ElevenLabs) -> list | None:
    try:
        voices_resp = client.voices.get_all()
        return voices_resp.voices
    except Exception as e:  # noqa: BLE001 - smoke test, report and continue
        print(f"voices.get_all() FAILED: {type(e).__name__}: {e}")
        return None


def main() -> int:
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

    print("== account quota/usage ==")
    try:
        sub = client.user.subscription.get()
        print("character_count:", sub.character_count)
        print("character_limit:", sub.character_limit)
    except Exception as e:  # noqa: BLE001 - smoke test, report and continue
        print(f"FAILED: {type(e).__name__}: {e}")

    print("\n== voices.get_all() ==")
    voices = try_list_voices(client)
    if voices is not None:
        print(f"total voices: {len(voices)}")
        for v in voices[:15]:
            print(f"- {v.name} | {v.voice_id} | labels={v.labels} | preview={v.preview_url}")

    print("\n== fallback: verifying classic premade voices against this key ==")
    verified: dict[str, str] = {}
    for name, vid in PREMADE_CANDIDATES.items():
        try:
            audio_iter = client.text_to_speech.convert(voice_id=vid, text="Hi.", model_id="eleven_v3")
            len(b"".join(audio_iter))
            verified[name] = vid
            print(f"{name} ({vid}): OK")
        except Exception as e:  # noqa: BLE001 - smoke test, report and continue
            print(f"{name} ({vid}): FAILED {type(e).__name__}: {e}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pairs = [(a, b) for a, b in CANDIDATE_PAIRS if a in verified and b in verified]
    print(f"\n== Text to Dialogue samples ({len(pairs)} pairs) ==")
    for idx, (name_a, name_b) in enumerate(pairs, start=1):
        voice_a, voice_b = verified[name_a], verified[name_b]
        inputs = [
            {"text": SAMPLE_TURNS[0], "voice_id": voice_a},
            {"text": SAMPLE_TURNS[1], "voice_id": voice_b},
        ]
        total_chars = sum(len(t["text"]) for t in inputs)
        print(f"pair {idx}: {name_a} + {name_b} ({total_chars} chars)")
        try:
            audio_iter = client.text_to_dialogue.convert(
                inputs=inputs,
                model_id="eleven_v3",
                seed=1234,
            )
            audio_bytes = b"".join(audio_iter)
            out_path = OUT_DIR / f"pair_{idx}_{name_a}_{name_b}.mp3"
            out_path.write_bytes(audio_bytes)
            print(f"  saved {out_path} ({len(audio_bytes)} bytes)")
        except Exception as e:  # noqa: BLE001 - smoke test, report and continue
            print(f"  FAILED: {type(e).__name__}: {e}")

    print("\n== PCM output format check ==")
    probe_voice = next(iter(verified.values()), None)
    if probe_voice:
        try:
            pcm_iter = client.text_to_dialogue.convert(
                inputs=[{"text": "Testing PCM output.", "voice_id": probe_voice}],
                model_id="eleven_v3",
                output_format="pcm_44100",
            )
            pcm_bytes = b"".join(pcm_iter)
            print(f"PCM allowed on this plan: YES ({len(pcm_bytes)} bytes)")
        except Exception as e:  # noqa: BLE001 - smoke test, report and continue
            print(f"PCM allowed on this plan: NO ({type(e).__name__}: {e})")
    else:
        print("No verified voice available to probe PCM with.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
