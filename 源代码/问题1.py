from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from 路径解析 import find_att

N = 144                       # 每天 144 个 10 min 时段
DT = 1.0 / 6.0                # 时段步长 / h
ETA = 0.9                     # 单程充电效率 = 单程放电效率
E_MIN, E_MAX = 1200.0, 10800.0
E_INIT = 6000.0               # 0:00 与 24:00 储电量（日循环）
P_MAX = 5000.0                # kW，最大充放电功率
S = P_MAX * DT                # 833.333... kWh，单时段最大充放电量
X_UP, X_DN = ETA * S, -S / ETA  # 内部电量增量的上/下限（+750 / −925.93）

TAB1_HOURS = (10, 12, 14, 16, 18, 20)          # 论文表 1 的指定时段
SEGS = [('0:00-4:00', 0, 24), ('4:00-8:00', 24, 48), ('8:00-12:00', 48, 72),
        ('12:00-16:00', 72, 96), ('16:00-20:00', 96, 120), ('20:00-24:00', 120, 144)]

ROOT = Path(__file__).resolve().parent
ATT1 = find_att() / '附件1.xlsx'          # 附件目录自动定位，见 路径解析.py
RESULT1 = ROOT / 'result1.xlsx'
TABLES = ROOT / '问题1_结果表.xlsx'


