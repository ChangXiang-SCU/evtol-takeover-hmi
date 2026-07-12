# -*- coding: utf-8 -*-
"""风切变剂量标定②：更强的多轴扰动(垂向掉速 + 横滚 + 俯仰)，测量能产生的姿态/掉高偏差。结尾恢复。"""
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
b = S(); balt = b["PLANE_ALTITUDE"]; bvs = b["VERTICAL_SPEED"]
print("   基线 VS=%.2f bank=%.2f pitch=%.2f" % (bvs, b["PLANE_BANK_DEGREES"], b["PLANE_PITCH_DEGREES"]))

dose = dict(down=-18.0, zloss=0.5, ail=0.4, elev=-0.15, dur=3.0)
print(">> 强多轴注入: down=%.0f Zloss=%.0f%% AIL=%.2f ELEV=%.2f dur=%.1fs" % (dose["down"], dose["zloss"]*100, dose["ail"], dose["elev"], dose["dur"]))
z0 = b.get("VELOCITY_BODY_Z") or 0.0
c.ap_stop()
t = time.time(); pk = dict(vs=0, bank=0, pitch=0)
while time.time() - t < dose["dur"]:
    c.set_param("VELOCITY_BODY_Y", dose["down"])
    c.set_param("VELOCITY_BODY_Z", z0 * (1 - dose["zloss"]))
    c.set_param("AILERON_POSITION", dose["ail"])
    c.set_param("ELEVATOR_POSITION", dose["elev"])
    s = S()
    pk["vs"] = max(pk["vs"], abs(s["VERTICAL_SPEED"])); pk["bank"] = max(pk["bank"], abs(s["PLANE_BANK_DEGREES"])); pk["pitch"] = max(pk["pitch"], abs(s["PLANE_PITCH_DEGREES"]))
    time.sleep(0.1)
a = S()
print("== 效果: 掉高 %.1fft | 峰值VS %.1f | 峰值bank %.1f° | 峰值pitch %.1f° ==" % (balt - a["PLANE_ALTITUDE"], pk["vs"], pk["bank"], pk["pitch"]))
# 松开操纵面
c.set_param("AILERON_POSITION", 0.0); c.set_param("ELEVATOR_POSITION", 0.0)
print(">> 恢复悬停(5s)")
c.ap_rotor_point(a["PLANE_LATITUDE"], a["PLANE_LONGITUDE"]); time.sleep(5)
r = S()
print("   恢复后 AGL=%.0f VS=%.2f bank=%.2f (趋稳=OK)" % (r.get("PLANE_ALT_ABOVE_GROUND"), r["VERTICAL_SPEED"], r["PLANE_BANK_DEGREES"]))
print("CAL2 done")
