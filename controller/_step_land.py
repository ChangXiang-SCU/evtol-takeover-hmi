# -*- coding: utf-8 -*-
"""阶梯式下降飞到停机坪(ZKMZN)演示。
关键: 油门:1 全程推到一个固定位置保持不动(持续前进, 速度才能建立);
      升降舵在 0(平飞段) 与 -0.9(下降段) 之间切 → 高度走阶梯; 每段重新对准停机坪。
到停机坪上方~30ft 且水平<20m → 悬停结束。"""
import os, time, math
import config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = os.environ.get("DEVKIT_URL", "http://127.0.0.1:5000")
config.HTTP_TIMEOUT_S = 6
import geo
from devkit_client import DevKitClient

c = DevKitClient()
THR = "GENERAL_ENG_THROTTLE_LEVER_POSITION:1"; ELEV = "ELEVATOR_POSITION"
HDG = "PLANE_HEADING_DEGREES_TRUE"; BANK = "PLANE_BANK_DEGREES"
VBX, VBY, VBZ = "VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"
HP = config.HELIPAD
CRAB = 15.0
ELEV_DN = -0.9
ARRIVE_ALT = HP["alt_ft"] + 30.0
ARRIVE_DIST = 20.0
FLOOR_AGL = 20.0
HZ = 12.0
MAX_WALL = 48.0


def S():
    return c.get_state() or {}

def gv(st, k, d=0.0):
    v = st.get(k, d)
    return d if v is None else v

def dist_brg():
    st = S()
    la, lo = gv(st, "PLANE_LATITUDE"), gv(st, "PLANE_LONGITUDE")
    return st, geo.distance_m(la, lo, HP["lat"], HP["lng"]), geo.bearing_deg(la, lo, HP["lat"], HP["lng"])

# 起点: 停机坪正南 55m, 300ft, 机头朝北
s0 = geo.move(HP["lat"], HP["lng"], 180.0, 55.0)
c.ap_stop(); time.sleep(0.2)
for n, v in [("PLANE_LATITUDE", s0[0]), ("PLANE_LONGITUDE", s0[1]), ("PLANE_ALTITUDE", 300.0),
             (HDG, 0.0), ("PLANE_PITCH_DEGREES", 0.0), (BANK, 0.0)]:
    c.set_param(n, v)
for n in (VBX, VBY, VBZ):
    c.set_param(n, 0.0)
c.ap_rotor_point(s0[0], s0[1]); time.sleep(4.0)
b = S(); neut = gv(b, THR, 46.5)
FWD_THR = min(neut + 22.0, 80.0)      # 全程固定平飞油门(温和)
_, d0, _ = dist_brg()
print("起点 alt=%.0f 距停机坪=%.0fm 中性油门=%.1f 固定平飞油门=%.1f | 目标:上方%.0fft 水平<%.0fm" % (
    gv(b, "PLANE_ALTITUDE"), d0, neut, FWD_THR, ARRIVE_ALT, ARRIVE_DIST))

W0 = time.time()


def seg(kind, hd, dur):
    """油门恒为 FWD_THR; kind='level'→升降舵0, 'down'→升降舵ELEV_DN。"""
    t = time.time(); nxt = 0.0
    while time.time() - t < dur:
        st, dist, brg = dist_brg()
        alt = gv(st, "PLANE_ALTITUDE"); agl = gv(st, "PLANE_ALT_ABOVE_GROUND", 9e9)
        c.set_param(THR, FWD_THR)                     # 油门保持不动
        c.set_param(ELEV, 0.0 if kind == "level" else ELEV_DN)
        c.set_param(HDG, hd); c.set_param(BANK, 0.0)
        if kind == "level":
            c.set_param(VBY, 0.0)
        el = time.time() - t
        if el >= nxt:
            print("   [%-5s] 距停机坪%5.0fm 高%4.0fft 航向%5.1f AGL%.0f" % (kind, dist, alt, gv(st, HDG), agl))
            nxt = el + 1.2
        if agl < FLOOR_AGL:
            return "AGL", dist, alt
        if dist < ARRIVE_DIST and alt <= ARRIVE_ALT + 15:
            return "arrive", dist, alt
        if kind == "down" and alt <= ARRIVE_ALT:
            break
        time.sleep(1.0 / HZ)
    return "", dist, alt


aborted = ""
try:
    for cyc in range(8):
        st, dist, brg = dist_brg(); alt = gv(st, "PLANE_ALTITUDE")
        print("周期%d: 距停机坪%.0fm 高度%.0fft (还需降%.0fft)" % (cyc + 1, dist, alt, max(0.0, alt - ARRIVE_ALT)))
        if dist < ARRIVE_DIST and alt <= ARRIVE_ALT + 15:
            print("  >> 到达停机坪上方"); break
        if time.time() - W0 > MAX_WALL:
            print("  >> 到时限, 收尾"); break
        hd = (brg - CRAB) % 360.0
        # 平飞段
        aborted, dist, alt = seg("level", hd, 3.5)
        if aborted in ("AGL", "arrive"):
            break
        # 下降段(还高就降一级)
        if alt > ARRIVE_ALT + 8:
            aborted, dist, alt = seg("down", hd, 4.0 if (alt - ARRIVE_ALT) > 60 else 2.5)
            if aborted in ("AGL", "arrive"):
                break
finally:
    st, dist, brg = dist_brg(); alt = gv(st, "PLANE_ALTITUDE")
    c.set_param(THR, neut); c.set_param(ELEV, 0.0)
    for n in (VBX, VBY, VBZ):
        c.set_param(n, 0.0)
    c.ap_rotor_point(HP["lat"], HP["lng"])
    tag = {"AGL": " (触发离地保护)", "arrive": " (已到达)"}.get(aborted, "")
    print("== 结束: 距停机坪%.0fm 高度%.0fft%s | 已切停机坪定点悬停 ==" % (dist, alt, tag))
