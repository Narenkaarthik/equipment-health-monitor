"""Check that the pre-registered recipe did not change while the main runs were made.

The main runs recorded two config hashes: the 21-sensor runs were evaluated before an amendment of the ONNX
export settings, the other two arms after it. This script compares the committed pre-registration (the Block 2
commit) with the current file field by field and fails if any field that affects training, selection or
evaluation differs. Writes results/config_audit.json.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREREG_COMMIT = "b5acfb9"  # "Block 2: pre-registered recipe ..." - before any main run
EXPORT_ONLY = {"_comment", "deployment_rule", "onnx"}


def main() -> None:
    before = json.loads(subprocess.run(["git", "show", f"{PREREG_COMMIT}:model/config/experiment.json"], cwd=ROOT,
                                       capture_output=True, text=True, check=True).stdout)
    now = json.loads((ROOT / "model" / "config" / "experiment.json").read_text())
    changed = sorted(k for k in set(before) | set(now) if before.get(k) != now.get(k))
    affecting = [k for k in changed if k not in EXPORT_ONLY]
    out = {"prereg_commit": PREREG_COMMIT, "changed_fields": changed, "fields_affecting_training_or_evaluation": affecting,
           "added_after_prereg": {k: now[k] for k in changed if k not in before},
           "verdict": "recipe unchanged" if not affecting else "RECIPE CHANGED"}
    (ROOT / "results" / "config_audit.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    assert not affecting, f"pre-registered fields changed: {affecting}"


if __name__ == "__main__":
    main()
