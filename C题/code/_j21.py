# -*- coding: utf-8 -*-
"""Decisive June-21 check: replicate solve_plan's LP rows exactly, verify the trivial
point (C=D=0, e=6000, q=max(net,0), r=max(-net,0)) satisfies every row, then ask HiGHS."""
import os, sys
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
G = utils.fc_to_grid(fc3.get((d, 0)), 0)
L = load_yr[d] * (1.0 / 6.0)
net = L - G / 6.0
n = 144
CMAX = 833.3333
off = {"C": 0, "D": n, "e": 2 * n, "q": 3 * n, "r": 4 * n}
Nvar = 5 * n

c = np.zeros(Nvar)
c[off["C"]:off["C"] + n] += price1
c[off["D"]:off["D"] + n] -= price1
lb = np.zeros(Nvar); ub = np.full(Nvar, np.inf)
ub[off["C"]:off["C"] + n] = CMAX
ub[off["D"]:off["D"] + n] = CMAX
lb[off["e"]:off["e"] + n] = 1200; ub[off["e"]:off["e"] + n] = 10800

rows, lows, ups = [], [], []
for t in range(n):
    r = np.zeros(Nvar); r[off["C"] + t] = 1; rows.append(r); lows.append(-np.inf); ups.append(CMAX)
    r = np.zeros(Nvar); r[off["D"] + t] = 1; rows.append(r); lows.append(-np.inf); ups.append(CMAX)
for t in range(n):
    r = np.zeros(Nvar); r[off["e"] + t] = 1
    if t > 0: r[off["e"] + t - 1] = -1
    r[off["C"] + t] = -0.9; r[off["D"] + t] = 1 / 0.9
    rows.append(r); lows.append(6000 if t == 0 else 0); ups.append(6000 if t == 0 else 0)
r = np.zeros(Nvar); r[off["e"] + n - 1] = 1
rows.append(r); lows.append(6000); ups.append(6000)
for t in range(n):
    r = np.zeros(Nvar)
    r[off["q"] + t] = 1; r[off["r"] + t] = 1; r[off["C"] + t] = -1; r[off["D"] + t] = 1
    rows.append(r); lows.append(net[t]); ups.append(net[t])

A = csr_matrix(np.vstack(rows))
Av = A.toarray()

# trivial feasible point
x = np.zeros(Nvar)
x[off["q"]:off["q"] + n] = np.maximum(net, 0)
x[off["r"]:off["r"] + n] = np.maximum(-net, 0)
x[off["e"]:off["e"] + n] = 6000
# C,D stay 0

worst = 0.0; bad = -1
for i in range(len(rows)):
    v = float(Av[i] @ x)
    lo, up = lows[i], ups[i]
    oklo = -np.inf if lo == -np.inf else lo - 1e-6
    okup = np.inf if up == np.inf else up + 1e-6
    if not (oklo <= v <= okup):
        d = max(abs(v - lo) if lo != -np.inf else 0, abs(v - up) if up != np.inf else 0)
        if d > worst:
            worst = d; bad = i
print("worst residual of trivial point:", round(worst, 4), "at row", bad, "(should be 0 if feasible)")
print("e within bounds:", bool((x[off["e"]:off["e"] + n] >= 1199.999).all() and (x[off["e"]:off["e"] + n] <= 10801).all()))

res = milp(c, integrality=np.zeros(Nvar, dtype=int), bounds=Bounds(lb, ub),
           constraints=LinearConstraint(A, np.array(lows), np.array(ups)))
print("HiGHS:", res.status, res.message[:50], "fun", res.fun if res.success else "")
if res.success:
    xr = res.x
    print("opt q total", round(xr[off["q"]:off["q"] + n].sum(), 1), "C", round(xr[off["C"]:off["C"] + n].sum(), 1),
          "D", round(xr[off["D"]:off["D"] + n].sum(), 1), "curt", round(xr[off["r"]:off["r"] + n].sum(), 1),
          "e_min", round(xr[off["e"]:off["e"] + n].min()), "e_end", round(xr[off["e"]:off["e"] + n].max()))
