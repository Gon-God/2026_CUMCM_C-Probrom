# -*- coding: utf-8 -*-
"""Isolate integer infeasibility: identical matrix, LP vs MILP, and numeric settings."""
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import utils
from scipy.sparse import csr_matrix
from scipy.optimize import milp, Bounds, LinearConstraint

fc3 = utils.load_attachment3()
load_yr, pv_yr = utils.load_attachment2()
price1, l1, v1 = utils.load_attachment1()
d = datetime(2025, 2, 1)
pv_plan = utils.fc_to_grid(fc3.get((d, 0)), 0)
L = load_yr[d] * (1.0 / 6.0)
G = pv_plan
n = 144
off = {"C":0,"D":n,"e":2*n,"z":3*n,"q":4*n,"r":5*n}
Nvar = 6*n
CMAX = 833.3333

def build():
    c = np.zeros(Nvar); c[off["C"]:off["C"]+n] += price1; c[off["D"]:off["D"]+n] -= price1
    lb = np.zeros(Nvar); ub = np.full(Nvar, np.inf)
    ub[off["C"]:off["C"]+n] = CMAX; ub[off["D"]:off["D"]+n] = CMAX
    lb[off["e"]:off["e"]+n] = 1200; ub[off["e"]:off["e"]+n] = 10800
    ub[off["z"]:off["z"]+n] = 1
    rows, lows, ups = [], [], []
    for t in range(n):
        r = np.zeros(Nvar); r[off["C"]+t]=1; r[off["z"]+t]=-CMAX
        rows.append(r); lows.append(-np.inf); ups.append(0)
        r = np.zeros(Nvar); r[off["D"]+t]=1; r[off["z"]+t]=CMAX
        rows.append(r); lows.append(-np.inf); ups.append(CMAX)
    for t in range(n):
        r = np.zeros(Nvar); r[off["e"]+t]=1
        if t>0: r[off["e"]+t-1] = -1
        r[off["C"]+t] = -0.9; r[off["D"]+t] = 1/0.9
        rows.append(r); lows.append(6000 if t==0 else 0); ups.append(6000 if t==0 else 0)
    r = np.zeros(Nvar); r[off["e"]+n-1]=1
    rows.append(r); lows.append(6000); ups.append(6000)
    for t in range(n):
        r = np.zeros(Nvar)
        r[off["q"]+t]=1; r[off["r"]+t]=1; r[off["C"]+t]=-1; r[off["D"]+t]=1
        rows.append(r); lows.append(L[t]-G[t]/6); ups.append(L[t]-G[t]/6)
    A = csr_matrix(np.vstack(rows))
    return c, Bounds(lb, ub), LinearConstraint(A, np.array(lows), np.array(ups))

c, B, LC = build()
ig = np.zeros(Nvar, dtype=int); ig[off["z"]:off["z"]+n] = 1

def run(name, integrality, opts):
    res = milp(c, integrality=integrality, bounds=B, constraints=LC, options=opts)
    print(name, "status", res.status, res.message[:40], "fun", res.fun if res.success else "")

run("LP", np.zeros(Nvar, dtype=int), {})
run("MILP default", ig, {})
run("MILP gap1e-5", ig, {"mip_rel_gap": 1e-5})
run("MILP presolve_off", ig, {"presolve": "off", "mip_rel_gap": 1e-4})
