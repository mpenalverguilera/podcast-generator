from app.models import EpisodeStatus
from app.pipeline import assemble, extract, fetch, planner, rank, script, voice

# The single source of truth for stage order -- both the runner and its tests
# import this instead of duplicating the sequence.
STAGE_ORDER: list[tuple[EpisodeStatus, object]] = [
    (EpisodeStatus.PLANNING, planner),
    (EpisodeStatus.FETCHING, fetch),
    (EpisodeStatus.RANKING, rank),
    (EpisodeStatus.EXTRACTING, extract),
    (EpisodeStatus.SCRIPTING, script),
    (EpisodeStatus.VOICING, voice),
    (EpisodeStatus.ASSEMBLING, assemble),
]
