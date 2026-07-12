# -*- coding: utf-8 -*-
"""把飞机传送回风切变起点并悬停; 打印 航向 与 到停机坪方位 的差, 看起点是不是本就对准停机坪。"""
import os, time
import config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = os.environ.get("DEVKIT_URL", "http://127.0.0.1:5000")
config.HTTP_TIMEOUT_S = 6
import geo
from devkit_client import DevKitClient

c = DevKitClient()
P = config.SCENARIOS["wind_shear"]["restore"]
HP = config.HELIPAD

def gv(s, k, d=0.0):
    v = s.get(k, d); return d if v is None else v

c.ap_stop(); time.sleep(0.2)
for n, v in [("PLANE_LATITUDE", P["lat"]), ("PLANE_LONGITUDE", P["lng"]), ("PLANE_ALTITUDE", P["alt_ft"]),
             ("PLANE_HEADING_DEGREES_TRUE", P["heading"]), ("PLANE_PITCH_DEGREES", 0.0), ("PLANE_BANK_DEGREES", 0.0)]:
    c.set_param(n, v)
for n in ("VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"):
    c.set_param(n, 0.0)
c.ap_rotor_point(P["lat"], P["lng"]); time.sleep(2.0)

st = c.get_state() or {}
la, lo = gv(st, "PLANE_LATITUDE"), gv(st, "PLANE_LONGITUDE")
hdg = gv(st, "PLANE_HEADING_DEGREES_TRUE")
d = geo.distance_m(la, lo, HP["lat"], HP["lng"])
brg = geo.bearing_deg(la, lo, HP["lat"], HP["lng"])
diff = (brg - hdg + 540) % 360 - 180
print("已回起点并悬停。alt=%.0f AGL=%.0f" % (gv(st, "PLANE_ALTITUDE"), gv(st, "PLANE_ALT_ABOVE_GROUND")))
print("到停机坪: 距离=%.0fm  方位=%.1f°  当前航向=%.1f°  航向-方位差=%+.1f°" % (d, brg, hdg, diff))
print("→ 差≈0 说明起点机头本就直指停机坪; 只要往前推油门理论上就朝停机坪去(下一步用纯操纵验证)。")
