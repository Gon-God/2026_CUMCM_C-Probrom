from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse as sp
from scipy.optimize import linprog

from 路径解析 import SRC, find_att

#参数
ROOT = SRC                     # 源代码/ 目录（不随启动时的工作目录变化）
ATT = find_att()               # 附件目录自动定位，见 路径解析.py（原先误用 ROOT.parent）

N = 144                        # 每日时段数（10 min 一段）
DT = 1.0 / 6.0                 # 单时段小时数
REL_HOURS = (0, 6, 12, 18)     # 预报发布 / 调整时刻
REL_SLOTS = {h: h * 6 for h in REL_HOURS}
REL_INDEX = {h: i for i, h in enumerate(REL_HOURS)}
Q4_START = '2025-02-01'        # 求解起点（2025-01 只作预报历史，共 334 天）
WIN = 25                       # 主口径日历窗半宽（天）
CAL_SIGMA = 25.0               # M7 日历高斯核尺度（天）

ETA = 0.9                      # 单程充放电效率
S_MAX = 5000.0 * DT            # 单时段最大充放电量 833.33 kWh
E_MIN, E_MAX, E_INIT = 1200.0, 10800.0, 6000.0
KAPPA = 5.0                    # 紧急购电倍数
BETA_UP, BETA_DN = 1.5, 0.5    # 向上 / 向下调整倍数
EPS_REG = 1e-7                 # 充放电互斥正则（使输出严格互斥）
EPS_X = 1e-6                   # 计划量唯一化正则（主口径与 microlib 同值）

PREFIX_LABEL = {(): 'S0', (6,): 'S1', (6, 12): 'S2', (6, 12, 18): 'S3'}

CALIBERS = {
    'main': dict(name='主口径（附件 3 原样）', kind='main', K_plan=20, K_adj=10,
                 kappa_plan=5.0, kappa_adj=5.0, eps_x=EPS_X, em_thresh=1.0),
    'm7': dict(name='M7 预报改进', kind='m7', K_plan=20, K_adj=20,
               kappa_plan=5.0, kappa_adj=5.0, eps_x=0.0, em_thresh=1e-6),
}
DEFAULT_CALIBER = {'42': 'main', '43': 'm7'}     


#数据层
class Q4Data:
    """附件 1/2/3/4 的统一 kWh 口径容器。"""

    def __init__(self, dates, L, V, fc, price_fix, price_rt):
        self.dates = dates        # (n,)       日期
        self.L = L                # (n,144)    负荷电量 kWh
        self.V = V                # (n,144)    实际光伏电量 kWh
        self.fc = fc              # (n,4,144)  四个发布时刻的预报电量 kWh
        self.price_fix = price_fix  # (144,)   附件 1 逐日相同电价
        self.price_rt = price_rt    # (n,144)  附件 4 实时电价

    @property
    def n(self) -> int:
        return len(self.dates)

    def solve_rows(self, start: str = Q4_START) -> np.ndarray:
        return np.where(self.dates >= pd.Timestamp(start))[0]


def build_forecast(marks: np.ndarray) -> np.ndarray:
    """附件 3 整点预报 (n,4,24) kW → (n,4,144) 逐 10 分钟电量 kWh（分段常数）。"""
    out = np.zeros((marks.shape[0], 4, N))
    for r in REL_HOURS:
        ri = REL_INDEX[r]
        v = marks[:, ri, :]
        for h in range(r, 24):
            out[:, ri, h * 6:h * 6 + 6] = np.repeat(v[:, h - r][:, None], 6, axis=1) * DT
    return out


def load_data(att: Path | str = ATT) -> Q4Data:
    """读取附件 1（电价）/ 2（负荷与实际光伏）/ 3（预报）/ 4（实时电价）。"""
    att = Path(att)
    f1 = pd.read_excel(att / '附件1.xlsx')
    price_fix = f1['电价'].to_numpy(float)[:N]

    d2 = pd.read_excel(att / '附件2.xlsx', sheet_name='小区负载')
    p2 = pd.read_excel(att / '附件2.xlsx', sheet_name='光伏发电实际功率')
    dates = pd.DatetimeIndex(pd.to_datetime(d2.iloc[:, 0]).dt.normalize())
    L = d2.iloc[:, 1:1 + N].to_numpy(float) * DT
    V = p2.iloc[:, 1:1 + N].to_numpy(float) * DT

    raw = pd.read_excel(att / '附件3.xlsx')
    dcol = pd.to_datetime(raw['日期']).ffill()
    tcol = raw['预报时刻'].astype(str).str.strip()
    vals = raw.iloc[:, 2:2 + 24].to_numpy(float)
    days = pd.DatetimeIndex(sorted(pd.DatetimeIndex(dcol).normalize().unique()))
    marks = np.full((len(days), 4, 24), np.nan)
    for k in range(len(raw)):
        d = int(days.get_loc(pd.Timestamp(dcol.iloc[k]).normalize()))
        marks[d, REL_INDEX[int(tcol.iloc[k].split(':')[0])], :] = vals[k]
    assert not np.isnan(marks).any(), '附件 3 存在未对齐的发布时刻'
    assert (days == dates).all(), '附件 2 与附件 3 的日期序列不一致'

    d4 = pd.read_excel(att / '附件4.xlsx')
    price_rt = d4.iloc[:, 1:1 + N].to_numpy(float)
    assert price_rt.shape == (len(dates), N) and L.shape == V.shape == (len(dates), N)
    return Q4Data(dates, L, V, build_forecast(marks), price_fix, price_rt)


