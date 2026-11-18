# -*- coding: utf-8 -*-
"""Read-only diagnostic for Problem 2.

Q1: how much emergency purchase does P2 actually produce, on which days?
Q2: what happens under the strict reading (day-ahead plan built from Attachment-2
    actual PV instead of the 0:00 Attachment-3 forecast)?
Q3: why is the "emergency" sheet of results/result2.xlsx empty?

Nothing is written; only stdout.
"""
import os, sys
from datetime import datetime
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.join(os.path.dirname(HERE), "code")
sys.path.insert(0, CODE)

import utils
from milp_core import solve_plan, solve_exec
from run_all import solve_one_day

def main():
    price1, l1, v1 = utils.load_attachment1()
    load_yr, pv_yr = utils.load_attachment2()
    fc3 = utils.load_attachment3()
    dates = sorted([d for d in load_yr if d >= datetime(2025, 2, 1)])
    print("days", len(dates), dates[0].date(), dates[-1].date())

    TARGET = [datetime(2025, 3, 20), datetime(2025, 6, 21),
              datetime(2025, 9, 23), datetime(2025, 12, 21)]

    rows_b, rows_a = [], []
    for d in dates:
        # --- reading B: day-ahead plan from the 0:00 forecast of Attachment 3 ---
        exb = solve_one_day(fc3, d, load_yr[d], pv_yr[d], price1, with_adj=False)
        em_b = float(np.maximum(exb["em"], 0).sum())
        rows_b.append((d, em_b, float(exb["emergency_cost"]),
                       float((price1 * exb["qDA"]).sum())))

        # --- reading A: day-ahead plan from Attachment-2 actual PV ---
        qa = solve_plan(price1, pv_yr[d], load_yr[d])["q"]
        exa = solve_exec(price1, pv_yr[d], load_yr[d], qa, qa)
        em_a = float(np.maximum(exa["em"], 0).sum())
        rows_a.append((d, em_a, float(exa["emergency_cost"]),
                       float((price1 * qa).sum())))

    def report(tag, rows):
        em = np.array([r[1] for r in rows])
        cost = np.array([r[2] for r in rows])
        plan = np.array([r[3] for r in rows])
        nz = em > 1e-3
        print("-" * 66)
        print(tag)
        print("  total emergency kWh   : %.1f" % em.sum())
        print("  total emergency cost  : %.1f" % cost.sum())
        print("  total plan cost       : %.1f" % plan.sum())
        print("  days with em > 0      : %d / %d" % (int(nz.sum()), len(em)))
        if nz.any():
            print("  em max day            : %s  %.1f kWh" %
                  (rows[int(np.argmax(em))][0].date(), em.max()))
            idx = np.argsort(-em)[:10]
            print("  top10 days            :")
            for i in idx:
                if em[i] > 1e-3:
                    print("      %s  %9.1f kWh  %9.1f yuan" %
                          (rows[i][0].date(), em[i], cost[i]))
            print("  monthly em kWh        :")
            m = {}
            for r in rows:
                m.setdefault(r[0].month, 0.0)
                m[r[0].month] += r[1]
            print("      " + "  ".join("%d:%d" % (k, round(v)) for k, v in sorted(m.items())))
        print("  the four dates required by Table 3:")
        for d in TARGET:
            hit = [r for r in rows if r[0] == d]
            if hit:
                print("      %s  em = %.1f kWh  em_cost = %.1f yuan  plan_cost = %.1f" %
                      (d.date(), hit[0][1], hit[0][2], hit[0][3]))
        print("  template placeholder dates (only these exist in the sheet):")
        for d in (datetime(2025, 2, 1), datetime(2025, 2, 2), datetime(2025, 12, 31)):
            hit = [r for r in rows if r[0] == d]
            if hit:
                print("      %s  em = %.3f kWh" % (d.date(), hit[0][1]))

    report("READING B: plan = 0:00 forecast (current code / paper)", rows_b)
    report("READING A: plan = Attachment-2 actual PV (strict statement reading)", rows_a)

    print("-" * 66)
    print("plan cost difference A - B = %.1f yuan" %
          (sum(r[3] for r in rows_a) - sum(r[3] for r in rows_b)))
    print("total cost A = %.1f ; total cost B = %.1f" %
          (sum(r[2] + r[3] for r in rows_a), sum(r[2] + r[3] for r in rows_b)))

if __name__ == "__main__":
    main()
