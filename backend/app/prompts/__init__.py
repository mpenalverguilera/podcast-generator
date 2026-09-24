import re
from pathlib import Path

from app.schemas import RenderedPrompt

_FILENAME_RE = re.compile(r"^(?P<name>.+)\.v(?P<version>\d+)\.md$")
_FRONT_MATTER_RE = re.compile(r"^---\n(?P<meta>.*?)\n---\n(?P<body>.*)$", re.DOTALL)

DEFAULT_PROMPTS_DIR = Path(__file__).parent


def _parse_front_matter(raw: str) -> str:
    """Strips a small `key: value` front-matter block, if present, and returns
    just the body. Hand-rolled rather than pulling in PyYAML for three keys."""
    match = _FRONT_MATTER_RE.match(raw)
    return match.group("body") if match else raw


def load_prompt(name: str, prompts_dir: Path | None = None, **placeholders: str) -> RenderedPrompt:
    """Loads the highest-versioned `{name}.v{N}.md` file in prompts_dir and
    renders its body with the given placeholders via str.format_map."""
    directory = prompts_dir or DEFAULT_PROMPTS_DIR

    candidates: list[tuple[int, Path]] = []
    for path in directory.glob(f"{name}.v*.md"):
        match = _FILENAME_RE.match(path.name)
        if match and match.group("name") == name:
            candidates.append((int(match.group("version")), path))

    if not candidates:
        raise FileNotFoundError(f"no prompt files found for {name!r} in {directory}")

    version, path = max(candidates, key=lambda c: c[0])
    body = _parse_front_matter(path.read_text(encoding="utf-8"))
    text = body.format_map(placeholders) if placeholders else body
    return RenderedPrompt(name=name, version=version, text=text)
