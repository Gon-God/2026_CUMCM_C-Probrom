# -*- coding: utf-8 -*-
import json, ssl, sys, time, urllib.parse, urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
H = {"User-Agent": "refcheck/1.0 (mailto:s@example.com)"}

DOIS = [
    "10.1016/j.apenergy.2015.05.090",
    "10.1016/j.apenergy.2014.08.080",
    "10.1016/j.apenergy.2018.09.185",
    "10.1109/TSTE.2011.2114901",
    "10.1016/j.apenergy.2017.06.043",
    "10.1109/TSG.2015.2476669",
    "10.1109/TSG.2017.2653198",
    "10.1016/j.apenergy.2014.09.081",
]

lines = []
for d in DOIS:
    try:
        url = "https://api.crossref.org/works/" + urllib.parse.quote(d)
        it = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=H),
                                              timeout=30, context=ctx))["message"]
        au = "; ".join((a.get("family", "") + " " + a.get("given", "")).strip()
                       for a in it.get("author", []))
        yr = it.get("issued", {}).get("date-parts", [[None]])[0][0]
        jour = (it.get("container-title") or [""])[0]
        lines.append(f"{au}. {it['title'][0]}[J]. {jour}, {yr}, "
                     f"{it.get('volume')}({it.get('issue', '')}): {it.get('page')}. DOI {it.get('DOI')}")
    except Exception as e:
        lines.append(f"ERR {d} {type(e).__name__}")
    time.sleep(0.4)

sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(lines))
