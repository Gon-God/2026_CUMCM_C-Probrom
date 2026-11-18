# -*- coding: utf-8 -*-
"""Probe journal platforms for full GB/T 7714 citation strings."""
import re, ssl, sys, urllib.parse, urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
H = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}
OUT = []


def get(url, timeout=25):
    req = urllib.request.Request(url, headers=H)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


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


def dump(tag, url):
    OUT.append("=" * 90)
    OUT.append(f"[{tag}] {url}")
    try:
        raw = get(url)
        t = text_of(raw)
        OUT.append("len=" + str(len(t)))
        # citation-like fragments: 期刊名,YYYY,卷(期)
        for m in re.finditer(r"[\u4e00-\u9fa5A-Za-z、,，\s\.\-]{0,80}\[\s*J\s*\][.．,，]?\s*[\u4e00-\u9fa5A-Za-z&\.\s]{2,30}[,，]\s*(19|20)\d{2}\s*[,，]\s*\d+\s*\(\s*\d+\s*\)\s*[:：]\s*[\d\-–]+", t):
            OUT.append("  CITE>> " + m.group(0).strip())
        for kw in ["引用本文", "引用格式", "DOI", "页码", "卷期"]:
            i = t.find(kw)
            if i >= 0:
                OUT.append(f"  [{kw}] " + t[max(0, i - 60):i + 200])
    except Exception as e:
        OUT.append("  ERR " + type(e).__name__ + " " + str(e))


dump("CSEE-search", "https://epjournal.csee.org.cn/zgdjgcxb/cn/search?searchType=1&q=" + urllib.parse.quote("微网经济调度问题的混合整数规划方法"))
dump("CSEE-home", "https://epjournal.csee.org.cn/zgdjgcxb/cn/")
dump("EPAE-2015-10", "https://www.epae.cn/dlzdhsb/ch/reader/view_abstract.aspx?file_no=201510005&flag=1")
dump("EPAE-2020-01", "https://www.epae.cn/dlzdhsb/ch/reader/view_abstract.aspx?journal_id=dlzdhsb&file_no=202001018")
dump("PCMP", "https://www.pcmp.info/ch/reader/view_abstract.aspx?file_no=20142301&flag=1")
dump("AIOPS", "http://www.aeps-info.com/aeps/article/abstract/200912053")

with open(r"C:\Users\Tower\Desktop\26年国赛\C题\_tmp\cn_cites.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(OUT))
print("written")
