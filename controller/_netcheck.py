# -*- coding: utf-8 -*-
"""诊断'卡死': 测 DevKit(/get) 与 面板(/status) 的响应延迟/成功率, 并看面板 STATE 实时值是否为空。"""
import os, time, json, statistics, urllib.request
DEV = os.environ.get("DEVKIT_URL", "http://127.0.0.1:5000")
PANEL = "http://127.0.0.1:8000"

def timeit(url, n=5, timeout=4):
    ts = []; ok = 0; err = ""
    for _ in range(n):
        t = time.time()
        try:
            urllib.request.urlopen(url, timeout=timeout).read()
            ts.append((time.time() - t) * 1000); ok += 1
        except Exception as e:
            ts.append((time.time() - t) * 1000); err = type(e).__name__ + ": " + str(e)[:70]
    return ok, ts, err

for name, url in [("DevKit /get", DEV + "/get"), ("Panel /status", PANEL + "/status")]:
    ok, ts, err = timeit(url)
    print("%-14s 成功 %d/%d  延迟 avg=%.0fms min=%.0f max=%.0f  %s" % (
        name, ok, len(ts), statistics.mean(ts), min(ts), max(ts), ("<<ERR " + err) if err else ""))

try:
    s = json.loads(urllib.request.urlopen(PANEL + "/status", timeout=5).read().decode())
    print("面板STATE: alt=%s vspeed=%s lat=%s dist=%s phase=%s armed=%s ap_on=%s" % (
        s.get("alt"), s.get("vspeed"), s.get("lat"), s.get("dist"), s.get("phase"), s.get("armed_cause"), s.get("ap_on")))
except Exception as e:
    print("读 /status 失败:", type(e).__name__, e)
