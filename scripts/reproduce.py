"""One-command reproduction.

    python scripts/reproduce.py --quick    # minutes: data, invariants, features, deployed model, every number and figure
    python scripts/reproduce.py            # hours: also every missing experiment (resumable) and the full Java suite

--quick
  1. downloads NASA C-MAPSS FD001 if data/raw is empty and checks its checksums;
  2. runs the pytest invariants (split leak, features, metrics, ONNX parity);
  3. rebuilds the features and the sensor sets of each arm from the frozen split;
  4. retrains the deployed model (same recipe, same seed) if its checkpoint is missing, and checks that it
     reproduces the committed parity fixture's predictions exactly: the shipped model is reproducible;
  5. regenerates every table, figure, report/numbers.tex, results/numbers.json, README.md and showcase/RESULTS.md;
  6. builds the Java modules and runs the Java unit tests (no services needed).
full (no flag), additionally
  * runs the main experiment and the post hoc ablations through the resumable queue (runs already in
    results/runs.csv are skipped, so on a fresh clone with the committed results nothing is retrained);
  * runs the full Java suite including integration tests (needs Docker, or MONITOR_TEST_DB_URL /
    MONITOR_TEST_REDIS_HOST / MONITOR_TEST_KAFKA_BOOTSTRAP pointing at running services);
  * compiles the paper and Learn.pdf and regenerates the showcase.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
URL = "https://phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip"
MD5 = {"train_FD001.txt": "259f340bac32ce6fa8894815600fa757", "test_FD001.txt": "62316d1dd70f88a9a43a1e2690765437",
       "RUL_FD001.txt": "8f4a8b3d2692b2f7d8e72b344927bf4b"}


def step(title: str) -> None:
    print(f"\n=== {title}", flush=True)


def run(*cmd, env=None) -> None:
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT, env=env)


def py(*args) -> None:
    run(sys.executable, *args)


def ensure_data() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    if not all((RAW / f).exists() for f in MD5):
        print(f"downloading {URL}")
        outer = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(URL, timeout=120).read()))
        inner_name = next(n for n in outer.namelist() if n.endswith("CMAPSSData.zip"))
        inner = zipfile.ZipFile(io.BytesIO(outer.read(inner_name)))
        for name in [*MD5, "readme.txt"]:
            (RAW / name).write_bytes(inner.read(name))
    for name, digest in MD5.items():
        got = hashlib.md5((RAW / name).read_bytes()).hexdigest()
        assert got == digest, f"{name}: checksum {got} != {digest}"
    print("data present, checksums match")


def deployed_model_reproduces() -> None:
    sys.path.insert(0, str(ROOT / "model"))
    import pickle

    import numpy as np
    from train import checkpoint_path, truncated

    meta = json.loads((ROOT / "service" / "src" / "main" / "resources" / "models" / "rul.json").read_text())
    if not checkpoint_path(meta["arm"], meta["seed"]).exists():
        print(f"retraining {meta['arm']} seed {meta['seed']} (a few minutes)")
        py("model/train.py", "fit", "--arm", meta["arm"], "--seed", str(meta["seed"]))
    with open(checkpoint_path(meta["arm"], meta["seed"]), "rb") as f:
        model = truncated(pickle.load(f)["model"], meta["n_estimators"])
    fx = json.loads((ROOT / "tests" / "fixtures" / f"parity_{meta['arm']}.json").read_text())
    diff = float(np.max(np.abs(model.predict(np.array(fx["rows"])) - np.array(fx["sklearn"]))))
    assert diff < 1e-9, f"retrained model differs from the shipped one by {diff}"
    print(f"deployed model {meta['version']} reproduced: max difference {diff:.1e} on {len(fx['rows'])} rows")


def mvn(*args) -> None:
    wrapper = ROOT / ("mvnw.cmd" if os.name == "nt" else "mvnw")
    if not shutil.which("java"):
        print("java not on PATH: skipping the Java build")
        return
    run(wrapper, "-B", "-ntp", *args)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()

    step("1. data")
    ensure_data()
    step("2. invariants (pytest)")
    py("-m", "pytest", "-q", "tests", "--junitxml=results/pytest.xml")
    step("3. features and arms from the frozen split")
    py("model/eda.py")
    py("model/pipeline.py")
    if not a.quick:
        step("experiments (resumable; existing runs are skipped)")
        py("scripts/run_queue.py")
        py("scripts/run_queue.py", "--ablations")
    step("4. the deployed model reproduces")
    deployed_model_reproduces()
    step("5. Java build and tests")
    if a.quick:
        mvn("package", "-DskipTests")
        mvn("-pl", "service,replayer", "test", "-Dtest=*Test", "-Dsurefire.failIfNoSpecifiedTests=false")
    else:
        mvn("verify")
        py("scripts/collect_build_facts.py")
    step("6. every number, table and figure")
    py("model/error_analysis.py", "summarise")
    py("model/report.py")
    if not a.quick:
        step("documents")
        py("scripts/build_docs.py")
    print("\nreproduction finished")


if __name__ == "__main__":
    main()
