# -*- coding: utf-8 -*-
"""Fetch Chinese journal abstract pages and dump compact text for manual parsing."""
import re, ssl, sys, urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

URLS = [
    "https://www.epae.cn/dlzdhsb/ch/reader/view_abstract.aspx?file_no=201510005&flag=1",
    "https://www.epae.cn/dlzdhsb/ch/reader/view_abstract.aspx?journal_id=dlzdhsb&file_no=202001018",
    "https://dlbh.net/ch/reader/view_abstract.aspx?file_no=20142301&flag=1",
    "https://www.pcmp.info/ch/reader/view_abstract.aspx?file_no=20142301&flag=1",
    "https://www.cnki.com.cn/Article/CJFDTotal-DLXT201002004.htm",
    "https://www.cnki.com.cn/Article/CJFDTotal-ZGDC201328002.htm",
    "https://www.cnki.com.cn/Article/CJFDTotal-TYLX202109068.htm",
]


def clean(html):
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = txt.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", txt).strip()


for u in URLS:
    print("=" * 100)
    print("URL:", u)
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=25, context=ctx)
        raw = r.read()
        for enc in ("utf-8", "gb18030"):
            try:
                html = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            html = raw.decode("utf-8", "ignore")
        txt = clean(html)
        print("LEN:", len(txt))
        # print citation-ish fragments
        for kw in ["DOI", "doi", "页码", "页", "卷", "期", "作者", "摘要", "引用"]:
            for m in re.finditer(re.escape(kw), txt):
                s = max(0, m.start() - 90)
                frag = txt[s:m.start() + 130]
                print(f"  [{kw}] ...{frag}...")
                break
        print("HEAD:", txt[:600])
    except Exception as e:
        print("ERR:", type(e).__name__, e)