#情景层
def cal_window(d: int, doy: np.ndarray, half: int = WIN) -> np.ndarray:
    """第 d 日**之前**、日历 ±half 天内的历史日（跨年环绕，严格 h < d）。"""
    hist = np.arange(d)
    if len(hist) == 0:
        return hist
    diff = np.abs(doy[hist] - doy[d])
    diff = np.minimum(diff, 365 - diff)
    sel = hist[diff <= half]
    if len(sel) < 8:                      # 年初样本不足时放宽到 ±60 天
        sel = hist[diff <= max(60, half)]
    return sel


def kmedoids(X: np.ndarray, K: int, iters: int = 30):
    """几何距离 K-medoids，权重 = 簇占比（与问题二/三主口径同构）。"""
    X = np.asarray(X, float)
    n = len(X)
    if n <= K:
        return X.copy(), np.full(n, 1.0 / n)
    Dm = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).sum(-1))
    order = np.argsort(X.sum(1))
    med = sorted(set(order[np.linspace(0, n - 1, K).round().astype(int)].tolist()))
    for _ in range(iters):
        assign = Dm[:, med].argmin(1)
        new = []
        for k in range(len(med)):
            mem = np.where(assign == k)[0]
            new.append(int(mem[Dm[np.ix_(mem, mem)].sum(1).argmin()]) if len(mem) else med[k])
        new = sorted(set(new))
        if new == med:
            break
        med = new
    assign = Dm[:, med].argmin(1)
    w = np.array([(assign == k).sum() for k in range(len(med))], float)
    w = np.where(w > 0, w, 1.0)
    return X[med].copy(), w / w.sum()


def scen_main(data: Q4Data, doy: np.ndarray, d: int, rel: int, K: int,
              half: int = WIN):
    """主口径情景：当日预报 + 历史加性残差（硬日历窗 + K-medoids 削减）。"""
    s0, ri = REL_SLOTS[rel], REL_INDEX[rel]
    sel = cal_window(d, doy, half)
    if len(sel) == 0:
        sel = np.arange(max(d, 1))
    R = data.V[sel][:, s0:] - data.fc[sel, ri, s0:]
    e, w = kmedoids(R, K)
    return data.fc[d, ri, s0:][None, :] + e, w


