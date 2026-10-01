"""把网址推给 IndexNow：Bing（ChatGPT 搜索、Copilot 用的就是它的索引）、Yandex、Seznam、Naver 等共享这一个接口。

用法（先部署，确认 https://embodiedterms.com/<key>.txt 能打开，再跑）：
    python3 _tools/indexnow.py                 # 推 site/sitemap.xml 里的全部网址
    python3 _tools/indexnow.py URL [URL ...]   # 只推改过的几条
key 在 site_config.json 的 indexnow_key，本来就是公开的：build_site.py 把它写成站点根目录的 <key>.txt，
搜索引擎靠这个文件确认推送的人管得了这个网站。
返回 200 / 202 都算成功（202 = key 还在验证）；403 = key 文件没找到；422 = 网址不属于这个域名；429 = 推得太频繁。
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
CFG = json.load(open(os.path.join(TOOLS, "site_config.json"), encoding="utf-8"))
ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH = 10000   # 协议规定一次最多 1 万条


def main():
    base = CFG["base_url"].rstrip("/")
    key = CFG["indexnow_key"]
    urls = sys.argv[1:] or re.findall(r"<loc>([^<]+)</loc>", open(os.path.join(ROOT, "site", "sitemap.xml"), encoding="utf-8").read())
    bad = [u for u in urls if not u.startswith(base + "/")]
    if bad:
        sys.exit(f"这些网址不属于 {base}：{bad[:3]}")
    host = base.split("://", 1)[1]
    for i in range(0, len(urls), BATCH):
        chunk = urls[i:i + BATCH]
        body = json.dumps({"host": host, "key": key, "keyLocation": f"{base}/{key}.txt", "urlList": chunk}).encode("utf-8")
        req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "embodiedterms-indexnow"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                print(f"{resp.status} {resp.reason}：推了 {len(chunk)} 条")
        except urllib.error.HTTPError as e:
            print(f"失败 {e.code} {e.reason}：{e.read()[:300].decode('utf-8', 'replace')}")
            sys.exit(1)


if __name__ == "__main__":
    main()