def enable_utf8_console() -> None:
    """Windows 控制台默认 GBK，直接 print 中文可能抛 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass


def time_label(t: int) -> str:
    """时段标签：0 -> '0:00-0:10'；143 -> '23:50-0:00+1'。"""
    s, e = t * 10, t * 10 + 10
    if e == 1440:
        return f'{s // 60}:{s % 60:02d}-0:00+1'
    return f'{s // 60}:{s % 60:02d}-{e // 60}:{e % 60:02d}'


def load_data():
    """读取附件 1：电价（元/kWh）、负荷与光伏发电预测功率（kW→kWh）。"""
    f1 = pd.read_excel(ATT1)
    price = f1['电价'].to_numpy(float)
    load = f1['小区负载'].to_numpy(float) * DT
    pv = f1['光伏发电预测功率'].to_numpy(float) * DT
    assert len(price) == len(load) == len(pv) == N
    return price, load, pv, load - pv


def solve_lp(net, price, E0=E_INIT):
    """纯线性规划求解问题一，返回 dict(g, C, D, U, E, J)。"""
    import pulp as pl

    T = range(N)
    m = pl.LpProblem('q1_det', pl.LpMinimize)
    g = [pl.LpVariable(f'g{t}', 0) for t in T]
    C = [pl.LpVariable(f'C{t}', 0, S) for t in T]
    D = [pl.LpVariable(f'D{t}', 0, S) for t in T]
    U = [pl.LpVariable(f'U{t}', 0) for t in T]
    E = [pl.LpVariable(f'E{t}', E_MIN, E_MAX) for t in T]

    m += pl.lpSum(price[t] * g[t] for t in T)
    for t in T:
        m += g[t] + D[t] == net[t] + C[t] + U[t]
        m += E[t] == (E0 if t == 0 else E[t - 1]) + ETA * C[t] - D[t] / ETA
    m += E[N - 1] == E0

    m.solve(pl.PULP_CBC_CMD(msg=0))
    assert m.status == pl.LpStatusOptimal, '确定性 LP 未求得最优解'
    out = {k: np.array([v.value() for v in vs])
           for k, vs in dict(g=g, C=C, D=D, U=U, E=E).items()}
    out['J'] = float(pl.value(m.objective))
    return out


def solve_milp(net, price, E0=E_INIT):
    """含 144 个 0-1 互斥变量的 MILP，仅用于验证命题 1（LP 松弛等价）。"""
    import pulp as pl

    T = range(N)
    m = pl.LpProblem('q1_milp', pl.LpMinimize)
    g = [pl.LpVariable(f'g{t}', 0) for t in T]
    C = [pl.LpVariable(f'C{t}', 0, S) for t in T]
    D = [pl.LpVariable(f'D{t}', 0, S) for t in T]
    U = [pl.LpVariable(f'U{t}', 0) for t in T]
    E = [pl.LpVariable(f'E{t}', E_MIN, E_MAX) for t in T]
    z = [pl.LpVariable(f'z{t}', cat='Binary') for t in T]

    m += pl.lpSum(price[t] * g[t] for t in T)
    for t in T:
        m += g[t] + D[t] == net[t] + C[t] + U[t]
        m += E[t] == (E0 if t == 0 else E[t - 1]) + ETA * C[t] - D[t] / ETA
        m += C[t] <= S * z[t]                  # 互斥：z=1 才可充电
        m += D[t] <= S * (1 - z[t])            # 互斥：z=0 才可放电
    m += E[N - 1] == E0

    m.solve(pl.PULP_CBC_CMD(msg=0))
    assert m.status == pl.LpStatusOptimal, 'MILP 未求得最优解'
    return float(pl.value(m.objective)), len(z)


def solve_dual(net, price):
    """用 HiGHS 重解同一 LP 并取对偶变量 π_t（平衡乘子）、λ_t（状态乘子）。

    变量次序 [g(T), C(T), D(T), U(T), E(T)]，等式约束 [平衡(T), 递推(T), 日循环(1)]。
    scipy 的 marginals = ∂J/∂b_eq，递推式右端为初始/末储电量，故 λ 需按中位符号翻转。
    """
    from scipy.optimize import linprog
    from scipy.sparse import lil_matrix

    n_var = 5 * N
    ig, ic, idd, iu, ie = (lambda t: t, lambda t: N + t, lambda t: 2 * N + t,
                           lambda t: 3 * N + t, lambda t: 4 * N + t)
    c_obj = np.zeros(n_var)
    c_obj[:N] = price

    A_eq = lil_matrix((2 * N + 1, n_var))
    b_eq = np.zeros(2 * N + 1)
    for t in range(N):                                   # 平衡约束
        A_eq[t, ig(t)] = 1
        A_eq[t, idd(t)] = 1
        A_eq[t, ic(t)] = -1
        A_eq[t, iu(t)] = -1
        b_eq[t] = net[t]
    for t in range(N):                                   # 储能递推
        r = N + t
        A_eq[r, ie(t)] = 1
        A_eq[r, ic(t)] = -ETA
        A_eq[r, idd(t)] = 1 / ETA
        if t == 0:
            b_eq[r] = E_INIT
        else:
            A_eq[r, ie(t - 1)] = -1
    A_eq[2 * N, ie(N - 1)] = 1                           # 日循环闭环
    b_eq[2 * N] = E_INIT

    bounds = ([(0, None)] * N + [(0, S)] * N + [(0, S)] * N
              + [(0, None)] * N + [(E_MIN, E_MAX)] * N)
    res = linprog(c_obj, A_eq=A_eq.tocsr(), b_eq=b_eq, bounds=bounds, method='highs')
    assert res.status == 0, f'对偶 LP 求解失败：{res.message}'

    pi = res.eqlin.marginals[:N]
    lam = res.eqlin.marginals[N:2 * N]
    if np.median(lam) < 0:                               # 统一为"库存边际价值为正"
        lam = -lam
    return dict(J=float(res.fun), pi=pi, lam=lam, x=res.x)


def solve_dp(load, pv, price, E0=E_INIT, de=2.5):
    """值函数 F_t(e) = min_{e'} { c_t·[n_t + ψ(e'−e)]⁺ + F_{t+1}(e') }，F_T(E0)=0。

    ψ(x) = max(x/η, η·x) 把内部增量折算到交流侧；日循环用硬终端（F_T 仅在 E0 处为 0）。
    状态 e 取步长 de 的均匀网格、动作 x 在 [−S/η, η·S] 内枚举并线性插值，
    故 DP 值是网格意义下的精确凸分段线性值函数，且随 de→0 单调收敛到 LP 最优值。
    """
    Tn = len(load)
    net = np.asarray(load, float) - np.asarray(pv, float)
    n_e = int(round((E_MAX - E_MIN) / de)) + 1
    eg = E_MIN + de * np.arange(n_e)
    xs = np.arange(int(np.floor(X_DN / de)), int(np.ceil(X_UP / de)) + 1) * de
    xs = xs[(xs >= X_DN - 1e-9) & (xs <= X_UP + 1e-9)]
    ks = np.round(xs / de).astype(int)
    jj = np.arange(n_e)[None, :] + ks[:, None]
    idx_tab = np.clip(jj, 0, n_e - 1)
    ok_tab = (jj >= 0) & (jj <= n_e - 1)

    def phi(t, x):
        return price[t] * np.maximum(net[t] + np.where(x >= 0, x / ETA, ETA * x), 0.0)

    j0 = int(round((E0 - E_MIN) / de))
    assert abs(eg[j0] - E0) < 1e-9, f'网格未包含日初储电量 E0={E0}'
    F = np.full(n_e, np.inf)
    F[j0] = 0.0
    Fs = [None] * (Tn + 1)
    Fs[Tn] = F.copy()
    step = max(abs(int(np.floor(X_UP / de))), abs(int(np.ceil(X_DN / de))))
    lo = np.array([max(0, j0 - (Tn - t) * step) for t in range(Tn + 1)])
    hi = np.array([min(n_e - 1, j0 + (Tn - t) * step) for t in range(Tn + 1)])

    for t in range(Tn - 1, -1, -1):
        vals = phi(t, xs)[:, None] + F[idx_tab]
        F = np.where(ok_tab, vals, np.inf).min(axis=0)
        Fs[t] = F.copy()

    e_idx, E_tr, C_tr, D_tr = j0, [], [], []
    for t in range(Tn):
        Fn, cand = Fs[t + 1], []
        for k, x in zip(ks, xs):
            j = e_idx + k
            if 0 <= j < n_e and lo[t + 1] <= j <= hi[t + 1] and np.isfinite(Fn[j]):
                cand.append((phi(t, x) + Fn[j], x, k))
        _, x, k = min(cand, key=lambda z: z[0])
        C_tr.append(max(x, 0.0) / ETA)
        D_tr.append(max(-x, 0.0) * ETA)
        e_idx += k
        E_tr.append(eg[e_idx])
    return dict(J=float(Fs[0][j0]), E=np.array(E_tr), C=np.array(C_tr),
                D=np.array(D_tr), de=de, n_state=n_e)


def no_storage(net, price):
    """无储能方案：逐时段购电量取净负荷正部，富余光伏全部弃掉。"""
    g0 = np.maximum(net, 0.0)
    curt0 = np.maximum(-net, 0.0)
    return dict(g=g0, curt=curt0, kwh=float(g0.sum()), cost=float((price * g0).sum()),
                curt_kwh=float(curt0.sum()),
                avg=float((price * g0).sum() / g0.sum()))


def write_result1(ps, path=RESULT1):
    """按附件 5 模板写出 result1.xlsx（只改显示格式，不改数值）。"""
    plan = pd.DataFrame({'时间段': [time_label(t) for t in range(N)],
                         '购电量': np.round(ps['g'], 4)})
    rows = []
    for name, a, b in SEGS:
        rows.append(dict(时间段=name,
                         充电量=round(float(ps['C'][a:b].sum()), 4),
                         放电量=round(float(ps['D'][a:b].sum()), 4),
                         时刻='', 储电量=''))
    rows[0]['时刻'], rows[0]['储电量'] = '0:00', round(E_INIT, 4)
    rows[1]['时刻'], rows[1]['储电量'] = '24:00', round(float(ps['E'][-1]), 4)

    with pd.ExcelWriter(path, engine='openpyxl') as w:
        plan.to_excel(w, sheet_name='计划购电量', index=False)
        pd.DataFrame(rows).to_excel(w, sheet_name='充放电量', index=False)

    import openpyxl
    wb = openpyxl.load_workbook(path)
    ws = wb['充放电量']
    ws.cell(row=2, column=4).number_format = 'h:mm'
    ws.cell(row=3, column=4).number_format = '@'
    wb.save(path)
    return path


def write_tables(ps, dual, price, load, pv, net, ns, milp=None, dps=None,
                 path=TABLES):
    """把论文表 1、表 2 与对偶、效益、命题验证明细写成一个多表工作簿。"""
    g, C, D, U, E = ps['g'], ps['C'], ps['D'], ps['U'], ps['E']
    pi, lam = dual['pi'], dual['lam']
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio = pi / lam

    t1 = pd.DataFrame({
        '时间段': [f'{h}:00-{h}:10' for h in TAB1_HOURS],
        '购电量_kWh': [float(g[6 * h]) for h in TAB1_HOURS],
        '电价_元每kWh': [float(price[6 * h]) for h in TAB1_HOURS]})
    t1.loc[len(t1)] = ['全天购电量_kWh', '%.4f' % g.sum(), '']
    t1.loc[len(t1)] = ['全天购电费_元', '%.6f' % ps['J'], '']

    t2 = pd.DataFrame({
        '时间段': [s[0] for s in SEGS],
        '充电量_kWh': [round(float(C[a:b].sum()), 4) for _, a, b in SEGS],
        '放电量_kWh': [round(float(D[a:b].sum()), 4) for _, a, b in SEGS]})
    t2.loc[len(t2)] = ['0:00储电量_kWh', round(E_INIT, 4), '']
    t2.loc[len(t2)] = ['24:00储电量_kWh', round(float(E[-1]), 4), '']

    t3 = pd.DataFrame({
        '时段': [time_label(t) for t in range(N)], '电价': price,
        '负荷_kWh': load, '光伏_kWh': pv, '净负荷_kWh': net,
        '计划购电量_kWh': g, '充电量_kWh': C, '放电量_kWh': D,
        '未利用_kWh': U, '储电量_kWh': E, '无储能购电量_kWh': ns['g'],
        'pi': pi, 'lam': lam, 'pi_over_lam': ratio})

    t4 = pd.DataFrame([
        dict(指标='全天购电量 /kWh', 有储能=g.sum(), 无储能=ns['kwh']),
        dict(指标='全天购电费 /元', 有储能=ps['J'], 无储能=ns['cost']),
        dict(指标='弃电量 /kWh', 有储能=U.sum(), 无储能=ns['curt_kwh']),
        dict(指标='储能充电量 /kWh', 有储能=C.sum(), 无储能=0.0),
        dict(指标='储能放电量 /kWh', 有储能=D.sum(), 无储能=0.0),
        dict(指标='净放电量 /kWh', 有储能=(D - C).sum(), 无储能=0.0),
        dict(指标='24:00储电量 /kWh', 有储能=E[-1], 无储能=E_INIT),
        dict(指标='购电均价 /(元/kWh)', 有储能=ps['J'] / g.sum(), 无储能=ns['avg']),
    ])
    t4['差额_有减无'] = t4['有储能'] - t4['无储能']
    t4['相对变化_%'] = 100 * t4['差额_有减无'] / t4['无储能'].replace(0, np.nan)

    rows = [dict(项目='LP 目标值 /元', 数值=f'{ps["J"]:.6f}'),
            dict(项目='LP 全天购电量 /kWh', 数值=f'{g.sum():.6f}'),
            dict(项目='LP 弃电量 /kWh', 数值=f'{U.sum():.6f}'),
            dict(项目='LP 24:00 储电量 /kWh', 数值=f'{E[-1]:.6f}'),
            dict(项目='对偶 LP 目标值 /元', 数值=f'{dual["J"]:.6f}'),
            dict(项目='对偶 LP 相对差', 数值=f'{abs(dual["J"] - ps["J"]) / ps["J"]:.3e}'),
            dict(项目='无储能购电量 /kWh', 数值=f'{ns["kwh"]:.4f}'),
            dict(项目='无储能购电费 /元', 数值=f'{ns["cost"]:.4f}'),
            dict(项目='节省额 /元', 数值=f'{ns["cost"] - ps["J"]:.4f}'),
            dict(项目='节省率 /%', 数值=f'{100 * (ns["cost"] - ps["J"]) / ns["cost"]:.4f}')]
    for de, r in (dps or {}).items():
        rows.append(dict(项目=f'DP 目标值（de={de:g} kWh）/元', 数值=f'{r["J"]:.6f}'))
        rows.append(dict(项目=f'DP 相对差（de={de:g} kWh）',
                         数值=f'{abs(r["J"] - ps["J"]) / ps["J"]:.3e}'))
    if milp is not None:
        rows.append(dict(项目='MILP 目标值 /元', 数值=f'{milp[0]:.6f}'))
        rows.append(dict(项目='MILP 0-1 变量个数', 数值=str(milp[1])))
        rows.append(dict(项目='LP vs MILP 相对差',
                         数值=f'{abs(milp[0] - ps["J"]) / ps["J"]:.3e}'))

    with pd.ExcelWriter(path, engine='openpyxl') as w:
        t1.to_excel(w, sheet_name='表1_指定时段购电量', index=False)
        t2.to_excel(w, sheet_name='表2_储能分段充放电量', index=False)
        t3.to_excel(w, sheet_name='表3_逐时段调度与对偶', index=False)
        t4.to_excel(w, sheet_name='表4_有无储能效益对照', index=False)
        pd.DataFrame(rows).to_excel(w, sheet_name='表5_命题数值验证', index=False)
    return path


def make_figures(ps, price, net, ns, figdir):
    """复现论文引用的 3 张问题一插图（图 2 gB05 / 图 3 gB03 / 图 4 gD01）。"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams.update({'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans'],
                         'axes.unicode_minus': False, 'pdf.fonttype': 42,
                         'savefig.bbox': 'tight'})
    figdir.mkdir(parents=True, exist_ok=True)
    plan_h = ps['g'].reshape(24, 6).sum(1)
    chg_h = ps['C'].reshape(24, 6).sum(1)
    dis_h = ps['D'].reshape(24, 6).sum(1)
    ns_h = ns['g'].reshape(24, 6).sum(1)
    price_h = price.reshape(24, 6).mean(1)
    hours = np.arange(24)
    names = []

    
    gv = np.array([ps['g'][6 * h] for h in TAB1_HOURS])
    pv_ = np.array([price[6 * h] for h in TAB1_HOURS])
    fig, ax = plt.subplots(figsize=(6.6, 3.9))
    ax.bar(np.arange(len(gv)), gv, width=0.54, color='#2E5C8A', label='计划购电量')
    for x, v in zip(np.arange(len(gv)), gv):
        ax.text(x, v + max(gv.max(), 1) * 0.035, '0' if abs(v) < 1e-9 else f'{v:,.1f}',
                ha='center', va='bottom', fontsize=9.5)
    ax.set_xticks(np.arange(len(gv)), [f'{h}:00' for h in TAB1_HOURS])
    ax.set_xlabel('表 1 指定时段'); ax.set_ylabel('时段购电量 / kWh')
    ax.set_ylim(0, max(gv.max(), 1.0) * 1.46); ax.grid(axis='y', alpha=.25)
    ax2 = ax.twinx()
    ax2.plot(np.arange(len(gv)), pv_, color='#C0392B', lw=1.8, marker='s', ms=5)
    ax2.set_ylabel('电价 / 元·kWh$^{-1}$', color='#C0392B')
    ax2.tick_params(axis='y', colors='#C0392B'); ax2.set_ylim(0, pv_.max() * 1.30)
    names.append(figdir / 'gB05_表1指定时段购电量.pdf')
    fig.savefig(names[-1]); plt.close(fig)

    
    fig, ax = plt.subplots(figsize=(8.2, 4.1))
    ax.bar(hours, chg_h, width=0.64, color='#2E7D5B', alpha=.9, label='充电量')
    ax.bar(hours, -dis_h, width=0.64, color='#A93226', alpha=.9, label='放电量')
    ax.axhline(0, color='#555', lw=1.0)
    ax.set_xlim(-0.6, 23.6)
    ax.set_xticks(range(0, 24, 2), [f'{h}:00' for h in range(0, 24, 2)])
    ax.set_xlabel('时刻'); ax.set_ylabel('小时充放电量 / kWh')
    ax.set_ylim(-dis_h.max() * 1.34, chg_h.max() * 1.22); ax.grid(axis='y', alpha=.25)
    ax2 = ax.twinx()
    ax2.plot(hours, price_h, color='#1F6FB2', lw=2.0, marker='o', ms=4)
    ax2.set_ylabel('电价 / 元·kWh$^{-1}$', color='#1F6FB2')
    ax2.tick_params(axis='y', colors='#1F6FB2'); ax2.set_ylim(0, price_h.max() * 1.30)
    ax.legend(loc='upper right', ncol=2, fontsize=9)
    names.append(figdir / 'gB03_储能充放电与电价.pdf')
    fig.savefig(names[-1]); plt.close(fig)

    
    fig, ax = plt.subplots(figsize=(8.2, 4.1))
    ax.plot(hours, ns_h, color='#7F8C8D', lw=1.9, ls='--', label='无储能基准购电量')
    ax.plot(hours, plan_h, color='#2E5C8A', lw=2.5, drawstyle='steps-mid',
            label='有储能计划购电量 $g_t$')
    ax.fill_between(hours, plan_h, ns_h, where=ns_h >= plan_h, color='#2E7D5B',
                    alpha=.16, lw=0, label='峰段少购（省费）')
    ax.fill_between(hours, plan_h, ns_h, where=ns_h < plan_h, color='#A93226',
                    alpha=.16, lw=0, label='谷段多购（存电）')
    ax.set_xlim(-0.6, 23.6)
    ax.set_xticks(range(0, 24, 2), [f'{h}:00' for h in range(0, 24, 2)])
    ax.set_xlabel('时刻'); ax.set_ylabel('小时购电量 / kWh')
    ax.set_ylim(0, max(plan_h.max(), ns_h.max()) * 1.30); ax.grid(axis='y', alpha=.25)
    ax.legend(loc='upper left', ncol=2, fontsize=9)
    names.append(figdir / 'gD01_有无储能购电曲线.pdf')
    fig.savefig(names[-1]); plt.close(fig)
    return names