#情景层
class M7Engine:
    """M7：因果收缩混合 + 同估计量条件残差池 + 电价加权缩减。

    预计算（只做一次）：C（气候法中心）、w（Kalman 增益）、V̂ = C + w(F − C)、
    同估计量残差 R = V − V̂。情景 = V̂ + 条件加权残差池的代表，再削减到 K 个。
    """

    def __init__(self, data: Q4Data, sigma: float = CAL_SIGMA, trail: int = 60,
                 min_train: int = 15, pool_max: int = 40, wx_beta: float = 1.0,
                 online_beta: float = 1.0, gate_frac: float = 0.05,
                 g_max: float = 0.5, eps_kwh: float = 5.0, mask_kwh: float = 1.0):
        self.data, self.sigma = data, sigma
        self.trail, self.min_train, self.pool_max = trail, min_train, pool_max
        self.wx_beta, self.online_beta = wx_beta, online_beta
        self.gate_frac, self.g_max = gate_frac, g_max
        self.eps_kwh, self.mask_kwh = eps_kwh, mask_kwh
        n = data.n
        self.C = {r: np.zeros((n, N - REL_SLOTS[r])) for r in REL_HOURS}
        self.w = {r: np.zeros(n) for r in REL_HOURS}
        self.Vhat = {r: np.zeros((n, N - REL_SLOTS[r])) for r in REL_HOURS}
        self.R = {r: np.zeros((n, N - REL_SLOTS[r])) for r in REL_HOURS}
        for r in REL_HOURS:
            s0, ri = REL_SLOTS[r], REL_INDEX[r]
            for h in range(n):
                self.C[r][h] = self._clim(h, s0)
                w = self._blend_w(r, h)
                self.w[r][h] = w
                self.Vhat[r][h] = self.C[r][h] + w * (data.fc[h, ri, s0:] - self.C[r][h])
                self.R[r][h] = data.V[h, s0:] - self.Vhat[r][h]

    #因果日历核
    def _pool(self, d: int):
        hist = np.arange(d)
        if len(hist) == 0:
            return hist, np.zeros(0)
        doy = self.data.dates.dayofyear.to_numpy()
        diff = np.abs(doy[hist] - doy[d])
        diff = np.minimum(diff, 365 - diff)
        m = diff <= 3.0 * self.sigma
        if int(m.sum()) < 10:                     # 年初样本太少时放宽
            m = diff <= 60
        return hist[m], np.exp(-0.5 * (diff[m] / self.sigma) ** 2)

    def _clim(self, d: int, s0: int) -> np.ndarray:
        idx, w = self._pool(d)
        if len(idx) == 0:
            return np.zeros(N - s0)
        return (w[:, None] * self.data.V[idx][:, s0:]).sum(0) / w.sum()

    def _blend_w(self, r: int, d: int) -> float:
        """因果 OLS 增益 w = Σ(F−C)(V−C) / Σ(F−C)²，截断到 [0,1]。"""
        ph = [h for h in range(max(self.min_train, d - self.trail), d)
              if h >= self.min_train]
        if len(ph) < self.min_train:
            return 0.0
        s0, ri = REL_SLOTS[r], REL_INDEX[r]
        Fp = self.data.fc[ph, ri, s0:]
        Cp = self.C[r][ph]
        Vp = self.data.V[ph, s0:]
        mk = (Vp > self.mask_kwh) | (Fp > self.mask_kwh)
        num = float(((Fp - Cp)[mk] * (Vp - Cp)[mk]).sum())
        den = float(((Fp - Cp)[mk] ** 2).sum())
        return 0.0 if den <= 0 else float(np.clip(num / den, 0.0, 1.0))

    #在线同化：当日已实现窗口的实际/预报对数比
    def _logratio(self, i: int, r: int) -> float:
        ri = REL_INDEX[r]
        if ri == 0:
            return 0.0
        s0, s1 = REL_SLOTS[REL_HOURS[ri - 1]], REL_SLOTS[r]
        a = float(self.data.V[i, s0:s1].sum())
        b = float(self.data.fc[i, REL_INDEX[REL_HOURS[ri - 1]], s0:s1].sum())
        if b < max(200.0, self.gate_frac * float(self.data.fc[i, 0].sum())):
            return 0.0                     # 日出前窗口没有信息
        return float(np.clip(np.log((a + self.eps_kwh) / (b + self.eps_kwh)),
                             -self.g_max, self.g_max))

    #情景构造
    def scenarios(self, d: int, r: int, K: int):
        s0, ri = REL_SLOTS[r], REL_INDEX[r]
        F = self.data.fc[d, ri, s0:]
        price = self.data.price_rt[d, s0:]
        center = self.C[r][d] + self.w[r][d] * (F - self.C[r][d])
        idx, wts = self._pool(d)
        if len(idx) == 0:
            return center[None, :].copy(), np.array([1.0])
        Rpool = self.R[r][idx]
        wts = np.asarray(wts, float).copy()

        #天气型核
        tot_h = np.log1p(self.data.fc[idx, ri, s0:].sum(1))
        sd = float(np.std(tot_h))
        if sd > 1e-6:
            wts = wts * np.exp(-0.5 * self.wx_beta
                               * ((tot_h - float(np.log1p(F.sum()))) / sd) ** 2)
        #在线核
        if r > 0:
            gs = np.array([self._logratio(int(i), r) for i in idx])
            g_obs = self._logratio(d, r)
            sd = float(np.std(gs))
            if g_obs != 0.0 and sd > 1e-9:
                wts = wts * np.exp(-0.5 * self.online_beta * ((gs - g_obs) / sd) ** 2)
        s = float(wts.sum())
        if not np.isfinite(s) or s <= 0:
            wts, s = np.ones(len(idx)), float(len(idx))
        wts = wts / s

        if len(idx) > self.pool_max:      # 池上限
            keep = np.argsort(-wts)[:self.pool_max]
            Rpool, wts = Rpool[keep], wts[keep]
            wts = wts / wts.sum()

        sc = np.maximum(center[None, :] + Rpool, 0.0)
        k = max(1, min(K, len(sc)))
        if k == 1:
            return sc[:1].copy(), np.array([1.0])
        return self._reduce(sc, wts, k, price)

    def _reduce(self, X: np.ndarray, w: np.ndarray, K: int, price: np.ndarray):
        """电价加权距离的加权 K-medoids（论文 M7 的决策导向缩减）。"""
        X, w = np.asarray(X, float), np.asarray(w, float)
        w = w / w.sum()
        n = len(X)
        if n <= K:
            return X.copy(), np.full(n, 1.0 / n)
        sl = price / price.mean()
        diff = X[:, None, :] - X[None, :, :]
        D = np.sqrt(((diff * np.sqrt(sl)[None, None, :]) ** 2).sum(-1))
        order = np.argsort(X.sum(1))
        med = self._pad(sorted(set(int(order[i]) for i in
                                   np.linspace(0, n - 1, K).round().astype(int))), K, order)
        for _ in range(20):
            asg = D[:, med].argmin(1)
            new = []
            for k in range(len(med)):
                mem = np.where(asg == k)[0]
                new.append(med[k] if len(mem) == 0 else
                           int(mem[int((D[np.ix_(mem, mem)] * w[mem][None, :]).sum(1).argmin())]))
            new = self._pad(sorted(set(new)), K, order)
            if new == med:
                break
            med = new
        asg = D[:, med].argmin(1)
        p = np.array([w[asg == k].sum() for k in range(len(med))], float)
        p = np.where(p > 0, p, 1e-12)
        return X[med].copy(), p / p.sum()

    @staticmethod
    def _pad(med, K, order):
        if len(med) >= K:
            return sorted(med)[:K]
        out = list(med)
        for j in order:
            if len(out) >= K:
                break
            if int(j) not in out:
                out.append(int(j))
        return sorted(out)


