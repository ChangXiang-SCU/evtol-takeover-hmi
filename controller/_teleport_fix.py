# -*- coding: utf-8 -*-
"""重载后验证:只用同事式传送(ap_stop→写位姿→清零VELOCITY_BODY),看是否稳住800ft。不碰油门。"""
import time, config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = "http://127.0.0.1:5000"
import devkit_client as k

c = k.DevKitClient()
p = config.SCENARIOS["wind_shear"]["restore"]

def st():
    return c.get_state() or {}

def row(tag):
    s = st()
    print("  %-8s alt=%6.1f vs=%8.1f on_gnd=%s thr=%.1f hdg=%.1f" % (
        tag, s.get("PLANE_ALTITUDE") or 0, s.get("VERTICAL_SPEED") or 0,
        s.get("SIM_ON_GROUND"), s.get("GENERAL_ENG_THROTTLE_LEVER_POSITION:1") or 0,
        s.get("PLANE_HEADING_DEGREES_TRUE") or 0))

print("重载后当前状态:"); row("now")
print("=== 同事式传送到起点(800ft),盯7秒 ===")
c.ap_stop(); time.sleep(0.3)
for n, v in [("PLANE_LATITUDE", p["lat"]), ("PLANE_LONGITUDE", p["lng"]), ("PLANE_ALTITUDE", p["alt_ft"]),
             ("PLANE_HEADING_DEGREES_TRUE", p["heading"]), ("PLANE_PITCH_DEGREES", 0.0), ("PLANE_BANK_DEGREES", 0.0)]:
    c.set_param(n, v)
for n in ["VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"]:
    c.set_param(n, 0.0)
t0 = time.time(); last = -1
while time.time() - t0 < 7:
    e = int(time.time() - t0)
    if e != last:
        row("t=%ds" % e); last = e
    time.sleep(0.4)
s = st()
held = abs((s.get("PLANE_ALTITUDE") or 0) - p["alt_ft"]) < 40
print("结论:", "✅ 稳住了(没掉)" if held else "❌ 还在掉")
