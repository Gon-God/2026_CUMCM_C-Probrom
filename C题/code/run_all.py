# -*- coding: utf-8 -*-
"""Run all four problems, fill Attachment-5 templates with results, write summary.json."""
import os, sys, json
from datetime import datetime
import numpy as np
import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import utils
from milp_core import solve_plan, solve_exec

ROOT = utils.ROOT
TEMPLATES = os.path.join(ROOT, "附件", "附件5")
OUTDIR = os.path.join(ROOT, "results")
os.makedirs(OUTDIR, exist_ok=True)

SEG = ["0:00-4:00", "4:00-8:00", "8:00-12:00", "12:00-16:00", "16:00-20:00", "20:00-24:00"]
N = 144

def slot_lbl(t):
    def hh(x):
        h = int(x); m = int(round((x - h) * 60))
        if m == 60:
            h += 1; m = 0
        return f"{h}:{m:02d}"
    return hh(t / 6.0) + "-" + hh((t + 1) / 6.0)

def latest_pv_grid(fc3, date):
    grid = np.zeros(N)
    hours = np.arange(1, N + 1) / 6.0
    for rel in (0, 6, 12, 18):
        nxt = rel + 6 if rel < 18 else 24
        mask = (hours >= rel) & (hours < nxt)
        if mask.any():
            fc = fc3.get((date, rel))
            grid[mask] = utils.fc_to_grid(fc, rel)[mask] if fc is not None else 0.0
    return grid

def solve_one_day(fc3, date, load_act, pv_act, price, with_adj=True):
    fc0 = fc3.get((date, 0))
    pv_plan = utils.fc_to_grid(fc0, 0) if fc0 is not None else np.zeros(N)
    plan = solve_plan(price, pv_plan, load_act)
    qDA = plan["q"]
    if with_adj:
        a = solve_plan(price, latest_pv_grid(fc3, date), load_act)["q"]
    else:
        a = qDA.copy()
    ex = solve_exec(price, pv_act, load_act, a, qDA)
    ex["qDA"] = qDA
    ex["a"] = a
    ex["plan_cost"] = ex.get("plan_cost", float((np.asarray(price) * qDA).sum()))
    return ex

# ---------------- workbook fillers ----------------

def _dates_rows(ws):
    rows = {}
    for r in range(2, ws.max_row + 1):
        v = ws.cell(r, 1).value
        if isinstance(v, datetime):
            rows[v] = r
    return rows

def _find_day_block(ws, date):
    for r in range(2, ws.max_row + 1):
        if isinstance(ws.cell(r, 1).value, datetime) and ws.cell(r, 1).value == date:
            return r
    return None

def _next_date_row(ws, fr):
    for r in range(fr + 1, ws.max_row + 1):
        if isinstance(ws.cell(r, 1).value, datetime):
            return r
    return ws.max_row + 1

def _fill_purchase(wb, data):
    ws = wb["计划购电量"]
    drow = _dates_rows(ws)
    for date, ex in data.items():
        if date not in drow:
            continue
        r = drow[date]
        for t in range(N):
            ws.cell(r, 2 + t).value = round(float(ex["qDA"][t]), 3)

def _fill_adjust(wb, data):
    if "调整购电量" not in wb.sheetnames:
        return
    ws = wb["调整购电量"]
    drow = _dates_rows(ws)
    for date, ex in data.items():
        if date not in drow:
            continue
        r = drow[date]
        for t in range(N):
            ws.cell(r, 2 + t).value = round(float(ex["a"][t]), 3)

def _fill_cd(wb, data):
    ws = wb["充放电量"]
    for date, ex in data.items():
        r0 = _find_day_block(ws, date)
        if r0 is None:
            continue
        C, D = ex["C"], ex["D"]
        for s in range(6):
            ws.cell(r0 + s, 3).value = round(float(C[s * 24:(s + 1) * 24].sum()), 3)
            ws.cell(r0 + s, 4).value = round(float(D[s * 24:(s + 1) * 24].sum()), 3)
        ws.cell(r0, 6).value = round(float(ex["e"][0]), 0)
        ws.cell(r0 + 1, 6).value = round(float(ex["e"][-1]), 0)