def get_scen(data: Q4Data, eng, doy: np.ndarray, d: int, rel: int, K: int, cal: dict):
    """按口径取情景集（main 用硬窗 K-medoids，m7 用预报引擎）。"""
    if cal['kind'] == 'main':
        return scen_main(data, doy, d, rel, K)
    return eng.scenarios(d, rel, K)


#优化层（LP）
def _solve(c, A_ub, b_ub, A_eq, b_eq, bounds):
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds,
                  method='highs')
    if not res.success:
        raise RuntimeError(f'LP 求解失败：{res.message}')
    return res


def solve_plan(L, price, scen, probs, E0=E_INIT, E_term=E_INIT, kappa=KAPPA,
               eps=EPS_REG, eps_x=0.0):
    """0:00 计划层两阶段随机 LP。列序：x(T)|C(T)|D(T)|E(T)|b(M,T)。"""
    M, T = scen.shape
    nC, nD, nE, nB = T, 2 * T, 3 * T, 4 * T
    n = nB + M * T

    c = np.zeros(n)
    c[:T] = price + eps_x                       # 计划购电费（+ 唯一化正则）
    for w in range(M):
        c[nB + w * T:nB + (w + 1) * T] = probs[w] * kappa * price
    c[nC:nC + T] = eps                          # 充放电互斥正则
    c[nD:nD + T] = eps

    rows, cols, vals, rhs, nrow = [], [], [], [], 0
    for t in range(T):                          # SOC 递推（等式）
        rows += [nrow] * 3
        cols += [nE + t, nC + t, nD + t]
        vals += [1.0, -ETA, 1.0 / ETA]
        if t > 0:
            rows.append(nrow)
            cols.append(nE + t - 1)
            vals.append(-1.0)
        rhs.append(E0 if t == 0 else 0.0)
        nrow += 1
    if E_term is not None:                      # 日循环
        rows += [nrow]
        cols += [nE + T - 1]
        vals += [1.0]
        rhs.append(E_term)
        nrow += 1
    A_eq = sp.csr_matrix((vals, (rows, cols)), shape=(nrow, n))
    b_eq = np.array(rhs)

    rows, cols, vals, rhs, nrow = [], [], [], [], 0
    for w in range(M):                          # x + V + D − C + b ≥ L
        base = nB + w * T
        for t in range(T):
            rows += [nrow] * 4
            cols += [t, nD + t, nC + t, base + t]
            vals += [-1.0, -1.0, 1.0, -1.0]
            rhs.append(scen[w, t] - L[t])
            nrow += 1
    A_ub = sp.csr_matrix((vals, (rows, cols)), shape=(nrow, n))
    b_ub = np.array(rhs)

    bounds = ([(0, None)] * T + [(0, S_MAX)] * T + [(0, S_MAX)] * T
              + [(E_MIN, E_MAX)] * T + [(0, None)] * (M * T))
    v = _solve(c, A_ub, b_ub, A_eq, b_eq, bounds).x
    return dict(x=np.maximum(v[:T], 0.0), C=v[nC:nC + T], D=v[nD:nD + T],
                E=v[nE:nE + T])


