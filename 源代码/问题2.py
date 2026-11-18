from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass
from datetime import time as dtime
from pathlib import Path

import numpy as np
import pandas as pd
import pulp as pl

from 路径解析 import SRC, find_att

ROOT = SRC                     # 源代码/ 目录（不随启动时的工作目录变化）
ATT = find_att()               # 附件目录自动定位，见 路径解析.py
REPORTS = ROOT / 'reports'
FIGS = ROOT / 'figures'
FIG_Q2 = FIGS / '2'
FIG_DATA = FIGS / '绘图数据'

N = 144                       # 每天 144 个 10 分钟时段
DT = 1.0 / 6.0                # 时段长度 h
ETA = 0.9                     # 单程充、放电效率
E_MIN, E_MAX, E_INIT = 1200.0, 10800.0, 6000.0
S = 5000.0 * DT               # 833.33 kWh/时段，交流侧充放电功率上限
KAPPA = 5.0                   # 紧急购电电价倍数
K_SCEN = 20                   # 主口径 K-medoids 情景数
WIN = 25                      # 主口径情景集日历窗半宽（天）
START = '2025-02-01'          # 输出起始日（附件 5 模板要求）
REPORT_DAYS = ['2025-03-20', '2025-06-21', '2025-09-23', '2025-12-21']
DATE_FMT, TIME_FMT = 'mm-dd-yy', 'h:mm'
SEGS = [('0:00-4:00', 0, 24), ('4:00-8:00', 24, 48), ('8:00-12:00', 48, 72),
        ('12:00-16:00', 72, 96), ('16:00-20:00', 96, 120), ('20:00-24:00', 120, 144)]

OUT_XLSX = ROOT / 'result2.xlsx'
OUT_XLSX_C = ROOT / 'result2_口径C_源荷双重不确定.xlsx'
CSV_DAILY = REPORTS / '问题2_逐日汇总.csv'
CSV_DAILY_C = REPORTS / '问题2_逐日汇总_口径C.csv'
CSV_ANNUAL = REPORTS / '问题2_全年运行结果.csv'
CSV_EMDAYS = REPORTS / '问题2_指定日期紧急购电量.csv'
CSV_MILP = REPORTS / 'LP_vs_MILP_全年对比.csv'
CSV_PROP = REPORTS / '问题二_命题P4核验.csv'
CSV_SENS = REPORTS / '灵敏度_情景数.csv'
CSV_COVER = REPORTS / '灵敏度_覆盖诊断.csv'
CSV_LOADCASE = REPORTS / '灵敏度_负荷口径.csv'


def utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass


@dataclass
class Case:
    dates: pd.DatetimeIndex       # (365,)
    price: np.ndarray             # (144,)    元/kWh，附件 1（每天相同）
    L: np.ndarray                 # (365,144) 负荷电量 kWh，附件 2
    P: np.ndarray                 # (365,144) 光伏电量 kWh，附件 2
    f1_load: np.ndarray
    f1_pv: np.ndarray

    @property
    def net(self) -> np.ndarray:
        """净负荷 N = L - V，(365,144)"""
        return self.L - self.P

    def index_of(self, date) -> int:
        idx = np.where(self.dates == pd.Timestamp(date))[0]
        if len(idx) == 0:
            raise KeyError(f'{date} 不在附件 2 的日期范围内')
        return int(idx[0])

    def rows_from(self, start) -> np.ndarray:
        return np.where(self.dates >= pd.Timestamp(start))[0]


def load_case() -> Case:
    """功率换算为电量 kWh"""
    f1 = pd.read_excel(ATT / '附件1.xlsx')
    price = f1['电价'].to_numpy(float)
    f1_load = f1['小区负载'].to_numpy(float) * DT
    f1_pv = f1['光伏发电预测功率'].to_numpy(float) * DT

    d2 = pd.read_excel(ATT / '附件2.xlsx', sheet_name='小区负载')
    p2 = pd.read_excel(ATT / '附件2.xlsx', sheet_name='光伏发电实际功率')
    dates = pd.DatetimeIndex(pd.to_datetime(d2.iloc[:, 0]).dt.normalize())
    L = d2.iloc[:, 1:].to_numpy(float) * DT
    P = p2.iloc[:, 1:].to_numpy(float) * DT

    assert L.shape == P.shape == (len(dates), N), (L.shape, P.shape, len(dates))
    assert len(price) == N, len(price)
    return Case(dates=dates, price=price, L=L, P=P, f1_load=f1_load, f1_pv=f1_pv)


def time_label(idx: int) -> str:
    """时段索引'H:MM-H:MM'"""
    s, e = idx * 10, idx * 10 + 10
    sh, sm = divmod(s, 60)
    if e == 1440:
        return f'{sh}:{sm:02d}-0:00+1'
    return f'{sh}:{sm:02d}-{e // 60}:{e % 60:02d}'


def mmss(minute: int) -> str:
    minute = int(minute)
    return '0:00+1' if minute == 1440 else f'{minute // 60}:{minute % 60:02d}'

def cal_window(d: int, dates, half: int = WIN) -> np.ndarray:

    doy = dates.dayofyear.to_numpy()
    hist = np.arange(d)
    if len(hist) == 0:
        return hist
    diff = np.abs(doy[hist] - doy[d])
    return hist[np.minimum(diff, 365 - diff) <= half]


def kmedoids(X: np.ndarray, K: int, iters: int = 30):
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


def scenarios(d: int, case: Case, base: str = 'P', K: int = K_SCEN, half: int = WIN):
    """第 d 日 0:00 可得的等权情景集。

    base='P' -> 光伏随机、负荷已知（主口径）
    base='N' -> 源荷双重不确定（负荷并入情景，论文灵敏度口径）
    """
    X = case.P if base == 'P' else case.net
    sel = cal_window(d, case.dates, half=half)
    if len(sel) == 0:
        return X[[0]].copy(), np.array([1.0])
    if len(sel) <= K:
        return X[sel].copy(), np.full(len(sel), 1.0 / len(sel))
    return kmedoids(X[sel], K)


