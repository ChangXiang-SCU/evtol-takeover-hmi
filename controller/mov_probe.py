# -*- coding: utf-8 -*-
"""飞行能力探查：命令旋翼定点飞到 100m 外，轮询看飞机到底动不动。结尾原地保持。"""
import time, config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = "http://10.7.144.111:5000"
config.HTTP_TIMEOUT_S = 8
from devkit_client import DevKitClient
import geo
c = DevKitClient()
def S(): return c.get_state()

s = S(); lat0, lon0 = s["PLANE_LATITUDE"], s["PLANE_LONGITUDE"]
tlat, tlon = geo.move(lat0, lon0, 0.0, 100)   # 正北 100m
print("起点 %.6f,%.6f  目标(北100m) %.6f,%.6f  AGL=%.0f" % (lat0, lon0, tlat, tlon, s.get("PLANE_ALT_ABOVE_GROUND")))
print("ap_rotor_point ->", c.ap_rotor_point(tlat, tlon))
for i in range(10):
    time.sleep(1)
    s = S()
    moved = geo.distance_m(lat0, lon0, s["PLANE_LATITUDE"], s["PLANE_LONGITUDE"])
    rem = geo.distance_m(s["PLANE_LATITUDE"], s["PLANE_LONGITUDE"], tlat, tlon)
    print("t%2ds 已移动 %.1fm 距目标 %.1fm alt=%.1f VBx=%.1f VBz=%.1f" % (
        i + 1, moved, rem, s["PLANE_ALTITUDE"], s.get("VELOCITY_BODY_X", 0), s.get("VELOCITY_BODY_Z", 0)))
s = S(); c.ap_rotor_point(s["PLANE_LATITUDE"], s["PLANE_LONGITUDE"])   # 原地保持
print("probe done")
