from __future__ import annotations

import argparse
import sys
import time
from datetime import time as dtime
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
import pulp as pl

from 路径解析 import SRC, find_att

ROOT = SRC                     # 源代码/ 目录（不随启动时的工作目录变化）
ATT = find_att()               # 附件目录自动定位，见 路径解析.py
REPORTS = ROOT / 'reports'

#参数（唯一来源）
N = 144                          # 每天 144 个 10 分钟时段
DT = 1.0 / 6.0                   # 时段长度 h
ETA = 0.9                        # 单程充、放电效率
E_MIN, E_MAX = 1200.0, 10800.0   # 储电量上下限 kWh
E_INIT = 6000.0                  # 0:00 与 24:00 储电量 kWh（日循环）
P_MAX = 5000.0                   # 最大充放电功率 kW
S = P_MAX * DT                   # 833.33 kWh/时段，交流侧充放电上限

KAPPA = 5.0                      # 紧急购电电价倍数
K_ADJ_UP, K_ADJ_DN = 1.5, 0.5    # 调整层向上追补 / 向下违约的电价倍数
K_SCEN, M_ADJ = 20, 10           # 计划层 / 调整层情景数
WIN = 25                         # 情景集日历窗半宽（天）
K_PLAN = 2.0                     # 计划层内部缺口惩罚倍数 → 1 − 1/κ = 50% 分位

START = '2025-02-01'             # 结果输出起始日（附件 5 模板口径，共 334 天）
REPORT_DAYS = ['2025-03-20', '2025-06-21', '2025-09-23', '2025-12-21']
SEGS = [('0:00-4:00', 0, 24), ('4:00-8:00', 24, 48), ('8:00-12:00', 48, 72),
        ('12:00-16:00', 72, 96), ('16:00-20:00', 96, 120), ('20:00-24:00', 120, 144)]
RELEASE_HOURS = (0, 6, 12, 18)   # 四个预报发布时刻
REL_INDEX = {0: 0, 6: 1, 12: 2, 18: 3}      # 发布时刻 -> 附件 3 的第几组预报
REL_SLOTS = {6: 36, 12: 72, 18: 108}        # 发布时刻 -> 剩余窗口起始时段
DATE_FMT, TIME_FMT = 'mm-dd-yy', 'h:mm'     # 与附件 5 模板逐字一致

# 调整时刻组合（对应论文“调整时刻消融”表与图 9/10）
POLICIES = {
    '无调整（仅 0:00 预报）': (),
    '仅 6:00': (6,),
    '仅 12:00': (12,),
    '仅 18:00': (18,),
    '6:00+12:00': (6, 12),
    '6:00+12:00+18:00（题面全用）': (6, 12, 18),
}
MAIN = '6:00+12:00+18:00（题面全用）'        # 论文主口径


