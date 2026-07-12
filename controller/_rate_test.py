# -*- coding: utf-8 -*-
"""量 DevKit 吞吐:urllib(每次新连接) vs keep-alive长连接。决定方案A能到多少Hz。
只写 VELOCITY_BODY_*=0(悬停态无扰动),安全。"""
import time, http.client, json, config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = "http://127.0.0.1:5000"
import devkit_client as k

c = k.DevKitClient()
N = 60

def timeit(fn, n=N):
    t0 = time.time()
    for _ in range(n):
        fn()
    dt = time.time() - t0
    return n / dt, dt / n * 1000.0

r, ms = timeit(lambda: c.set_param("VELOCITY_BODY_Y", 0.0))
print("urllib  set : %6.1f Hz  (%.1f ms/次)" % (r, ms))
r, ms = timeit(lambda: c.get_state())
print("urllib  get : %6.1f Hz  (%.1f ms/次)" % (r, ms))

conn = http.client.HTTPConnection("127.0.0.1", 5000, timeout=3)
def kset(n, v):
    conn.request("PUT", "/set", json.dumps({"name": n, "val": v}), {"Content-Type": "application/json"})
    conn.getresponse().read()
def kget():
    conn.request("GET", "/get")
    conn.getresponse().read()

r, ms = timeit(lambda: kset("VELOCITY_BODY_Y", 0.0))
print("keepalive set : %6.1f Hz  (%.1f ms/次)" % (r, ms))
r, ms = timeit(lambda: kget())
print("keepalive get : %6.1f Hz  (%.1f ms/次)" % (r, ms))

def frame():
    kget(); kset("VELOCITY_BODY_X", 0.0); kset("VELOCITY_BODY_Z", 0.0); kset("VELOCITY_BODY_Y", 0.0)
r, ms = timeit(frame, 40)
print("keepalive 一帧(1get+3set) : %6.1f Hz" % r)

def frame_noget():
    kset("VELOCITY_BODY_X", 0.0); kset("VELOCITY_BODY_Z", 0.0); kset("VELOCITY_BODY_Y", 0.0)
r, ms = timeit(frame_noget, 40)
print("keepalive 一帧(仅3set,get另线程) : %6.1f Hz" % r)
conn.close()
