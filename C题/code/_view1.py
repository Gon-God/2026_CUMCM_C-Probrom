# -*- coding: utf-8 -*-
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import utils

fc3 = utils.load_attachment3()
load_yr, pv_yr = utils.load_attachment2()
d = datetime(2025, 6, 21)
Lk = load_yr[d]            # kW
Gk = utils.fc_to_grid(fc3.get((d, 0)), 0)   # kW forecast
# 4-hour block means in kWh per block (28 slots)
for nb, (a, b) in enumerate([(0,28),(28,56),(56,84),(84,112),(112,144)]):
    print(f"block {nb}: slots {a}-{b}  load kW mean {Lk[a:b].mean():.0f}  pv kW mean {Gk[a:b].mean():.0f}  "
          f"net kWh/slot (L-G/6) mean {(Lk[a:b]-Gk[a:b]/6).mean():.1f}")
print("daily load kWh", round(Lk.sum()/6), "pv kWh", round(Gk.sum()/6))
print("max load kW", round(Lk.max()), "at slot", int(Lk.argmax()))
print("max net L-G/6", round((Lk-Gk/6).max()), "at slot", int((Lk-Gk/6).argmax()))
print("min net L-G/6", round((Lk-Gk/6).min()), "at slot", int((Lk-Gk/6).argmin()))
