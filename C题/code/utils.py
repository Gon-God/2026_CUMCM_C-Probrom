# -*- coding: utf-8 -*-
"""Data loading and interpolation utilities.

All attachments are read positionally (by column index) to avoid depending on
the (encoding-sensitive) Chinese header text. openpyxl reads real unicode; the
garbling only appears when printing to this terminal.
"""
from pathlib import Path
import numpy as np
import openpyxl

ROOT = Path(__file__).resolve().parent.parent
ATT = ROOT / "附件"

# Appendix 1 parameters
EMAX, EMIN, E0 = 12000.0, 1200.0, 6000.0
PMAX = 5000.0
ETA_C = ETA_D = 0.9
DT = 1.0 / 6.0          # 10 minutes in hours
C_MAX = PMAX * DT       # 833.333 kWh per 10-min slot
N = 144


def nan_replace(a, fill=0.0):
    a = np.asarray(a, dtype=float)
    return np.where(np.isnan(a), fill, a)


def load_attachment1():
    """Attachment 1 (single day). Returns (price[144], load[144], pv_pred[144])."""
    wb = openpyxl.load_workbook(ATT / "附件1.xlsx", read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    price, load, pv = [], [], []
    for r in rows[1:]:
        if r[0] is None:
            continue
        price.append(float(r[1]))
        load.append(float(r[2]))
        pv.append(float(r[3]))
    return np.array(price), np.array(load), np.array(pv)


def load_attachment2():
    """Attachment 2 (full year). Returns (load: dict date->[144], pv_act: dict date->[144]).
    The PV sheet is identified by having a much higher daytime than overnight mean.
    """
    wb = openpyxl.load_workbook(ATT / "附件2.xlsx", read_only=True, data_only=True)
    sets = []
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        d = {}
        for r in rows[1:]:
            if r[0] is None:
                continue
            v = [x for x in r[1:1 + N]]
            if all(x is None for x in v):
                continue
            d[r[0]] = np.array([float(x) if x is not None else np.nan for x in v])
        sets.append(d)

    def nighttime_mean(d):
        # late-evening/overnight 18:00-24:00 (slots 108..144): PV ~0, load stays high
        arr = np.array([nan_replace(v) for v in d.values()])
        return float(arr[:, 108:144].mean())

    # PV is ~0 late at night; the load sheet has a high overnight mean.
    night = [nighttime_mean(s) for s in sets]
    pv_idx = int(np.argmin(night))   # the sheet whose overnight mean is ~0 is PV
    load_idx = 1 - pv_idx
    return sets[load_idx], sets[pv_idx]


def load_attachment3():
    """Attachment 3. Returns {(date, release_hour): pv_pred[24]} with release_hour in {0,6,12,18}.
    The forecast for hour k (1..24) is the PV at absolute hour (release + k).
    """
    wb = openpyxl.load_workbook(ATT / "附件3.xlsx", read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    fc = {}
    from datetime import datetime
    cur = None
    for r in rows[1:]:
        date, rel = r[0], r[1]
        if rel is None:
            continue
        # date only on the first row of each day -> forward-fill
        if isinstance(date, str) and date.strip():
            cur = datetime.strptime(date.strip()[:10], "%Y-%m-%d")
        if cur is None:
            continue
        hi = int(str(rel).split(":")[0])
        vals = [float(x) if x is not None else 0.0 for x in r[2:26]]
        fc[(cur, hi)] = np.array(vals)
    return fc


def load_attachment4():
    """Attachment 4 (dynamic price). Returns {date: price[144]}."""
    wb = openpyxl.load_workbook(ATT / "附件4.xlsx", read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    d = {}
    for r in rows[1:]:
        if r[0] is None:
            continue
        v = [x for x in r[1:1 + N]]
        if all(x is None for x in v):
            continue
        d[r[0]] = nan_replace(np.array([float(x) if x is not None else np.nan for x in v]))
    return d


def fc_to_grid(fc24, release_hour):
    """Interpolate the (release, 24-hour) forecast onto the 144 ten-minute grid.
    Forecast sample k sits at absolute hour release+k. Returns array of length 144.
    """
    rel = float(release_hour)
    grid_h = (np.arange(1, 145) / 6.0)              # 0.1667 .. 24.0
    abs_h = rel + np.arange(1, 25, dtype=float)     # rel+1 .. rel+24
    return np.interp(grid_h, abs_h, fc24, left=fc24[0], right=fc24[-1])


def t_hour(t):
    """Start hour of slot t (0..143): 0.1667..24.0"""
    return (t + 1) / 6.0


def fmt_time(t):
    h = int(t)
    m = int(round((t - h) * 60))
    if m == 60:
        h += 1
        m = 0
    return f"{h}:{m:02d}"


def dates_between(start="2025-02-01", end="2025-12-31"):
    from datetime import datetime, timedelta
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    out, cur = [], s
    while cur <= e:
        out.append(cur)
        cur += timedelta(days=1)
    return out


if __name__ == "__main__":
    p, l, v = load_attachment1()
    print("A1 price", round(p.min(), 4), round(p.max(), 4),
          "load", round(l.min(), 1), round(l.max(), 1), "pv max", round(v.max(), 1))
    ld, pv = load_attachment2()
    ds = sorted(ld)
    print("A2 days", len(ds), ds[0].date(), ds[-1].date(),
          "load d1 head", ld[ds[0]][:4], "pv d1 max", round(pv[ds[0]].max(), 1))
    fc3 = load_attachment3()
    print("A3 entries", len(fc3))
    pr = load_attachment4()
    print("A4 days", len(pr))
