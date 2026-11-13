# 0003: In-process ONNX Runtime, not a separate Python model service

**Status:** accepted (stage 3)

## Options

1. **ONNX Runtime inside the Java service.** Train in Python, export with skl2onnx, load the file
   from the classpath, score each window in the request thread.
2. **A small Python scoring service** (FastAPI + sklearn) called over HTTP per reading or per batch.
3. **Re-implement the model in Java** (walk the trees by hand).

## Decision

Option 1. The parity test (`OnnxRulModelParityTest`, 300 real test rows, tolerance 1e-3 cycles,
double-precision input) is what makes it safe: without a parity test, option 1 silently serves a
different model than the one that was validated.

## Why

- **Latency.** One tree-ensemble call is tens of microseconds in-process; an HTTP hop is a
  millisecond or more and adds a second failure mode. The plan's "done when" for stage 3 is
  "a predicted RUL within a few milliseconds".
- **One deployable.** `docker compose up` starts one application container. A Python service would
  double the images, the health checks and the version skew to manage.
- **Versioning is explicit.** `rul.json` carries the model version, the arm, the selected number
  of trees and the exact feature names; every health score row stores that version. Deploying a
  new model is: export, run the parity test, ship the jar. Zero-downtime deploy is a rolling
  restart; scores from both versions coexist in the table, distinguishable by `model_version`.

## What we gave up

- The model family is limited to what skl2onnx converts (tree ensembles, linear models, small
  MLPs are fine; a custom PyTorch sequence model would need its own export path).
- Pre-processing must be reproduced in Java (the window features). That is why the feature
  parity fixture exists (`MachineWindowTest.matchesThePythonFeatureFixture`, tolerance 1e-6).
- Float precision: ONNX Runtime's `TreeEnsembleRegressor` computes in float32 (a double-typed
  variant does not run), so features and thresholds are rounded to float32 and a value within
  about 1e-7 relative of a split could land in a different leaf. Measured on 300 real test rows
  the largest difference from sklearn was 2.7e-5 cycles; the parity test guards the 1e-3 bound.

## Fallback (not needed)

The plan allows a Python HTTP scorer if ONNX blocks for more than a week. It did not block.
