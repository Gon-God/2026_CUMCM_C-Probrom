# -*- coding: utf-8 -*-
"""Compile paper/main.tex with xelatex (twice) and report errors."""
import os, sys, subprocess, shutil

paper = os.path.dirname(os.path.abspath(__file__))
main = os.path.join(paper, "main.tex")
pdf = os.path.join(paper, "main.pdf")

xel = "D:/texlive/2026/bin/windows/xelatex.exe"
if not os.path.isfile(xel):
    xel = shutil.which("xelatex") or shutil.which("xelatex.exe") or "xelatex"

log = open(os.path.join(paper, "_compile.log"), "w", encoding="utf-8")
rcs = []
for i in range(2):
    r = subprocess.run([xel, "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
                       cwd=paper, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", errors="replace")
    rcs.append(r.returncode)
    log.write("\n===== pass %d rc=%d =====\n" % (i + 1, r.returncode))
    log.write(out)
log.close()

print("xelatex:", xel)
print("return codes:", rcs)
print("main.pdf exists:", os.path.isfile(pdf),
      "size:", os.path.getsize(pdf) if os.path.isfile(pdf) else 0)

# print the most relevant error lines
try:
    txt = open(os.path.join(paper, "_compile.log"), encoding="utf-8").read()
except Exception:
    txt = ""
lines = txt.splitlines()
errs = [l for l in lines if l.startswith("!") or "Error" in l or "Fatal" in l
        or "Undefined control sequence" in l or "not found" in l]
print("--- error lines ---")
for l in errs[:25]:
    print(l)
