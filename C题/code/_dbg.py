# -*- coding: utf-8 -*-
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import utils
import milp_core
from milp_core import solve_plan

fc3 = utils.load_attachment3()
load_yr, pv_yr = utils.load_attachment2()
price1, l1, v1 = utils.load_attachment1()
dates = sorted([d for d in load_yr if d >= datetime(2025, 2, 1)])
d = dates[0]
fc0 = fc3.get((d, 0))
pv_plan = utils.fc_to_grid(fc0, 0) if fc0 is not None else np.zeros(144)
print("date", d, "fc0 present", fc0 is not None)
print("pv_plan max", pv_plan.max(), "load act max", load_yr[d].max())
try:
    r = solve_plan(price1, pv_plan, load_yr[d])
    print("OK cost", round(r["cost"], 2), "curt", round(r["curt"].sum(), 1))
except Exception as e:
    print("FAIL:", e)
    # diagnostics
    print("price len", len(price1), "pv len", len(pv_plan), "load len", len(load_yr[d]))
    L = load_yr[d] * (1.0 / 6.0)
    G = pv_plan
    print("L-G/6 min", (L - G / 6).min(), "max", (L - G / 6).max())
