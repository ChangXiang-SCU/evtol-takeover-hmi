# -*- coding: utf-8 -*-
"""端到端测数据采集:POST /rec_start(TEST)→等2.5s→/rec_stop→读F:里最新csv, 看表头/字段数/帧数。"""
import urllib.request, json, time, os, glob

def post(path, body=None):
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request("http://127.0.0.1:8000" + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=5).read().decode()

print("rec_start ->", post("/rec_start", {"subject": "TEST"}))
time.sleep(2.5)
print("rec_stop  ->", post("/rec_stop"))
d = r"F:\Evtol_TAKEOVER"
files = sorted(glob.glob(os.path.join(d, "*.csv")), key=os.path.getmtime)
if files:
    f = files[-1]
    lines = open(f, encoding="utf-8-sig").read().splitlines()
    hdr = lines[0].split(",")
    print("最新文件:", os.path.basename(f))
    print("行数(含表头):", len(lines), "| 列数:", len(hdr))
    print("表头前8列:", hdr[:8])
    print("表头末5列:", hdr[-5:])
    if len(lines) > 1:
        print("第一帧前6列:", lines[1].split(",")[:6])
else:
    print("没找到 csv!")