def solve_det(net, price, E0=E_INIT):
    """问题一确定性单日 LP

    min sum_t c_t g_t  s.t.  g_t + D_t = net_t + C_t + U_t ；储能递推；日循环。
    返回 dict(g, C, D, U, E, J)
    """
    T = range(N)
    m = pl.LpProblem('det', pl.LpMinimize)
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


def solve_stoch(load, scen, probs, price, E0=E_INIT, kappa=KAPPA,
                eps_reg=1e-6, eps_x=1e-6, milp=False, time_limit=None):
    """两阶段随机 LP。"""
    ns, T = len(scen), range(N)
    m = pl.LpProblem('stoch', pl.LpMinimize)
    x = [pl.LpVariable(f'x{t}', 0) for t in T]
    C = [pl.LpVariable(f'C{t}', 0, S) for t in T]
    D = [pl.LpVariable(f'D{t}', 0, S) for t in T]
    E = [pl.LpVariable(f'E{t}', E_MIN, E_MAX) for t in T]
    b = [[pl.LpVariable(f'b{s}_{t}', 0) for t in T] for s in range(ns)]
    U = [[pl.LpVariable(f'U{s}_{t}', 0) for t in T] for s in range(ns)]
    y = [pl.LpVariable(f'y{t}', cat='Binary') for t in T] if milp else None

    m += (pl.lpSum(price[t] * x[t] for t in T)
          + pl.lpSum(kappa * price[t] * probs[s] * b[s][t]
                     for s in range(ns) for t in T)
          + eps_reg * pl.lpSum(C[t] + U[s][t] for s in range(ns) for t in T)
          + eps_x * pl.lpSum(x[t] for t in T))
    for t in T:
        m += E[t] == (E0 if t == 0 else E[t - 1]) + ETA * C[t] - D[t] / ETA
        if milp:
            m += C[t] <= S * y[t]
            m += D[t] <= S * (1 - y[t])
        for s in range(ns):
            m += x[t] + scen[s][t] + D[t] + b[s][t] == load[t] + C[t] + U[s][t]
    m += E[N - 1] == E0

    kw = {'msg': 0}
    if time_limit is not None:
        kw['timeLimit'] = time_limit
    m.solve(pl.PULP_CBC_CMD(**kw))
    assert m.status == pl.LpStatusOptimal, f'两阶段随机 LP 未求得最优解（status={m.status}）'
    out = {k: np.array([v.value() for v in vs])
           for k, vs in dict(x=x, C=C, D=D, E=E).items()}
    out['b'] = np.array([[v.value() for v in b[s]] for s in range(ns)])
    out['U'] = np.array([[v.value() for v in U[s]] for s in range(ns)])
    out['J'] = float(pl.value(m.objective))
    out['J_plan'] = float((price * out['x']).sum())
    out['J_em'] = float((kappa * price[None, :] * (probs[:, None] * out['b'])).sum())
    return out


def evaluate(x, C, D, L_real, V_real, price, kappa=KAPPA):

    x = np.asarray(x, float)
    C = np.asarray(C, float)
    D = np.asarray(D, float)
    r = (np.asarray(L_real, float) - np.asarray(V_real, float)) - x - (D - C)
    deficit, curtail = np.maximum(r, 0.0), np.maximum(-r, 0.0)
    price = np.asarray(price, float)
    plan_cost = float((price * x).sum())
    em_cost = float((kappa * price * deficit).sum())
    return dict(plan_kwh=float(x.sum()), plan_cost=plan_cost,
                em_kwh=float(deficit.sum()), em_cost=em_cost,
                curt_kwh=float(curtail.sum()), total=plan_cost + em_cost,
                deficit=deficit, curtail=curtail)


def merge_intervals(deficit, delta=1.0):
    """把相邻的紧急购电时段合并成区间，返回 [(时间段标签, 电量), ...]。"""
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


def soc_trace(E0, C, D, eta=ETA):
    C, D = np.asarray(C, float), np.asarray(D, float)
    out, e = [], E0
    for t in range(len(C)):
        e = e + eta * C[t] - D[t] / eta
        out.append(e)
    return np.array(out)


