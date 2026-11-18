# -*- coding: utf-8 -*-
"""Smoke-test a few days end-to-end before the full run."""
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import utils, run_all
from milp_core import solve_plan, solve_exec

fc3 = utils.load_attachment3()
load_yr, pv_yr = utils.load_attachment2()
price1, l1, v1 = utils.load_attachment1()
price_yr = utils.load_attachment4()

rep = [datetime(2025, 3, 20), datetime(2025, 6, 21), datetime(2025, 9, 23), datetime(2025, 12, 21)]
for d in rep:
    if d not in load_yr:
        print(d, "missing"); continue
    p3 = run_all.solve_one_day(fc3, d, load_yr[d], pv_yr[d], price1, with_adj=True)
    print("=== ", d.date())
    print("  plan_cost", round(p3["plan_cost"], 1), "adj", round(p3["adj_cost"], 1),
          "emerg", round(p3["emergency_cost"], 1),
          "qDA kWh", round(p3["qDA"].sum(), 1))
    print("  em kWh", round(max(0, p3["em"].sum()), 1),
          "  C kWh", round(p3["C"].sum(), 1), "D kWh", round(p3["D"].sum(), 1),
          "  e0/e_end", round(p3["e"][0]), round(p3["e"][-1]))
    # deviation magnitude
    print("  |a-qDA| total", round(np.abs(p3["a"] - p3["qDA"]).sum(), 1))
