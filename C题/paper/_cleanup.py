# -*- coding: utf-8 -*-
"""Tidy the paper/ directory: drop diagnostics, archive superseded Typst sources."""
import os, shutil, glob

paper = os.path.dirname(os.path.abspath(__file__))

# 1) remove one-off diagnostic scripts and logs
junk = ["_diag.py", "_diag.bat", "_diag_py.log", "_xel_diag.log",
        "_check.py", "_check2.py", "_pdfinfo.py", "_compile.bat", "_compile_py.log",
        "main.aux", "main.out", "main.toc"]
removed = []
for j in junk:
    p = os.path.join(paper, j)
    if os.path.isfile(p):
        os.remove(p)
        removed.append(j)

# 2) archive the superseded Typst sources (keep them, just out of the way)
arch = os.path.join(paper, "_typst_superseded")
os.makedirs(arch, exist_ok=True)
moved = []
for p in glob.glob(os.path.join(paper, "*.typ")) + glob.glob(os.path.join(paper, "sections", "*.typ")):
    if os.path.isfile(p):
        shutil.move(p, os.path.join(arch, os.path.basename(p)))
        moved.append(os.path.basename(p))
if os.path.isdir(os.path.join(paper, "sections")):
    try:
        os.rmdir(os.path.join(paper, "sections"))
    except OSError:
        pass

print("removed:", removed)
print("archived:", moved)
print("\npaper/ now contains:")
for f in sorted(os.listdir(paper)):
    print("  ", f)