def daily_summary(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    cols = ['plan_kwh', 'plan_cost', 'em_kwh', 'em_cost', 'curt_kwh', 'date',
            'em_listed', 'n_seg']
    for c in cols:
        if c not in df.columns:
            df[c] = 0.0
    return df[cols]

def solve_day(i, case, base='P'):
    """第 i 日 0:00 制定计划。

    base='P' -> 光伏随机、负荷已知（主口径）：情景即光伏电量空间
    base='N' -> 源荷双重不确定：情景取净负荷 (L-V)，等价于"负荷也随机"
    """
    scen, probs = scenarios(i, case, base=base)
    if base == 'N':
        scen = case.L[i][None, :] - scen          # 净负荷情景 -> 等效光伏情景
    return solve_stoch(case.L[i], scen, probs, case.price, E0=E_INIT)


def run_main(base='P', out=OUT_XLSX, csv=CSV_DAILY, verbose=True):
    """result2.xlsx + 逐日汇总 + 论文表。"""
    case = load_case()
    idx = case.rows_from(START)
    recs, plan_rows, soc_rows, em_rows = [], [], [], []
    t0 = time.time()

    for cnt, i in enumerate(idx, 1):
        r = solve_day(i, case, base=base)
        x, C, D = r['x'], r['C'], r['D']
        ev = evaluate(x, C, D, case.L[i], case.P[i], case.price)
        segs = merge_intervals(ev['deficit'])
        recs.append(dict(plan_kwh=ev['plan_kwh'], plan_cost=ev['plan_cost'],
                         em_kwh=ev['em_kwh'], em_cost=ev['em_cost'],
                         curt_kwh=ev['curt_kwh'], date=case.dates[i],
                         em_listed=float(sum(v for _, v in segs)), n_seg=len(segs)))
        plan_rows.append([case.dates[i]] + [round(v, 4) for v in x]
                         + [round(ev['plan_kwh'], 4), round(ev['plan_cost'], 4)])
        for k, (name, a, b) in enumerate(SEGS):
            soc_rows.append([case.dates[i] if k == 0 else '', name,
                             round(float(C[a:b].sum()), 4), round(float(D[a:b].sum()), 4),
                             dtime(0, 0) if k == 0 else ('24:00' if k == 1 else ''),
                             round(E_INIT, 4) if k <= 1 else ''])
        if not segs:
            em_rows.append([case.dates[i], '', ''])
        else:
            for k, (span, kwh) in enumerate(segs):
                em_rows.append([case.dates[i] if k == 0 else '', span, round(kwh, 4)])
        if verbose and cnt % 60 == 0:
            el = time.time() - t0
            print(f'  {cnt}/{len(idx)} 天, 累计 {el:.1f} s, '
                  f'预计剩余 {el / cnt * (len(idx) - cnt) / 60:.1f} min', flush=True)

    hdr = ['日期\\时间'] + [time_label(t) for t in range(N)] + ['全天购电量', '全天购电费']
    df1 = pd.DataFrame(plan_rows, columns=hdr)
    df2 = pd.DataFrame(soc_rows, columns=['日期', '时间段', '充电量', '放电量', '时刻', '储电量'])
    df3 = pd.DataFrame(em_rows, columns=['日期', '购电时间段', '购电量'])
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        df1.to_excel(w, sheet_name='计划购电量', index=False)
        df2.to_excel(w, sheet_name='充放电量', index=False)
        df3.to_excel(w, sheet_name='紧急购电量', index=False)
    _format_workbook(out)

    rows = daily_summary(recs)
    rows['date'] = pd.to_datetime(rows['date'])
    rows.to_csv(csv, index=False, encoding='utf-8-sig')

    s = lambda k: float(rows[k].sum())
    pv_sum = float(case.P[case.dates >= pd.Timestamp(START)].sum())
    plan_kwh, plan_cost = s('plan_kwh'), s('plan_cost')
    em_kwh, em_cost, curt = s('em_kwh'), s('em_cost'), s('curt_kwh')

    summary = pd.DataFrame([
        ('计划购电量/kWh', round(plan_kwh, 2)),
        ('计划购电费/元', round(plan_cost, 2)),
        ('紧急购电量/kWh', round(em_kwh, 2)),
        ('紧急购电费/元', round(em_cost, 2)),
        ('全年总费用/元', round(plan_cost + em_cost, 2)),
        ('弃电量/kWh', round(curt, 2)),
        ('弃电率/%', round(curt / pv_sum * 100, 2)),
        ('仿真天数/天', len(rows)),
    ], columns=['指标', '数值'])
    if base == 'P':
        summary.to_csv(CSV_ANNUAL, index=False, encoding='utf-8-sig')
        write_emergency_table(case, base=base)

    if verbose:
        tag = '主口径（负荷已知、光伏随机）' if base == 'P' else '灵敏度口径（源荷双重不确定）'
        print('')
        print('=' * 78)
        print(f'问题二 {tag}')
        print('=' * 78)
        print(f'  计划购电量  : {plan_kwh:>16.2f} kWh')
        print(f'  计划购电费  : {plan_cost:>16.2f} 元')
        print(f'  紧急购电量  : {em_kwh:>16.2f} kWh   （列入表 3 的 {s("em_listed"):.2f} kWh）')
        print(f'  紧急购电费  : {em_cost:>16.2f} 元   占全年 {em_cost / (plan_cost + em_cost) * 100:.2f}%')
        print(f'  全年总计费  : {plan_cost + em_cost:>16.2f} 元   日均 {(plan_cost + em_cost) / len(rows):.2f} 元')
        print(f'  紧急购电天数: {int((rows.em_kwh > 1.0).sum())} / {len(rows)}   入表区间 {int(s("n_seg"))} 段')
        print(f'  弃电量      : {curt:>16.2f} kWh   占同期光伏 {curt / pv_sum * 100:.2f}%')
        print(f'  计划电均价  : {plan_cost / plan_kwh:.4f} 元/kWh（电价均价 {case.price.mean():.4f}）')
        print(f'  [已写出] {out.name}、{csv.name}、{CSV_ANNUAL.name}、{CSV_EMDAYS.name}')
        print('')
        print('[校验]')
        print(f'  计划购电量负值个数        : {int((df1.iloc[:, 1:1 + N].to_numpy() < -1e-9).sum())}')
        print(f'  Σ144 列 vs 全天购电量偏差 : '
              f'{float(np.abs(df1.iloc[:, 1:1 + N].sum(1) - df1["全天购电量"]).max()):.2e} kWh')
        print(f'  Σ(λx) vs 全天购电费偏差   : '
              f'{float(np.abs((df1.iloc[:, 1:1 + N].to_numpy() * case.price).sum(1) - df1["全天购电费"]).max()):.2e} 元')

    return rows, case


def _format_workbook(path):
    import openpyxl
    wb = openpyxl.load_workbook(path)
    for name in ('计划购电量', '充放电量', '紧急购电量'):
        ws = wb[name]
        for r in range(2, ws.max_row + 1):
            c = ws.cell(row=r, column=1)
            if hasattr(c.value, 'year'):
                c.number_format = DATE_FMT
    ws = wb['充放电量']
    for r in range(2, ws.max_row + 1, len(SEGS)):
        if ws.cell(row=r, column=2).value != SEGS[0][0]:
            continue
        ws.cell(row=r, column=5).number_format = TIME_FMT
        ws.cell(row=r + 1, column=5).number_format = '@'
    wb.save(path)


def write_emergency_table(case, base='P'):
    recs = []
    for ds in REPORT_DAYS:
        i = case.index_of(ds)
        r = solve_day(i, case, base=base)
        ev = evaluate(r['x'], r['C'], r['D'], case.L[i], case.P[i], case.price)
        segs = merge_intervals(ev['deficit'])
        if not segs:
            recs.append(dict(日期=ds, 购电时间段='无紧急购电', 购电量=0.0))
        for span, kwh in segs:
            recs.append(dict(日期=ds, 购电时间段=span, 购电量=round(kwh, 4)))
    pd.DataFrame(recs).to_csv(CSV_EMDAYS, index=False, encoding='utf-8-sig')
    return pd.DataFrame(recs)


def run_prop(n_days=None, verbose=True):
    case = load_case()
    days = case.rows_from(START)
    rows = []
    t_all = time.time()
    for k, di in enumerate(days):
        pool = case.P[max(0, di - 30):di]
        scen = pool[-10:] if len(pool) >= 10 else pool
        probs = np.full(len(scen), 1.0 / len(scen))
        r1 = _milp_cmp(case, di, scen, probs, milp=False, reg=False)
        r2 = _milp_cmp(case, di, scen, probs, milp=False, reg=True)
        r3 = _milp_cmp(case, di, scen, probs, milp=True, reg=False)
        rows.append(dict(日期=str(case.dates[di].date()),
                         cost_LP=r1['cost'], cost_LPreg=r2['cost'], cost_MILP=r3['cost'],
                         t_LP=r1['t'], t_LPreg=r2['t'], t_MILP=r3['t'],
                         sim_LP=r1['sim'], sim_LPreg=r2['sim'],
                         dplan_1_3=float(np.abs(r1['C'] - r3['C']).max()),
                         dplan_2_3=float(np.abs(r2['C'] - r3['C']).max())))
        if (k + 1) % 40 == 0:
            el = time.time() - t_all
            print(f'  [LP/MILP] {k + 1:3d}/{len(days)} 天, 累计 {el:6.1f}s, '
                  f'预计剩余 {el / (k + 1) * (len(days) - k - 1) / 60:.1f} min', flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(CSV_MILP, index=False, encoding='utf-8-sig')

    rel = lambda a, b: np.abs(df[a] - df[b]) / np.maximum(np.abs(df[b]), 1e-9)
    if verbose:
        print('')
        print('=' * 78)
        print(f'LP 松弛 vs MILP 全年 {len(df)} 天对比')
        print('=' * 78)
        for tag, col in (('LP   ', 'cost_LP'), ('LP+reg', 'cost_LPreg')):
            r = rel(col, 'cost_MILP')
            print(f'  真实费用相对差 {tag} vs MILP: 最大 {r.max():.3e}  平均 {r.mean():.3e}'
                  f'  >1e-6 的天数 {int((r > 1e-6).sum())}')
        print(f'  LP 直接解出现同时充放的天数     : {int((df.sim_LP > 1e-3).sum())}'
              f' (最大同时充放量 {df.sim_LP.max():.3f} kWh)')
        print(f'  LP+reg 解出现同时充放的天数     : {int((df.sim_LPreg > 1e-3).sum())}'
              f' (最大同时充放量 {df.sim_LPreg.max():.3f} kWh)')
        print(f'  充放电计划与 MILP 不同(>1e-3) 的天数: LP {int((df.dplan_1_3 > 1e-3).sum())} 天,'
              f' LP+reg {int((df.dplan_2_3 > 1e-3).sum())} 天')
        print(f'  平均单日耗时  LP {df.t_LP.mean():.3f} s | LP+reg {df.t_LPreg.mean():.3f} s'
              f' | MILP {df.t_MILP.mean():.3f} s  (MILP/LP = {df.t_MILP.mean() / df.t_LP.mean():.2f} 倍)')
        print(f'  全年节省整数变量: {144 * len(df):,} 个')

    idx = days if n_days is None else days[:n_days]
    recs, t0 = [], time.time()
    for cnt, i in enumerate(idx, 1):
        r = solve_day(i, case, base='P')
        x, C, D, b, U = r['x'], r['C'], r['D'], r['b'], r['U']
        scen, probs = scenarios(i, case, base='P')
        R = case.L[i][None, :] - scen - x[None, :] - (D - C)[None, :]
        b2, U2 = np.maximum(R, 0.0), np.maximum(-R, 0.0)
        J_plan = float((case.price * x).sum())
        J_em = float((KAPPA * case.price[None, :] * (probs[:, None] * b)).sum())
        J_em2 = float((KAPPA * case.price[None, :] * (probs[:, None] * b2)).sum())
        k_t = (R > 1e-6).sum(0)
        recs.append(dict(date=case.dates[i], J_lp=r['J'], J_dec=J_plan + J_em,
                         rel_dec=abs(J_plan + J_em - r['J']) / r['J'],
                         rel_replay=abs(J_plan + J_em2 - r['J']) / r['J'],
                         max_b=float(np.abs(b - b2).max()),
                         max_U=float(np.abs(U - U2).max()),
                         k_zero=float((k_t == 0).mean()),
                         k_star=float((k_t == int(round(K_SCEN / KAPPA))).mean()),
                         k_mean=float(k_t.mean())))
        if cnt % 20 == 0:
            print(f'  [命题P4] ... {cnt}/{len(idx)}  用时 {time.time() - t0:.0f}s', flush=True)
    dp = pd.DataFrame(recs)
    dp.to_csv(CSV_PROP, index=False, encoding='utf-8-sig')

    if verbose:
        print('')
        print('=' * 78)
        print('目标分解与可执行性核验（命题 P4）')
        print('=' * 78)
        print(f'  天数                          : {len(dp)}')
        print(f'  J_plan + J_em - J_LP 合计 /元 : {(dp.J_dec - dp.J_lp).sum():.6e}')
        print(f'  分解相对差  最大 / 平均       : {dp.rel_dec.max():.3e} / {dp.rel_dec.mean():.3e}')
        print(f'  解析重放相对差 最大 / 平均    : {dp.rel_replay.max():.3e} / {dp.rel_replay.mean():.3e}')
        print(f'  b / U 重算最大偏差 / kWh      : {dp.max_b.max():.3e} / {dp.max_U.max():.3e}')
        print('  结论：LP 目标 = 计划费 + 期望紧急费；"当期观测唯一决定 b、U"的解析执行器')
        print('        重放同一计划结果一致 -> 计划因果可执行，无计划-执行偏差。')
        print(f'  命题 P2 离散推论（每时段缺额情景数 k，M={K_SCEN}，k* = M/kappa = 4）：')
        print(f'    k=0 时段占比 {dp.k_zero.mean() * 100:.4f}%   '
              f'k=4 时段占比 {dp.k_star.mean() * 100:.4f}%   k 均值 {dp.k_mean.mean():.4f}')
    return df, dp


def _milp_cmp(case, di, scen, probs, milp=False, reg=False, time_limit=60):
    """LP / LP+reg / MILP 三口径单日求解。"""
    t0 = time.time()
    r = solve_stoch(case.L[di], scen, probs, case.price, E0=E_INIT,
                    eps_reg=1e-6 if reg else 0.0, eps_x=0.0,
                    milp=milp, time_limit=time_limit)
    el = time.time() - t0
    cost = (float((case.price * r['x']).sum())
            + float((KAPPA * case.price[None, :] * (probs[:, None] * r['b'])).sum()))
    return dict(cost=cost, t=el, sim=float(np.minimum(r['C'], r['D']).sum()),
                C=r['C'], D=r['D'], x=r['x'])

VARIANTS = {'kmed10': (10, 25), 'kmed20': (20, 25), 'full25': (None, 25),
            'kmed20w120': (20, 120)}


def _scen_of(case, d, K, half):
    if K is None:
        sel = cal_window(d, case.dates, half=half)
        if len(sel) == 0:
            return case.P[[0]].copy(), np.array([1.0])
        return case.P[sel].copy(), np.full(len(sel), 1.0 / len(sel))
    return scenarios(d, case, base='P', K=K, half=half)


def run_sens(parts='ADE', only=None, verbose=True):
    """灵敏度分析。"""
    case = load_case()
    idx = case.rows_from(START)
    rows = []

    if 'A' in parts:
        for name, (K, half) in VARIANTS.items():
            if only and name != only:
                continue
            acc = dict(plan_kwh=0.0, plan_cost=0.0, em_kwh=0.0, em_cost=0.0, curt_kwh=0.0)
            t0 = time.time()
            for n, d in enumerate(idx, 1):
                scen, probs = _scen_of(case, d, K, half)
                r = solve_stoch(case.L[d], scen, probs, case.price, E0=E_INIT)
                ev = evaluate(r['x'], r['C'], r['D'], case.L[d], case.P[d], case.price)
                for k in acc:
                    acc[k] += ev[k]
                if n % 60 == 0:
                    print(f'  [{name}] {n}/{len(idx)} 天，累计 {time.time() - t0:.0f} s', flush=True)
            rows.append(dict(情景集=name, 情景数=(K if K else '窗口全部'), 窗口半宽=half,
                             计划购电量=acc['plan_kwh'], 计划购电费=acc['plan_cost'],
                             紧急购电量=acc['em_kwh'], 紧急购电费=acc['em_cost'],
                             总费用=acc['plan_cost'] + acc['em_cost'], 弃电量=acc['curt_kwh'],
                             耗时s=time.time() - t0))
            r = rows[-1]
            print(f'  [{name}] 总费用 {r["总费用"]:,.2f} 元 | 紧急购电费 {r["紧急购电费"]:,.2f}'
                  f' | 弃电 {r["弃电量"]:,.0f} kWh | 耗时 {r["耗时s"]:.0f} s')

        if len(rows) == len(VARIANTS):
            df = pd.DataFrame(rows)
            base = float(df.loc[df['情景集'] == 'kmed20', '总费用'].iloc[0])
            df['相对差_%'] = (100 * (df['总费用'] - base) / base).round(3)
            df.to_csv(CSV_SENS, index=False, encoding='utf-8-sig')
            if verbose:
                print('')
                print(df.round(4).to_string(index=False))

    if 'D' in parts:
        em = {}
        if CSV_DAILY.exists():
            sm = pd.read_csv(CSV_DAILY)
            sm['date'] = pd.to_datetime(sm['date'])
            em = dict(zip(sm['date'], sm['em_cost']))
        tot_em = sum(em.get(case.dates[d], 0.0) for d in idx)

        crows = []
        for half in (25, 120):
            boot = []
            for d in idx:
                scen, _ = scenarios(d, case, base='P', half=half)
                if int((scen.sum(1) < float(case.P[d].sum())).sum()) == 0:
                    boot.append(d)
            boot_em = sum(em.get(case.dates[d], 0.0) for d in boot) if em else float('nan')
            months = {}
            for d in boot:
                months[case.dates[d].month] = months.get(case.dates[d].month, 0) + 1
            crows.append(dict(窗口半宽=half, 垫底天数=len(boot), 总天数=len(idx),
                              垫底紧急购电费=boot_em,
                              占全年紧急购电费百分比=(100 * boot_em / tot_em) if em else float('nan'),
                              垫底月份分布=str(dict(sorted(months.items())))))
            print(f'  [覆盖] 半宽 {half:>3} 天 : 垫底 {len(boot)}/{len(idx)} 天，'
                  f'贡献紧急购电费 {boot_em:,.2f} 元，月份 {dict(sorted(months.items()))}')
        pd.DataFrame(crows).to_csv(CSV_COVER, index=False, encoding='utf-8-sig')

    if 'E' in parts and CSV_DAILY.exists():
        daily_c, _ = run_main(base='N', out=OUT_XLSX_C, csv=CSV_DAILY_C, verbose=False)
        a, b = pd.read_csv(CSV_DAILY), daily_c
        s = lambda df, k: float(df[k].sum())
        lc = pd.DataFrame([
            ('计划购电量_kWh', s(a, 'plan_kwh'), s(b, 'plan_kwh')),
            ('计划购电费_元', s(a, 'plan_cost'), s(b, 'plan_cost')),
            ('紧急购电量_kWh', s(a, 'em_kwh'), s(b, 'em_kwh')),
            ('紧急购电费_元', s(a, 'em_cost'), s(b, 'em_cost')),
            ('弃电量_kWh', s(a, 'curt_kwh'), s(b, 'curt_kwh')),
            ('总费用_元', s(a, 'plan_cost') + s(a, 'em_cost'),
             s(b, 'plan_cost') + s(b, 'em_cost')),
        ], columns=['指标', 'O1_负荷已知', 'C_源荷双随机'])
        lc['变化_pct'] = 100 * (lc['C_源荷双随机'] - lc['O1_负荷已知']) / lc['O1_负荷已知']
        lc.to_csv(CSV_LOADCASE, index=False, encoding='utf-8-sig')
        print('')
        print(lc.round(4).to_string(index=False))
    return rows


def _style_main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'Arial', 'DejaVu Sans'],
        'font.family': 'sans-serif', 'axes.unicode_minus': False,
        'font.size': 9.5, 'axes.titlesize': 10.5, 'axes.labelsize': 10,
        'xtick.labelsize': 8.5, 'ytick.labelsize': 8.5, 'legend.fontsize': 9.5,
        'figure.dpi': 140, 'savefig.dpi': 240, 'savefig.bbox': 'tight',
        'savefig.pad_inches': 0.08, 'axes.linewidth': 0.8,
        'grid.color': '#D9DEE5', 'grid.linewidth': 0.65,
    })
    return plt


