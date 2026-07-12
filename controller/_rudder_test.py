# -*- coding: utf-8 -*-
"""快速测: 写 RUDDER_POSITION 能不能让这台 eVTOL 偏航(改航向)? 用完回中。"""
import os, time
import config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = os.environ.get("DEVKIT_URL", "http://127.0.0.1:5000")
config.HTTP_TIMEOUT_S = 6
from devkit_client import DevKitClient
c = DevKitClient()
RUD = "RUDDER_POSITION"; HDG = "PLANE_HEADING_DEGREES_TRUE"
def gv(st, k, d=0.0):
    v = st.get(k, d); return d if v is None else v
def S(): return c.get_state() or {}

c.ap_stop(); time.sleep(0.3)
h0 = gv(S(), HDG)
print("初始航向=%.1f" % h0)
for val in (0.6, -0.6):
    print("--- 方向舵=%+.1f 保持4s ---" % val)
    t = time.time()
    while time.time() - t < 4.0:
        c.set_param(RUD, val)
        st = S()
        print("  舵=%+.1f 回读=%+.2f 航向=%.1f 偏航率=%.3f" % (
            val, gv(st, RUD), gv(st, HDG), gv(st, "ROTATION_VELOCITY_BODY_Y")))
        time.sleep(0.5)
c.set_param(RUD, 0.0)
time.sleep(0.5)
print("回中后航向=%.1f" % gv(S(), HDG))
