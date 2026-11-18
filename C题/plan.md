# 方案

要依次调用这些 skill，按照里面要求完成任务。

用户偏好：
- 排版引擎：LaTeX（xelatex 编译，两遍解决交叉引用）
- 竞赛类型：国赛（CUMCM 模板）
- 论文语言：中文
- 子问题数量：4 个（由题面确定）

## 题目概况

题目研究含光伏、储能和社区负荷的并网微网购电调控。时间分辨率为 10 分钟，储能容量 12000 kWh，最大充放电功率 5000 kW，充放电效率 90%，SOC 工作区间为 1200--10800 kWh。目标是在满足负荷供电约束和储能状态约束的同时，最小化计划购电、紧急购电、偏差调整及波动电价下的综合费用。

## workflow

| step | skills | 主要产出 |
|---|---|---|
| 1. 赛题分析与建模设计 | `2analysis-modeling` | `reports/ANALYSIS_MODELING_REPORT.md`：题意拆解、变量与参数、假设、四问模型、目标函数、约束、求解策略与验证方案 |
| 2. 编程实现和图表生成 | `3coding-visual` | `code/`、`results/`、`reports/RESULTS_REPORT.md`、`figures/` 中的数据图表及完整 `result*.xlsx` |
| 3. 流程与架构图绘制 | `4drawio` | `figures/*.drawio`、对应 PDF、`reports/DRAWIO_REPORT.md` |
| 4. 竞赛论文撰写 | `5writing` | `paper/main.tex`、编译后的 `paper/main.pdf`（xelatex 两遍） |
| 5. 验证和验收 | `6verity` | `reports/VERIFY_REPORT.md`：数据、数值、图表、引用、编译、可复现性与提交就绪检查 |

## 阶段边界与风险控制

- `2analysis-modeling` 负责把附件字段和四问的计划/调整/紧急购电关系写清楚，并避免把预测值与实际值混用。
- `3coding-visual` 负责所有数值求解、约束校验、Excel 模板填充和数据驱动图表；所有论文数值必须来自其结果报告或结果表。
- `4drawio` 只绘制算法流程、滚动调整架构和模型结构等非数据型图示，不重复绘制统计图。
- `5writing` 使用 LaTeX（xelatex 编译）；正文直接引用 `figures/*.pdf`，不得编造计算结果。
- `6verity` 对结果文件格式、储能首尾状态、负荷平衡、紧急购电和调整费用进行最终交叉验证。
- 若外部求解器不可用，优先采用 SciPy/HiGHS 或其他当前环境已安装的线性/混合整数规划求解器，并在结果报告中记录求解器与版本。
