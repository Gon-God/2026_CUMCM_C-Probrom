# -*- coding: utf-8 -*-
"""Daily schedule for the microgrid (LP formulation).

Storage SOC:  e_t = e_{t-1} + 0.9*C - D/0.9, with 1200 <= e <= 10800 and e_0 = e_144 = 6000 kWh.
Power balance (energy kWh per 10-min slot):  grid + PV*dt + D = L*dt + C + curt.

No binary variables are needed: charging and discharging in the same slot each cost
±p with no sell-back revenue and each transition loses 0.9*eta, so optimising an LP
over (C,D) with independent caps naturally keeps them mutually exclusive. Dropping the
binaries both avoids HiGHS numerical infeasibility from the 833-scale big-M and keeps
per-day solves fast (needed for the full-year run).

  - "plan": grid purchase q >= 0 is a variable; objective = sum p*q.
  - "exec": adjusted contract a is FIXED; storage re-dispatched; emergency purchase
    em >= 0 covers residual shortfall (5*p), and deviation vs qDA is settled at
    0.5*p (below) / 1.5*p (above).
"""
import numpy as np
import scipy.optimize as opt
from scipy.sparse import csr_matrix
from scipy.optimize import Bounds, LinearConstraint

from utils import C_MAX, E0, N

SOC_MAX = 10800.0
SOC_MIN = 1200.0
REL_GAP = 1e-4
TIME_LIMIT = 10.0


def solve_plan(price, pv_kw, load_kw):
    """Day-ahead plan: purchase contract q[144] and storage schedule (PV basis)."""
    p = np.asarray(price, float)
    G = np.asarray(pv_kw, float).ravel()
    L = np.asarray(load_kw, float) * (1.0 / 6.0)
    n = N
    offs = {"C": 0, "D": n, "e": 2 * n, "q": 3 * n, "r": 4 * n}
    Nvar = 5 * n
    c = np.zeros(Nvar)
    c[offs["C"]:offs["C"] + n] += p
    c[offs["D"]:offs["D"] + n] -= p
    lb = np.zeros(Nvar)
    ub = np.full(Nvar, np.inf)
    ub[offs["C"]:offs["C"] + n] = C_MAX
    ub[offs["D"]:offs["D"] + n] = C_MAX
    lb[offs["e"]:offs["e"] + n] = SOC_MIN
    ub[offs["e"]:offs["e"] + n] = SOC_MAX
    # q, r >= 0 (lb 0)
    rows, lows, ups = [], [], []

    def add(Arow, lo, up):
        rows.append(Arow); lows.append(lo); ups.append(up)

    for t in range(n):
        r = np.zeros(Nvar); r[offs["C"] + t] = 1
        add(r, -np.inf, C_MAX)
        r = np.zeros(Nvar); r[offs["D"] + t] = 1
        add(r, -np.inf, C_MAX)
    for t in range(n):                                  # SOC recursion
        r = np.zeros(Nvar)
        r[offs["e"] + t] = 1
        if t > 0:
            r[offs["e"] + t - 1] = -1
        r[offs["C"] + t] = -0.9
        r[offs["D"] + t] = 1.0 / 0.9
        rhs = E0 if t == 0 else 0.0
        add(r, rhs, rhs)
    r = np.zeros(Nvar); r[offs["e"] + n - 1] = 1       # terminal SOC = E0
    add(r, E0, E0)
    for t in range(n):                                  # balance: q - C + D - r = L - G*dt
        r = np.zeros(Nvar)
        r[offs["q"] + t] = 1
        r[offs["r"] + t] = -1
        r[offs["C"] + t] = -1
        r[offs["D"] + t] = 1
        add(r, L[t] - G[t] * (1.0 / 6.0), L[t] - G[t] * (1.0 / 6.0))
    A = csr_matrix(np.vstack(rows))
    res = opt.milp(c, integrality=np.zeros(Nvar, dtype=int), bounds=Bounds(lb, ub),
                   constraints=LinearConstraint(A, np.array(lows), np.array(ups)))
    if not res.success:
        raise RuntimeError("plan infeasible: " + res.message)
    x = res.x
    C = x[offs["C"]:offs["C"] + n]; D = x[offs["D"]:offs["D"] + n]
    e = x[offs["e"]:offs["e"] + n]; q = x[offs["q"]:offs["q"] + n]
    curt = x[offs["r"]:offs["r"] + n]
    return {"q": q, "C": C, "D": D, "e": e, "curt": curt, "cost": float((p * q).sum())}


