from pathlib import Path

import pytest

from app.prompts import load_prompt


def test_picks_highest_version(tmp_path: Path) -> None:
    (tmp_path / "foo.v1.md").write_text("---\nname: foo\nversion: 1\n---\nOld: {placeholder}")
    (tmp_path / "foo.v2.md").write_text("---\nname: foo\nversion: 2\n---\nNew: {placeholder}")

    result = load_prompt("foo", prompts_dir=tmp_path, placeholder="x")

    assert result.version == 2
    assert result.text == "New: x"


def test_numeric_not_lexicographic_sort(tmp_path: Path) -> None:
    # "v10" < "v2" as strings but must sort after it numerically.
    (tmp_path / "foo.v2.md").write_text("---\nname: foo\nversion: 2\n---\nv2 body")
    (tmp_path / "foo.v10.md").write_text("---\nname: foo\nversion: 10\n---\nv10 body")

    result = load_prompt("foo", prompts_dir=tmp_path)

    assert result.version == 10
    assert result.text == "v10 body"


def test_missing_prompt_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("does-not-exist", prompts_dir=tmp_path)
