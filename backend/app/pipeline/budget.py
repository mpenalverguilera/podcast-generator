"""Episode length arithmetic shared by ranking (how many stories fit) and
scripting (how many words each part gets), so the two can't drift apart
(docs/DECISIONS.md D-65). Pure functions only."""

from typing import Literal

Depth = Literal["headlines", "deep"]

# D-28 measured eleven_v3 at 973 words -> 428 s, about 136 words per minute
# once pauses and section breaks are counted; 150 overshot by ~19%.
WORDS_PER_MINUTE = 135
MIN_MINUTES = 6
MAX_MINUTES = 20
DEFAULT_MINUTES = 10

# D-65: the frame (intro + outro) is 12% of the episode, clamped to 120-200
# words -- about 55-90 s -- so a short episode still gets a real cold open and
# a long one doesn't spend 2+ minutes on preview and sign-off.
_FRAME_SHARE = 0.12
_MIN_FRAME_WORDS = 120
_MAX_FRAME_WORDS = 200
_INTRO_SHARE_OF_FRAME = 0.65

# D-65: minutes a selected story is budgeted for, by the depth of the topic it
# is covered under. Enough room for a discussion, not just a read-out.
STORY_MINUTES: dict[str, float] = {"deep": 3.0, "headlines": 1.5}


def word_budget(target_minutes: int) -> tuple[int, int, int]:
    """(total, frame, story) words. The frame is the intro + outro."""
    total = target_minutes * WORDS_PER_MINUTE
    frame = min(_MAX_FRAME_WORDS, max(_MIN_FRAME_WORDS, round(_FRAME_SHARE * total)))
    return total, frame, total - frame


def frame_word_targets(frame_budget: int) -> tuple[int, int]:
    """(intro, outro) word targets within the frame budget."""
    intro = round(frame_budget * _INTRO_SHARE_OF_FRAME)
    return intro, frame_budget - intro


def story_minutes(target_minutes: int) -> float:
    """Minutes left for stories once the frame is taken out."""
    return word_budget(target_minutes)[2] / WORDS_PER_MINUTE


def estimated_story_count(target_minutes: int, depths: list[Depth]) -> int:
    """The settings page's "~N stories" hint: the story minutes divided by the
    average cost of the user's topic depths (an even deep/headlines mix if
    they have none yet). An estimate -- the real count depends on which
    topics have news that day."""
    costs = [STORY_MINUTES[d] for d in depths] or list(STORY_MINUTES.values())
    return max(1, round(story_minutes(target_minutes) / (sum(costs) / len(costs))))
