# -*- coding: utf-8 -*-
"""Locate the code dir (by content of milp_core.py / 附件), then run _dbg10.py in place and print its output."""
import os, sys, subprocess

def find_code():
    desk = os.path.join(os.path.expanduser("~"), "Desktop")
    hits = []
    for n in sorted(os.listdir(desk)):
        sub = os.path.join(os.path.join(desk, n, "C题"))
        code = os.path.join(sub, "code")
        if os.path.isdir(sub) and os.path.isdir(code):
            has = os.path.isfile(os.path.join(code, "milp_core.py"))
            att = os.path.isdir(os.path.join(sub, "附件"))
            hits.append((code, has, att, n))
    return hits

hits = find_code()
print("CANDIDATES:")
for (code, has, att, n) in hits:
    print("  ", n, "| has milp_core:", has, "| has 附件:", att, "|", code)

# choose: code dir that has both milp_core.py and 附件 (the real project)
chosen = None
for (code, has, att, n) in hits:
    if has and att:
        chosen = code
        break
if chosen is None and hits:
    chosen = hits[0][0]
print("CHOSEN:", chosen)
if not chosen:
    sys.exit(2)

target = os.path.join(chosen, "_dbg10.py")
if not os.path.isfile(target):
    # fallback: run _dbg9.py
    target = os.path.join(chosen, "_dbg9.py")
rc = subprocess.call([sys.executable, target], cwd=chosen)
print("SUBPROC_EXIT:", rc)
