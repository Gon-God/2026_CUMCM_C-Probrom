# -*- coding: utf-8 -*-
"""Auto-locate the code dir by content and exec a named script within it, writing output to a log."""
import os, sys, subprocess

def find_code():
    desk = os.path.join(os.path.expanduser("~"), "Desktop")
    for n in sorted(os.listdir(desk)):
        c = os.path.join(os.path.join(desk, n, "C题"), "code")
        if os.path.isdir(c) and os.path.isfile(os.path.join(c, "_dbg10.py")):
            return c
    # fallback: scan all dirs recursively-ish for _dbg10.py
    for n in sorted(os.listdir(desk)):
        c = os.path.join(desk, n, "C题", "code")
        if os.path.isdir(c):
            fl = [x for x in os.listdir(c) if x.startswith("_dbg10")]
            if fl:
                return c
    return None

code = find_code()
print("CODEFOUND:", code)
try:
    import numpy as np
    import utils
    from scipy.sparse import csr_matrix
    from scipy.optimize import milp, Bounds, LinearConstraint
    np.set_printoptions(linewidth=200)
