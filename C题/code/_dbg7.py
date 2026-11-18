# -*- coding: utf-8 -*-
"""Deep-diagnose June 21: profile, feasibility-only, and a constructed feasible point."""
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
print("G max", round(G.max(),1), "min", round(G.min(),1), "G>0 count", int((G>0).sum()))
print("L min/max", round(L.min(),1), round(L.max(),1))
print("net L-G/6 min/max", round((L-G/6).min(),1), round((L-G/6).max(),1))

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
# feasibility-only
res = milp(np.zeros(Nvar), integrality=np.zeros(Nvar,dtype=int), bounds=B, constraints=LC)
print("feasibility-only status", res.status, res.message[:45])

# constructed trivial feasible point: C=D=0, e=6000, r=0, q=L-G/6 (positive per all slots)
qb = np.maximum(L-G/6, 0.0)
rb = np.maximum(G/6-L, 0.0)
x0 = np.zeros(Nvar)
x0[off["C"]:off["C"]+n] = 0
x0[off["D"]:off["D"]+n] = 0
x0[off["e"]:off["e"]+n] = 6000
x0[off["q"]:off["q"]+n] = qb
x0[off["r"]:off["r"]+n] = rb
# check all constraints manually
ok = True
def cv(vname, row, lo, up):
    global ok
    val = float(row @ x0)
    if val < lo - 1e-6 or val > up + 1e-6:
        print("VIOLATION", vname, val, "vs", lo, up); ok = False
for t in range(n): cv("cC", np.array([1 if i==off["C"]+t else 0 for i in range(Nvar)]), -np.inf, CMAX)
r = np.zeros(Nvar); r[off["e"]+n-1]=1
cv("term", r, 6000, 6000)
for t in range(n):
    r = np.zeros(Nvar); r[off["q"]+t]=1; r[off["r"]+t]=1; r[off["C"]+t]=-1; r[off["D"]+t]=1
    cv("bal%d"%t, r, L[t]-G[t]/6, L[t]-G[t]/6)
print("constructed point feasible:", ok)
