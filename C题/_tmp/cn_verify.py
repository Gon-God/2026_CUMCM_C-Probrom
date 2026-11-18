# -*- coding: utf-8 -*-
"""Verify Chinese references via Semantic Scholar API + journal websites; write UTF-8 report."""
import json, re, ssl, sys, time, urllib.parse, urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
OUT = []
FIELDS = "title,authors,year,venue,externalIds,journal,publicationVenue"


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers=H)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


def s2(title):
    url = ("https://api.semanticscholar.org/graph/v1/paper/search?limit=3&fields=" + FIELDS +
           "&query=" + urllib.parse.quote(title))
    raw = fetch(url)
    return json.loads(raw.decode("utf-8"))


CN_TITLES = [
    "分布式发电、微网与智能配电网的发展与挑战",
    "微电网技术综述",
    "微网经济调度问题的混合整数规划方法",
    "微电网两阶段鲁棒优化经济调度方法",
    "包含钠硫电池储能的微网系统经济运行优化",
    "考虑风电随机性的微网多时间尺度能量优化调度",
    "计及分时电价下用户需求响应的分布式储能多目标优化运行",
    "计及蓄电池使用寿命的微电网经济调度模型",
    "主动配电网中电池储能系统最优充放电策略",
    "微网系统的动态经济调度",
]

OUT.append("################ Semantic Scholar lookups ################")
for t in CN_TITLES:
    OUT.append("")
    OUT.append("Q: " + t)
    try:
        d = s2(t)
        for p in d.get("data", []):
            au = "; ".join(a.get("name", "") for a in p.get("authors", []))
            OUT.append(f"   - {p.get('title')} | {au} | {p.get('year')} | venue={p.get('venue')} "
                       f"| journal={p.get('journal')} | ids={p.get('externalIds')}")
    except Exception as e:
        OUT.append("   ERR " + type(e).__name__ + " " + str(e))
    time.sleep(1.2)

OUT.append("")
OUT.append("################ epae.cn issue list 2015-10 ################")
try:
    raw = fetch("https://www.epae.cn/dlzdhsb/ch/reader/issue_list.aspx?year_id=2015&quarter_id=10")
    for enc in ("utf-8", "gb18030"):
        try:
            html = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    OUT.append(txt[:6000])
except Exception as e:
    OUT.append("ERR " + type(e).__name__ + " " + str(e))

OUT.append("")
OUT.append("################ epjournal.csee.org.cn reachability ################")
for u in [
    "https://epjournal.csee.org.cn/zgdjgcxb/cn/article/doi/10.13334/j.0258-8013.pcsee.2013.28.001",
    "http://ntps.epri.sgcc.com.cn/djgcxb/CN/10.13334/j.0258-8013.pcsee.2013.28.001",
    "https://www.dwjs.com.cn/CN/10.13335/j.1000-3673.pst.2018.14.001",
]:
    try:
        raw = fetch(u, timeout=20)
        OUT.append(f"OK {u} len={len(raw)}")
        for enc in ("utf-8", "gb18030"):
            try:
                html = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
        OUT.append("   " + txt[:500])
    except Exception as e:
        OUT.append(f"ERR {u} {type(e).__name__} {e}")

with open(r"C:\Users\Tower\Desktop\26年国赛\C题\_tmp\cn_verify.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(OUT))
print("done", len(OUT), "lines")
