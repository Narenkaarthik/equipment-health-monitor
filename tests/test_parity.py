"""Python side of the parity test: the exported ONNX model reproduces sklearn within the pre-registered tolerance."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "service" / "src" / "main" / "resources" / "models"
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="module")
def deployed():
    if not (MODELS / "rul.onnx").exists():
        pytest.skip("no exported model yet")
    meta = json.loads((MODELS / "rul.json").read_text())
    fx = json.loads((FIXTURES / f"parity_{meta['arm']}.json").read_text())
    assert fx["version"] == meta["version"], "fixture and deployed model are from different exports"
    return meta, fx


def test_onnxruntime_matches_sklearn_on_fixture(deployed):
    import onnxruntime as ort

    meta, fx = deployed
    sess = ort.InferenceSession((MODELS / "rul.onnx").read_bytes(), providers=["CPUExecutionProvider"])
    X = np.array(fx["rows"], dtype=np.float64)
    pred = sess.run(None, {meta["input_name"]: X.astype(np.float32) if meta["input_type"] == "float" else X})[0].reshape(-1)
    np.testing.assert_allclose(pred, np.array(fx["sklearn"]), atol=fx["tolerance_abs"])
    assert X.shape[1] == len(meta["feature_names"])


def test_feature_names_are_a_subset_of_the_java_layout(deployed):
    sys.path.insert(0, str(ROOT / "model"))
    from data import SENSORS
    from features import feature_names

    meta, _ = deployed
    assert set(meta["feature_names"]) <= set(feature_names(SENSORS))
