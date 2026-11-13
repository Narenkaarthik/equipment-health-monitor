"""Freeze the group-aware engine split for FD001 (run once; the JSON is committed).

70 train / 15 validation / 15 test engines, chosen by a fixed seed. An engine never appears in two
splits, so no cycle of a test engine is ever seen in training (tests/test_split.py enforces it).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data import SPLIT_FILE, load_train, make_split  # noqa: E402

SEED = 20240613
N_VAL = 15
N_TEST = 15


def main() -> None:
    if SPLIT_FILE.exists():
        print(f"{SPLIT_FILE} already exists; refusing to overwrite a frozen split")
        return
    units = sorted(load_train().unit.unique().tolist())
    split = make_split(units, SEED, N_VAL, N_TEST)
    SPLIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SPLIT_FILE.write_text(json.dumps(split, indent=2))
    print(f"wrote {SPLIT_FILE}: train={len(split['train'])} val={len(split['val'])} test={len(split['test'])}")


if __name__ == "__main__":
    main()
