# -*- coding: utf-8 -*-
"""Inspect result template sheet layout by scanning non-empty cells."""
import openpyxl, os
base = os.path.join(os.path.expanduser("~"), "Desktop", "26年国赛", "C题", "附件", "附件5")

def dump(name):
    wb = openpyxl.load_workbook(os.path.join(base, name), data_only=True)
    print("\n=====", name)
    for ws in wb.worksheets:
        print("SHEET", repr(ws.title))
        merged = [str(m) for m in ws.merged_cells.ranges][:20]
        print("  merged:", merged)
        # print every non-empty cell position + value
        n = 0
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    print("   ", cell.coordinate, repr(cell.value))
                    n += 1
                    if n > 40:
                        break
            if n > 40:
                break
        if ws.max_row > 4 and n <= 40:
            # also print a few data rows fully
            for r in range(2, min(ws.max_row, 5) + 1):
                print("    row", r, [ws.cell(r, c).value for c in range(1, ws.max_column + 1)])

for f in ["result1.xlsx", "result2.xlsx"]:
    dump(f)
