# 验证与验收报告

## 完成状态

本 C 题（2026 国赛“微网与外部电网电力调控策略”）已完成五个阶段，全部实现并跑通：

| 阶段 | 产物 | 状态 |
|---|---|---|
| 1 分析建模 | reports/ANALYSIS_MODELING_REPORT.md | 完成 |
| 2 编程与结果 | code/、results/、reports/RESULTS_REPORT.md、figures/*.pdf | 完成 |
| 3 图示 | figures/*.drawio、figures/fig_roadmap、flow_q1、flow_q3.pdf | 完成 |
| 4 论文 | paper/main.tex + paper/main.pdf（已编译） | 完成 |
| 5 验收 | 本报告 | 完成 |

## 结果文件核对

- result1.xlsx、result2.xlsx、result3.xlsx、result4-2.xlsx、result4-3.xlsx 均已生成并按附件5模板填入数值；summary.json 记录全年汇总。
- 约束自动校验通过：功率平衡、SOC递推、SOC在[1200,10800]、首末储电6000、充放互斥（LP天然满足）。

## 全年关键结果（2025-02-01~12-31）

| 指标 | 问题2(仅0:00预报) | 问题3(四次预报) |
|---|---|---|
| 计划购电 kWh | 24,945,384 | 24,945,384 |
| 紧急购电 kWh | 30,102 | 808 |
| 总购电费(元) | 15,892,187 | 16,649,872 |

问题1（附件1单日）：购电 86108 kWh、购电费 55363 元。

## 图表资产

- 数据图：fig_repday、fig_emergency、fig_daily_cost、fig_price（PDF）
- 流程图：fig_roadmap、fig_flow_q1、fig_flow_q3（.drawio 源 + PDF）

## 论文编译（LaTeX / xelatex）

- 引擎：TeX Live 2026，`xelatex`（`D:\texlive\2026\bin\windows\xelatex.exe`）。
- 模板：`ctexart`（中文），A4、12pt，`graphicspath` 指向 `../figures/`。
- 编译命令（在 `paper/` 目录执行两遍以解决交叉引用）：
  ```
  xelatex -interaction=nonstopmode main.tex
  xelatex -interaction=nonstopmode main.tex
  ```
  或使用 `python _compile.py` / `latexmk -xelatex main.tex`。
- 编译结果：`main.pdf` 共 **6 页**，退出码 0；**0 条缺字警告、0 条未定义引用**；6 张图（roadmap、repday、flow_q1、flow_q3、emergency、price）全部成功嵌入。
- 说明：初版曾出现圈码 ①②③④ 在拉丁字体缺字，已改用 `(1)~(4)` 编号，重新编译后缺字警告清零。

## 一致性说明

论文所有数值均取自 `reports/RESULTS_REPORT.md` 与 `results/*.xlsx`，无编造；图表引用路径已核对，编解码与页数均经编译日志确认。
