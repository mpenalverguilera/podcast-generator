from app.adapters.llm.protocol import LLM
from app.config import Settings, get_settings
from app.prompts import load_prompt
from app.schemas import InterestProfile, Usage

# Reused by the CLI's `profile` command and, later, the frontend's guided
# interview (GET /profile/questions). `key` is the stable identifier answers
# are keyed by; `question` is the display text.
GUIDED_QUESTIONS: list[dict[str, str]] = [
    {"key": "work", "question": "What do you follow for work?"},
    {"key": "fun", "question": "What do you follow for fun?"},
    {"key": "avoid", "question": "Anything you never want to hear about?"},
    {"key": "depth", "question": "Headlines or deeper analysis -- and for which topics?"},
]


def extract_profile(
    answers: dict[str, str], llm: LLM, settings: Settings | None = None
) -> tuple[InterestProfile, Usage]:
    settings = settings or get_settings()
    qa_text = "\n\n".join(
        f"Q: {q['question']}\nA: {answers[q['key']].strip()}"
        for q in GUIDED_QUESTIONS
        if answers.get(q["key"], "").strip()
    )
    prompt = load_prompt("profile_extractor", answers=qa_text or "(no answers given)")
    return llm.structured(prompt, InterestProfile, model=settings.model_profile, reasoning="low")
