# -*- coding: utf-8 -*-
"""Probe aggregators (Baidu Xueshu etc.) and journal issue lists for Chinese refs."""
import re, ssl, urllib.parse, urllib.request

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


def dump(tag, url, keep=2500):
    OUT.append("=" * 90)
    OUT.append(f"[{tag}] {url}")
    try:
        req = urllib.request.Request(url, headers=H)
        with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
            raw = r.read()
        t = text_of(raw)
        OUT.append("len=" + str(len(t)))
        OUT.append(t[:keep])
    except Exception as e:
        OUT.append("  ERR " + type(e).__name__ + " " + str(e))


dump("BAIDU-XUESHU", "https://xueshu.baidu.com/s?wd=" + urllib.parse.quote("微网经济调度问题的混合整数规划方法"))
dump("EPAE-ISSUE-2015-10", "https://www.epae.cn/dlzdhsb/ch/reader/issue_list.aspx?year_id=2015&quarter_id=10", 8000)
dump("CNKI-WX", "https://www.cnki.com.cn/Article/CJFDTotal-ZGDC201328002.htm")

with open(r"C:\Users\Tower\Desktop\26年国赛\C题\_tmp\agg_probe.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(OUT))
print("ok")
