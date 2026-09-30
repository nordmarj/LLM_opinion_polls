import pytest

from survey.analysis import wilson


def test_wilson_known_values():
    lo, hi = wilson(10, 20)
    assert lo == pytest.approx(0.299, abs=1e-3) and hi == pytest.approx(0.701, abs=1e-3)
    assert wilson(0, 10)[0] == pytest.approx(0.0, abs=1e-12)
    assert wilson(10, 10)[1] == pytest.approx(1.0, abs=1e-12)
    assert wilson(0, 0) == (0.0, 1.0)
