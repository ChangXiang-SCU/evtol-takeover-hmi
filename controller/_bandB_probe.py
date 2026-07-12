# -*- coding: utf-8 -*-
"""方案B探针:悬停态小幅试 ELEVATOR(前进?) 和 油门(垂直?),看清控制映射。破坏了就重载。"""
import time, config, geo
config.USE_MOCK = False
config.DEVKIT_BASE_URL = "http://127.0.0.1:5000"
import devkit_client as k

c = k.DevKitClient(); HP = config.HELIPAD; p = config.SCENARIOS["wind_shear"]["restore"]
TH = "GENERAL_ENG_THROTTLE_LEVER_POSITION:1"

def s():
    return c.get_state() or {}
def gv(st, n, d=0.0):
    v = st.get(n); return d if v is None else v
def show(tag):
    st = s()
    print("  %-12s alt=%6.1f vs=%7.1f 空速=%4.1f dist=%5.0f pitch=%5.1f 油门=%.1f elev=%.3f" % (
        tag, gv(st, "PLANE_ALTITUDE"), gv(st, "VERTICAL_SPEED"), gv(st, "AIRSPEED_TRUE"),
        geo.distance_m(gv(st, "PLANE_LATITUDE"), gv(st, "PLANE_LONGITUDE"), HP["lat"], HP["lng"]),
        gv(st, "PLANE_PITCH_DEGREES"), gv(st, TH), gv(st, "ELEVATOR_POSITION")))

# 传送到起点(同事式)
c.ap_stop(); time.sleep(0.3)
for n, v in [("PLANE_LATITUDE", p["lat"]), ("PLANE_LONGITUDE", p["lng"]), ("PLANE_ALTITUDE", p["alt_ft"]),
             ("PLANE_HEADING_DEGREES_TRUE", p["heading"]), ("PLANE_PITCH_DEGREES", 0.0), ("PLANE_BANK_DEGREES", 0.0)]:
    c.set_param(n, v)
for n in ["VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"]:
    c.set_param(n, 0.0)
time.sleep(1.5)

print("=== 基线悬停(应alt稳、空速~0) ===")
for _ in range(3):
    show("hover"); time.sleep(0.6)

print("=== 测试1: ELEVATOR=+0.5 4s → 前进? ===")
for _ in range(6):
    c.set_param("ELEVATOR_POSITION", 0.5); show("elev+0.5"); time.sleep(0.6)
c.set_param("ELEVATOR_POSITION", 0.0)
for _ in range(3):
    show("恢复"); time.sleep(0.6)

print("=== 测试2: 油门 53.5→48 4s → 下降? (看恢复) ===")
for _ in range(6):
    c.set_param(TH, 48.0); show("油门48"); time.sleep(0.6)
c.set_param(TH, 53.515625)
for _ in range(4):
    show("恢复"); time.sleep(0.6)

print("=== 测试3: 油门 53.5→60 4s → 上升/前进? ===")
for _ in range(6):
    c.set_param(TH, 60.0); show("油门60"); time.sleep(0.6)
c.set_param(TH, 53.515625)
for _ in range(4):
    show("恢复"); time.sleep(0.6)
print("探针结束")
