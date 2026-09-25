"""Curated voice list for `GET /voices` (docs/phases/05-api-scheduler.md
step 2). The ElevenLabs key on this project has no `voices_read` scope
(docs/DECISIONS.md D-09), so the account's real voice library can't be
listed live -- this is the fixed set of classic premade voices phase 00
verified against this key (scripts/smoke/elevenlabs_check.py), with short
labels for the settings UI. Antoni and Rachel are the defaults
(DEFAULT_VOICE_HOST_A/B); the rest are offered as alternatives."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CuratedVoice:
    id: str
    name: str
    label: str


CURATED_VOICES: list[CuratedVoice] = [
    CuratedVoice(id="ErXwobaYiN019PkySvjV", name="Antoni", label="warm male"),
    CuratedVoice(id="21m00Tcm4TlvDq8ikWAM", name="Rachel", label="calm female"),
    CuratedVoice(id="pNInz6obpgDQGcFmaJgB", name="Adam", label="deep male narrator"),
    CuratedVoice(id="EXAVITQu4vr4xnSDxMaL", name="Bella", label="soft female"),
    CuratedVoice(id="AZnzlk1XvdvUeBnXmlld", name="Domi", label="confident female"),
    CuratedVoice(id="MF3mGyEYCl7XYWbV9V6O", name="Elli", label="bright female"),
    CuratedVoice(id="TxGEqnHWrfWFTfGW9XjX", name="Josh", label="deep male"),
    CuratedVoice(id="VR6AewLTigWG4xSOukaG", name="Arnold", label="bold male"),
    CuratedVoice(id="yoZ06aMxZJJ28mfd3POQ", name="Sam", label="energetic male"),
]
