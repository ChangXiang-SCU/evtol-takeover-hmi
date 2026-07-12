# -*- coding: utf-8 -*-
"""快速读状态并把飞机恢复到安全悬停(升降舵归0、油门归中性、原地旋翼定点)。"""
import os, time, config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = os.environ.get("DEVKIT_URL", "http://127.0.0.1:5000")
config.HTTP_TIMEOUT_S = 6
import geo
from devkit_client import DevKitClient
c = DevKitClient()
def gv(st, k, d=0.0):
    v = st.get(k, d); return d if v is None else v
HP = config.HELIPAD
st = c.get_state() or {}
la, lo = gv(st, "PLANE_LATITUDE"), gv(st, "PLANE_LONGITUDE")
dist = geo.distance_m(la, lo, HP["lat"], HP["lng"]) if la else -1
print("当前 alt=%.0f AGL=%.0f 距停机坪=%.0fm 油门:1=%.1f 升降舵=%.2f VBX=%.1f VBY=%.1f VBZ=%.1f" % (
    gv(st, "PLANE_ALTITUDE"), gv(st, "PLANE_ALT_ABOVE_GROUND"), dist,
    gv(st, "GENERAL_ENG_THROTTLE_LEVER_POSITION:1"), gv(st, "ELEVATOR_POSITION"),
    gv(st, "VELOCITY_BODY_X"), gv(st, "VELOCITY_BODY_Y"), gv(st, "VELOCITY_BODY_Z")))
c.set_param("ELEVATOR_POSITION", 0.0)
for n in ("VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"):
    c.set_param(n, 0.0)
if la:
    c.ap_rotor_point(la, lo)
time.sleep(2.0)
st = c.get_state() or {}
print("恢复后 alt=%.0f AGL=%.0f VBY=%.1f → 已原地悬停" % (
    gv(st, "PLANE_ALTITUDE"), gv(st, "PLANE_ALT_ABOVE_GROUND"), gv(st, "VELOCITY_BODY_Y")))
