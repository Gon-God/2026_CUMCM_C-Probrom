# -*- coding: utf-8 -*-
"""Last probe: try to obtain page numbers for Chinese core-journal papers."""
import json, re, ssl, urllib.parse, urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
H = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
OUT = []


def text_of(raw):
    for enc in ("utf-8", "gb18030"):
        try:
            html = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        html = raw.decode("utf-8", "ignore")
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def dump(tag, url, keep=1200):
    OUT.append("=" * 90)
    OUT.append(f"[{tag}] {url}")
    try:
        req = urllib.request.Request(url, headers=H)
        with urllib.request.urlopen(req, timeout=22, context=ctx) as r:
            raw = r.read()
        t = text_of(raw)
        OUT.append("len=" + str(len(t)))
        OUT.append(t[:keep])
    except Exception as e:
        OUT.append("  ERR " + type(e).__name__ + " " + str(e))


# 1) journal platforms
dump("CSEE-ROOT", "https://epjournal.csee.org.cn/")
dump("CSEE-ZGDC", "https://epjournal.csee.org.cn/zgdjgcxb")
dump("NTPS-RAW", "http://ntps.epri.sgcc.com.cn/djgcxb/CN/Y2013/V33/I28")

# 2) epae abstract pages WITH journal_id (to read GB/T 7714 citation incl. pages)
for fn in ("201510005", "201510004"):
    dump("EPAE-" + fn, "https://www.epae.cn/dlzdhsb/ch/reader/view_abstract.aspx?journal_id=dlzdhsb&file_no=" + fn)

# 3) Chinese aggregators that sometimes expose full citation
dump("TAIXUESHU", "https://doc.taixueshu.com/journal/20130002zgdygc.html")
dump("WANFANG-S", "https://s.wanfangdata.com.cn/paper?q=" + urllib.parse.quote("微网经济调度问题的混合整数规划方法"))

# 4) OpenAlex (broad coverage incl. some Chinese journals)
try:
    u = "https://api.openalex.org/works?per_page=3&search=" + urllib.parse.quote("微网经济调度问题的混合整数规划方法")
    req = urllib.request.Request(u, headers=H)
    with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
        d = json.loads(r.read().decode("utf-8"))
    OUT.append("=" * 90)
    OUT.append("[OPENALEX] 微网经济调度问题的混合整数规划方法")
    for w in d.get("results", []):
        OUT.append(f"  - {w.get('title')} | {w.get('publication_year')} | {w.get('doi')} | "
                   f"{(w.get('primary_location') or {}).get('source', {}) and ((w.get('primary_location') or {}).get('source') or {}).get('display_name')} | "
                   f"biblio={w.get('biblio')} | " +
                   "; ".join(a['author']['display_name'] for a in w.get('authorships', [])))
except Exception as e:
    OUT.append("[OPENALEX] ERR " + type(e).__name__ + " " + str(e))

# OpenAlex lookups for several Chinese titles
OA_TITLES = [
    "微电网技术综述",
    "微电网两阶段鲁棒优化经济调度方法",
    "包含钠硫电池储能的微网系统经济运行优化",
    "计及蓄电池使用寿命的微电网经济调度模型",
    "分布式发电、微网与智能配电网的发展与挑战",
    "主动配电网中电池储能系统最优充放电策略",
    "微网系统的动态经济调度",
]
for t in OA_TITLES:
    OUT.append("=" * 90)
    OUT.append("[OPENALEX] " + t)
    try:
        u = "https://api.openalex.org/works?per_page=3&search=" + urllib.parse.quote(t)
        req = urllib.request.Request(u, headers=H)
        with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
            d = json.loads(r.read().decode("utf-8"))
        for w in d.get("results", []):
            src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
            OUT.append(f"  - {w.get('title')} | {w.get('publication_year')} | {w.get('doi')} | {src} | "
                       f"{w.get('biblio')} | " + "; ".join(a['author']['display_name'] for a in w.get('authorships', [])))
    except Exception as e:
        OUT.append("  ERR " + type(e).__name__ + " " + str(e))

with open(r"C:\Users\Tower\Desktop\26年国赛\C题\_tmp\pages_probe.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(OUT))
print("ok")
