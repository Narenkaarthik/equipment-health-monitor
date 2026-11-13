"""Window features: vectorised implementation == reference, and == values computed by hand."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from features import window_features_1d, window_features_reference  # noqa: E402


def test_hand_computed_small_window():
    # x = [1, 2, 4, 8], W = 3. Hand values:
    # k=0: [1]      mean 1, std 0, slope 0
    # k=1: [1,2]    mean 1.5, std 0.5, slope 1
    # k=2: [1,2,4]  mean 7/3, std sqrt(((1-7/3)^2+(2-7/3)^2+(4-7/3)^2)/3)=sqrt(14/9)=1.2472, slope 1.5
    # k=3: [2,4,8]  mean 14/3, std sqrt(((2-14/3)^2+(4-14/3)^2+(8-14/3)^2)/3)=sqrt(56/9)=2.4944, slope 3
    f = window_features_1d(np.array([1.0, 2.0, 4.0, 8.0]), 3)
    expected = np.array([
        [1.0, 0.0, 0.0],
        [1.5, 0.5, 1.0],
        [7 / 3, np.sqrt(14 / 9), 1.5],
        [14 / 3, np.sqrt(56 / 9), 3.0],
    ])
    np.testing.assert_allclose(f, expected, atol=1e-12)


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_vectorised_matches_reference(seed):
    rng = np.random.default_rng(seed)
    x = 9000 + rng.normal(0, 5, size=400).cumsum() * 0.01 + rng.normal(0, 3, size=400)
    for w in (1, 2, 5, 30):
        np.testing.assert_allclose(window_features_1d(x, w), window_features_reference(x, w), atol=1e-7, rtol=1e-9)


def test_constant_sensor_has_zero_std_and_slope():
    f = window_features_1d(np.full(50, 518.67), 30)
    assert np.allclose(f[:, 0], 518.67)
    assert np.allclose(f[:, 1], 0.0, atol=1e-9)
    assert np.allclose(f[:, 2], 0.0, atol=1e-9)


def test_fixture_matches_current_implementation():
    import json

    fixture_path = ROOT / "tests" / "fixtures" / "window_features_engine1.json"
    if not fixture_path.exists():
        pytest.skip("fixture not generated yet")
    fx = json.loads(fixture_path.read_text())
    raw = np.array(fx["raw"])
    for j, s in enumerate(fx["sensors"]):
        np.testing.assert_allclose(window_features_1d(raw[:, j], fx["window"]), np.array(fx["expected"][s]), atol=1e-9)