def solve_exec(price, pv_act_kw, load_kw, a_contract, qDA):
    """Actual execution with fixed adjusted contract `a`; emergencies + deviations."""
    p = np.asarray(price, float)
    G = np.asarray(pv_act_kw, float).ravel()
    L = np.asarray(load_kw, float) * (1.0 / 6.0)
    a = np.asarray(a_contract, float).ravel()
    qDA = np.asarray(qDA, float).ravel()
    n = N
    offs = {"C": 0, "D": n, "e": 2 * n, "em": 3 * n, "r": 4 * n, "sm": 5 * n, "sp": 6 * n}
    Nvar = 7 * n
    c = np.zeros(Nvar)
    c[offs["em"]:offs["em"] + n] += 5.0 * p
    c[offs["sm"]:offs["sm"] + n] += 0.5 * p
    c[offs["sp"]:offs["sp"] + n] += 1.5 * p
    lb = np.zeros(Nvar)
    ub = np.full(Nvar, np.inf)
    ub[offs["C"]:offs["C"] + n] = C_MAX
    ub[offs["D"]:offs["D"] + n] = C_MAX
    lb[offs["e"]:offs["e"] + n] = SOC_MIN
    ub[offs["e"]:offs["e"] + n] = SOC_MAX
    rows, lows, ups = [], [], []

    def add(Arow, lo, up):
        rows.append(Arow); lows.append(lo); ups.append(up)

    for t in range(n):
        r = np.zeros(Nvar); r[offs["C"] + t] = 1
        add(r, -np.inf, C_MAX)
        r = np.zeros(Nvar); r[offs["D"] + t] = 1
        add(r, -np.inf, C_MAX)
    for t in range(n):
        r = np.zeros(Nvar)
        r[offs["e"] + t] = 1
        if t > 0:
            r[offs["e"] + t - 1] = -1
        r[offs["C"] + t] = -0.9
        r[offs["D"] + t] = 1.0 / 0.9
        rhs = E0 if t == 0 else 0.0
        add(r, rhs, rhs)
    r = np.zeros(Nvar); r[offs["e"] + n - 1] = 1
    add(r, E0, E0)
    for t in range(n):                                   # a + G*dt + D + em = L + C + r
        r = np.zeros(Nvar)
        r[offs["em"] + t] = 1
        r[offs["r"] + t] = -1
        r[offs["C"] + t] = -1
        r[offs["D"] + t] = 1
        rhs = L[t] - a[t] - G[t] * (1.0 / 6.0)
        add(r, rhs, rhs)
    for t in range(n):                                   # a - qDA = sm - sp
        r = np.zeros(Nvar)
        r[offs["sm"] + t] = 1
        r[offs["sp"] + t] = -1
        add(r, a[t] - qDA[t], a[t] - qDA[t])
    A = csr_matrix(np.vstack(rows))
    res = opt.milp(c, integrality=np.zeros(Nvar, dtype=int), bounds=Bounds(lb, ub),
                   constraints=LinearConstraint(A, np.array(lows), np.array(ups)))
    if not res.success:
        raise RuntimeError("exec infeasible: " + res.message)
    x = res.x
    C = x[offs["C"]:offs["C"] + n]; D = x[offs["D"]:offs["D"] + n]
    e = x[offs["e"]:offs["e"] + n]; em = x[offs["em"]:offs["em"] + n]
    sm = x[offs["sm"]:offs["sm"] + n]; sp = x[offs["sp"]:offs["sp"] + n]
    return {"C": C, "D": D, "e": e, "em": em, "sm": sm, "sp": sp,
            "emergency_cost": float((5.0 * p * em).sum()),
            "adj_cost": float((0.5 * p * sm).sum() + (1.5 * p * sp).sum()),
            "plan_cost": float((p * qDA).sum())}


if __name__ == "__main__":
    import utils
    p, l, v = utils.load_attachment1()
    r = solve_plan(p, v, l)
    print("P1 plan cost", round(r["cost"], 2), "curt", round(r["curt"].sum(), 2))
    both = int(((r["C"] > 1e-3) & (r["D"] > 1e-3)).sum())
    print("simultaneous C&D slots (should be ~0):", both)
    print("e min/max/end", round(r["e"].min()), round(r["e"].max()), round(r["e"][-1]))
    ex = solve_exec(p, v, l, r["q"], r["q"])
    print("P1 exec emerg cost", round(ex["emergency_cost"], 2), "em kWh", round(ex["em"].sum(), 2))
