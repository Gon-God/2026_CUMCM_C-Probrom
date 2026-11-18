# -*- coding: utf-8 -*-
"""Inspect the emergency sheet of the Attachment-5 templates and of the produced results."""
import os, sys
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, "\u9644\u4ef6", "\u9644\u4ef65")
EM = "\u7d27\u6025\u8d2d\u7535\u91cf"   # 紧急购电量

def dump(path, label):
    wb = openpyxl.load_workbook(path)
    print("=" * 70)
    print(label, os.path.basename(path))
    print("sheets:", [s.encode("unicode_escape").decode() for s in wb.sheetnames])
    ws = wb[EM] if EM in wb.sheetnames else None
    if ws is None:
        print("  no emergency sheet")
        return
    print("  dims rows=%d cols=%d" % (ws.max_row, ws.max_column))
    filled = 0
    for r in range(1, ws.max_row + 1):
        vals = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
        if any(v is not None for v in vals):
            filled += 1
            if filled <= 25:
                print("   r%-4d %s" % (r, [str(v) for v in vals]))
    print("  non-empty rows:", filled)

dump(os.path.join(TPL, "result2.xlsx"), "TEMPLATE")
dump(os.path.join(ROOT, "results", "result2.xlsx"), "RESULT")
