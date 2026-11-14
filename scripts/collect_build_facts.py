"""Collect facts produced by the build into results/ so documents can cite them as generated numbers:
JaCoCo line coverage, Java and Python test counts, and the Java inference timing from the parity test.

    ./mvnw verify && python -m pytest tests --junitxml=results/pytest.xml && python scripts/collect_build_facts.py
"""
from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"


def coverage() -> dict:
    rows = list(csv.DictReader(open(ROOT / "service" / "target" / "site" / "jacoco" / "jacoco.csv")))

    def pct(pkgs):
        miss = sum(int(r["LINE_MISSED"]) for r in rows if r["PACKAGE"] in pkgs)
        cov = sum(int(r["LINE_COVERED"]) for r in rows if r["PACKAGE"] in pkgs)
        return round(100 * cov / (miss + cov), 1)

    all_pkgs = {r["PACKAGE"] for r in rows}
    out = {"processing_alerts": pct({"dev.eqmon.processing", "dev.eqmon.alerts"}), "overall": pct(all_pkgs)}
    for p in sorted(all_pkgs):
        out[p.replace("dev.eqmon.", "").replace("dev.eqmon", "root")] = pct({p})
    return out


def junit(paths) -> dict:
    tests = failures = errors = skipped = 0
    for p in paths:
        root = ET.parse(p).getroot()
        suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
        for s in suites:
            tests += int(s.get("tests", 0))
            failures += int(s.get("failures", 0))
            errors += int(s.get("errors", 0))
            skipped += int(s.get("skipped", 0))
    return {"tests": tests, "failures": failures, "errors": errors, "skipped": skipped}


def main() -> None:
    RES.mkdir(exist_ok=True)
    (RES / "coverage.json").write_text(json.dumps(coverage(), indent=2))
    java = junit(list((ROOT / "service" / "target" / "surefire-reports").glob("TEST-*.xml"))
                 + list((ROOT / "replayer" / "target" / "surefire-reports").glob("TEST-*.xml")))
    py = junit([RES / "pytest.xml"]) if (RES / "pytest.xml").exists() else {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    counts = {"java": java["tests"], "java_failed": java["failures"] + java["errors"], "python": py["tests"],
              "python_failed": py["failures"] + py["errors"], "python_skipped": py["skipped"]}
    (RES / "test_counts.json").write_text(json.dumps(counts, indent=2))
    inf = ROOT / "service" / "target" / "java_inference.json"
    if inf.exists():
        (RES / "java_inference.json").write_text(inf.read_text())
    print(json.dumps({"coverage": json.loads((RES / "coverage.json").read_text()), "tests": counts,
                      "inference": json.loads(inf.read_text()) if inf.exists() else None}, indent=2))


if __name__ == "__main__":
    main()