def solve_adjust(L, price, x_old, scen, probs, E_start, E_term=E_INIT, kappa=KAPPA,
                 beta_up=BETA_UP, beta_dn=BETA_DN, eps=EPS_REG, eps_x=0.0):
    """调整层增量 LP（只覆盖剩余时段）。列序：X(T)|C(T)|D(T)|E(T)|u(T)|v(T)|α(M,T)。"""
    M, T = scen.shape
    nX, nC, nD, nE, nU, nV, nA = 0, T, 2 * T, 3 * T, 4 * T, 5 * T, 6 * T
    n = nA + M * T

    c = np.zeros(n)
    c[nU:nU + T] = beta_up * price
    c[nV:nV + T] = beta_dn * price
    for w in range(M):
        c[nA + w * T:nA + (w + 1) * T] = probs[w] * kappa * price
    if eps_x:
        c[nX:nX + T] += eps_x
    c[nC:nC + T] = eps
    c[nD:nD + T] = eps

    rows, cols, vals, rhs, nrow = [], [], [], [], 0
    for t in range(T):                          # X − u + v = x_old
        rows += [nrow] * 3
        cols += [nX + t, nU + t, nV + t]
        vals += [1.0, -1.0, 1.0]
        rhs.append(x_old[t])
        nrow += 1
    for t in range(T):                          # SOC 递推
        rows += [nrow] * 3
        cols += [nE + t, nC + t, nD + t]
        vals += [1.0, -ETA, 1.0 / ETA]
        if t > 0:
            rows.append(nrow)
            cols.append(nE + t - 1)
            vals.append(-1.0)
        rhs.append(E_start if t == 0 else 0.0)
        nrow += 1
    if E_term is not None:
        rows += [nrow]
        cols += [nE + T - 1]
        vals += [1.0]
        rhs.append(E_term)
        nrow += 1
    A_eq = sp.csr_matrix((vals, (rows, cols)), shape=(nrow, n))
    b_eq = np.array(rhs)

    rows, cols, vals, rhs, nrow = [], [], [], [], 0
    for w in range(M):                          # X + V + D − C + α ≥ L
        base = nA + w * T
        for t in range(T):
            rows += [nrow] * 4
            cols += [nX + t, nD + t, nC + t, base + t]
            vals += [-1.0, -1.0, 1.0, -1.0]
            rhs.append(scen[w, t] - L[t])
            nrow += 1
    A_ub = sp.csr_matrix((vals, (rows, cols)), shape=(nrow, n))
    b_ub = np.array(rhs)

    bounds = ([(0, None)] * T + [(0, S_MAX)] * T + [(0, S_MAX)] * T
              + [(E_MIN, E_MAX)] * T + [(0, None)] * T + [(0, None)] * T
              + [(0, None)] * (M * T))
    v = _solve(c, A_ub, b_ub, A_eq, b_eq, bounds).x
    u = np.maximum(v[nU:nU + T], 0.0)
    dn = np.maximum(v[nV:nV + T], 0.0)
    return dict(x=np.maximum(v[nX:nX + T], 0.0), C=v[nC:nC + T], D=v[nD:nD + T],
                E=v[nE:nE + T], u=u, v=dn,
                adj_fee=float((beta_up * price * u).sum() + (beta_dn * price * dn).sum()))


def settle_day(L, V, price, x, X, C, D, adj_events=None, kappa=KAPPA, E0=E_INIT):
    """用实际光伏回代结算：计划购电费 + 调整费 + 紧急购电费。"""
    deficit = np.maximum(L + C - X - D - V, 0.0)
    adj_fee = adj_up = adj_dn = 0.0
    for s0, up, dn in (adj_events or []):
        p = price[s0:]
        adj_fee += float((BETA_UP * p * up).sum() + (BETA_DN * p * dn).sum())
        adj_up += float(up.sum())
        adj_dn += float(dn.sum())
    E = np.cumsum(ETA * C - D / ETA) + E0
    return dict(plan_kwh=float(x.sum()), plan_fee=float((price * x).sum()),
                deliv_kwh=float(X.sum()), adj_fee=adj_fee, adj_up=adj_up,
                adj_dn=adj_dn, em_kwh=float(deficit.sum()),
                em_fee=float(kappa * (price * deficit).sum()),
                curt_kwh=float(np.maximum(X + D + V - L - C, 0.0).sum()),
                total=float((price * x).sum()) + adj_fee
                + float(kappa * (price * deficit).sum()),
                E=E, E_end=float(E[-1]), deficit=deficit)


def merge_intervals(mask: np.ndarray, thresh: float = 1e-6) -> list:
    """把逐 10 分钟缺额掩码合并成 [(起始时段, 结束时段, 电量)]，供结果表填写。"""
    out, t, T = [], 0, len(mask)
    on = mask > thresh
    while t < T:
        if not on[t]:
            t += 1
            continue
        s = t
        while t < T and on[t]:
            t += 1
        out.append((s, t, float(mask[s:t].sum())))
    return out


def slot_label(t: int) -> str:
    return f'{t // 6}:{(t % 6) * 10:02d}'


