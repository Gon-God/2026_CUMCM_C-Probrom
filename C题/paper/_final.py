# -*- coding: utf-8 -*-
"""Compile main.tex twice and produce a concise verification summary."""
import os, sys, re, subprocess, shutil

paper = os.path.dirname(os.path.abspath(__file__))
figdir = os.path.join(os.path.dirname(paper), "figures")
pdf = os.path.join(paper, "main.pdf")

xel = "D:/texlive/2026/bin/windows/xelatex.exe"
if not os.path.isfile(xel):
    xel = shutil.which("xelatex") or "xelatex"

logs = []
for i in range(2):
    r = subprocess.run([xel, "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
                       cwd=paper, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    logs.append(r.stdout.decode("utf-8", errors="replace"))
open(os.path.join(paper, "_compile.log"), "w", encoding="utf-8").write("\n".join(logs))

last = logs[-1]
print("return code (pass2):", r.returncode)
m = re.search(r"Output written on main\.pdf \((\d+) pages?, (\d+) bytes\)", last)
print("output:", m.group(0) if m else "not reported")
print("missing chars:", len([l for l in last.splitlines() if "Missing character" in l]))
undef = [l for l in last.splitlines() if "undefined" in l.lower()]
print("undefined refs:", len(undef))
for l in undef[:5]:
    print("   ", l)
print("main.pdf exists:", os.path.isfile(pdf), os.path.getsize(pdf) if os.path.isfile(pdf) else 0)

print("\n--- referenced figures present on disk ---")
for f in ["fig_roadmap", "fig_repday", "fig_flow_q1", "fig_flow_q3", "fig_emergency", "fig_price"]:
    p = os.path.join(figdir, f + ".pdf")
    print("   %-16s %s" % (f, "OK" if os.path.isfile(p) else "MISSING"))
