# -*- coding: utf-8 -*-
"""Fetch CNKI issue TOC pages to confirm Chinese articles' titles and authors."""
import re, ssl, urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
H = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9",
}
OUT = []
TARGETS = [
    ("ZGDC-2013-28", "https://www.cnki.com.cn/Journal/F-F2-ZGDC-2013-28.htm", "混合整数"),
    ("ZGDC-2014-01", "https://www.cnki.com.cn/Journal/F-F2-ZGDC-2014-01.htm", "微电网技术综述"),
    ("ZGDC-2018-14", "https://www.cnki.com.cn/Journal/F-F2-ZGDC-2018-14.htm", "鲁棒"),
    ("ZGDC-2011-04", "https://www.cnki.com.cn/Journal/F-F2-ZGDC-2011-04.htm", "钠硫"),
    ("DLXT-2010-02", "https://www.cnki.com.cn/Journal/F-F2-DLXT-2010-02.htm", "分布式发电"),
    ("DLXT-2016-20", "https://www.cnki.com.cn/Journal/F-F2-DLXT-2016-20.htm", "储能"),
    ("TYLX-2021-09", "https://www.cnki.com.cn/Journal/F-F2-TYLX-2021-09.htm", "微能源网"),
]


def text_of(raw):
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def clean(html):
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


for tag, url, kw in TARGETS:
    OUT.append("=" * 90)
    OUT.append(f"[{tag}] {url}  (keyword={kw})")
    try:
        req = urllib.request.Request(url, headers=H)
        with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
            html = text_of(r.read())
        t = clean(html)
        OUT.append("len=" + str(len(t)))
        idx = t.find(kw)
        if idx >= 0:
            OUT.append("HIT: " + t[max(0, idx - 400):idx + 400])
        else:
            OUT.append("no keyword hit; head: " + t[:800])
        # collect candidate links for the keyword article
        for m in re.finditer(r'href="(/Article/CJFDTotal-[A-Z0-9]+\.htm)"[^>]*>([^<]{4,60})<', html):
            if kw in m.group(2):
                OUT.append("LINK: " + m.group(1) + " -> " + m.group(2))
    except Exception as e:
        OUT.append("ERR " + type(e).__name__ + " " + str(e))

with open(r"C:\Users\Tower\Desktop\26年国赛\C题\_tmp\cnki_toc.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(OUT))
print("ok")
