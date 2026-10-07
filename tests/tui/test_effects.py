"""效果引擎测试（实现计划任务 3）。"""

import random

import pytest

from neow.tui.effects.gradient import GRADIENT, gradient_hex, gradient_text
from neow.tui.effects.scramble import SCRAMBLE_RUNES, ScrambleEngine


def test_gradient_endpoints():
    assert gradient_hex(0.0) == "#22d3ee"
    assert gradient_hex(1.0) == "#facc15"


def test_gradient_text_styles_every_char():
    t = gradient_text("abc", phase=0.2)
    assert len(t) == 3 and all(s.style for s in t._spans)


def test_scramble_deterministic_with_seed():
    a = ScrambleEngine(rng=random.Random(42))
    b = ScrambleEngine(rng=random.Random(42))
    assert (
        a.frame("settled ", "frontier", phase=0.1).plain
        == b.frame("settled ", "frontier", phase=0.1).plain
    )


def test_scramble_frontier_chars_from_runeset():
    e = ScrambleEngine(rng=random.Random(1))
    txt = e.frame("ok ", "XXXXXXXX", phase=0.0).plain
    assert txt.startswith("ok ") and len(txt) == 11
    assert set(txt[3:]) <= set(SCRAMBLE_RUNES)


def test_settle_has_no_random_chars():
    e = ScrambleEngine(rng=random.Random(7))
    assert e.settle("final answer", phase=0.3).plain == "final answer"


def test_scramble_disabled_returns_plain():
    e = ScrambleEngine(enabled=False)
    assert e.frame("a", "b", phase=0.0).plain == "a b"


def test_advance_wraps_phase():
    e = ScrambleEngine(phase_step=0.4)
    assert e.advance(0.8) == pytest.approx(0.2)
    assert e.advance(0.0) == pytest.approx(0.4)
