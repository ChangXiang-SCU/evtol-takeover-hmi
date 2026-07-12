# -*- coding: utf-8 -*-
"""风切变机制③：改用 AP 垂速模式命令急降(这才真能动飞机)，用真实高度差衡量效果。AGL<100 自动中止。结尾恢复。"""
import time, config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = "http://10.7.144.111:5000"
config.HTTP_TIMEOUT_S = 8
from devkit_client import DevKitClient
c = DevKitClient()
def S(): return c.get_state()

s = S(); lat, lon = s["PLANE_LATITUDE"], s["PLANE_LONGITUDE"]
print("AGL=%.0fft" % s.get("PLANE_ALT_ABOVE_GROUND"))
print(">> 稳定悬停(4s)")
c.ap_rotor_point(lat, lon); time.sleep(4)
b = S(); balt = b["PLANE_ALTITUDE"]; bagl = b.get("PLANE_ALT_ABOVE_GROUND")
print("   基线 ASL=%.1f AGL=%.0f" % (balt, bagl))

tvs = -25   # AP 垂速目标(负=下降)；单位以实测掉高为准
print(">> AP 垂速模式急降 target_v_speed=%d，2.5s" % tvs)
print("   ap_start 返回:", c.ap_start({"state": 2, "target_v_speed": tvs}))
t = time.time(); alts = []
while time.time() - t < 2.5:
    s = S(); alts.append(s["PLANE_ALTITUDE"])
    if s.get("PLANE_ALT_ABOVE_GROUND", 999) < 100:
        print("   !! AGL<100 安全中止"); break
    time.sleep(0.2)
a = S()
drop = balt - a["PLANE_ALTITUDE"]
# 用高度差算真实平均下降率
dur = time.time() - t
print("== 效果: 真实掉高 %.1fft / %.1fs = 平均 %.1f ft/s ==" % (drop, dur, drop/dur if dur else 0))
print(">> 恢复悬停(5s)")
c.ap_rotor_point(a["PLANE_LATITUDE"], a["PLANE_LONGITUDE"]); time.sleep(5)
r = S()
print("   恢复后 AGL=%.0f ASL=%.1f (与基线 %.1f 比，趋稳=OK)" % (r.get("PLANE_ALT_ABOVE_GROUND"), r["PLANE_ALTITUDE"], balt))
print("CAL3 done")
