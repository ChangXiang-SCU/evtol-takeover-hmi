# -*- coding: utf-8 -*-
"""把油门:1 推到指定值并保持, 看这台 eVTOL 前后动多少。
用法: python -X utf8 _push_throttle.py [值=11.99] [秒=8]
从当前位置推(不传送), 只影响前后不影响高度; AGL<150 自动中止; 结束油门归回中性并悬停。"""
import os, sys, time, math
import config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = os.environ.get("DEVKIT_URL", "http://127.0.0.1:5000")
config.HTTP_TIMEOUT_S = 6
import geo
from devkit_client import DevKitClient

c = DevKitClient()
THR = "GENERAL_ENG_THROTTLE_LEVER_POSITION:1"
VAL = float(sys.argv[1]) if len(sys.argv) > 1 else 11.99
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
FLOOR_AGL = 150.0


def S():
    return c.get_state() or {}

def gv(st, k, d=0.0):
    v = st.get(k, d)
    return d if v is None else v

b = S()
lat0, lon0 = b.get("PLANE_LATITUDE"), b.get("PLANE_LONGITUDE")
hdg = gv(b, "PLANE_HEADING_DEGREES_TRUE"); alt0 = gv(b, "PLANE_ALTITUDE"); thr0 = gv(b, THR, 46.5)
print("基线 alt=%.0f AGL=%.0f 航向=%.1f 油门:1=%.2f  ->  目标 %.2f 保持 %.0fs (中性≈%.1f, 低于中性=后退)" % (
    alt0, gv(b, "PLANE_ALT_ABOVE_GROUND"), hdg, thr0, VAL, DUR, thr0))
if lat0 is None:
    print("拿不到状态, 退出"); sys.exit(1)


def proj(st):
    la, lo = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
    if la is None:
        return 0.0, 0.0
    d = geo.distance_m(lat0, lon0, la, lo)
    if d < 1e-6:
        return 0.0, 0.0
    rel = math.radians(geo.bearing_deg(lat0, lon0, la, lo) - hdg)
    return d * math.cos(rel), d * math.sin(rel)


c.ap_stop(); time.sleep(0.2)
t0 = time.time(); nxt = 0.0; aborted = ""; fwd = right = 0.0
try:
    while time.time() - t0 < DUR:
        c.set_param(THR, VAL)
        st = S(); agl = gv(st, "PLANE_ALT_ABOVE_GROUND", 9e9)
        fwd, right = proj(st); dalt = gv(st, "PLANE_ALTITUDE") - alt0; el = time.time() - t0
        if el >= nxt:
            print("  t=%.1fs 前进%+7.1fm 侧移%+6.1fm Δ高%+6.0fft 空速%4.1f 油门:1回读=%.2f AGL=%.0f" % (
                el, fwd, right, dalt, gv(st, "AIRSPEED_TRUE"), gv(st, THR), agl))
            nxt = el + 0.5
        if agl < FLOOR_AGL:
            aborted = "AGL<%.0f" % FLOOR_AGL; break
        time.sleep(0.15)
finally:
    st = S(); fwd, right = proj(st)
    c.set_param(THR, thr0)
    for n in ("VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"):
        c.set_param(n, 0.0)
    la, lo = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
    if la is not None:
        c.ap_rotor_point(la, lo)
    print("== 结束: 前进%.1fm 侧移%.1fm 用时%.1fs%s | 油门归回%.2f, 悬停复位 ==" % (
        fwd, right, time.time() - t0, (" 中止:" + aborted) if aborted else "", thr0))
