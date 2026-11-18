# -*- coding: utf-8 -*-
"""Test June 21 with a FREE terminal SOC (no e_144=6000) to isolate whether the
terminal equality is causing the infeasibility."""
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy.sparse import csr_matrix
from scipy.optimize import milp, Bounds, LinearConstraint
import utils

fc3 = utils.load_attachment3()
load_yr, pv_yr = utils.load_attachment2()
price1, l1, v1 = utils.load_attachment1()
# try a set of days
days = [datetime(2025,6,21), datetime(2025,3,20), datetime(2025,9,23), datetime(2025,12,21)]
n = 144
CMAX = 833.3333
off = {"C":0,"D":n,"e":2*n,"q":3*n,"r":4*n}
Nvar = 5*n

def build(G,L,terminal):
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
    if terminal:
        r = np.zeros(Nvar); r[off["e"]+n-1]=1
        rows.append(r); lows.append(6000); ups.append(6000)
    for t in range(n):
        r = np.zeros(Nvar)
        r[off["q"]+t]=1; r[off["r"]+t]=1; r[off["C"]+t]=-1; r[off["D"]+t]=1
        rows.append(r); lows.append(L[t]-G[t]/6); ups.append(L[t]-G[t]/6)
    A = csr_matrix(np.vstack(rows))
    return c, Bounds(lb,ub), LinearConstraint(A, np.array(lows), np.array(ups))

for d in days:
    fc0 = fc3.get((d,0))
    G = utils.fc_to_grid(fc0,0) if fc0 is not None else np.zeros(n)
    L = load_yr[d]*(1.0/6.0)
    line = []
    for term in (True, False):
        c,B,LC = build(G,L,term)
        ig = np.zeros(Nvar,dtype=int)
        res = milp(c, integrality=ig, bounds=B, constraints=LC)
        line.append("term" if term else "free")
        line.append("OK" if res.success else "INFEAS")
    print(d.date(), " | ", line[0], line[1], " | ", line[2], line[3])
