# -*- coding: utf-8 -*-
"""Second verification round: query Crossref by title with container filters."""
import json, ssl, sys, time, urllib.parse, urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
HEAD = {"User-Agent": "refcheck/1.0 (mailto:student@example.com)"}


def get(url):
    req = urllib.request.Request(url, headers=HEAD)
    with urllib.request.urlopen(req, timeout=35, context=ctx) as r:
        return json.load(r)


def fmt(it):
    au = "; ".join(f"{a.get('family','')} {a.get('given','')}".strip() for a in it.get("author", []))
    yr = it.get("issued", {}).get("date-parts", [[None]])[0][0]
    return (f"{au}. {it.get('title',[''])[0]}[J]. {'/'.join(it.get('container-title',['']))}, "
            f"{yr}, {it.get('volume','')}({it.get('issue','')}): {it.get('page','')}. DOI: {it.get('DOI','')}")


QUERIES = [
    ("Smart energy management system for optimal microgrid economic operation", "IET Renewable Power Generation"),
    ("Centralized control for optimizing microgrids operation", "IEEE Transactions on Energy Conversion"),
    ("Operation and sizing of energy storage for wind power plants in a market system", "International Journal of Electrical Power"),
    ("Community energy storage: A smart choice for the smart grid?", "Applied Energy"),
    ("Optimal operation of a microgrid with energy storage and demand response", "IEEE Transactions on Smart Grid"),
    ("Energy storage for peak shaving and valley filling in microgrid time-of-use price", ""),
    ("A review of microgrid energy management systems", ""),
    ("Optimal sizing of battery energy storage in microgrid using mixed integer linear programming", ""),
    ("Two-stage robust optimization for microgrid day-ahead scheduling uncertainty", ""),
    ("Economic model predictive control for microgrid energy management", ""),
]

out = []
for title, cont in QUERIES:
    url = ("https://api.crossref.org/works?rows=3&select=title,author,container-title,volume,issue,page,issued,DOI,type"
           "&query.bibliographic=" + urllib.parse.quote(title))
    if cont:
        url += "&query.container-title=" + urllib.parse.quote(cont)
    ok = False
    for _ in range(3):
        try:
            items = get(url)["message"]["items"]
            out.append("Q: " + title + ("  [in " + cont + "]" if cont else ""))
            for it in items:
                out.append("   -> " + fmt(it))
            ok = True
            break
        except Exception as e:
            time.sleep(1.5)
    if not ok:
        out.append("Q: " + title + " -> FAILED")
    out.append("")
    time.sleep(0.4)

sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(out))