#单日/全年推演
def solve_day(data: Q4Data, eng, doy, d: int, price, cal: dict, adjust: bool = True):
    """单日推演：计划层 + 6:00/12:00/18:00 依次滚动调整，前缀缓存给出 S0~S3。"""
    L, V = data.L[d], data.V[d]
    e0, w0 = get_scen(data, eng, doy, d, 0, cal['K_plan'], cal)
    plan = solve_plan(L, price, e0, w0, E0=E_INIT, E_term=E_INIT,
                      kappa=cal['kappa_plan'], eps_x=cal['eps_x'])
    states = {(): dict(X=plan['x'].copy(), C=plan['C'].copy(), D=plan['D'].copy(),
                       events=[])}
    X, C, D = plan['x'].copy(), plan['C'].copy(), plan['D'].copy()
    events, prev = [], ()
    if adjust:
        for k in (6, 12, 18):
            s0 = REL_SLOTS[k]
            Ecur = E_INIT + float(np.sum(ETA * C[:s0] - D[:s0] / ETA))
            ek, wk = get_scen(data, eng, doy, d, k, cal['K_adj'], cal)
            ra = solve_adjust(L[s0:], price[s0:], X[s0:], ek, wk, Ecur,
                              E_term=E_INIT, kappa=cal['kappa_adj'], eps_x=cal['eps_x'])
            X, C, D = X.copy(), C.copy(), D.copy()
            X[s0:], C[s0:], D[s0:] = ra['x'], ra['C'], ra['D']
            events = events + [(s0, ra['u'], ra['v'])]
            prev = prev + (k,)
            states[prev] = dict(X=X.copy(), C=C.copy(), D=D.copy(), events=list(events))
    settle = {pre: settle_day(L, V, price, plan['x'], st['X'], st['C'], st['D'],
                              st['events'] if pre else None, kappa=KAPPA, E0=E_INIT)
              for pre, st in states.items()}
    return dict(plan=plan, states=states, settle=settle)


def run_case(data: Q4Data, eng, rows, price_of, cal: dict, name: str,
             adjust: bool = True, keep_detail: bool = False, progress: int = 50):
    """全年逐日推演，返回逐日表 + 汇总表（+ 明细）。"""
    doy = np.asarray(data.dates.dayofyear, float)
    recs, detail = [], {}
    t0 = time.time()
    for i, d in enumerate(rows, 1):
        d = int(d)
        price = price_of(d)
        r = solve_day(data, eng, doy, d, price, cal, adjust=adjust)
        rec = dict(案例=name, 日期=data.dates[d])
        for pre, st in r['settle'].items():
            lab = PREFIX_LABEL[pre]
            rec.update({f'{lab}_计划购电量': st['plan_kwh'], f'{lab}_计划购电费': st['plan_fee'],
                        f'{lab}_交付购电量': st['deliv_kwh'], f'{lab}_调整费': st['adj_fee'],
                        f'{lab}_向上调整量': st['adj_up'], f'{lab}_向下调整量': st['adj_dn'],
                        f'{lab}_紧急购电量': st['em_kwh'], f'{lab}_紧急购电费': st['em_fee'],
                        f'{lab}_弃电量': st['curt_kwh'], f'{lab}_总费用': st['total']})
        recs.append(rec)
        if keep_detail:
            detail[data.dates[d]] = dict(
                price=price, x=r['plan']['x'],
                states={pre: dict(X=st['X'], C=st['C'], D=st['D'],
                                  E=r['settle'][pre]['E'],
                                  deficit=r['settle'][pre]['deficit'])
                        for pre, st in r['states'].items()})
        if progress and i % progress == 0:
            el = time.time() - t0
            print(f'    [{name}] {i}/{len(rows)} 天，累计 {el:.0f} s，'
                  f'预计剩余 {el / i * (len(rows) - i) / 60:.1f} min', flush=True)
    daily = pd.DataFrame(recs)
    return daily, summarize(daily), detail


def summarize(daily: pd.DataFrame) -> pd.DataFrame:
    """逐日表 → 全年汇总（S0~S3 各一行）。"""
    rows = []
    for lab in ('S0', 'S1', 'S2', 'S3'):
        if f'{lab}_总费用' not in daily.columns:
            continue
        rows.append(dict(方案=lab, 天数=len(daily),
                         计划购电量=daily[f'{lab}_计划购电量'].sum(),
                         计划购电费=daily[f'{lab}_计划购电费'].sum(),
                         交付购电量=daily[f'{lab}_交付购电量'].sum(),
                         调整费=daily[f'{lab}_调整费'].sum(),
                         向上调整量=daily[f'{lab}_向上调整量'].sum(),
                         向下调整量=daily[f'{lab}_向下调整量'].sum(),
                         紧急购电量=daily[f'{lab}_紧急购电量'].sum(),
                         紧急购电费=daily[f'{lab}_紧急购电费'].sum(),
                         弃电量=daily[f'{lab}_弃电量'].sum(),
                         总费用=daily[f'{lab}_总费用'].sum()))
    return pd.DataFrame(rows)