C = {'plan': '#2B6CB0', 'deliver': '#D97706', 'emerg': '#C2413A', 'curt': '#6B7280',
     'pv': '#2F855A', 'load': '#374151', 'net': '#7C3AED', 'soc': '#0F766E',
     'ref': '#6B7280'}


def _clean(ax, grid='y'):
    ax.set_axisbelow(True)
    ax.grid(False) if grid == 'none' else ax.grid(True, axis=grid, alpha=0.8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(length=3, width=0.8)


def _legend(ax, **kw):
    h, l = ax.get_legend_handles_labels()
    if h:
        kw.pop('loc', None)
        ax.legend(h, l, loc='lower center', bbox_to_anchor=(0.5, 1.02),
                  ncol=kw.pop('ncol', min(len(h), 3)), borderaxespad=0.0,
                  frameon=True, framealpha=0.93, facecolor='white',
                  edgecolor='#D1D5DB', **kw)


def _save(fig, name, data=None, data_name=None, clear_title=True):
    import matplotlib.pyplot as plt
    FIG_Q2.mkdir(parents=True, exist_ok=True)
    if clear_title:
        for ax in fig.axes:
            ax.set_title('')
    fig.savefig(FIG_Q2 / f'{name}.pdf')
    fig.savefig(FIG_Q2 / f'{name}.png')
    if data is not None:
        FIG_DATA.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(data).to_csv(FIG_DATA / f'图_{data_name or name}.csv',
                                  index=False, encoding='utf-8-sig')
    plt.close(fig)
    print(f'  [图] figures/2/{name}.pdf')


def _matrix(sheet):
    return sheet.iloc[:, 1:1 + N].to_numpy(float)


def _emergency_matrix(sheet, dates):
    """把区间紧急购电量均匀摊到 10 分钟时段。"""
    sheet = sheet.copy()
    sheet[sheet.columns[0]] = sheet[sheet.columns[0]].ffill()
    z = np.zeros((len(dates), N))
    idx = {pd.Timestamp(x).normalize(): i for i, x in enumerate(dates)}
    for _, r in sheet.dropna(subset=[sheet.columns[0], sheet.columns[1], sheet.columns[2]]).iterrows():
        d = pd.Timestamp(r.iloc[0]).normalize()
        i = idx.get(d)
        if i is None:
            continue
        m = re.findall(r'(\d{1,2}):(\d{2})', str(r.iloc[1]))
        if len(m) != 2:
            continue
        a = int(m[0][0]) * 6 + int(m[0][1]) // 10
        b = int(m[1][0]) * 6 + int(m[1][1]) // 10
        if b <= a:
            b = N
        z[i, a:b] += float(r.iloc[2]) / max(1, b - a)
    return z


def _hourly(a):
    return np.asarray(a).reshape(24, 6).sum(axis=1)


def run_figs():
    """复现论文问题二一节的 4 张插图。"""
    plt = _style_main()

    #LP 与决策重放一致性
    chk = pd.read_csv(CSV_PROP).sort_values('date').reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8.6, 3.7))
    xx = np.arange(len(chk))
    ax.plot(xx, chk.rel_dec * 1e4, color=C['plan'], lw=1.1, label='相对目标差异')
    ax.axhline(0, color=C['ref'], lw=1.0, ls='--')
    ax.set_xlabel('日期序号（2 月 1 日起）')
    ax.set_ylabel('相对差异 / $10^{-4}$')
    ax.set_xlim(0, len(chk) - 1)
    _clean(ax)
    _legend(ax, loc='upper right')
    _save(fig, '问题2_LP与决策重放一致性',
          chk[['date', 'J_lp', 'J_dec', 'rel_dec', 'rel_replay']],
          data_name='LP与决策重放一致性')

    #典型日
    plan = pd.read_excel(OUT_XLSX, sheet_name='计划购电量')
    ems = pd.read_excel(OUT_XLSX, sheet_name='紧急购电量')
    dates = pd.DatetimeIndex(pd.to_datetime(plan.iloc[:, 0]).dt.normalize())
    x = _matrix(plan)
    em = _emergency_matrix(ems, dates)
    a2 = pd.read_excel(ATT / '附件2.xlsx', sheet_name='小区负载')
    pv = pd.read_excel(ATT / '附件2.xlsx', sheet_name='光伏发电实际功率')

    day = pd.Timestamp('2025-06-21')
    i = int(np.where(dates == day)[0][0])
    j = int(np.where(pd.to_datetime(a2.iloc[:, 0]).dt.normalize() == day)[0][0])
    L = _hourly(a2.iloc[j, 1:145].to_numpy(float))
    V = _hourly(pv.iloc[j, 1:145].to_numpy(float))
    X, E = _hourly(x[i]), _hourly(em[i])
    h = np.arange(24)
    fig, ax = plt.subplots(figsize=(8.8, 4.0))
    ax.plot(h, L, color=C['load'], lw=1.8, label='负荷')
    ax.plot(h, V, color=C['pv'], lw=1.8, label='实际光伏')
    ax.plot(h, np.maximum(L - V, 0), color=C['net'], lw=1.6, ls='--', label='净负荷')
    ax.step(h, X, where='mid', color=C['plan'], lw=2.0, label='计划购电量')
    ax.bar(h, E, color=C['emerg'], alpha=.7, width=.65, label='紧急购电量')
    ax.set_xlabel('时刻 / 时')
    ax.set_ylabel('小时电量 / kWh')
    ax.set_xlim(-.5, 23.5)
    ax.set_xticks(range(0, 24, 3))
    _clean(ax)
    _legend(ax, ncol=3, loc='upper right')
    _save(fig, '问题2_典型日_2025-06-21',
          pd.DataFrame({'小时': h, '负荷_kWh': L, '实际光伏_kWh': V,
                        '净负荷_kWh': np.maximum(L - V, 0),
                        '计划购电_kWh': X, '紧急购电_kWh': E}),
          data_name='典型日_2025-06-21')

    # 情景数量与历史窗口敏感性
    s = pd.read_csv(CSV_SENS)
    s['总费用_万元'] = s['总费用'] / 1e4
    base = s[s['窗口半宽'] == 25].copy()
    base['横轴标签'] = base['情景集'].map({'kmed10': 'K=10', 'kmed20': 'K=20',
                                          'full25': '窗口全部'})
    base = (base.dropna(subset=['横轴标签']).set_index('横轴标签')
            .reindex(['K=10', 'K=20', '窗口全部']).reset_index())
    wide = s[s['情景集'].isin(['kmed20', 'kmed20w120']) &
             s['窗口半宽'].isin([25, 120])].sort_values('窗口半宽')

    fig, ax = plt.subplots(1, 2, figsize=(9.0, 3.7), sharey=True,
                           gridspec_kw={'wspace': 0.12})
    x0 = np.arange(len(base))
    ax[0].plot(x0, base['总费用_万元'], color=C['plan'], marker='o', lw=2, label='全年总费用')
    ax[0].set_xticks(x0, base['横轴标签'])
    ax[0].set_xlabel('情景集规模（历史窗口 ±25 天）')
    ax[0].set_ylabel('全年总费用 / 万元')
    x1 = wide['窗口半宽'].to_numpy()
    ax[1].plot(x1, wide['总费用_万元'], color=C['emerg'], marker='o', lw=2, label='全年总费用')
    ax[1].set_xticks(x1, [f'±{int(v)} 天' for v in x1])
    ax[1].set_xlabel('历史窗口半宽（K=20）')
    for a in ax:
        _clean(a)
        a.margins(x=0.12)
    ax[0].set_title('(a) 情景数量')
    ax[1].set_title('(b) 历史窗口')
    _legend(ax[0])
    _legend(ax[1])
    _save(fig, '问题2_情景数敏感性', s[['情景数', '总费用', '相对差_%']],
          data_name='情景数敏感性')

    _soc_figure(plt)
    print(f'  [图] 共 4 张，输出目录 {FIG_Q2}')
    return FIG_Q2


