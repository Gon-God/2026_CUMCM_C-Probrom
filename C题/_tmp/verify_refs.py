# -*- coding: utf-8 -*-
"""Batch-verify candidate references against the Crossref REST API."""
import json, ssl, sys, time, urllib.parse, urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEAD = {"User-Agent": "refcheck/1.0 (mailto:student@example.com)"}

QUERIES = [
    "Estimating the value of electricity storage in PJM: Arbitrage and some welfare effects",
    "Economic viability of energy storage systems based on price arbitrage potential in real-time US electricity markets",
    "Optimal scheduling of a renewable micro-grid in an isolated load area using mixed-integer linear programming",
    "Energy management and operational planning of a microgrid with a PV-based active generator for smart grid applications",
    "Smart energy management system for optimal microgrid economic operation",
    "A microgrid energy management system based on the rolling horizon strategy",
    "A model predictive control approach to microgrid operation optimization",
    "Centralized control for optimizing microgrids operation",
    "Operation optimization of standalone microgrids considering lifetime characteristics of battery energy storage system",
    "Real-time energy management in microgrids",
    "The price of robustness",
    "Mixed-integer-linear-programming-based energy management system for hybrid PV-wind-battery microgrids: modeling, design, and experimental verification",
    "Operation and sizing of energy storage for wind power plants in a market system",
    "Decomposed stochastic model predictive control for optimal dispatch of storage and generation",
    "Multiagent system for real-time operation of a microgrid in real-time digital simulator",
    "Optimal operation of energy storage systems considering forecast uncertainty: a review",
    "A review of energy management strategies for microgrids",
    "Sizing and optimal operation of battery energy storage system for peak shaving application",
    "Battery energy storage system scheduling for peak shaving and valley filling based on time-of-use price",
    "Optimal allocation and economic analysis of energy storage in microgrid considering time-of-use price",
]


def fetch(title):
    url = ("https://api.crossref.org/works?rows=1"
           "&select=title,author,container-title,volume,issue,page,issued,DOI,type"
           "&query.bibliographic=" + urllib.parse.quote(title))
    req = urllib.request.Request(url, headers=HEAD)
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.load(r)["message"]["items"]


def fmt(it):
    au = "; ".join(
        f"{a.get('family','')} {a.get('given','')}".strip() for a in it.get("author", [])
    )
    yr = it.get("issued", {}).get("date-parts", [[None]])[0][0]
    return (f"{au}. {it.get('title',[''])[0]}[J]. "
            f"{'/'.join(it.get('container-title',['']))}, {yr}, "
            f"{it.get('volume','')}({it.get('issue','')}): {it.get('page','')}. DOI: {it.get('DOI','')}")


out = []
for q in QUERIES:
    ok = False
    for attempt in range(3):
        try:
            items = fetch(q)
            for it in items[:1]:
                out.append("Q: " + q)
                out.append("  -> " + fmt(it))
            ok = True
            break
        except Exception as e:  # noqa
            time.sleep(1.5)
    if not ok:
        out.append("Q: " + q)
        out.append("  -> FAILED")

sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(out))
