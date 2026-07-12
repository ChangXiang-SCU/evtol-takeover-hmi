# -*- coding: utf-8 -*-
"""用油门:1 闭环让这台 eVTOL 丝滑水平向前定速巡航(稳定版)。
实测结论(2026-07-09):
  · 油门:1 = 前后推进(可写、生效); 高度不受影响。P+I 闭环跟踪目标前进地速 → 定速、不狂奔。
  · 航向/横滚 写入生效 → 锁死 → 姿态稳、走直线。
  · VELOCITY_BODY_X 写入飞行中不生效(指令-12 回读~0), 直接写航向做偏流会震荡;
    ~15° 推力侧偏留给下一步"飞到点"用方向舵闭环。
  · 传送后中性油门会漂(33~58), 故按"绝对油门"限幅到 96, 并多稳定几秒。
用法: python -X utf8 _fwd_fly.py [目标m/s=4.0] [巡航s=10] [KP=4.5] [KI=3.2]"""
import os, sys, time, math
import config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = os.environ.get("DEVKIT_URL", "http://127.0.0.1:5000")
config.HTTP_TIMEOUT_S = 6
import geo
from devkit_client import DevKitClient

c = DevKitClient()
THR = "GENERAL_ENG_THROTTLE_LEVER_POSITION:1"
HDG = "PLANE_HEADING_DEGREES_TRUE"; BANK = "PLANE_BANK_DEGREES"
VBX, VBY, VBZ = "VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"
VT = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
CRUISE = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
KP = float(sys.argv[3]) if len(sys.argv) > 3 else 4.5
KI = float(sys.argv[4]) if len(sys.argv) > 4 else 3.2
THR_MIN, THR_MAX = 2.0, 96.0      # 绝对油门限幅(不再按中性偏置, 避免中性漂移导致饱和)
RAMP, RAMPDN, HZ = 3.0, 2.0, 16.0
FLOOR_AGL = 200.0
EMA = 0.35
P = config.SCENARIOS["wind_shear"]["restore"]


def S():
    return c.get_state() or {}

def gv(st, k, d=0.0):
    v = st.get(k, d)
    return d if v is None else v

c.ap_stop(); time.sleep(0.2)
for n, v in [("PLANE_LATITUDE", P["lat"]), ("PLANE_LONGITUDE", P["lng"]), ("PLANE_ALTITUDE", P["alt_ft"]),
             (HDG, P["heading"]), ("PLANE_PITCH_DEGREES", 0.0), (BANK, 0.0)]:
    c.set_param(n, v)
for n in (VBX, VBY, VBZ):
    c.set_param(n, 0.0)
c.ap_rotor_point(P["lat"], P["lng"]); time.sleep(5.0)     # 多稳定几秒, 让旋翼转速稳定

b = S()
lat0, lon0 = b.get("PLANE_LATITUDE"), b.get("PLANE_LONGITUDE")
hdg = gv(b, HDG); alt0 = gv(b, "PLANE_ALTITUDE"); neut = gv(b, THR, 46.5)
if lat0 is None:
    print("无状态,退出"); sys.exit(1)
print("已传送到起点。alt=%.0f AGL=%.0f 航向=%.2f 中性油门=%.2f | 目标%.1f m/s 巡航%.0fs KP=%.1f KI=%.1f" % (
    alt0, gv(b, "PLANE_ALT_ABOVE_GROUND"), hdg, neut, VT, CRUISE, KP, KI))


def proj(st):
    la, lo = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
    if la is None:
        return None
    d = geo.distance_m(lat0, lon0, la, lo)
    if d < 1e-9:
        return (0.0, 0.0)
    rel = math.radians(geo.bearing_deg(lat0, lon0, la, lo) - hdg)
    return (d * math.cos(rel), d * math.sin(rel))


TOT = RAMP + CRUISE + RAMPDN
c.ap_stop(); time.sleep(0.2)
thr_cmd = neut; t0 = time.time(); nxt = 0.0; aborted = ""
pf, pt = 0.0, t0; vema = 0.0; f = r = 0.0
try:
    while True:
        el = time.time() - t0
        if el >= TOT:
            break
        tv = VT * (el / RAMP) if el < RAMP else (VT if el < RAMP + CRUISE else VT * max(0.0, (TOT - el) / RAMPDN))
        st = S(); now = time.time()
        pr = proj(st); agl = gv(st, "PLANE_ALT_ABOVE_GROUND", 9e9)
        if pr is not None:
            f, r = pr
            dt = now - pt
            if dt > 1e-3:
                vema = EMA * ((f - pf) / dt) + (1 - EMA) * vema
                pf, pt = f, now
        err = tv - vema
        # 绝对油门 = 积分(自寻配平) + 比例(快响应), 直接对绝对量限幅
        thr_cmd = max(THR_MIN, min(THR_MAX, thr_cmd + KI * err * (1.0 / HZ)))
        thr = max(THR_MIN, min(THR_MAX, thr_cmd + KP * err))
        c.set_param(THR, thr)
        c.set_param(HDG, hdg)
        c.set_param(BANK, 0.0)
        c.set_param(VBY, 0.0)
        if el >= nxt:
            print("  t=%4.1fs 目标%4.1f 实速%5.2f m/s 油门=%5.1f 前进%6.1fm 侧%5.1fm 航向%.2f Δ高%+4.0fft AGL%.0f" % (
                el, tv, vema, thr, f, r, gv(st, HDG), gv(st, "PLANE_ALTITUDE") - alt0, agl))
            nxt = el + 0.5
        if agl < FLOOR_AGL:
            aborted = "AGL<%.0f" % FLOOR_AGL; break
        time.sleep(1.0 / HZ)
finally:
    st = S(); pr = proj(st)
    if pr:
        f, r = pr
    c.set_param(THR, neut)
    for n in (VBX, VBY, VBZ):
        c.set_param(n, 0.0)
    la, lo = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
    if la is not None:
        c.ap_rotor_point(la, lo)
    print("== 结束: 前进%.1fm 侧偏%.1fm(%.0f%%) 均速%.2fm/s%s | 油门归%.1f 悬停复位 ==" % (
        f, r, 100.0 * abs(r) / max(1.0, f), f / max(0.1, time.time() - t0),
        (" 中止:" + aborted) if aborted else "", neut))
