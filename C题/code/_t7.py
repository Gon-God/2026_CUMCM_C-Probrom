# -*- coding: utf-8 -*-
"""Verify the fixed balance on previously-infeasible days by calling the real solvers."""
import os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import utils
from milp_core import solve_plan, solve_exec

fc3 = utils.load_attachment3()
load_yr, pv_yr = utils.load_attachment2()
price1, l1, v1 = utils.load_attachment1()

for d in [datetime(2025, 6, 21), datetime(2025, 3, 20), datetime(2025, 9, 23), datetime(2025, 12, 21)]:
    fc0 = fc3.get((d, 0))
    G = utils.fc_to_grid(fc0, 0) if fc0 is not None else np.zeros(144)
    L = load_yr[d]
    try:
        r = solve_plan(price1, G, L)
        print(d.date(), "plan OK  cost", round(r["cost"], 1), "curt", round(r["curt"].sum(), 1),
              "C/D tot", round(r["C"].sum(), 1), round(r["D"].sum(), 1),
              "e end", round(r["e"][-1]))
        ex = solve_exec(price1, pv_yr[d], L, r["q"], r["q"])
        print("   exec OK  emerg cost", round(ex["emergency_cost"], 1), "em kWh", round(ex["em"].sum(), 1))
    except Exception as e:
        print(d.date(), "FAIL:", str(e)[:60])
