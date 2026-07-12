# -*- coding: utf-8 -*-
"""诊断 AP 旋翼定点的经纬度顺序：传送到风切变起点(800ft)→定点飞向停机坪(SWAP=False约定)
→测5s实际移动方位 vs 应有方位。若两者接近=不用反(SWAP_LATLNG=False)；差~90/180=要反(True)。"""
import time, config, geo
config.USE_MOCK = False
config.DEVKIT_BASE_URL = "http://127.0.0.1:5000"
from devkit_client import DevKitClient
c = DevKitClient()
HP = config.HELIPAD
s = config.SCENARIOS["wind_shear"]["restore"]

# 传送到起点(800ft 空中)
for n, v in [("PLANE_LATITUDE", s["lat"]), ("PLANE_LONGITUDE", s["lng"]),
             ("PLANE_ALTITUDE", 800.0), ("PLANE_HEADING_DEGREES_TRUE", s.get("heading", 0)),
             ("PLANE_PITCH_DEGREES", 0.0), ("PLANE_BANK_DEGREES", 0.0)]:
    c.set_param(n, v)
time.sleep(2.5)
st0 = c.get_state()
lat0, lng0 = st0["PLANE_LATITUDE"], st0["PLANE_LONGITUDE"]
brg_hp = geo.bearing_deg(lat0, lng0, HP["lat"], HP["lng"])
print("起点 %.5f,%.5f  应飞向停机坪方位=%.0f°" % (lat0, lng0, brg_hp))

# 定点飞向停机坪（按当前 SWAP_LATLNG=%s 约定）
print("当前 config.SWAP_LATLNG =", config.SWAP_LATLNG)
c.ap_rotor_point(HP["lat"], HP["lng"])
time.sleep(6)
st1 = c.get_state()
lat1, lng1 = st1["PLANE_LATITUDE"], st1["PLANE_LONGITUDE"]
c.ap_stop()
moved = geo.distance_m(lat0, lng0, lat1, lng1)
if moved > 3:
    brg_mov = geo.bearing_deg(lat0, lng0, lat1, lng1)
    diff = abs((brg_mov - brg_hp + 180) % 360 - 180)
    verdict = "✓方向对(不用反)" if diff < 45 else ("✗反了~90(要SWAP=True)" if 45 <= diff <= 135 else "✗反向~180")
    print("实际移动=%.0fm 方位=%.0f°  与应有差=%.0f°  → %s" % (moved, brg_mov, diff, verdict))
else:
    print("几乎没动(%.0fm)——可能在地面/AP没接管；换法再测" % moved)
