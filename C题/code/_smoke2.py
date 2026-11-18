# -*- coding: utf-8 -*-
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import utils
from milp_core import solve_plan

fc3 = utils.load_attachment3()
load_yr, pv_yr = utils.load_attachment2()
price1, l1, v1 = utils.load_attachment1()

for d in [datetime(2025, 3, 20), datetime(2025, 6, 21), datetime(2025, 9, 23)]:
    fc0 = fc3.get((d, 0))
    pv_plan = utils.fc_to_grid(fc0, 0) if fc0 is not None else np.zeros(144)
    L = load_yr[d]
    G = pv_plan
    net = L - G / 6.0
    print("===", d.date(), "load max", round(L.max(), 1), "pv_plan max", round(G.max(), 1),
          "net (L-G/6) min", round(net.min(), 1), "max", round(net.max(), 1),
          "net<0 slots", int((net < 0).sum()))
    try:
        r = solve_plan(price1, pv_plan, L)
        print("   feasible cost", round(r["cost"], 1), "curt", round(r["curt"].sum(), 1))
    except Exception as e:
        print("   INFEASIBLE:", str(e)[:60])
