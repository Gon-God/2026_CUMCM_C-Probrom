# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import utils, run_all
from milp_core import solve_plan, solve_exec

# sanity on emergency label formatting
print("slot_lbl(0)=", run_all.slot_lbl(0))
print("slot_lbl(5)=", run_all.slot_lbl(5))
print("slot_lbl(143)=", run_all.slot_lbl(143))

# Problem 1 end-to-end
p1, l1, v1 = utils.load_attachment1()
ex = run_all.solve_one_day(utils.load_attachment3(), None, None, None, p1, with_adj=False) if False else None

# quickly run P1 via the driver's solve for attachment1 (no forecasts -> plan uses 0:00 missing -> zeros)
import numpy as np
# We'll instead directly test plan on attachment1
plan = solve_plan(p1, v1, l1)
a = plan["q"].copy()
exe = solve_exec(p1, v1, l1, a, plan["q"])
print("P1 plan cost", round(plan["cost"], 2))
print("P1 exec emerg cost", round(exe["emergency_cost"], 2), "em kWh", round(exe["em"].sum(), 1))
print("P1 execute C sum", round(exe["C"].sum(), 1), "D sum", round(exe["D"].sum(), 1))
print("P1 e0/e_end", round(exe["e"][0]), round(exe["e"][-1]))
