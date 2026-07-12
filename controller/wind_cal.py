# -*- coding: utf-8 -*-
"""风切变剂量标定：稳定悬停 -> 注入一次扰动并测量效果 -> 立即恢复悬停。剂量按 AGL 自适应。"""
import time, config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = "http://10.7.144.111:5000"
config.HTTP_TIMEOUT_S = 8
from devkit_client import DevKitClient
c = DevKitClient()
def S(): return c.get_state()

s = S()
agl = s.get("PLANE_ALT_ABOVE_GROUND"); alt = s.get("PLANE_ALTITUDE")
lat, lon = s["PLANE_LATITUDE"], s["PLANE_LONGITUDE"]
print("当前 AGL=%.0fft ASL=%.0fft" % (agl, alt))

print(">> 先稳定悬停(4s)...")
c.ap_rotor_point(lat, lon); time.sleep(4)
b = S(); balt = b["PLANE_ALTITUDE"]; bagl = b.get("PLANE_ALT_ABOVE_GROUND")
print("   稳定后 AGL=%.0f VS=%.2f pitch=%.2f bank=%.2f" % (bagl, b["VERTICAL_SPEED"], b["PLANE_PITCH_DEGREES"], b["PLANE_BANK_DEGREES"]))

if bagl is not None and bagl < 120:
    dose = dict(down=-3.0, zloss=0.25, dur=1.5); print("   AGL 偏低 -> 保守剂量")
else:
    dose = dict(down=-8.0, zloss=0.40, dur=2.5)
print(">> 注入风切变: down=%.1fft/s  Zloss=%.0f%%  dur=%.1fs" % (dose["down"], dose["zloss"]*100, dose["dur"]))

z0 = b.get("VELOCITY_BODY_Z") or 0.0
c.ap_stop()
t = time.time(); maxvs = 0; maxbank = 0; maxpitch = 0
while time.time() - t < dose["dur"]:
    c.set_param("VELOCITY_BODY_Y", dose["down"])
    c.set_param("VELOCITY_BODY_Z", z0 * (1 - dose["zloss"]))
    s = S()
    maxvs = max(maxvs, abs(s["VERTICAL_SPEED"])); maxbank = max(maxbank, abs(s["PLANE_BANK_DEGREES"])); maxpitch = max(maxpitch, abs(s["PLANE_PITCH_DEGREES"]))
    time.sleep(0.1)
a = S()
print("== 效果: 掉高 %.1fft | 峰值VS %.1fft/s | 峰值bank %.1f° | 峰值pitch %.1f° ==" % (balt - a["PLANE_ALTITUDE"], maxvs, maxbank, maxpitch))

print(">> 恢复悬停(4s)...")
c.ap_rotor_point(a["PLANE_LATITUDE"], a["PLANE_LONGITUDE"]); time.sleep(4)
r = S()
print("   恢复后 AGL=%.0f VS=%.2f (趋于 0 = 已稳)" % (r.get("PLANE_ALT_ABOVE_GROUND"), r["VERTICAL_SPEED"]))
print("CAL done  dose=%r" % dose)
