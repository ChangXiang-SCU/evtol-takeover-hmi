# -*- coding: utf-8 -*-
"""立即把飞机传送回风切变起点, 舵面/速度清零, 切 DevKit 定点悬停(不做任何高频控制)。"""
import os, time
import config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = os.environ.get("DEVKIT_URL", "http://127.0.0.1:5000")
config.HTTP_TIMEOUT_S = 6
from devkit_client import DevKitClient

c = DevKitClient()
def gv(st, k, d=0.0):
    v = st.get(k, d); return d if v is None else v

P = config.SCENARIOS["wind_shear"]["restore"]
c.ap_stop(); time.sleep(0.3)
for n in ("ELEVATOR_POSITION", "AILERON_POSITION", "RUDDER_POSITION"):
    c.set_param(n, 0.0)
for n, v in [("PLANE_LATITUDE", P["lat"]), ("PLANE_LONGITUDE", P["lng"]), ("PLANE_ALTITUDE", P["alt_ft"]),
             ("PLANE_HEADING_DEGREES_TRUE", P["heading"]), ("PLANE_PITCH_DEGREES", 0.0), ("PLANE_BANK_DEGREES", 0.0)]:
    c.set_param(n, v)
for n in ("VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"):
    c.set_param(n, 0.0)
c.ap_rotor_point(P["lat"], P["lng"])
time.sleep(2.0)
st = c.get_state() or {}
print("已传送回起点: alt=%.0f AGL=%.0f 航向=%.2f 油门:1=%.1f VBY=%.1f 升降舵=%.2f → 定点悬停(无高频控制)" % (
    gv(st, "PLANE_ALTITUDE"), gv(st, "PLANE_ALT_ABOVE_GROUND"), gv(st, "PLANE_HEADING_DEGREES_TRUE"),
    gv(st, "GENERAL_ENG_THROTTLE_LEVER_POSITION:1"), gv(st, "VELOCITY_BODY_Y"), gv(st, "ELEVATOR_POSITION")))
