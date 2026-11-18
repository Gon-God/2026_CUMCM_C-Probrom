# -*- coding: utf-8 -*-
"""Decisive check for a high-PV day (June 21): build the exact solve_plan LP,
verify the trivial point (q/net, curt/surplus, battery idle at 6000) satisfies
every row, then solve with both milp and linprog(highs)."""
import os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import utils
import milp_core
from scipy.sparse import csr_matrix
from scipy.optimize import milp, Bounds, LinearConstraint, linprog

fc3 = utils.load_attachment3()
load_yr, pv_yr = utils.load_attachment2()
price1, l1, v1 = utils.load_attachment1()
d = datetime(2025, 6, 21)
fc0 = fc3.get((d, 0))
G = utils.fc_to_grid(fc0, 0)
L = load_yr[d] * (1.0 / 6.0)
net = L - G / 6.0
print("net min/max", round(net.min(),1), round(net.max(),1), "n<0", int((net<0).sum()))

n = 144
CMAX = 833.3333
off = {"C":0,"D":n,"e":2*n,"q":3*n,"r":4*n}
Nvar = 5*n
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
    rows.append(r); lows.append(net[t]); ups.append(net[t])
A = csr_matrix(np.vstack(rows))
AV = A.toarray()

# trivial feasible point
x = np.zeros(Nvar)
x[off["q"]:off["q"]+n] = np.maximum(net,0)
x[off["r"]:off["r"]+n] = np.maximum(-net,0)
x[off["e"]:off["e"]+n] = 6000  # battery idle
maxres = 0.0; bad = -1
for i,row in enumerate(AV):
    v = float(row @ x)
    lo, hi = lows[i], ups[i]
    if v < lo-1e-6 or v > hi+1e-6:
        d = max(abs(v-lo), abs(v-hi))
        if d>maxres: maxres=d; bad=i
print("trivial point max constraint violation:", round(maxres,4), "at row", bad, "(0 = feasible)")

# milp
res = milp(c, integrality=np.zeros(Nvar,dtype=int), bounds=Bounds(lb,ub),
           constraints=LinearConstraint(A, np.array(lows), np.array(ups)))
print("milp status", res.status, res.message[:45], "fun", res.fun if res.success else "")

# linprog highs (convert bounds to tuple array)
bnds = np.vstack([lb, ub]).T
res2 = linprog(c, A_eq=A, b_eq=np.array(ups), bounds=bnds, method="highs")
print("linprog(highs) status", res2.status, res2.message[:45], "fun", res2.fun if res2.success else "")
