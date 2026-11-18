# -*- coding: utf-8 -*-
"""Verify specific DOIs, and try Crossref lookups for Chinese-language titles."""
import json, ssl, sys, time, urllib.parse, urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
HEAD = {"User-Agent": "refcheck/1.0 (mailto:student@example.com)"}


def get(url):
    req = urllib.request.Request(url, headers=HEAD)
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.load(r)


def fmt(it):
    au = "; ".join(f"{a.get('family','')} {a.get('given','')}".strip() for a in it.get("author", []))
    yr = it.get("issued", {}).get("date-parts", [[None]])[0][0]
    return (f"{au}. {it.get('title',[''])[0]}[J]. {'/'.join(it.get('container-title',['']))}, "
            f"{yr}, {it.get('volume','')}({it.get('issue','')}): {it.get('page','')}. DOI: {it.get('DOI','')}")


DOIS = [
    "10.1049/iet-rpg.2010.0123",     # Chen et al. smart EMS
    "10.1109/TCST.2013.2295737",     # Parisio MPC
    "10.1109/TEC.2007.914174",       # Tsikalakis 2008
    "10.1287/opre.1030.0065",        # Bertsimas & Sim
    "10.1109/TSG.2015.2462294",      # Shi et al. real-time EMS
    "10.1016/S0142-0615(02)00116-3", # Korpas et al.
    "10.1016/j.apenergy.2017.12.046",# Barbour community energy storage
    "10.1109/TSG.2014.2321762",      # Zhu & Hug
    "10.1016/j.rser.2016.11.188",    # maybe
    "10.1109/TSTE.2013.2248400",     # Zhao lifetime
]

CN_TITLES = [
    "微电网关键技术研究",
    "微电网技术综述",
    "分布式发电、微网与智能配电网的发展与挑战",
    "微网系统的动态经济调度",
    "微网研究中的关键技术",
    "考虑分时电价的用户侧储能优化配置",
    "含光伏和储能的微电网优化调度",
    "微电网经济调度研究综述",
]

out = []
for d in DOIS:
    try:
        it = get("https://api.crossref.org/works/" + urllib.parse.quote(d))["message"]
        out.append("DOI " + d + " -> " + fmt(it))
    except Exception as e:
        out.append("DOI " + d + " -> FAILED " + type(e).__name__)

out.append("")
out.append("=== Chinese-title lookups (Crossref coverage test) ===")
for q in CN_TITLES:
    try:
        url = ("https://api.crossref.org/works?rows=2&select=title,author,container-title,volume,issue,page,issued,DOI"
               "&query.bibliographic=" + urllib.parse.quote(q))
        items = get(url)["message"]["items"]
        out.append("Q: " + q)
        for it in items:
            out.append("   -> " + fmt(it))
    except Exception as e:
        out.append("Q: " + q + " -> FAILED " + type(e).__name__)
    time.sleep(0.5)

sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(out))
