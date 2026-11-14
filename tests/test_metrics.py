"""Metric unit tests: the headline (RMSE) and the secondaries against hand-computed values."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "model"))
from metrics import mae, nasa_score, rmse, status_metrics, status_of  # noqa: E402


def test_rmse_and_mae_by_hand():
    y = [10, 20, 30]
    p = [12, 18, 30]  # errors 2, -2, 0
    assert rmse(y, p) == np.sqrt(8 / 3)
    assert mae(y, p) == 4 / 3


def test_nasa_score_penalises_late_more_than_early():
    # late by 10: exp(10/10) - 1 = e - 1 ; early by 13: exp(13/13) - 1 = e - 1
    assert np.isclose(nasa_score([50], [60]), np.e - 1)
    assert np.isclose(nasa_score([50], [37]), np.e - 1)
    assert nasa_score([50], [60]) > nasa_score([50], [40])
    assert nasa_score([5, 5], [5, 5]) == 0.0


def test_status_thresholds():
    np.testing.assert_array_equal(status_of([100, 60, 59.9, 30, 29.9, 0]), [0, 0, 1, 1, 2, 2])


def test_accuracy_misleads_on_an_imbalanced_label():
    # 8 healthy, 1 warning, 1 critical; a model that always says "healthy" scores 80% accuracy
    y = [100] * 8 + [45, 10]
    p = [100] * 10
    m = status_metrics(y, p)
    assert m["status_acc"] == 0.8
    assert m["critical_recall"] == 0.0
    assert m["status_f1_macro"] < 0.35
