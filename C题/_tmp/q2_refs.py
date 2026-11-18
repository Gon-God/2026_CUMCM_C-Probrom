# -*- coding: utf-8 -*-
"""Crossref bibliographic search for Problem-2 candidate references."""
import json, ssl, sys, time, urllib.parse, urllib.request

sys.stdout.reconfigure(encoding="utf-8")
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
HEAD = {"User-Agent": "refcheck/1.0 (mailto:student@example.com)"}


def get(url):
    req = urllib.request.Request(url, headers=HEAD)
    with urllib.request.urlopen(req, timeout=40, context=ctx) as r:
        return json.load(r)


def fmt(it):
    au = "; ".join(f"{a.get('family','')} {a.get('given','')}".strip() for a in it.get("author", [])[:3])
    yr = it.get("issued", {}).get("date-parts", [[None]])[0][0]
    return (f"{au} | {it.get('title',[''])[0]} | {'/'.join(it.get('container-title',['']))} | "
            f"{yr} | {it.get('volume','')}({it.get('issue','')}) | {it.get('page','')} | {it.get('DOI','')}")


QUERIES = [
    "Two-stage energy management for networked microgrids with high renewable penetration",
    "day-ahead optimal scheduling independent DC microgrid generalized energy storage IGDT",
    "real-time microgrid economic dispatch based on model predictive control strategy",
    "microgrid day-ahead scheduling renewable uncertainty chance constrained programming",
    "conditional value at risk microgrid energy management stochastic scheduling",
    "optimal bidding strategy microgrid day-ahead market hybrid stochastic robust optimization",
    "imbalance penalty optimal bidding day-ahead balancing market stochastic",
    "newsvendor model electricity procurement penalty unmet demand power",
    "value of perfect information stochastic unit commitment power system scheduling",
    "operating reserve scheduling microgrid photovoltaic forecast error uncertainty",
    "battery degradation cost linearized mixed integer linear programming microgrid dispatch",
    "resilience microgrid two-stage robust optimization column and constraint generation scheduling",
    "energy storage arbitrage perfect foresight price uncertainty value",
    "distributionally robust optimization microgrid energy management Wasserstein",
    "microgrid energy management forecast error impact cost sensitivity analysis",
]

out = []
for q in QUERIES:
    try:
        url = ("https://api.crossref.org/works?rows=3"
               "&select=title,author,container-title,volume,issue,page,issued,DOI,type"
               "&query.bibliographic=" + urllib.parse.quote(q))
        items = get(url)["message"]["items"]
        out.append("### " + q)
        for it in items:
            out.append("   - " + fmt(it))
    except Exception as e:
        out.append("### " + q + " -> FAILED " + type(e).__name__)
    out.append("")
    time.sleep(0.4)

print("\n".join(out))
