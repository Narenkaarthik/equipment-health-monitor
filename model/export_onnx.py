"""Export the deployed model to ONNX and write the parity fixture.

    python model/export_onnx.py            # applies the pre-registered deployment rule
    python model/export_onnx.py --arm full21 --seed 0   # explicit

Writes service/src/main/resources/models/rul.onnx + rul.json (feature names, version) and
tests/fixtures/parity_<arm>.json with 300 test rows, their sklearn predictions and the onnxruntime
predictions, so Python (tests/test_parity.py) and Java (OnnxRulModelParityTest) check the same numbers.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from baselines import arm_columns, load_arm  # noqa: E402
from features import CONFIG  # noqa: E402
from results import config_hash, load_runs  # noqa: E402
from train import SELECTIONS, checkpoint_path, truncated  # noqa: E402

MODELS = ROOT / "service" / "src" / "main" / "resources" / "models"
FIXTURES = ROOT / "tests" / "fixtures"
CAP = int(CONFIG["label"]["cap"])


def deployment_arm() -> str:
    runs = load_runs()
    main = runs[runs.phase == "main"]
    gap = main[main.arm == "reduced8"].test_rmse.mean() - main[main.arm == "full21"].test_rmse.mean()
    return "reduced8" if gap < 1.0 else "full21"


def export(arm: str, seed: int) -> dict:
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType
    import onnxruntime as ort

    n = json.loads(SELECTIONS.read_text())[arm]["n_estimators"]
    with open(checkpoint_path(arm, seed), "rb") as f:
        model = truncated(pickle.load(f)["model"], n)
    names, _ = arm_columns(arm)
    onx = convert_sklearn(model, initial_types=[("features", FloatTensorType([None, len(names)]))],
                          target_opset={"": 17, "ai.onnx.ml": 3})
    MODELS.mkdir(parents=True, exist_ok=True)
    (MODELS / "rul.onnx").write_bytes(onx.SerializeToString())
    version = f"gbr-{arm}-s{seed}-n{n}-{config_hash()}"
    meta = {"version": version, "arm": arm, "seed": seed, "n_estimators": n, "feature_names": names,
            "input_name": "features", "input_type": "float", "cap": CAP, "window": CONFIG["window"]["size"]}
    (MODELS / "rul.json").write_text(json.dumps(meta, indent=2))

    d = load_arm(arm)
    rng = np.random.default_rng(0)
    idx = np.sort(rng.choice(len(d["test_X"]), size=300, replace=False))
    X = np.ascontiguousarray(d["test_X"][idx])
    sk = model.predict(X)
    sess = ort.InferenceSession((MODELS / "rul.onnx").read_bytes(), providers=["CPUExecutionProvider"])
    rt = sess.run(None, {"features": X.astype(np.float32)})[0].reshape(-1)
    max_diff = float(np.max(np.abs(sk - rt)))
    fixture = {"version": version, "arm": arm, "feature_names": names, "rows": X.tolist(),
               "sklearn": sk.tolist(), "onnxruntime_python": rt.tolist(), "true_rul": d["test_y"][idx].tolist(),
               "tolerance_abs": CONFIG["parity_tolerance"]["onnx_prediction_abs"], "max_abs_diff_sklearn_vs_ort": max_diff}
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / f"parity_{arm}.json").write_text(json.dumps(fixture))
    print(f"exported {version}: {len(names)} features, {(MODELS / 'rul.onnx').stat().st_size / 1e6:.2f} MB, "
          f"sklearn vs onnxruntime max |diff| = {max_diff:.2e}")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    arm = a.arm or deployment_arm()
    export(arm, a.seed)


if __name__ == "__main__":
    main()
