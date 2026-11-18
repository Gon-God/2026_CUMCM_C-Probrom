# -*- coding: utf-8 -*-
"""Probe June 21: is the 'infeasible' a HiGHS numerical artifact? Test tolerance settings."""
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import utils
from scipy.sparse import csr_matrix
from scipy.optimize import milp, Bounds, LinearConstraint
import scipy.optimize as opt

fc3 = utils.load_attachment3()
load_yr, pv_yr = utils.load_attachment2()
price1, l1, v1 = utils.load_attachment1()
d = datetime(2025, 6, 21)
pv_plan = utils.fc_to_grid(fc3.get((d, 0)), 0)
L = load_yr[d] * (1.0 / 6.0)
G = pv_plan
n = 144
off = {"C":0,"D":n,"e":2*n,"q":3*n,"r":4*n}
Nvar = 5*n
CMAX = 833.3333

def build():
    c = np.zeros(Nvar); c[off["C"]:off["C"]+n] += price1; c[off["D"]:off["D"]+n] -= price1
    lb = np.zeros(Nvar); ub = np.full(Nvar, np.inf)
    ub[off["C"]:off["C"]+n] = CMAX; ub[off["D"]:off["D"]+n] = CMAX
    lb[off["e"]:off["e"]+n] = 1200; ub[off["e"]:off["e"]+n] = 10800
    rows, lows, ups = [], [], []
    for t in range(n):
        r = np.zeros(Nvar); r[off["C"]+t]=1; rows.append(r); lows.append(-np.inf); ups.append(CMAX)
        r = np.zeros(Nvar); r[off["D"]+t]=1; rows.append(r); lows.append(-np.inf); ups.append(CMAX)
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
ig = np.zeros(Nvar, dtype=int)
for name, opts in [("default", {}), ("feasibility_tol_1e-9", {"primal_feasibility_tolerance": 1e-9}),
                   ("feas_tol_1e-7", {"primal_feasibility_tolerance": 1e-7}),
                   ("dual_tol_1e-8", {"dual_feasibility_tolerance": 1e-8})]:
    res = milp(c, integrality=ig, bounds=B, constraints=LC, options=opts)
    print(name, "status", res.status, res.message[:45], "fun", res.fun if res.success else "")