def _write_emergency(wb, data):
    if "紧急购电量" not in wb.sheetnames:
        return
    ws = wb["紧急购电量"]
    drow = _dates_rows(ws)
    for date, ex in data.items():
        if date not in drow:
            continue
        em = np.asarray(ex["em"], float)
        eps = []
        start = None
        for t in range(N):
            if em[t] > 1e-3:
                if start is None:
                    start = t
            elif start is not None:
                eps.append((start, t - 1, em[start:t].sum()))
                start = None
        if start is not None:
            eps.append((start, N - 1, em[start:].sum()))
        if not eps:
            continue
        r0 = drow[date]
        nxt = _next_date_row(ws, r0)
        free = [r for r in range(r0 + 1, nxt) if ws.cell(r, 2).value is None]
        if len(free) < len(eps):
            ws.insert_rows(nxt, len(eps) - len(free))
            nxt += len(eps) - len(free)
            free = [r for r in range(r0 + 1, nxt) if ws.cell(r, 2).value is None]
        for i, (s, e, val) in enumerate(eps):
            rr = free[i]
            ws.cell(rr, 2).value = f"{slot_lbl(s)}-{slot_lbl(e)}"
            ws.cell(rr, 3).value = round(float(val), 3)

def write_result(template, fname, data):
    wb = openpyxl.load_workbook(os.path.join(TEMPLATES, template))
    _fill_purchase(wb, data)
    _fill_adjust(wb, data)
    _fill_cd(wb, data)
    _write_emergency(wb, data)
    out = os.path.join(OUTDIR, fname)
    wb.save(out)
    return out

def write_p1(p1):
    wb = openpyxl.load_workbook(os.path.join(TEMPLATES, "result1.xlsx"))
    ws1 = wb["计划购电量"]
    for t in range(N):
        ws1.cell(2 + t, 2).value = round(float(p1["qDA"][t]), 3)
    ws2 = wb["充放电量"]
    C, D = p1["C"], p1["D"]
    for s in range(6):
        ws2.cell(2 + s, 2).value = round(float(C[s * 24:(s + 1) * 24].sum()), 3)
        ws2.cell(2 + s, 3).value = round(float(D[s * 24:(s + 1) * 24].sum()), 3)
    ws2.cell(2, 5).value = round(float(p1["e"][0]), 0)
    ws2.cell(3, 5).value = round(float(p1["e"][-1]), 0)
    out = os.path.join(OUTDIR, "result1.xlsx")
    wb.save(out)
    return out

def _summarize(days):
    q = sum(float(ex["qDA"].sum()) for ex in days.values())
    em = sum(float(np.maximum(ex["em"], 0).sum()) for ex in days.values())
    plan = sum(float(ex["plan_cost"]) for ex in days.values())
    em_cost = sum(float(ex["emergency_cost"]) for ex in days.values())
    adj = sum(float(ex.get("adj_cost", 0.0)) for ex in days.values())
    return {"plan_purchase_kWh": q, "emergency_kWh": em, "plan_cost": plan,
            "emergency_cost": em_cost, "adj_cost": adj, "total_cost": plan + em_cost + adj}

def main():
    price1, l1, v1 = utils.load_attachment1()
    load_yr, pv_yr = utils.load_attachment2()
    fc3 = utils.load_attachment3()
    price_yr = utils.load_attachment4()
    dates = sorted([d for d in load_yr if d >= datetime(2025, 2, 1)])

    # P1
    p1 = solve_one_day(fc3, datetime(2025, 1, 1), l1, v1, price1, with_adj=False)
    write_p1(p1)
    print("P1 done cost", round(p1["plan_cost"], 2))

    p2 = {d: solve_one_day(fc3, d, load_yr[d], pv_yr[d], price1, with_adj=False) for d in dates}
    write_result("result2.xlsx", "result2.xlsx", p2)
    print("P2 done")

    p3 = {d: solve_one_day(fc3, d, load_yr[d], pv_yr[d], price1, with_adj=True) for d in dates}
    write_result("result3.xlsx", "result3.xlsx", p3)
    print("P3 done")

    p42 = {d: solve_one_day(fc3, d, load_yr[d], pv_yr[d], price_yr[d], with_adj=False) for d in dates}
    write_result("result4-2.xlsx", "result4-2.xlsx", p42)
    print("P4-2 done")

    p43 = {d: solve_one_day(fc3, d, load_yr[d], pv_yr[d], price_yr[d], with_adj=True) for d in dates}
    write_result("result4-3.xlsx", "result4-3.xlsx", p43)
    print("P4-3 done")

    summary = {
        "P1": {"cost": p1["plan_cost"], "qDA_kWh": float(p1["qDA"].sum()),
               "C_kWh": float(p1["C"].sum()), "D_kWh": float(p1["D"].sum())},
        "P2": _summarize(p2), "P3": _summarize(p3),
        "P4-2": _summarize(p42), "P4-3": _summarize(p43),
    }
    with open(os.path.join(OUTDIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=float)
    print("RESULTS ->", OUTDIR)
    for k in ("P1", "P2", "P3", "P4-2", "P4-3"):
        print(k, json.dumps(summary[k], ensure_ascii=False))

if __name__ == "__main__":
    main()
