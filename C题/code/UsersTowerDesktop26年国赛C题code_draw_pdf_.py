# -*- coding: utf-8 -*-
"""Render the drawio content as paper-ready PDF flow diagrams via matplotlib."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "figures")

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False


def box(ax, cx, cy, w, h, text, fc="#eef4fb", ec="#2f6db3", fs=10, weight="normal"):
    b = FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle="round,pad=0.02",
                       fc=fc, ec=ec, lw=1.2)
    ax.add_patch(b)
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, weight=weight)


def arrow(ax, x1, y1, x2, y2, color="#555555"):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=14,
                        color=color, lw=1.4)
    ax.add_patch(a)


def render_roadmap():
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.set_xlim(0, 10); ax.set_ylim(0, 6); ax.axis("off")
    box(ax, 1.6, 5.4, 2.4, 0.7, "附件数据\n(附件1-4)")
    box(ax, 5.0, 5.4, 2.6, 0.7, "数据处理与口径定义\n(144时段·储能参数)")
    arrow(ax, 2.8, 5.4, 3.7, 5.4)
    box(ax, 1.6, 4.2, 2.4, 0.7, "问题1\n单日确定性日前计划 LP")
    box(ax, 1.6, 3.2, 2.4, 0.7, "问题2\n全年日前计划 + 紧急购电")
    box(ax, 5.5, 4.2, 2.5, 0.8, "问题3\n四次预报滚动调整购电")
    box(ax, 5.5, 3.2, 2.5, 0.8, "问题4\n动态电价下重算问题2、3")
    box(ax, 3.6, 1.4, 3.4, 0.8, "result1 / result2 / result3\nresult4-2 / result4-3 + 论文图表")
    arrow(ax, 5.0, 5.4, 5.0, 4.6)
    arrow(ax, 5.0, 4.6, 1.6, 4.2)
    arrow(ax, 5.0, 4.6, 5.5, 4.2)
    arrow(ax, 2.8, 4.2, 2.8, 3.55)
    arrow(ax, 6.75, 4.2, 6.75, 3.58)
    arrow(ax, 2.8, 3.2, 2.8, 2.4)
    arrow(ax, 6.75, 3.2, 6.75, 2.4)
    arrow(ax, 2.8, 2.4, 1.9, 1.8)
    arrow(ax, 5.5, 2.4, 5.3, 1.8)
    fig.savefig(os.path.join(OUT, "fig_roadmap.pdf"), bbox_inches="tight")
    plt.close(fig)


def render_q1():
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_xlim(0, 10); ax.set_ylim(0, 9); ax.axis("off")
    box(ax, 2.2, 8.2, 2.6, 0.7, "附件1: 电价p、负荷L、光伏预测G")
    box(ax, 7.8, 8.2, 2.6, 0.9, "储能参数: 容量12000\nSOC[1200,10800]·效率0.9·功率5000")
    box(ax, 5.0, 6.6, 3.2, 0.8, "0:00制定日前计划 (LP)\nmin Σ p·q")
    box(ax, 5.0, 4.6, 3.6, 1.0, "约束: 功率平衡·SOC递推·充放互斥(天然)\n首末SOC=6000·购电≥0·弃光≥0")
    box(ax, 5.0, 2.4, 3.0, 0.8, "输出: 计划购电量q、充放电量、购电费\n→ result1")
    arrow(ax, 3.5, 8.2, 5.0, 7.0)
    arrow(ax, 6.5, 8.2, 5.4, 7.0)
    arrow(ax, 5.0, 6.2, 5.0, 5.1)
    arrow(ax, 5.0, 4.1, 5.0, 2.8)
    fig.savefig(os.path.join(OUT, "fig_flow_q1.pdf"), bbox_inches="tight")
    plt.close(fig)


def render_q3():
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.set_xlim(0, 10); ax.set_ylim(0, 8); ax.axis("off")
    box(ax, 2.0, 7.0, 2.8, 0.9, "0:00 附件3预报\n制定计划购电量 qDA")
    box(ax, 6.0, 7.0, 2.6, 0.9, "6/12/18时新预报\n对剩余时段重优化")
    box(ax, 2.0, 5.0, 2.8, 0.9, "调整购电量 a\n(调整购电工作表)")
    box(ax, 6.0, 5.0, 2.8, 1.0, "实际光伏执行\n储能再调度 → 紧急购电 5×")
    box(ax, 6.0, 3.2, 2.8, 0.9, "偏差结算\na>qDA按1.5×，a<qDA按0.5×")
    box(ax, 4.0, 1.2, 3.4, 0.8, "总费用 = 计划+调整偏差+紧急\n输出 result3")
    arrow(ax, 3.4, 7.0, 4.7, 7.0)
    arrow(ax, 7.3, 7.0, 7.3, 6.0)
    arrow(ax, 3.4, 5.9, 4.6, 1.6)
    arrow(ax, 7.3, 5.0, 7.3, 4.1)
    arrow(ax, 7.3, 3.2, 5.7, 1.6)
    fig.savefig(os.path.join(OUT, "fig_flow_q3.pdf"), bbox_inches="tight")
    plt.close(fig)


render_roadmap()
render_q1()
render_q3()
print("PDF diagrams written to", OUT)
print(sorted([x for x in os.listdir(OUT) if x.endswith(".pdf")]))