def paper_table(s42: pd.DataFrame, s43: pd.DataFrame) -> pd.DataFrame:
    """论文表：问题四-2 与问题四-3 的全年结果对照。"""
    a, b = s42[s42.方案 == 'S0'].iloc[0], s43[s43.方案 == 'S3'].iloc[0]
    rows = [('计划购电量/kWh', a.计划购电量, b.计划购电量),
            ('计划购电费/元', a.计划购电费, b.计划购电费),
            ('调整后交付购电量/kWh', a.交付购电量, b.交付购电量),
            ('向上调整量/kWh', a.向上调整量, b.向上调整量),
            ('向下调整量/kWh', a.向下调整量, b.向下调整量),
            ('调整相关费用/元', a.调整费, b.调整费),
            ('紧急购电量/kWh', a.紧急购电量, b.紧急购电量),
            ('紧急购电费/元', a.紧急购电费, b.紧急购电费),
            ('弃电量/kWh', a.弃电量, b.弃电量),
            ('全年总费用/元', a.总费用, b.总费用)]
    return pd.DataFrame(rows, columns=['指标', '问题四-2（0:00 计划、无调整）',
                                       '问题四-3（0:00 计划、三次调整）'])


def _interval_labels():
    lab = []
    for t in range(N):
        a = f'{t // 6}:{(t % 6) * 10:02d}'
        b = f'{(t + 1) // 6}:{((t + 1) % 6) * 10:02d}'
        lab.append(f'{a}-{"0:00+1" if t == N - 1 else b}')
    return lab


SEGMENTS = ['0:00-4:00', '4:00-8:00', '8:00-12:00', '12:00-16:00', '16:00-20:00',
            '20:00-24:00']


def write_result(path: Path, daily: pd.DataFrame, detail: dict, with_adjust: bool,
                 thresh: float = 1.0) -> None:
    """写出 result4-2.xlsx / result4-3.xlsx（附件 5 模板的工作表与列序）。

    with_adjust=False 用 0:00 计划轨迹（问题四-2），True 用 6/12/18 调整后轨迹（问题四-3）。
    """
    pre = (6, 12, 18) if with_adjust else ()
    dates = [pd.Timestamp(x) for x in daily['日期']]
    cols = ['日期\\时间'] + _interval_labels() + ['全天购电量', '全天购电费']
    plan_rows, adj_rows, sto_rows, em_rows = [], [], [], []
    for dt in dates:
        s, st = detail[dt], detail[dt]['states'][pre]
        x, price = s['x'], s['price']
        plan_rows.append([dt] + [float(v) for v in x]
                         + [float(x.sum()), float((price * x).sum())])
        if with_adjust:
            X = st['X']
            adj_rows.append([dt] + [float(v) for v in X]
                            + [float(X.sum()), float((price * X).sum())])
        for i, sg in enumerate(SEGMENTS):
            a, b = i * 24, (i + 1) * 24
            sto_rows.append([dt if i == 0 else None, sg, float(st['C'][a:b].sum()),
                             float(st['D'][a:b].sum()),
                             '0:00' if i == 0 else ('24:00' if i == 5 else None),
                             float(E_INIT) if i == 0 else
                             (float(st['E'][-1]) if i == 5 else None)])
        segs = merge_intervals(st['deficit'], thresh)
        if not segs:
            em_rows.append([dt, None, None])
        else:
            for k, (a, b, kwh) in enumerate(segs):
                nm = slot_label(b) if b < N else '24:00'
                em_rows.append([dt if k == 0 else None, f'{slot_label(a)}-{nm}', float(kwh)])
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine='openpyxl') as w:
        pd.DataFrame(plan_rows, columns=cols).to_excel(w, sheet_name='计划购电量', index=False)
        if with_adjust:
            pd.DataFrame(adj_rows, columns=cols).to_excel(w, sheet_name='调整购电量', index=False)
        pd.DataFrame(sto_rows, columns=['日期', '时间段', '充电量', '放电量', '时刻', '储电量']
                     ).to_excel(w, sheet_name='充放电量', index=False)
        pd.DataFrame(em_rows, columns=['日期', '购电时间段', '购电量']
                     ).to_excel(w, sheet_name='紧急购电量', index=False)
    print(f'[已写出] {path.name}（{"含调整" if with_adjust else "无调整"}，'
          f'{len(dates)} 天）', flush=True)


#主流程
def _utf8_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass


