# -*- coding: utf-8 -*-
"""Generate paper figures (PDF, no in-figure titles) from solved results."""
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
x_axis = np.linspace(0, 24, N)

load_yr, pv_yr = utils.load_attachment2()
fc3 = utils.load_attachment3()
price1, l1, v1 = utils.load_attachment1()
price_yr = utils.load_attachment4()

def solve_day(d, price, with_adj=True):
    return run_all.solve_one_day(fc3, d, load_yr[d], pv_yr[d], price, with_adj=with_adj)

dates = sorted([d for d in load_yr if d >= datetime(2025, 2, 1)])

# Fig 1: representative spring day 2025-03-20 (P3)
rep = datetime(2025, 3, 20)
ex = solve_day(rep, price1, with_adj=True)
fig, ax = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
ax[0].plot(x_axis, load_yr[rep], label="小区负荷", color="C3")
ax[0].plot(x_axis, pv_yr[rep], label="光伏实际功率", color="C1")
ax[0].plot(x_axis, ex["qDA"], label="计划购电量", color="C0", lw=2)
ax[0].plot(x_axis, ex["a"], label="调整购电量", color="C2", ls="--")
ax[0].set_ylabel("负荷/光伏 (kW), 购电 (kWh)")
ax[0].legend(); ax[0].grid(alpha=0.3)
ax[1].plot(x_axis, ex["e"], label="储能电量", color="C4")
ax[1].axhline(10800, color="gray", ls=":", lw=0.8)
ax[1].axhline(1200, color="gray", ls=":", lw=0.8)
ax[1].set_xlabel("时刻 (小时)"); ax[1].set_ylabel("储电量 (kWh)")
ax[1].legend(); ax[1].grid(alpha=0.3)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig_repday.pdf")); plt.close(fig)

# Fig 2: daily emergency kWh P2 vs P3
em2, em3 = [], []
for d in dates:
    em2.append(float(np.maximum(solve_day(d, price1, False)["em"], 0).sum()))
    em3.append(float(np.maximum(solve_day(d, price1, True)["em"], 0).sum()))
idx = range(len(dates))
fig, ax = plt.subplots(figsize=(9, 4))
ax.bar(idx, em2, width=0.8, label="P2: 仅0:00预报", color="C0", alpha=0.75)
ax.bar(idx, em3, width=0.8, label="P3: 四次预报", color="C1", alpha=0.85)
ax.set_yscale("symlog")
ax.set_xlabel("日期序号 (2025-02-01 .. 2025-12-31)")
ax.set_ylabel("紧急购电量 (kWh/日)")
ax.legend(); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig_emergency.pdf")); plt.close(fig)

# Fig 3: daily P2 total cost series
p2c = []
for d in dates:
    e2 = solve_day(d, price1, False)
    p2c.append(float(e2["plan_cost"] + e2["emergency_cost"]))
fig, ax = plt.subplots(figsize=(8, 3.5))
ax.plot(idx, p2c, color="C0")
ax.set_xlabel("日期序号"); ax.set_ylabel("日购电费用 P2 (元)")
ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig_daily_cost.pdf")); plt.close(fig)

# Fig 4: price curves fixed vs dynamic
fig, ax = plt.subplots(figsize=(8, 3.5))
ax.plot(x_axis, price1, label="固定电价 (附件1)", color="C0")
ax.plot(x_axis, price_yr[rep], label="动态电价 (附件4, 2025-03-20)", color="C1", ls="--")
ax.set_xlabel("时刻 (小时)"); ax.set_ylabel("电价 (元/kWh)")
ax.legend(); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig_price.pdf")); plt.close(fig)

print("figures in", OUT)
print(sorted(os.listdir(OUT)))
