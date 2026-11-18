# -*- coding: utf-8 -*-
"""Why does Problem 2 have emergency purchase at all, and where does it come from?

Read-only: correlates the daily emergency energy with the PV forecast error
(forecast above actual) that the day-ahead plan could not foresee.
"""
import os, sys
from datetime import datetime
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "code"))

import utils
from run_all import solve_one_day

price1, l1, v1 = utils.load_attachment1()
load_yr, pv_yr = utils.load_attachment2()
fc3 = utils.load_attachment3()
dates = sorted([d for d in load_yr if d >= datetime(2025, 2, 1)])
DT = 1.0 / 6.0

rows = []
for d in dates:
    fc0 = fc3.get((d, 0))
    g_fc = utils.fc_to_grid(fc0, 0) if fc0 is not None else np.zeros(144)
    g_act = pv_yr[d]
    ex = solve_one_day(fc3, d, load_yr[d], g_act, price1, with_adj=False)
    em = float(np.maximum(ex["em"], 0).sum())
    deficit = np.maximum(0.0, (g_fc - g_act) * DT)      # kWh the plan over-credited
    surplus = np.maximum(0.0, (g_act - g_fc) * DT)
    rows.append((d, em, float(deficit.sum()), float(deficit.max()),
                 float(surplus.sum()), float((price1 * ex["qDA"]).sum())))

em = np.array([r[1] for r in rows])
defi = np.array([r[2] for r in rows])
mx = np.array([r[3] for r in rows])
sur = np.array([r[4] for r in rows])
plan = np.array([r[5] for r in rows])

print("days                          :", len(rows))
print("sum em kWh                    : %.1f" % em.sum())
print("sum forecast deficit kWh      : %.1f" % defi.sum())
print("corr(em, daily deficit)       : %.3f" % np.corrcoef(em, defi)[0, 1])
print("corr(em, max slot deficit)    : %.3f" % np.corrcoef(em, mx)[0, 1])
print("corr(em, daily surplus)       : %.3f" % np.corrcoef(em, sur)[0, 1])
nz = em > 1e-3
print("mean deficit | em>0            : %.1f kWh" % defi[nz].mean())
print("mean deficit | em=0            : %.1f kWh" % defi[~nz].mean())
print("max slot deficit threshold     : min over em>0 = %.1f kWh (storage cap/slot 833.3)"
      % mx[nz].min() if nz.any() else "n/a")

print("")
print("the four Table-3 dates (forecast vs actual):")
for d in (datetime(2025, 3, 20), datetime(2025, 6, 21), datetime(2025, 9, 23), datetime(2025, 12, 21)):
    i = [k for k, r in enumerate(rows) if r[0] == d][0]
    print("  %s  em=%8.1f kWh | forecast deficit %8.1f kWh | surplus %8.1f kWh | plan %8.1f kWh"
          % (d.date(), em[i], defi[i], sur[i], plan[i]))

print("")
print("monthly: em kWh / forecast deficit kWh")
m = {}
for r in rows:
    a, b = m.get(r[0].month, (0.0, 0.0))
    m[r[0].month] = (a + r[1], b + r[2])
for k in sorted(m):
    print("   %2d  %9.1f  %10.1f" % (k, m[k][0], m[k][1]))
