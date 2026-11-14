"""Compile the paper and Learn.pdf, check them for LaTeX errors, undefined macros and overfull boxes, then rebuild
the showcase (which copies both PDFs). Run after model/report.py has regenerated report/numbers.tex.

    python scripts/build_docs.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = [(ROOT / "report", "paper.tex"), (ROOT / "learn", "Learn.tex")]


def build(folder: Path, tex: str) -> None:
    subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", tex], cwd=folder,
                   capture_output=True, text=True)
    log = (folder / tex.replace(".tex", ".log")).read_text(encoding="latin-1")
    problems = [line for line in log.splitlines()
                if line.startswith("!") or "Overfull" in line or re.search(r"(Reference|Citation) .* undefined", line)]
    pdf = folder / tex.replace(".tex", ".pdf")
    if problems or not pdf.exists():
        print(f"{tex}: FAILED", *problems[:10], sep="\n  ")
        sys.exit(1)
    pages = re.search(r"Output written on .*\((\d+) pages", log)
    print(f"{tex}: ok, {pages.group(1) if pages else '?'} pages, no errors, no overfull boxes")


def main() -> None:
    for folder, tex in DOCS:
        build(folder, tex)
    subprocess.run([sys.executable, str(ROOT / "model" / "showcase.py")], check=True)


if __name__ == "__main__":
    main()