def _soc_figure(plt):
    from matplotlib.ticker import FuncFormatter
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'Noto Sans SC', 'DejaVu Sans'],
        'axes.unicode_minus': False, 'font.size': 10.5, 'axes.labelsize': 10.5,
        'xtick.labelsize': 9.5, 'ytick.labelsize': 9.5, 'legend.fontsize': 9,
        'figure.dpi': 160, 'savefig.dpi': 320, 'savefig.bbox': 'tight',
        'savefig.pad_inches': 0.06, 'pdf.fonttype': 42, 'ps.fonttype': 42,
        'axes.edgecolor': '#667085', 'axes.linewidth': 0.8, 'xtick.color': '#475467',
        'ytick.color': '#475467', 'text.color': '#1D2939',
        'lines.solid_capstyle': 'round', 'lines.solid_joinstyle': 'round',
    })

    case = load_case()
    q1 = np.r_[E_INIT, solve_det(case.f1_load - case.f1_pv, case.price)['E']]
    q2 = {}
    for ds in REPORT_DAYS:
        i = case.index_of(ds)
        q2[ds] = np.r_[E_INIT, solve_day(i, case, base='P')['E']]

    for tag, soc in [('问题1', q1)] + [(f'问题2_{d}', v) for d, v in q2.items()]:
        lo, hi = float(soc.min()), float(soc.max())
        assert lo >= E_MIN - 1e-6 and hi <= E_MAX + 1e-6, f'{tag} SOC 越界：[{lo}, {hi}]'
        assert abs(soc[0] - E_INIT) < 1e-6 and abs(soc[-1] - E_INIT) < 1e-6, f'{tag} 日循环不闭合'

    x = np.arange(N + 1, dtype=float) * DT
    rows = []
    for problem, date, soc in [('问题1', '典型日', q1)] + \
            [('问题2', d, v) for d, v in q2.items()]:
        for slot, (hour, value) in enumerate(zip(x, soc)):
            rows.append({'problem': problem, 'date': date, 'slot': slot,
                         'hour': round(float(hour), 10), 'soc_kwh': float(value),
                         'soc_pct': float((value - E_MIN) / (E_MAX - E_MIN) * 100.0),
                         'within_bounds': bool(E_MIN - 1e-6 <= value <= E_MAX + 1e-6)})

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.4, 4.75), sharey=True,
                                   gridspec_kw={'wspace': 0.10})
    for ax in (ax1, ax2):
        ax.axhspan(E_MIN, E_MAX, color='#DCEFE8', alpha=0.52, zorder=0,
                   label='SOC可行域' if ax is ax1 else None)
        for y, ls in ((E_MIN, (0, (4, 3))), (E_MAX, (0, (4, 3)))):
            ax.axhline(y, color='#55A88B', lw=0.85, ls=ls, zorder=1)
        ax.axhline(E_INIT, color='#98A2B3', lw=0.8, ls=(0, (2, 3)), zorder=1)
        ax.text(23.85, E_MAX + 70, f'上限 {E_MAX:,.0f}', ha='right', va='bottom',
                color='#39816B', fontsize=8.2)
        ax.text(23.85, E_MIN - 70, f'下限 {E_MIN:,.0f}', ha='right', va='top',
                color='#39816B', fontsize=8.2)
        ax.text(23.85, E_INIT + 70, f'初始 {E_INIT:,.0f}', ha='right', va='bottom',
                color='#667085', fontsize=8.2)
        ax.set_xlim(0, 24)
        ax.set_ylim(850, 11150)
        ax.set_xticks(np.arange(0, 25, 4))
        ax.set_xticklabels([f'{h}:00' for h in range(0, 25, 4)])
        ax.set_yticks(np.arange(2000, 11001, 2000))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:,.0f}'))
        ax.set_xlabel('时刻')
        ax.grid(axis='y', color='#D0D5DD', lw=0.65, alpha=0.72)
        ax.grid(axis='x', visible=False)
        ax.set_axisbelow(True)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.tick_params(length=3, width=0.75)
    ax1.set_ylabel('SOC / 储电量（kWh）')

    def mark_bounds(ax, xs, soc, color):
        at = np.isclose(soc, E_MIN, atol=1e-6) | np.isclose(soc, E_MAX, atol=1e-6)
        if np.any(at):
            ax.scatter(xs[at], soc[at], s=16, color=color, edgecolor='white',
                       linewidth=0.55, zorder=5)

    c1 = '#6F42C1'
    ax1.plot(x, q1, color=c1, lw=2.15, marker='o', ms=2.35, markevery=12,
             label='问题1优化轨迹', zorder=4)
    mark_bounds(ax1, x, q1, c1)
    ax1.scatter([0, 24], [q1[0], q1[-1]], s=28, color=c1, edgecolor='white',
                linewidth=0.8, zorder=6)
    for xx_, txt in ((0, '起点'), (24, '终点')):
        ax1.annotate(f'{txt} {q1[xx_]:,.0f}', xy=(xx_, q1[xx_]),
                     xytext=(1.1 if xx_ == 0 else 21.0, q1[xx_] + 650), fontsize=8.5,
                     color=c1, arrowprops=dict(arrowstyle='-|>', lw=0.8, color=c1), zorder=6)
    ax1.text(0.01, 1.03, '(a)', transform=ax1.transAxes, fontsize=12,
             fontweight='bold', va='bottom')
    ax1.set_title('问题1：确定性优化', pad=10, color='#344054', fontweight='bold')

    colors = ['#0E8C8C', '#E8871E', '#2E6FB7', '#C0392B']
    for color, date in zip(colors, REPORT_DAYS):
        soc = q2[date]
        ax2.plot(x, soc, color=color, lw=1.65, marker='o', ms=1.8, markevery=12,
                 label=date, zorder=3)
        mark_bounds(ax2, x, soc, color)
    ax2.scatter([0] * len(REPORT_DAYS), [q2[d][0] for d in REPORT_DAYS], s=21,
                color=colors, edgecolor='white', linewidth=0.7, zorder=6)
    ax2.scatter([24] * len(REPORT_DAYS), [q2[d][-1] for d in REPORT_DAYS], s=21,
                color=colors, edgecolor='white', linewidth=0.7, zorder=6)
    ax2.text(0.01, 1.03, '(b)', transform=ax2.transAxes, fontsize=12,
             fontweight='bold', va='bottom')
    ax2.set_title('问题2：典型代表日优化', pad=10, color='#344054', fontweight='bold')
    ax2.legend(loc='upper center', bbox_to_anchor=(0.5, -0.18), ncol=2, frameon=False,
               handlelength=2.0, columnspacing=1.3)
    _save(fig, '问题1问题2_SOC轨迹图', rows, data_name='SOC轨迹', clear_title=False)


if __name__ == '__main__':
    utf8_console()
    REPORTS.mkdir(exist_ok=True)
    args = {a.lower() for a in sys.argv[1:]}
    if not args:
        args = {'main'}
    if 'all' in args:
        args = {'main', 'prop', 'sens', 'fig'}
    t0 = time.time()
    if 'main' in args:
        run_main()
    if 'prop' in args:
        run_prop()
    if 'sens' in args:
        run_sens()
    if 'fig' in args:
        run_figs()
    for tag in ('sens-e', 'sens-a', 'sens-d'):
        if tag in args:                       
            run_sens(parts=tag.split('-')[1].upper())
    print(f'\n全部完成，用时 {(time.time() - t0) / 60:.1f} min')
