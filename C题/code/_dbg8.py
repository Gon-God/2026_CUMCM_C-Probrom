# -*- coding: utf-8 -*-
"""Build a genuinely feasible point for June 21 using charge + curtailment, then verify with HiGHS."""
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
d = datetime(2025, 6, 21)
pv_plan = utils.fc_to_grid(fc3.get((d, 0)), 0)
L = load_yr[d] * (1.0 / 6.0)
G = pv_plan
n = 144
CMAX = 833.3333
off = {"C":0,"D":n,"e":2*n,"q":3*n,"r":4*n}
Nvar = 5*n

def build():
    c = np.zeros(Nvar)
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
res = milp(c, integrality=np.zeros(Nvar,dtype=int), bounds=B, constraints=LC)
print("feasibility-only status", res.status, res.message[:45])

C = np.zeros(n); D = np.zeros(n); q = np.zeros(n); r = np.zeros(n); e = np.empty(n)
es = 6000.0
for t in range(n):
    surplus = (G[t]/6 - L[t])
    if surplus > 0:
        cap = 10800.0 - es
        ct = min(surplus, CMAX, cap)
        C[t] = ct
        es += 0.9*ct
        if surplus - ct > 0:
            r[t] = surplus - ct
    else:
        deficit = -surplus
        avail = es - 1200.0
        dt = min(deficit, CMAX, avail)
        D[t] = dt
        es -= dt/0.9
        q[t] = deficit - dt
    e[t] = es
# terminal: adjust so e[-1]=6000 (scale the last discharge/charge)
print("e end before", round(es,1))
# post-force terminal by adding free variable r? Instead just report boundaries.
x = np.zeros(Nvar); x[off["C"]:off["C"]+n]=C; x[off["D"]:off["D"]+n]=D
x[off["e"]:off["e"]+n]=e; x[off["q"]:off["q"]+n]=q; x[off["r"]:off["r"]+n]=r
# print balance residuals on constructed point
mb = 0.0
for t in range(n):
    row = np.zeros(Nvar); row[off["q"]+t]=1; row[off["r"]+t]=1; row[off["C"]+t]=-1; row[off["D"]+t]=1
    v = float(row @ x) - (L[t]-G[t]/6)
    mb = max(mb, abs(v))
print("max balance residual on constructed:", round(mb,3))
print("e min/max", round(e.min(),1), round(e.max(),1), "e_end", round(e[-1],1))
print("C sum", round(C.sum(),1), "D sum", round(D.sum(),1), "q>0 count", int((q>1e-9).sum()), "r>0 count", int((r>1e-9).sum()))
