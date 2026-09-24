import pytest

from app.pricing import cost_for


def test_openai_cost_is_exact_and_not_estimated() -> None:
    cost, is_estimate = cost_for("openai", "gpt-6-luna", units_in=1_000_000, units_out=1_000_000)
    assert cost == pytest.approx(0.10 + 0.50)
    assert is_estimate is False


def test_openai_unknown_model_raises() -> None:
    with pytest.raises(ValueError):
        cost_for("openai", "not-a-real-model", units_in=1, units_out=1)


def test_typesafe_cost_is_input_only_and_exact() -> None:
    cost, is_estimate = cost_for("typesafe", "jev-1.13.0", units_in=1_000_000, units_out=500)
    assert cost == pytest.approx(0.042)
    assert is_estimate is False
    with pytest.raises(ValueError):
        cost_for("typesafe", "jev-unknown", units_in=1)


def test_exa_cost_passes_through_and_is_not_estimated() -> None:
    cost, is_estimate = cost_for("exa", None, units_in=0, exa_cost_usd=0.007)
    assert cost == pytest.approx(0.007)
    assert is_estimate is False


def test_elevenlabs_cost_is_estimate() -> None:
    cost, is_estimate = cost_for("elevenlabs", "eleven_v3", units_in=1000)
    assert cost == pytest.approx(0.11)
    assert is_estimate is True


def test_local_and_fake_are_free() -> None:
    assert cost_for("local", None, 0) == (0.0, False)
    assert cost_for("fake", None, 0) == (0.0, False)
