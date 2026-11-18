# -*- coding: utf-8 -*-
"""Reading C: the storage strictly follows the day-ahead plan (no intra-day
re-dispatch); emergency purchase covers the whole residual shortfall.

Quantifies how much of Problem 2's small emergency total comes from the freedom
to re-dispatch storage inside the day.
"""
import os, sys
from datetime import datetime
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "code"))

import utils
from milp_core import solve_plan
from run_all import solve_one_day

price1, l1, v1 = utils.load_attachment1()
load_yr, pv_yr = utils.load_attachment2()
fc3 = utils.load_attachment3()
dates = sorted([d for d in load_yr if d >= datetime(2025, 2, 1)])
DT = 1.0 / 6.0

tot_rigid = 0.0
tot_flex = 0.0
rigid_cost = 0.0
days_nz = 0
per_month = {}
worst = None
for d in dates:
    fc0 = fc3.get((d, 0))
    g_fc = utils.fc_to_grid(fc0, 0) if fc0 is not None else np.zeros(144)
    L = load_yr[d] * DT
    g_act = pv_yr[d] * DT
    plan = solve_plan(price1, g_fc, load_yr[d])
    # storage frozen at the planned schedule -> shortfall paid at 5p
    em_rigid = np.maximum(0.0, L + plan["C"] - plan["q"] - g_act - plan["D"])
    v = float(em_rigid.sum())
    tot_rigid += v
    rigid_cost += float((5.0 * price1 * em_rigid).sum())
    if v > 1e-3:
        days_nz += 1
        per_month[d.month] = per_month.get(d.month, 0.0) + v
        if worst is None or v > worst[1]:
            worst = (d, v)
    ex = solve_one_day(fc3, d, load_yr[d], pv_yr[d], price1, with_adj=False)
    tot_flex += float(np.maximum(ex["em"], 0).sum())

print("READING C: storage frozen at the planned schedule (no re-dispatch)")
print("  total emergency kWh   : %.1f" % tot_rigid)
print("  total emergency cost  : %.1f yuan" % rigid_cost)
print("  days with emergency   : %d / %d" % (days_nz, len(dates)))
if worst:
    print("  worst day             : %s  %.1f kWh" % (worst[0].date(), worst[1]))
print("  monthly kWh           : " + ", ".join("%d:%.0f" % kv for kv in sorted(per_month.items())))
print("")
print("READING B (current, storage re-dispatched) total emergency kWh: %.1f" % tot_flex)
print("ratio C/B               : %.1f x" % (tot_rigid / tot_flex))
