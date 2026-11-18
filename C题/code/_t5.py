# -*- coding: utf-8 -*-
import sys, os, time
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import utils, run_all
from milp_core import solve_plan, solve_exec

fc3 = utils.load_attachment3()
load_yr, pv_yr = utils.load_attachment2()
price1, l1, v1 = utils.load_attachment1()
price_yr = utils.load_attachment4()
dates = sorted([d for d in load_yr if d >= datetime(2025, 2, 1)])
d = dates[0]

t0 = time.time()
p2 = run_all.solve_one_day(fc3, d, load_yr[d], pv_yr[d], price1, with_adj=False)
t1 = time.time()
p4 = run_all.solve_one_day(fc3, d, load_yr[d], pv_yr[d], price_yr[d], with_adj=True)
t2 = time.time()

print("1 day P2-style (plan+exec): %.2fs" % (t1 - t0))
print("1 day P4/P3-style (plan+adj+exec): %.2fs" % (t2 - t1))
print("P2 em kWh", round(max(0, p2["em"].sum()), 1), "em cost", round(p2["emergency_cost"], 2))
print("P2 plan cost", round(p2["plan_cost"], 2))
print("P4 adj cost", round(p4.get("adj_cost", 0), 2), "em kWh", round(max(0, p4["em"].sum()), 1))
n = len(dates)
print("n dates", n, "est full-year (P2+P3+2xP4) seconds ~",
      round((t1 - t0) * n + (t2 - t1) * n * 3, 1))