def main(argv=None):
    ap = argparse.ArgumentParser(description='问题一：确定性购电与储能协同调度')
    ap.add_argument('--milp', action='store_true', help='MILP 对照（验证命题 1）')
    ap.add_argument('--dual', action='store_true', help='对偶与阈值结构（验证命题 2）')
    ap.add_argument('--dp', action='store_true', help='连续状态 DP 复算')
    ap.add_argument('--fig', action='store_true', help='复现论文图 2/3/4')
    ap.add_argument('--all', action='store_true', help='等价于 --milp --dual --dp')
    ap.add_argument('--figdir', default=None, help='图片输出目录，默认 figures/1')
    a = ap.parse_args(argv)
    do_milp = a.milp or a.all
    do_dual = a.dual or a.all
    do_dp = a.dp or a.all
    enable_utf8_console()

    price, load, pv, net = load_data()
    print('=' * 74)
    print('问题一 确定性购电与储能协同调度（附件 1，144 × 10 min）')
    print('=' * 74)

    ps = solve_lp(net, price)
    ns = no_storage(net, price)
    print(f'  最低购电费        : {ps["J"]:.6f} 元')
    print(f'  全天购电量        : {ps["g"].sum():.6f} kWh（无储能 {ns["kwh"]:.4f} kWh）')
    print(f'  弃电量            : {ps["U"].sum():.6f} kWh')
    print(f'  0:00 / 24:00 储电量: {E_INIT:.4f} / {ps["E"][-1]:.6f} kWh')
    print(f'  储能充电 / 放电    : {ps["C"].sum():.4f} / {ps["D"].sum():.4f} kWh')
    print(f'  可行性自检        : SOC 越界 '
          f'{int(((ps["E"] < E_MIN - 1e-6) | (ps["E"] > E_MAX + 1e-6)).sum())}，'
          f'功率越界 {int((ps["C"] > S + 1e-6).sum() + (ps["D"] > S + 1e-6).sum())}，'
          f'同时充放电 {int(((ps["C"] > 1e-6) & (ps["D"] > 1e-6)).sum())}')

    milp = None
    if do_milp:
        J_milp, nz = solve_milp(net, price)
        milp = (J_milp, nz)
        print('')
        print(f'  [命题 1] LP   {ps["J"]:.6f} 元（0 个整数变量）')
        print(f'  [命题 1] MILP {J_milp:.6f} 元（{nz} 个 0-1 变量），'
              f'相对差 {abs(J_milp - ps["J"]) / ps["J"]:.2e}')

    dual = solve_dual(net, price)
    if do_dual:
        pi, lam = dual['pi'], dual['lam']
        ch, di = ps['C'] > 1e-4, ps['D'] > 1e-4
        idle = ~ch & ~di
        rc, rd = pi - ETA * lam, -pi + lam / ETA
        print('')
        print(f'  [命题 2] 对偶 LP 目标值 {dual["J"]:.6f} 元，'
              f'相对差 {abs(dual["J"] - ps["J"]) / ps["J"]:.2e}')
        print(f'    充电 {int(ch.sum())} 个时段：max(π−ηλ) = {rc[ch].max():+.2e}（应 ≤ 0）')
        print(f'    放电 {int(di.sum())} 个时段：max(−π+λ/η) = {rd[di].max():+.2e}（应 ≤ 0）')
        print(f'    闲置 {int(idle.sum())} 个时段：min(π−ηλ) = {rc[idle].min():+.2e}，'
              f'min(−π+λ/η) = {rd[idle].min():+.2e}（应 ≥ 0）')
        buy = ps['g'] > 1e-6
        print(f'    购电未被截断的 {int(buy.sum())} 个时段：max|π−c| = '
              f'{np.abs(pi[buy] - price[buy]).max():.2e}（推论 π_t = c_t）')
        pairs = [(t1, t2) for t1 in np.where(ch)[0] for t2 in np.where(di)[0]
                 if t2 > t1 and price[t2] * ETA ** 2 > price[t1]]
        print(f'    满足纯套利条件 c_t < 0.81·c_s 的"先充后放"组合：{len(pairs)} 对')

    dps = {}
    if do_dp:
        print('')
        print('  DP 复算（独立第二套算法，de 为储电量网格步长）：')
        for de in (10.0, 5.0, 2.5):
            r = solve_dp(load, pv, price, de=de)
            dps[de] = r
            print(f'    de={de:>5.1f} kWh  DP={r["J"]:12.6f} 元  '
                  f'与 LP 相对差 {abs(r["J"] - ps["J"]) / ps["J"]:.2e}  '
                  f'E_T={r["E"][-1]:.4f}')

    print('')
    print('  论文表 1（指定时段购电量 / kWh）：')
    for h in TAB1_HOURS:
        print(f'    {h:>2d}:00-{h:>2d}:10  {ps["g"][6 * h]:>12.4f}')
    print(f'    {"全天购电量":>12s}  {ps["g"].sum():>12.6f} kWh')
    print(f'    {"全天购电费":>12s}  {ps["J"]:>12.6f} 元')
    print('')
    print('  论文表 2（储能分段充放电量 / kWh）：')
    for name, lo_, hi_ in SEGS:
        print(f'    {name:<10s} 充 {ps["C"][lo_:hi_].sum():>10.4f}   '
              f'放 {ps["D"][lo_:hi_].sum():>10.4f}')
    print('')
    print(f'  储能经济价值：节省 {ns["cost"] - ps["J"]:.4f} 元，'
          f'节省率 {100 * (ns["cost"] - ps["J"]) / ns["cost"]:.2f}%；'
          f'购电均价 {ns["avg"]:.4f} → {ps["J"] / ps["g"].sum():.4f} 元/kWh')

    print('')
    print(f'  [已写出] {write_result1(ps)}')
    print(f'  [已写出] {write_tables(ps, dual, price, load, pv, net, ns, milp, dps)}')
    if a.fig:
        figdir = Path(a.figdir) if a.figdir else ROOT / 'figures' / '1'
        for p in make_figures(ps, price, net, ns, figdir):
            print(f'  [已画出] {p}')
    return ps


if __name__ == '__main__':
    main()
