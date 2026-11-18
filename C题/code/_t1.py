# -*- coding: utf-8 -*-
import numpy as np
import utils
from milp_core import solve_plan

p, l, v = utils.load_attachment1()
r = solve_plan(p, v, l)
e = r["e"]
print("EMAX", utils.EMAX, "EMIN", utils.EMIN)
print("e min/max", e.min(), e.max())
print("n above 10800", int((e > 10800).sum()))
print("max idx", e.argmax())
print("cost", r["cost"])
print("sum p*q", float((p * r["q"]).sum()))
print("e end", e[-1])
print("C sum", float(r["C"].sum()), "D sum", float(r["D"].sum()))
