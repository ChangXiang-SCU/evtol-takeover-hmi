# -*- coding: utf-8 -*-
"""面板链路自测：arm blank -> 手动触发 -> 0.8s 后模拟触摸屏接管 -> 看 RT -> 复位。"""
import urllib.request as u, json, time
B = "http://127.0.0.1:8000"
def P(p, d=None):
    return u.urlopen(u.Request(B + p, data=(json.dumps(d).encode() if d else b""),
        method="POST", headers={"Content-Type": "application/json"}), timeout=5).read().decode()
def G(p):
    return u.urlopen(B + p, timeout=5).read().decode()
print("arm:", P("/arm", {"cause": "blank"}))
print("fire:", P("/fire"))
time.sleep(0.8)
print("takeover:", P("/takeover"))
print("STATUS:", G("/status"))
print("reset:", P("/reset"))
