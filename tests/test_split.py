"""The frozen split must partition the 100 FD001 engines with no group leak."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "data" / "splits" / "fd001_split.json"
RAW = ROOT / "data" / "raw" / "train_FD001.txt"


@pytest.fixture(scope="module")
def split():
    return json.loads(SPLIT.read_text())


def test_split_sizes(split):
    assert len(split["train"]) == 70
    assert len(split["val"]) == 15
    assert len(split["test"]) == 15


def test_no_group_leak(split):
    train, val, test = set(split["train"]), set(split["val"]), set(split["test"])
    assert not (train & val), "engine in both train and val"
    assert not (train & test), "engine in both train and test"
    assert not (val & test), "engine in both val and test"


def test_split_covers_every_engine(split):
    assert sorted(split["train"] + split["val"] + split["test"]) == list(range(1, 101))


@pytest.mark.skipif(not RAW.exists(), reason="raw data not present (gitignored)")
def test_no_row_leak_in_frames():
    import sys

    sys.path.insert(0, str(ROOT / "model"))
    from data import load_split, load_train, split_frames

    frames = split_frames(load_train(), load_split())
    seen = {}
    for name, frame in frames.items():
        for unit in frame.unit.unique():
            assert unit not in seen, f"engine {unit} rows appear in {seen.get(unit)} and {name}"
            seen[unit] = name
    assert sum(len(f) for f in frames.values()) == 20631
