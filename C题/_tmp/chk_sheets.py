# -*- coding: utf-8 -*-
"""Count how much of each sheet in the Attachment-5 templates vs results is actually filled."""
import os
import openpyxl
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, "\u9644\u4ef6", "\u9644\u4ef65")
NAMES = {
    "plan": "\u8ba1\u5212\u8d2d\u7535\u91cf",
    "cd": "\u5145\u653e\u7535\u91cf",
    "adj": "\u8c03\u6574\u8d2d\u7535\u91cf",
    "em": "\u7d27\u6025\u8d2d\u7535\u91cf",
}


def inspect(path, label):
    wb = openpyxl.load_workbook(path)
    print("=" * 72)
    print(label, os.path.basename(path))
    for key, name in NAMES.items():
        if name not in wb.sheetnames:
            continue
        ws = wb[name]
        dates = 0
        numeric = 0
        for r in range(1, ws.max_row + 1):
            v = ws.cell(r, 1).value
            if isinstance(v, datetime):
                dates += 1
            for c in range(2, ws.max_column + 1):
                if isinstance(ws.cell(r, c).value, (int, float)):
                    numeric += 1
        print("  %-14s rows=%-5d cols=%-3d date_rows=%-4d numeric_cells=%d"
              % (name.encode("unicode_escape").decode(), ws.max_row, ws.max_column, dates, numeric))


for f in ["result1.xlsx", "result2.xlsx", "result3.xlsx", "result4-2.xlsx", "result4-3.xlsx"]:
    inspect(os.path.join(TPL, f), "TEMPLATE")
    rp = os.path.join(ROOT, "results", f)
    if os.path.exists(rp):
        inspect(rp, "RESULT  ")
