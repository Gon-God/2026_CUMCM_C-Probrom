# -*- coding: utf-8 -*-
"""Generate paper figures (PDF, no in-figure titles) from the solved results."""
import os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import utils
import run_all

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = os.path.join(utils.ROOT, "figures")
os.makedirs(OUT, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

N = 144
hours = np.arange(1, N + 1) / 6.0  # 0:10..24:00 ~ hour labels (x-axis 0..24)
x_axis = np.linspace(0, 24, N)

load_yr, pv_yr = utils.load_attachment2()
fc3 = utils.load_attachment3()
price1, l1, v1 = utils.load_attachment1()
price_yr = utils.load_attachment4()


def date_obj(d):
    return d if isinstance(d, datetime) else datetime.strptime(str(d)[:10], "%Y-%m-%d")


def solve_day(date, price, with_adj=True):
    return run_all.solve_one_day(fc3, date_obj(date), load_yr[date_obj(date)],
                                 pv_yr[date_obj(date)], price, with_adj=with_adj)


# ---- Figure 1: representative day (2025-03-20 equinox) under P3 (four forecasts) ----
rep = datetime(2025, 3, 20)
ex = solve_day(rep, price1, with_adj=True)
fig, ax = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
ax[0].plot(x_axis, load_yr[rep], label="小区负荷", color="C3")
ax[0].plot(x_axis, pv_yr[rep], label="光伏实际功率", color="C1")
ax[0].plot(x_axis, ex["qDA"], label="计划购电量", color="C0", lw=2)
ax[0].plot(x_axis, ex["a"], label="调整购电量", color="C2", ls="--")
ax[0].set_ylabel("功率/购电 (kW), 购电 (kWh)")
ax[0].legend()
ax[0].grid(alpha=0.3)
ax[1].plot(x_axis, ex["e"], label="储能电量 (SOC)", color="C4")
ax[1].axhline(10800, color="gray", ls=":", lw=0.8)
ax[1].axhline(1200, color="gray", ls=":", lw=0.8)
ax[1].set_xlabel("时刻 (小时)")
ax[1].set_ylabel("储电量 (kWh)")
ax[1].legend()
ax[1].grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig_repday.pdf"))
plt.close(fig)

# ---- Figure 2: emergency kWh day-by-day, P2 (0:00 forecast only) vs P3 (four forecasts) ----
dates = sorted([d for d in load_yr if d >= datetime(2025, 2, 1)])
d2 = {}
d3 = {}
for d in dates:
    ex2 = solve_day(d, price1, with_adj=False)
    ex3 = solve_day(d, price1, with_adj=True)
    d2[d] = float(np.maximum(ex2["em"], 0).sum())
    d3[d] = float(np.maximum(ex3["em"], 0).sum())
idx = np.arange(len(dates))
fig, ax = plt.subplots(figsize=(9, 4))
ax.bar(idx, [d2[d] for d in dates], width=0.8, label="P2: 仅0:00预报", color="C0", alpha=0.75)
ax.bar(idx, [d3[d] for d in dates], width=0.8, label="P3: 四次预报", color="C1", alpha=0.85)
ax.set_yscale("symlog")
ax.set_xlabel("日期序号 (2025-02-01 .. 2025-12-31)")
ax.set_ylabel("紧急购电量 (kWh/日)")
ax.legend()
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig_emergency.pdf"))
plt.close(fig)

# ---- Figure 3: daily plan cost box across seasons (P2 fixed price) ----
costs = {d: float(ex_plan.get("plan_cost")) for d, ex_plan in {} for d in []}  # placeholder, will fill below
# better: compute per-day total P2 cost
p2c = {}
for d in dates:
    ex2 = solve_day(d, price1, with_adj=False)
    p2c[d] = float(ex2["plan_cost"] + ex2["emergency_cost"])
fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(idx, [p2c[d] for d in dates], color="C0")
ax.set_xlabel("日期序号")
ax.set_ylabel("日购电费用 P2 (元)")
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig_daily_cost.pdf"))
plt.close(fig)

print("figures written to", OUT)
print("P2 annual totals: plan", round(sum(p2c.values()) or 0, None) if False else "")
