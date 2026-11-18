# -*- coding: utf-8 -*-
"""Resolve the actual project code directory (locks down the real on-disk folder name)."""
import os, json

def find_code():
    desk = os.path.join(os.path.expanduser("~"), "Desktop")
    for name in sorted(os.listdir(desk)):
        cand = os.path.join(desk, name)
        if not os.path.isdir(cand):
            continue
        code = os.path.join(os.path.join(cand, "C题"), "code")
        if os.path.isdir(code) and os.path.isfile(os.path.join(code, "milp_core.py")):
            return code, name
    return None

res = find_code()
if res:
    code, name = res
    print("REAL_DIR:", repr(code))
    print("FOLDER:", repr(name))
    print("py files:", [x for x in sorted(os.listdir(code)) if x.endswith(".py")])
else:
    print("NOT FOUND")
