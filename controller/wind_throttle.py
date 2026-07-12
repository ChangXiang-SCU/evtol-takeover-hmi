# -*- coding: utf-8 -*-
"""重查风切变机制：阶段1=猛砍油门(旋翼升力真正的杆位)，阶段2=大值密集注入VELOCITY_BODY。
用真实高度差衡量。AGL<120 自动中止。每段结尾恢复悬停。"""
import time, config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = "http://10.7.144.111:5000"
config.HTTP_TIMEOUT_S = 8
from devkit_client import DevKitClient
c = DevKitClient()
def S(): return c.get_state()
THR = "GENERAL_ENG_THROTTLE_LEVER_POSITION:1"

def hover_settle(sec=4):
    s = S(); c.ap_rotor_point(s["PLANE_LATITUDE"], s["PLANE_LONGITUDE"]); time.sleep(sec)
    return S()

def phase(name, injector, dur=3.0):
    b = hover_settle(); balt = b["PLANE_ALTITUDE"]
    print("[%s] 基线 ASL=%.1f AGL=%.0f thr=%.1f" % (name, balt, b.get("PLANE_ALT_ABOVE_GROUND"), b.get(THR)))
    c.ap_stop()
    t = time.time(); nrep = 0; nset = 0; minagl = 9999
    while time.time() - t < dur:
        injector(b); nset += 1
        if time.time() - t > nrep * 0.5:   # 每0.5s查一次AGL(不拖慢注入太多)
            s = S(); nrep += 1; minagl = min(minagl, s.get("PLANE_ALT_ABOVE_GROUND", 9999))
            if s.get("PLANE_ALT_ABOVE_GROUND", 999) < 120:
                print("   !! AGL<120 中止"); break
    a = S()
    print("   == 效果: 掉高 %.1fft | 注入%d次(%.0f次/s) | 期间最低AGL=%.0f ==" % (
        balt - a["PLANE_ALTITUDE"], nset, nset / (time.time()-t), minagl))
    print("   >> 恢复悬停(5s)")
    c.ap_rotor_point(a["PLANE_LATITUDE"], a["PLANE_LONGITUDE"]); time.sleep(5)
    r = S(); print("   恢复后 AGL=%.0f thr=%.1f" % (r.get("PLANE_ALT_ABOVE_GROUND"), r.get(THR)))

s = S(); print("开始 AGL=%.0f thr=%.1f" % (s.get("PLANE_ALT_ABOVE_GROUND"), s.get(THR)))
# 阶段1：猛砍油门到 3
phase("阶段1 砍油门->3", lambda b: c.set_param(THR, 3.0), dur=3.0)
# 阶段2：大值密集注入 VELOCITY_BODY_Y=-50
def big_vel(b):
    c.set_param("VELOCITY_BODY_Y", -50.0)
phase("阶段2 VBY=-50密灌", big_vel, dur=3.0)
print("done")
