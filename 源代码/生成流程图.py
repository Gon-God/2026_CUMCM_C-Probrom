from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

# 输出目录随脚本定位（源代码/figures/总体数据），不依赖绝对路径与当前工作目录。
OUT = Path(__file__).resolve().parent / "figures" / "总体数据"
OUT.mkdir(parents=True, exist_ok=True)
mpl.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"], "axes.unicode_minus": False, "pdf.fonttype": 42, "ps.fonttype": 42})

fig, ax = plt.subplots(figsize=(16.5, 8.8))
ax.set_xlim(0, 16.5); ax.set_ylim(0, 8.7); ax.axis("off")

def round_box(x, y, w, h, text, face="#FFFFFF", edge="#64748B", fs=9.4):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.035,rounding_size=0.08", linewidth=1.15, facecolor=face, edgecolor=edge)
    ax.add_patch(p)
    ax.text(x+w/2, y+h/2, text, ha="center", va="center", fontsize=fs, color="#1E293B", linespacing=1.22)

def down_arrow(x, y1, y2, color):
    ax.add_patch(FancyArrowPatch((x, y1), (x, y2), arrowstyle="-|>", mutation_scale=13, linewidth=1.15, color=color))

def right_arrow(x1, x2, y):
    ax.add_patch(FancyArrowPatch((x1, y), (x2, y), arrowstyle="-|>", mutation_scale=11, linewidth=1.0, color="#94A3B8"))

blocks = [
        ("问题一  确定性计划", "#DCE8F3", "#58738C", [
            "典型日电价、负荷、光伏",
            "变量与约束\n购电 / 充放电 / SOC",
            "日前线性规划\n功率平衡 + 日循环",
            "策略识别\n低价充电、高价放电",
            "最优调度与费用",
        ]),
        ("问题二  随机日前计划", "#E5F0D8", "#6C8D58", [
            "全年负荷与实际光伏",
            "场景构造\nK-medoids 聚类 20 情景",
            "两阶段随机规划\n日前计划 + 场景补救",
            "风险控制\n非预期性约束 + 兜底",
            "日前计划、紧急购电、弃电",
        ]),
        ("问题三  计划—调整", "#F6E2E0", "#A56864", [
            "滚动预报与历史残差",
            "预报更新\n0 / 6 / 12 / 18 时点",
            "两层滚动规划\n锁定计划、调整交付量",
            "结算校验\n追补 / 下调 / 兜底",
            "计划—调整—实际执行",
        ]),
        ("问题四  波动电价", "#DDEFF1", "#5B8A90", [
            "逐时波动电价",
            "价格映射\n固定价 → 实时价",
            "同族模型重算\n随机日前 + 滚动调整",
            "策略比较\n费用 / 服务 / CVaR",
            "成本、风险与套利响应",
        ]),
]

left, gap, width = 0.22, 0.22, 3.91
bottom, height, header_h = 0.25, 8.20, 0.67
card_xpad, card_w = 0.25, width - 0.50

card_h = 1.12
ys = [6.66, 5.20, 3.74, 2.28, 0.82]
hs = [card_h] * 5
for i, (title, fill, edge, texts) in enumerate(blocks):
    x = left + i * (width + gap)
    ax.add_patch(Rectangle((x, bottom), width, height, facecolor=fill, edgecolor=edge, linewidth=1.35))
    ax.add_patch(Rectangle((x, bottom + height - header_h), width, header_h, facecolor=edge, edgecolor=edge, linewidth=0))
    ax.text(x + width/2, bottom + height - header_h/2, title, ha="center", va="center", fontsize=13.4, color="white", fontweight="bold")
    for j, (y, h, txt) in enumerate(zip(ys, hs, texts)):
        round_box(x + card_xpad, y, card_w, h, txt, edge=edge, fs=14.2)
        if j < len(ys) - 1:
            down_arrow(x + width/2, y - 0.06, ys[j+1] + hs[j+1] + 0.06, edge)
    if i < len(blocks) - 1:
        right_arrow(x + width + 0.03, x + width + gap - 0.03, bottom + height - header_h/2)

final_stem = "fig_\u56db\u95ee\u603b\u4f53\u6d41\u7a0b"
fig.savefig(OUT / f"{final_stem}.pdf", bbox_inches="tight", pad_inches=0.08)
fig.savefig(OUT / f"{final_stem}.png", dpi=260, bbox_inches="tight", pad_inches=0.08)

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "&#xa;")

cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
for i, (title, fill, edge, texts) in enumerate(blocks):
    x = 20 + i * 390
    cells.append(f'<mxCell id="bg{i}" value="" style="rounded=0;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={edge};strokeWidth=1.4" vertex="1" parent="1"><mxGeometry x="{x}" y="20" width="370" height="800" as="geometry"/></mxCell>')
    cells.append(f'<mxCell id="h{i}" value="{esc(title)}" style="rounded=0;whiteSpace=wrap;html=1;fillColor={edge};strokeColor={edge};fontColor=#FFFFFF;fontStyle=1;fontSize=15;align=center;verticalAlign=middle" vertex="1" parent="1"><mxGeometry x="{x}" y="20" width="370" height="62" as="geometry"/></mxCell>')
    for j, (y, h, txt, fs) in enumerate([(105, 100, texts[0], 18), (235, 100, texts[1], 18), (365, 100, texts[2], 18), (495, 100, texts[3], 18), (625, 100, texts[4], 18)]):
        cells.append(f'<mxCell id="c{i}_{j}" value="{esc(txt)}" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor={edge};fontSize={fs};align=center;verticalAlign=middle" vertex="1" parent="1"><mxGeometry x="{x+25}" y="{y}" width="320" height="{h}" as="geometry"/></mxCell>')
    for j in range(4):
        cells.append(f'<mxCell id="a{i}_{j+1}" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor={edge};strokeWidth=1.2;endArrow=block" edge="1" parent="1" source="c{i}_{j}" target="c{i}_{j+1}"><mxGeometry relative="1" as="geometry"/></mxCell>')
    if i < len(blocks) - 1:
        cells.append(f'<mxCell id="r{i}" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#94A3B8;strokeWidth=1;endArrow=block" edge="1" parent="1" source="h{i}" target="h{i+1}"><mxGeometry relative="1" as="geometry"/></mxCell>')
xml = '<mxfile host="app.diagrams.net" modified="2026-09-12T12:00:00.000Z" agent="Codex" version="24.7.17"><diagram id="four-question-flow" name="四问总体流程"><mxGraphModel dx="1422" dy="794" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1600" pageHeight="900" math="0" shadow="0"><root>' + ''.join(cells) + '</root></mxGraphModel></diagram></mxfile>'
(OUT / f"{final_stem}.drawio").write_text(xml, encoding="utf-8")
print("flowchart generated")