def main():
    ap = argparse.ArgumentParser(description='问题四：波动电价下的微网购电策略')
    ap.add_argument('--task', default='both', choices=('42', '43', 'both'),
                    help='42=问题四-2（主口径），43=问题四-3（M7），both=两个都跑')
    ap.add_argument('--caliber', default='', choices=('', 'main', 'm7'),
                    help='情景口径，默认 42→main、43→m7（论文口径）')
    ap.add_argument('--kappa-plan', type=float, default=None, help='计划层 κ（默认按口径 5）')
    ap.add_argument('--fixed', action='store_true', help='追加附件 1 固定电价两组（2×2 交互对照）')
    ap.add_argument('--days', type=int, default=0, help='抽样天数（0 = 全年 334 天，抽样时写结果文件）')
    ap.add_argument('--no-write', action='store_true', help='不写 result4-x.xlsx')
    a = ap.parse_args()
    _utf8_console()

    t0 = time.time()
    print('[读取] 附件 1/2/3/4 ……', flush=True)
    data = load_data()
    rows = data.solve_rows()
    if a.days:
        step = max(1, len(rows) // a.days)
        rows = rows[::step][:a.days]
    print(f'[范围] {len(rows)} 天（{data.dates[rows[0]].date()} ~ {data.dates[rows[-1]].date()}）')

    tasks = ('42', '43') if a.task == 'both' else (a.task,)
    cals = {t: (a.caliber or DEFAULT_CALIBER[t]) for t in tasks}
    need_m7 = any(cals[t] == 'm7' for t in tasks)
    eng = None
    if need_m7:
        print('[预计算] M7 预报引擎（气候中心 + 因果混合权重 + 同估计量残差池）……', flush=True)
        eng = M7Engine(data)

    results, summary_txt = {}, {}
    for t in tasks:
        cal = dict(CALIBERS[cals[t]])
        if a.kappa_plan is not None:
            cal['kappa_plan'] = a.kappa_plan
        name = f'问题四-{t[0]}-{t[1]}｜{cal["name"]}'
        print(f'\n=== {name}｜κ_plan={cal["kappa_plan"]:g}｜K={cal["K_plan"]}/{cal["K_adj"]}'
              f'｜附件 4 实时电价 ===', flush=True)
        daily, summ, detail = run_case(data, eng, rows, lambda d: data.price_rt[d], cal,
                                       name, adjust=True, keep_detail=not a.no_write)
        results[t] = dict(daily=daily, summ=summ, detail=detail, cal=cal, caliber=cals[t])
        summary_txt[t] = summ
        print(summ.to_string(index=False, float_format=lambda v: f'{v:,.2f}'), flush=True)
        if not a.no_write:
            suffix = '' if cals[t] == DEFAULT_CALIBER[t] else f'_{cals[t]}'
            write_result(ROOT / f'result4-{t[1]}{suffix}.xlsx', daily, detail,
                         with_adjust=(t == '43'), thresh=cal['em_thresh'])

    #论文表：4-2与4-3
    if a.task == 'both':
        tab = paper_table(summary_txt['42'], summary_txt['43'])
        print('\n===== 论文表：波动电价下问题四-2 与问题四-3 的全年结果 =====')
        print(tab.to_string(index=False, float_format=lambda v: f'{v:,.2f}'), flush=True)
        if not a.no_write:
            tab.to_csv(ROOT / '问题四_全年结果.csv', index=False, encoding='utf-8-sig')

    #逐日结果表
    if not a.no_write:
        pd.concat([results[t]['daily'] for t in tasks], ignore_index=True).to_csv(
            ROOT / '问题四_逐日结果.csv', index=False, encoding='utf-8-sig')

    #2×2 交互对照：价格机制×运行机制
    if a.fixed:
        cells = {}
        for t in tasks:
            base = results[t]
            cells[(base['caliber'], 'rt')] = base['summ']
            print(f'\n=== {base["cal"]["name"]}｜附件 1 固定电价 ===', flush=True)
            cells[(base['caliber'], 'fix')] = run_case(
                data, eng, rows, lambda d: data.price_fix, base['cal'], 'fixed',
                adjust=True, progress=0)[1]
        for cb in ('main', 'm7'):
            if (cb, 'rt') not in cells:
                continue
            f0 = float(cells[(cb, 'fix')].query('方案 == "S0"').总费用.iloc[0])
            f1 = float(cells[(cb, 'fix')].query('方案 == "S3"').总费用.iloc[0])
            r0 = float(cells[(cb, 'rt')].query('方案 == "S0"').总费用.iloc[0])
            r1 = float(cells[(cb, 'rt')].query('方案 == "S3"').总费用.iloc[0])
            print(f'\n===== 交互对照（{cb} 口径，单位：万元）=====')
            print(pd.DataFrame([
                dict(价格机制='固定电价（附件 1）', 无调整费用=f0 / 1e4, 有调整费用=f1 / 1e4,
                     调整节省=(f0 - f1) / 1e4),
                dict(价格机制='实时电价（附件 4）', 无调整费用=r0 / 1e4, 有调整费用=r1 / 1e4,
                     调整节省=(r0 - r1) / 1e4)]
            ).to_string(index=False, float_format=lambda v: f'{v:,.3f}'))
            rat = (f'{(r0 - r1) / (f0 - f1) * 100:,.2f}%' if abs(f0 - f1) > 1.0 else '—')
            print(f'  交互增益 ΔI = (R0−R1) − (F0−F1) = {(r0 - r1) - (f0 - f1):,.2f} 元；'
                  f'实时电价下的调整节省为固定电价下的 {rat}')
        print('\n注：论文 2×2 表中固定电价两格（1 391.801 / 1 366.045 万元）取自问题二、问题三的'
              '代码；上表给出的是同一套情景口径下的固定电价对照值。')

    print(f'\n[总用时] {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