def utf8_console() -> None:
    """Windows 控制台默认 GBK，直接 print 中文可能抛 UnicodeEncodeError。"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass


#数据层
def build_case() -> dict:
    """附件 1（电价、发电预测）与附件 2（全年实际负荷/光伏），功率一律换算为电量 kWh。"""
    f1 = pd.read_excel(ATT / '附件1.xlsx')
    price = f1['电价'].to_numpy(float)
    d2 = pd.read_excel(ATT / '附件2.xlsx', sheet_name='小区负载')
    p2 = pd.read_excel(ATT / '附件2.xlsx', sheet_name='光伏发电实际功率')
    dates = pd.DatetimeIndex(pd.to_datetime(d2.iloc[:, 0]).dt.normalize())
    L = d2.iloc[:, 1:].to_numpy(float) * DT      # (365,144) 负荷电量
    P = p2.iloc[:, 1:].to_numpy(float) * DT      # (365,144) 光伏电量
    assert L.shape == P.shape == (len(dates), N), (L.shape, P.shape, len(dates))
    assert len(price) == N, len(price)
    return dict(dates=dates, price=price, L=L, P=P)


def load_pv_forecast() -> np.ndarray:
    """附件 3 -> (365, 4, 144) 光伏电量预报 kWh；[d, r, t] = 第 d 天第 r 次发布。

    时间对齐：附件 3 第 j 列（0-based）对应**发布时刻当刻起的那个小时**，即
        列 j ↔ 小时区间 [(τ+j) mod 24, (τ+j+1) mod 24)，
    列值是该小时的功率（kW），按分段常数铺到 10 分钟粒度。
    判据（全年前向窗口 RMSE，kW）：本口径 564/541/427/77，明显优于整体错位一小时
    的 679/713/798/176；例：2025-01-01 的 6:00 预报第 1 列 = 3.1 kW，而实际
    6:00-7:00 均值 1.5 kW、7:00-8:00 才是 845.5 kW，只有本口径对得上。
    """
    raw = pd.read_excel(ATT / '附件3.xlsx')
    dcol = pd.to_datetime(raw[raw.columns[0]]).ffill()
    tcol = raw[raw.columns[1]].astype(str).str.strip()
    hours = raw.iloc[:, 2:].to_numpy(float)                  # (1460, 24) kW
    days = pd.DatetimeIndex(sorted(dcol.unique()))
    out = np.zeros((len(days), len(RELEASE_HOURS), N))
    for k in range(len(raw)):
        d = int(days.get_loc(dcol.iloc[k]))
        rel = int(tcol.iloc[k].split(':')[0])
        r = RELEASE_HOURS.index(rel)
        for j in range(24):
            h = (rel + j) % 24
            out[d, r, h * 6:h * 6 + 6] = hours[k, j] * DT
    return out


def time_label(t: int) -> str:
    """时段标签：t=0 -> '0:00-0:10'；t=143 -> '23:50-0:00+1'。"""
    s, e = t * 10, t * 10 + 10
    if e == 1440:
        return f'{s // 60}:{s % 60:02d}-0:00+1'
    return f'{s // 60}:{s % 60:02d}-{e // 60}:{e % 60:02d}'


def mmss(minute: int) -> str:
    """分钟数 -> 'H:MM'；1440 -> '0:00+1'。"""
    minute = int(minute)
    return '0:00+1' if minute == 1440 else f'{minute // 60}:{minute % 60:02d}'


def merge_intervals(deficit, delta=1.0) -> list:
    """把相邻的紧急购电时段并成区间，返回 [(时间段标签, 电量), ...]。

    delta：单时段缺额低于该值（kWh）视为计划设计内的微小偏差，不入表；
    缺额 1 kWh 对应约 6 kW，比负荷量级低三个数量级。
    """
    idx = np.where(np.asarray(deficit, float) > delta)[0]
    if len(idx) == 0:
        return []
    spans, st, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i == prev + 1:
            prev = i
        else:
            spans.append((st, prev))
            st = prev = i
    spans.append((st, prev))
    return [(f'{mmss(a * 10)}-{mmss((b + 1) * 10)}', float(deficit[a:b + 1].sum()))
            for a, b in spans]


#情景层
def cal_window(d: int, dates, half: int = WIN) -> np.ndarray:
    """第 d 日**之前**、日历日 ±half 天内的历史日索引（跨年环绕）。

    严格因果：不含 d 当天及以后，故 0:00 制定计划时不使用任何未来信息。
    """
    doy = dates.dayofyear.to_numpy()
    hist = np.arange(d)
    if len(hist) == 0:
        return hist
    diff = np.abs(doy[hist] - doy[d])
    return hist[np.minimum(diff, 365 - diff) <= half]


def kmedoids(X: np.ndarray, K: int, iters: int = 30):
    """K-medoids（PAM 简化版）情景削减，返回 (代表情景 (K,T), 权重 (K,))。"""
    n = len(X)
    D = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).sum(-1))
    order = np.argsort(X.sum(1))
    med = sorted(set(order[np.linspace(0, n - 1, K).round().astype(int)].tolist()))
    for _ in range(iters):
        assign = D[:, med].argmin(1)
        new = []
        for k in range(len(med)):
            mem = np.where(assign == k)[0]
            new.append(int(mem[D[np.ix_(mem, mem)].sum(1).argmin()]) if len(mem) else med[k])
        new = sorted(set(new))
        if new == med:
            break
        med = new
    assign = D[:, med].argmin(1)
    w = np.array([(assign == k).sum() for k in range(len(med))], float)
    w = np.where(w > 0, w, 1.0)
    return X[med].copy(), w / w.sum()


def residual_pool(d, case, fc, rel=0, half=WIN) -> np.ndarray:
    """第 d 日之前日历 ±half 天内的历史**残差**样本：残差 = 实际 − 预报。

    残差样本的均值自动校正该发布时刻预报的系统性偏倚，因此
        “情景 = 当日预报 + 历史残差”
    才是经历史经验校正后的光伏分布。若误写成“预报 +（预报 − 实际）”，
    会把偏倚放大一倍，得到过度乐观的调整策略。
    """
    sel = cal_window(d, case['dates'], half=half)
    if len(sel) == 0:
        return np.zeros((1, N))
    return case['P'][sel, :] - fc[sel, REL_INDEX[rel], :]


def scen_of(res: np.ndarray, f: np.ndarray, K: int):
    """把残差样本削减到 K 个后叠加当日预报 f，返回 (情景 (M,144), 概率 (M,))。

    叠加后按物理可行性截断为 max{·, 0}：光伏出力不可能为负，而"历史日的残差"
    取自别的日期，与当日预报叠加后仍可能为负（例如历史晴天早晨的残差为 −5000，
    叠加到当日小预报上）。这一截断是论文主口径的一部分，去掉会使全年计划购电量
    偏高约 2.07 万 kWh、总费用偏高约 1.55 万元（13 675 957.47 元）。
    """
    if len(res) <= K:
        scen, w = f[None, :] + res, np.full(len(res), 1.0 / len(res))
    else:
        e, w = kmedoids(res, K)
        scen = f[None, :] + e
    return np.maximum(scen, 0.0), np.asarray(w, float)


def plan_scenarios(d, case, fc, K=K_SCEN, half=WIN):
    """计划层情景 = 0:00 预报 + 历史残差（20 个等权情景）。"""
    return scen_of(residual_pool(d, case, fc, 0, half), fc[d, REL_INDEX[0]], K)


def adjust_scenarios(d, case, fc, rel_h, K=M_ADJ, half=WIN):
    """调整层情景 = 该发布时刻预报 + 历史同期残差（10 个等权情景）。"""
    return scen_of(residual_pool(d, case, fc, rel_h, half), fc[d, REL_INDEX[rel_h]], K)


#优化层
def solve_plan(load, scen, probs, price, kappa=K_PLAN, eps=1e-6) -> dict:
    """计划层两阶段随机 LP。

        min Σ_t c_t x_t + Σ_ω p_ω Σ_t κ c_t b_{t,ω}
            + ε Σ(C_t + U_{t,ω}) + ε Σ_t x_t      （唯一化正则项，量级 1e-6，不改经济结论）
        s.t. E_t = E_{t-1} + η C_t − D_t/η ,  E_0 = E_{N-1} = 6000
             x_t + V_{t,ω} + D_t + b_{t,ω} = L_t + C_t + U_{t,ω}   ∀ω
             1200 ≤ E_t ≤ 10800 ,  0 ≤ C_t, D_t ≤ 833.33 ,  x, b, U ≥ 0

    第一阶段（与 ω 无关，满足非预期性）：x / C / D / E
    第二阶段（逐情景追索）：b = 紧急购电，U = 未利用供能（弃光）
    """
    ns, T = len(scen), range(N)
    probs = np.asarray(probs, float)
    m = pl.LpProblem('plan', pl.LpMinimize)
    x = [pl.LpVariable(f'x{t}', 0) for t in T]
    C = [pl.LpVariable(f'C{t}', 0, S) for t in T]
    D = [pl.LpVariable(f'D{t}', 0, S) for t in T]
    E = [pl.LpVariable(f'E{t}', E_MIN, E_MAX) for t in T]
    b = [[pl.LpVariable(f'b{s}_{t}', 0) for t in T] for s in range(ns)]
    U = [[pl.LpVariable(f'U{s}_{t}', 0) for t in T] for s in range(ns)]

    m += (pl.lpSum(price[t] * x[t] for t in T)
          + pl.lpSum(kappa * price[t] * probs[s] * b[s][t]
                     for s in range(ns) for t in T)
          + eps * pl.lpSum(C[t] + U[s][t] for s in range(ns) for t in T)
          + eps * pl.lpSum(x[t] for t in T))
    for t in T:
        m += E[t] == (E_INIT if t == 0 else E[t - 1]) + ETA * C[t] - D[t] / ETA
        for s in range(ns):
            m += x[t] + scen[s][t] + D[t] + b[s][t] == load[t] + C[t] + U[s][t]
    m += E[N - 1] == E_INIT

    m.solve(pl.PULP_CBC_CMD(msg=0))
    assert m.status == pl.LpStatusOptimal, '计划层 LP 未求得最优解'
    return dict(x=np.array([v.value() for v in x]),
                C=np.array([v.value() for v in C]),
                D=np.array([v.value() for v in D]),
                E=np.array([v.value() for v in E]),
                J=float(pl.value(m.objective)))


def solve_adjust(load_rest, price_rest, x_old_rest, scen_rest, probs,
                 E_start, E_term=E_INIT, kappa=KAPPA,
                 k_up=K_ADJ_UP, k_dn=K_ADJ_DN, eps=1e-6) -> dict:
    """调整层随机 LP（增量目标：计划费已按计划量全额结算）。

        min Σ_t (k_up c_t Δ⁺_t + k_dn c_t Δ⁻_t) + Σ_ω p_ω Σ_t κ c_t α_{t,ω}
            + ε Σ(C_t + U_{t,ω}) + ε Σ_t X_t
        s.t. X_t − x_old_t = Δ⁺_t − Δ⁻_t ,  X, Δ⁺, Δ⁻ ≥ 0
             X_t + V_{t,ω} + D_t + α_{t,ω} = L_t + C_t + U_{t,ω}   ∀ω
             E_t = E_{t-1} + η C_t − D_t/η ,  E_{n-1} = E_term
             1200 ≤ E_t ≤ 10800 ,  0 ≤ C_t, D_t ≤ 833.33

    关键差别（也是本函数存在的理由）：调整阶段“多交一度电”的边际成本是 1.5c、
    “少交一度电”的代价是 0.5c（不是 −c，因为不退计划费）。若沿用 Σc·X 目标，
    会把调整量与调整费从账上抹掉，算出与账务不一致的策略。
    交付量 X 与充放电在这一时刻一次性锁定，缺额 α 逐情景追索 ⇒
    P(缺额) = k_up/κ = 30%，即交付量取净需求的 70% 分位。
    """
    n = len(load_rest)
    if n <= 0:
        return dict(X=np.zeros(0), C=np.zeros(0), D=np.zeros(0), E=np.zeros(0),
                    delta=np.zeros(0), fee_adj=0.0, J=0.0)
    scen = np.asarray(scen_rest, float)
    ns, T = scen.shape[0], range(n)
    probs = np.asarray(probs, float)
    x_old = np.asarray(x_old_rest, float)
    m = pl.LpProblem('adjust', pl.LpMinimize)
    X = [pl.LpVariable(f'X{t}', 0) for t in T]
    C = [pl.LpVariable(f'C{t}', 0, S) for t in T]
    D = [pl.LpVariable(f'D{t}', 0, S) for t in T]
    E = [pl.LpVariable(f'E{t}', E_MIN, E_MAX) for t in T]
    dP = [pl.LpVariable(f'dp{t}', 0) for t in T]      # Δ⁺ 向上调整
    dN = [pl.LpVariable(f'dn{t}', 0) for t in T]      # Δ⁻ 向下调整
    a = [[pl.LpVariable(f'a{s}_{t}', 0) for t in T] for s in range(ns)]
    U = [[pl.LpVariable(f'U{s}_{t}', 0) for t in T] for s in range(ns)]

    m += (pl.lpSum(price_rest[t] * (k_up * dP[t] + k_dn * dN[t]) for t in T)
          + pl.lpSum(kappa * price_rest[t] * probs[s] * a[s][t]
                     for s in range(ns) for t in T)
          + eps * pl.lpSum(C[t] + U[s][t] for s in range(ns) for t in T)
          + eps * pl.lpSum(X[t] for t in T))
    for t in T:
        m += X[t] - x_old[t] == dP[t] - dN[t]
        m += E[t] == (E_start if t == 0 else E[t - 1]) + ETA * C[t] - D[t] / ETA
        for s in range(ns):
            m += X[t] + scen[s][t] + D[t] + a[s][t] == load_rest[t] + C[t] + U[s][t]
    m += E[n - 1] == E_term

    m.solve(pl.PULP_CBC_CMD(msg=0))
    assert m.status == pl.LpStatusOptimal, '调整层 LP 未求得最优解'
    pf = np.asarray(price_rest, float)
    fee = float((pf * (k_up * np.array([v.value() for v in dP])
                       + k_dn * np.array([v.value() for v in dN]))).sum())
    Xa = np.array([v.value() for v in X])
    return dict(X=Xa, C=np.array([v.value() for v in C]),
                D=np.array([v.value() for v in D]),
                E=np.array([v.value() for v in E]),
                delta=Xa - x_old, fee_adj=fee, J=float(pl.value(m.objective)))


#推演层
def settle(X, C, D, L, V, price, kappa=KAPPA) -> dict:
    """执行层结算：实际光伏回代，缺额按 5c 紧急购电、富余计为弃光。

        r_t = (L_t − V_t^实际) − X_t − (D_t − C_t) ,  α_t = [r_t]⁺ ,  U_t = [−r_t]⁺
    """
    r = (np.asarray(L, float) - np.asarray(V, float)) - np.asarray(X, float) \
        - (np.asarray(D, float) - np.asarray(C, float))
    deficit = np.maximum(r, 0.0)
    price = np.asarray(price, float)
    return dict(em_kwh=float(deficit.sum()),
                em_fee=float((kappa * price * deficit).sum()),
                curt_kwh=float(np.maximum(-r, 0.0).sum()),
                deficit=deficit)


def plan_day(d, case, fc, kappa_plan=K_PLAN) -> dict:
    """第 d 日 0:00 制定计划：0:00 预报 + 历史残差情景（20 个）两阶段随机 LP。"""
    scen, probs = plan_scenarios(d, case, fc)
    return solve_plan(case['L'][d], scen, probs, case['price'], kappa=kappa_plan)


def state_after(prefix, d, case, fc, plan, cache):
    """共享前缀缓存：返回该调整前缀下的 (X, C, D, 累计调整费)。

    已执行时段 [0, s) 的 x/C/D 严格冻结，当前储电量由已执行轨迹给出，
    只对剩余时段 [s, 144) 用该时刻的新预报重新规划。
    """
    if prefix in cache:
        return cache[prefix]
    X, C, D, fee = state_after(prefix[:-1], d, case, fc, plan, cache)
    rel_h = prefix[-1]
    s = REL_SLOTS[rel_h]
    E_cur = E_INIT + float(np.sum(ETA * C[:s] - D[:s] / ETA))
    scen, probs = adjust_scenarios(d, case, fc, rel_h)
    rr = solve_adjust(case['L'][d][s:], case['price'][s:], X[s:].copy(),
                      scen[:, s:], probs, E_cur)
    X, C, D = X.copy(), C.copy(), D.copy()
    X[s:], C[s:], D[s:] = rr['X'], rr['C'], rr['D']
    cache[prefix] = (X, C, D, fee + rr['fee_adj'])
    return cache[prefix]


def simulate_day(d, case, fc, plan) -> dict:
    """一天推演覆盖全部调整时刻组合（共享前缀缓存，避免重复求解）。"""
    price = case['price']
    cache = {(): (plan['x'].copy(), plan['C'].copy(), plan['D'].copy(), 0.0)}
    plan_fee = float((price * plan['x']).sum())
    out = {}
    for name, rels in POLICIES.items():
        X, C, D, adj_fee = state_after(rels, d, case, fc, plan, cache)
        ev = settle(X, C, D, case['L'][d], case['P'][d], price)
        out[name] = dict(date=case['dates'][d], plan_kwh=float(plan['x'].sum()),
                         plan_fee=plan_fee, deliv_kwh=float(X.sum()),
                         adj_fee=adj_fee, adj_abs=float(np.abs(X - plan['x']).sum()),
                         em_kwh=ev['em_kwh'], em_fee=ev['em_fee'],
                         curt_kwh=ev['curt_kwh'],
                         total=plan_fee + adj_fee + ev['em_fee'],
                         x=plan['x'], X=X, C=C, D=D, deficit=ev['deficit'])
    return out


#主流程
def run(days=0, out=None):
    utf8_console()
    case, fc = build_case(), load_pv_forecast()
    idx = np.where(case['dates'] >= pd.Timestamp(START))[0]
    if days:
        idx = idx[:days]
    print('=' * 78)
    print(f'问题三 计划—调整两层策略（计划层 κ_plan={K_PLAN:g} → '
          f'{1 - 1 / K_PLAN:.0%} 分位；结算按题面 1.5c / 0.5c / 5c）')
    print('=' * 78)
    print(f'  天数 {len(idx)}（{case["dates"][idx[0]].date()} ~ '
          f'{case["dates"][idx[-1]].date()}）；计划层情景 {K_SCEN}，'
          f'调整层情景 {M_ADJ}；日历窗 ±{WIN} 天')

    daily = {k: [] for k in POLICIES}
    t0 = time.time()
    for n, d in enumerate(idx, 1):
        res = simulate_day(int(d), case, fc, plan_day(int(d), case, fc))
        for name in POLICIES:
            daily[name].append(res[name])
        if n % 25 == 0 or n == len(idx):
            el = time.time() - t0
            print(f'  {n}/{len(idx)} 天，累计 {el:.0f} s，预计剩余 '
                  f'{el / n * (len(idx) - n) / 60:.1f} min', flush=True)

    #调整时刻消融
    rows = []
    for name in POLICIES:
        recs = daily[name]
        s = lambda k: float(sum(r[k] for r in recs))
        rows.append(dict(调整时刻=name, 计划购电量=s('plan_kwh'), 计划购电费=s('plan_fee'),
                         交付购电量=s('deliv_kwh'), 调整相关费用=s('adj_fee'),
                         调整量绝对值=s('adj_abs'), 紧急购电量=s('em_kwh'),
                         紧急购电费=s('em_fee'), 弃电量=s('curt_kwh'), 总费用=s('total')))
    df = pd.DataFrame(rows)
    base = float(df.loc[df['调整时刻'].str.startswith('无调整'), '总费用'].iloc[0])
    df['相对无调整_%'] = (100 * (df['总费用'] - base) / base).round(3)
    REPORTS.mkdir(exist_ok=True)
    df.to_csv(REPORTS / '问题3_调整时刻对照.csv', index=False, encoding='utf-8-sig')
    print('')
    print(df.round(2).to_string(index=False))

    #主口径（题面全用）逐日明细
    recs = daily[MAIN]
    pd.DataFrame([{k: v for k, v in r.items() if k not in ('x', 'X', 'C', 'D', 'deficit')}
                  for r in recs]
                 ).to_csv(REPORTS / '问题3_逐日汇总.csv', index=False, encoding='utf-8-sig')

    #写 result3.xlsx（附件 5 模板：4 张表）
    out = Path(out) if out else (ROOT / ('result3_自检.xlsx' if days else 'result3.xlsx'))
    plan_rows, adj_rows, soc_rows, em_rows = [], [], [], []
    for d, r in zip(idx, recs):
        plan_rows.append([case['dates'][d]] + [round(v, 4) for v in r['x']]
                         + [round(r['plan_kwh'], 4), round(r['plan_fee'], 4)])
        adj_rows.append([case['dates'][d]] + [round(v, 4) for v in r['X']]
                        + [round(r['deliv_kwh'], 4), round(r['adj_fee'], 4)])
        for k, (seg, a, b) in enumerate(SEGS):
            soc_rows.append([case['dates'][d] if k == 0 else '', seg,
                             round(float(r['C'][a:b].sum()), 4),
                             round(float(r['D'][a:b].sum()), 4),
                             dtime(0, 0) if k == 0 else ('24:00' if k == 1 else ''),
                             round(E_INIT, 4) if k <= 1 else ''])
        segs = merge_intervals(r['deficit'])
        if not segs:
            em_rows.append([case['dates'][d], '', ''])
        else:
            for k, (span, kwh) in enumerate(segs):
                em_rows.append([case['dates'][d] if k == 0 else '', span, round(kwh, 4)])

    hdr = ['日期\\时间'] + [time_label(t) for t in range(N)] + ['全天购电量', '全天购电费']
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        pd.DataFrame(plan_rows, columns=hdr).to_excel(w, sheet_name='计划购电量', index=False)
        pd.DataFrame(adj_rows, columns=hdr).to_excel(w, sheet_name='调整购电量', index=False)
        pd.DataFrame(soc_rows, columns=['日期', '时间段', '充电量', '放电量', '时刻', '储电量']
                     ).to_excel(w, sheet_name='充放电量', index=False)
        pd.DataFrame(em_rows, columns=['日期', '购电时间段', '购电量']
                     ).to_excel(w, sheet_name='紧急购电量', index=False)
    wb = openpyxl.load_workbook(out)                     # 日期/时间列格式对齐附件 5 模板
    for sh in ('计划购电量', '调整购电量', '充放电量', '紧急购电量'):
        ws = wb[sh]
        for rr in range(2, ws.max_row + 1):
            c = ws.cell(row=rr, column=1)
            if hasattr(c.value, 'year'):
                c.number_format = DATE_FMT
    ws = wb['充放电量']
    for rr in range(2, ws.max_row + 1, len(SEGS)):
        if ws.cell(row=rr, column=2).value != SEGS[0][0]:
            continue
        ws.cell(row=rr, column=5).number_format = TIME_FMT
        ws.cell(row=rr + 1, column=5).number_format = '@'
    wb.save(out)
    print(f'\n  [已写出] {out.name}、reports/问题3_调整时刻对照.csv、'
          f'reports/问题3_逐日汇总.csv')

    #指定日期（论文附录 B 表 1/2/3
    by_date = {r['date']: r for r in recs}
    print('\n' + '=' * 78 + '\n指定日期（论文附录 B 表 1 / 表 2 / 表 3）\n' + '=' * 78)
    for ds in REPORT_DAYS:
        if pd.Timestamp(ds) not in by_date:
            continue                              # --days 截断时指定日期可能不在样本内
        r = by_date[pd.Timestamp(ds)]
        E_end = float(E_INIT + np.sum(ETA * r['C'] - r['D'] / ETA))
        print(f'\n【{ds}】')
        print('  表 1 计划购电量(kWh): ' + '  '.join(
            f'{h}:00 {r["x"][h * 6]:.2f}' for h in (10, 12, 14, 16, 18, 20)))
        print(f'        计划 {r["plan_kwh"]:.2f} kWh / {r["plan_fee"]:.2f} 元；'
              f'调整后交付 {r["deliv_kwh"]:.2f} kWh，调整相关费用 {r["adj_fee"]:.2f} 元')
        print('  表 2 储能(最终): ' + ' | '.join(
            f'{seg} 充{float(r["C"][a:b].sum()):.2f}/放{float(r["D"][a:b].sum()):.2f}'
            for seg, a, b in SEGS))
        print(f'        0:00 储电量 {E_INIT:.2f}，24:00 储电量 {E_end:.2f} kWh')
        segs = merge_intervals(r['deficit'])
        print('  表 3 紧急购电: ' + ('无' if not segs else ' | '.join(
            f'{sp}: {kw:.2f}' for sp, kw in segs)))
        print(f'        紧急购电费 {r["em_fee"]:.2f} 元，当日结算 {r["total"]:.2f} 元')

    #校验
    s = lambda k: float(sum(r[k] for r in recs))
    bad_soc = sum(1 for r in recs
                  if (lambda E: E.min() < E_MIN - 0.05 or E.max() > E_MAX + 0.05)(
                      E_INIT + np.cumsum(ETA * r['C'] - r['D'] / ETA)))
    print('\n[校验]')
    print(f'  交付量 − 计划量合计           : {s("deliv_kwh") - s("plan_kwh"):+.2f} kWh（应 ≥ 0）')
    print(f'  向下调整量合计                : {sum(float(np.sum(np.maximum(r["x"] - r["X"], 0))) for r in recs):.2f} kWh（应 0）')
    print(f'  储电量越界的天数              : {bad_soc}（应 0）')
    print(f'  计划/交付量负值个数           : '
          f'{int(sum((r["x"] < -1e-9).sum() for r in recs))} / '
          f'{int(sum((r["X"] < -1e-9).sum() for r in recs))}')
    print(f'  同时充放电时段数              : '
          f'{int(sum(((r["C"] > 1e-6) & (r["D"] > 1e-6)).sum() for r in recs))}')
    print(f'  每日 24:00 储电量 = 6000 的天数: '
          f'{sum(1 for r in recs if abs(float(E_INIT + np.sum(ETA * r["C"] - r["D"] / ETA)) - E_INIT) < 1e-3)}'
          f'/{len(recs)}')
    print(f'  全年总费用                    : {s("total"):,.2f} 元')

    return df


#计划层服务水平扫描
SCAN_KAPPAS = (1.2, 1.5, 2.0, 2.5, 3.0, 5.0, 11.0)
SCAN_DAYS = 30


def scan(n_days=SCAN_DAYS, kappas=SCAN_KAPPAS):
    """计划层服务水平扫描（论文图 11 的数据来源）。

    把计划层**内部**使用的缺口惩罚倍数 κ_plan 当旋钮（对应计划量服务水平
    1 − 1/κ_plan），**结算始终按题面真实规则**（1.5c / 0.5c / 5c），
    每个 κ 跑完整的“0:00 计划 + 6/12/18 调整”链条，取全年均匀抽样的 n_days 天。
    输出 reports/问题3_分位扫描.csv。
    """
    utf8_console()
    case, fc = build_case(), load_pv_forecast()
    idx = np.where(case['dates'] >= pd.Timestamp(START))[0]
    if 0 < n_days < len(idx):
        idx = idx[np.unique(np.linspace(0, len(idx) - 1, n_days).round().astype(int))]
    print('=' * 78)
    print(f'计划层服务水平扫描（抽样 {len(idx)} 天，结算按真实 1.5c/0.5c/5c）')
    print('=' * 78)
    rows = []
    for kap in kappas:
        t0 = time.time()
        tot = dict(plan=0.0, plan_fee=0.0, adj=0.0, em=0.0, em_fee=0.0, curt=0.0)
        for d in idx:
            d = int(d)
            plan = plan_day(d, case, fc, kappa_plan=kap)
            cache = {(): (plan['x'].copy(), plan['C'].copy(), plan['D'].copy(), 0.0)}
            X, C, D, fee = state_after((6, 12, 18), d, case, fc, plan, cache)
            ev = settle(X, C, D, case['L'][d], case['P'][d], case['price'])
            tot['plan'] += float(plan['x'].sum())
            tot['plan_fee'] += float((case['price'] * plan['x']).sum())
            tot['adj'] += fee
            tot['em'] += ev['em_kwh']
            tot['em_fee'] += ev['em_fee']
            tot['curt'] += ev['curt_kwh']
        total = tot['plan_fee'] + tot['adj'] + tot['em_fee']
        rows.append(dict(计划层内部κ=kap, 理论服务水平=round(1 - 1 / kap, 4), 天数=len(idx),
                         计划购电量=round(tot['plan'], 2), 计划购电费=round(tot['plan_fee'], 2),
                         调整相关费用=round(tot['adj'], 2), 紧急购电量=round(tot['em'], 2),
                         紧急购电费=round(tot['em_fee'], 2), 弃电量=round(tot['curt'], 2),
                         总费用=round(total, 2), 耗时_s=round(time.time() - t0, 1)))
        print(f'  κ_plan={kap:<4g} 服务水平 {rows[-1]["理论服务水平"]:.2f}  '
              f'计划 {tot["plan"]:>12,.0f} kWh  调整费 {tot["adj"]:>10,.0f}  '
              f'紧急 {tot["em"]:>9,.0f} kWh  总费用 {total:>14,.2f} 元  '
              f'({rows[-1]["耗时_s"]} s)', flush=True)
    df = pd.DataFrame(rows)
    best = float(df['总费用'].min())
    df['相对最优_%'] = (100 * (df['总费用'] - best) / best).round(3)
    REPORTS.mkdir(exist_ok=True)
    df.to_csv(REPORTS / '问题3_分位扫描.csv', index=False, encoding='utf-8-sig')
    print(f'\n  [已写出] reports/问题3_分位扫描.csv；费用最优 κ_plan = '
          f'{df.loc[df["总费用"].idxmin(), "计划层内部κ"]:g}')
    return df


#论文图 9 / 10 / 11 
FIGDIR = ROOT / 'figures'
_C = {'plan': '#2B6CB0', 'deliver': '#D97706', 'emerg': '#C2413A', 'ref': '#6B7280'}


def make_figs(ab=None, scan_csv=None):
    """只画论文引用的三张问题三插图（读 reports/*.csv，不重解模型）。

        图 9  问题3_调整时刻消融          figures/3/问题3_调整时刻消融.pdf|.png
        图 10 问题3_不同预报时间紧急购电量  figures/3/问题3_不同预报时间紧急购电量.pdf|.png
        图 11 问题3_计划层服务水平扫描      figures/3/问题3_计划层服务水平扫描.pdf|.png
    同时把绘图数值写到 figures/绘图数据/<图名>.csv。
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans'],
        'font.family': 'sans-serif', 'axes.unicode_minus': False,
        'font.size': 9.5, 'axes.labelsize': 10, 'xtick.labelsize': 8.5,
        'ytick.labelsize': 8.5, 'legend.fontsize': 9.5, 'figure.dpi': 140,
        'savefig.dpi': 240, 'savefig.bbox': 'tight', 'savefig.pad_inches': 0.08,
        'axes.linewidth': 0.8, 'grid.color': '#D9DEE5', 'grid.linewidth': 0.65,
    })
    (FIGDIR / '3').mkdir(parents=True, exist_ok=True)
    (FIGDIR / '绘图数据').mkdir(parents=True, exist_ok=True)

    def clean(ax):
        ax.set_axisbelow(True)
        ax.grid(True, axis='y', alpha=0.8)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.tick_params(length=3, width=0.8)

    def save(fig, name, data=None):
        fig.savefig(FIGDIR / '3' / f'{name}.png')
        fig.savefig(FIGDIR / '3' / f'{name}.pdf')
        if data is not None:
            pd.DataFrame(data).to_csv(FIGDIR / '绘图数据' / f'{name}.csv',
                                      index=False, encoding='utf-8-sig')
        plt.close(fig)
        print(f'  [已写出] figures/3/{name}.pdf|.png')

    if ab is None:
        ab = pd.read_csv(REPORTS / '问题3_调整时刻对照.csv')      # 由 python 问题3.py 产生
    if scan_csv is None:
        scan_csv = REPORTS / '问题3_分位扫描.csv'                 # 由 python 问题3.py --scan 产生
    abp = ab.rename(columns={'调整相关费用': '调整费'})

    # 图 9：全年调整费（各调整时刻组合）
    xx = np.arange(len(abp))
    fig, ax = plt.subplots(figsize=(8.2, 3.8))
    ax.bar(xx, abp.调整费 / 1e4,
           color=[_C['ref']] + [_C['deliver']] * (len(abp) - 1))
    ax.set_xticks(xx, [str(v).replace('（', '\n（') for v in abp.调整时刻])
    ax.set_xlabel('调整信息窗')
    ax.set_ylabel('全年调整费 / 万元')
    ax.set_ylim(0, abp.调整费.max() / 1e4 * 1.14)
    clean(ax)
    save(fig, '问题3_调整时刻消融', abp[['调整时刻', '调整费', '紧急购电量']])

    # 图 10：四种单独预报组合下的全年紧急购电量
    combo = abp.iloc[:4].copy()
    combo['预报组合'] = ['无调整', '0:00+6:00', '0:00+12:00', '0:00+18:00']
    combo['紧急购电量_kWh'] = combo['紧急购电量'].astype(float)
    combo['紧急购电量_千kWh'] = combo['紧急购电量_kWh'] / 1e3
    combo['相对无调整减少_pct'] = 100 * (1 - combo['紧急购电量_kWh']
                                         / float(combo['紧急购电量_kWh'].iloc[0]))
    yy = combo['紧急购电量_千kWh'].to_numpy(float)
    fig, ax = plt.subplots(figsize=(8.2, 4.1))
    bars = ax.bar(np.arange(4), yy, width=.58,
                  color=[_C['ref']] + [_C['deliver']] * 3, edgecolor='white', linewidth=.8)
    ax.set_xticks(np.arange(4), combo['预报组合'])
    ax.set_xlabel('可用预报时间组合')
    ax.set_ylabel('全年紧急购电量 / 千 kWh')
    ax.set_ylim(0, yy.max() * 1.28)
    for rect, val, red in zip(bars, yy, combo['相对无调整减少_pct']):
        ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + yy.max() * .025,
                f'{val:,.1f} 千kWh\n' + ('基准' if red < 1e-9 else f'减少 {red:.1f}%'),
                ha='center', va='bottom', fontsize=8.5)
    ax.text(.98, .96, '同一计划层，仅改变可用预报时刻组合', transform=ax.transAxes,
            ha='right', va='top', fontsize=8.2, color='#4B5563')
    clean(ax)
    save(fig, '问题3_不同预报时间紧急购电量',
         combo[['预报组合', '调整时刻', '紧急购电量_kWh', '紧急购电量_千kWh',
                '相对无调整减少_pct']])

    # 图 11：计划层服务水平扫描
    sc = pd.read_csv(scan_csv)
    fig, ax = plt.subplots(figsize=(7.8, 3.8))
    ax.plot(sc.理论服务水平 * 100, sc.总费用 / 1e4, color=_C['plan'], marker='o', lw=2,
            label=None)
    best = sc.loc[sc.总费用.idxmin()]
    ax.scatter([best.理论服务水平 * 100], [best.总费用 / 1e4], color=_C['emerg'], s=46,
               zorder=5, label=f'最优 κ={best.iloc[0]:g}')
    ax.set_xlabel('计划层理论服务水平 / %')
    ax.set_ylabel('抽样期总费用 / 万元')
    ax.legend(frameon=True, framealpha=0.93, edgecolor='#D1D5DB')
    clean(ax)
    save(fig, '问题3_计划层服务水平扫描',
         sc[['计划层内部κ', '理论服务水平', '总费用', '相对最优_%']])


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='问题三：计划—调整两层购电策略')
    ap.add_argument('--days', type=int, default=0, help='只跑前 N 天（0=全年 334 天）')
    ap.add_argument('--out', default=None, help='result3.xlsx 写出路径')
    ap.add_argument('--scan', action='store_true', help='只做计划层服务水平扫描')
    ap.add_argument('--scan-days', type=int, default=SCAN_DAYS, help='扫描抽样天数')
    ap.add_argument('--figs', action='store_true',
                    help='只画论文图 9/10/11（读 reports/*.csv，不重解模型）')
    a = ap.parse_args()
    if a.scan:
        scan(n_days=a.scan_days)
    elif a.figs:
        utf8_console()
        make_figs()
    else:
        run(days=a.days, out=a.out)
