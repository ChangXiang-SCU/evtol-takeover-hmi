# -*- coding: utf-8 -*-
"""纯操纵·阶梯进近: 从进近起点 只用 油门(前后)+升降舵(升降), 平飞一段→下降一段→交替,
直到停机坪正上方(不触地, 停在坪上方约40ft)。
飞行中不写任何姿态/位置/速度(仅起点一次性传送做实验复位) —— 像人开飞机。
起点机头 = 到坪方位 - 18°, 因为油门推力在机头右侧约18° → 合成航迹正指停机坪, 全程不需给航向。"""
import os, time
import config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = os.environ.get("DEVKIT_URL", "http://127.0.0.1:5000")
config.HTTP_TIMEOUT_S = 6
import geo
from devkit_client import DevKitClient

c = DevKitClient()
THR = "GENERAL_ENG_THROTTLE_LEVER_POSITION:1"; ELEV = "ELEVATOR_POSITION"
HP = config.HELIPAD
COUPLE = 18.0
ELEV_DN = -0.85
ARRIVE_DIST = 22.0
FLOOR_AGL = 22.0
HZ = 12.0
MAX_WALL = 58.0


def S():
    return c.get_state() or {}

def gv(st, k, d=0.0):
    v = st.get(k, d); return d if v is None else v

def hdist(st=None):
    st = st or S()
    return st, geo.distance_m(gv(st, "PLANE_LATITUDE"), gv(st, "PLANE_LONGITUDE"), HP["lat"], HP["lng"])

# 起点: 停机坪正南 130m, 360ft; 机头 = 到坪方位 - COUPLE
s0 = geo.move(HP["lat"], HP["lng"], 180.0, 130.0)
brg0 = geo.bearing_deg(s0[0], s0[1], HP["lat"], HP["lng"])
hdg0 = (brg0 - COUPLE) % 360.0
c.ap_stop(); time.sleep(0.2)
for n, v in [("PLANE_LATITUDE", s0[0]), ("PLANE_LONGITUDE", s0[1]), ("PLANE_ALTITUDE", 360.0),
             ("PLANE_HEADING_DEGREES_TRUE", hdg0), ("PLANE_PITCH_DEGREES", 0.0), ("PLANE_BANK_DEGREES", 0.0)]:
    c.set_param(n, v)
for n in ("VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"):
    c.set_param(n, 0.0)
c.ap_rotor_point(s0[0], s0[1]); time.sleep(4.0)
c.ap_stop(); time.sleep(0.3)      # 接管
b = S(); neut = gv(b, THR, 46.5)
FWD = min(neut + 24.0, 82.0)
HOVER_ALT = HP["alt_ft"] + 40.0
_, d0 = hdist(b)
print("接管起点: alt=%.0f AGL=%.0f 机头=%.1f 到坪方位=%.1f 距离=%.0fm 中性油门=%.1f 平飞油门=%.1f 目标停坪上方%.0fft" % (
    gv(b, "PLANE_ALTITUDE"), gv(b, "PLANE_ALT_ABOVE_GROUND"), gv(b, "PLANE_HEADING_DEGREES_TRUE"),
    brg0, d0, neut, FWD, HOVER_ALT))

W0 = time.time()


def seg(thr, elev, dur, tag, stop_dist=None, stop_alt=None):
    t = time.time(); nxt = 0.0
    while time.time() - t < dur:
        st, dist = hdist(); alt = gv(st, "PLANE_ALTITUDE"); agl = gv(st, "PLANE_ALT_ABOVE_GROUND", 9e9)
        c.set_param(THR, thr); c.set_param(ELEV, elev)
        el = time.time() - t
        if el >= nxt:
            print("   [%-4s] 距停机坪%5.0fm 高%4.0fft AGL%.0f 油门%.0f 升降舵%+.2f" % (tag, dist, alt, agl, thr, elev))
            nxt = el + 1.2
        if agl < FLOOR_AGL:
            return "AGL"
        if stop_dist is not None and dist < stop_dist:
            break
        if stop_alt is not None and alt <= stop_alt:
            break
        time.sleep(1.0 / HZ)
    return ""


aborted = ""
try:
    for cyc in range(9):
        st, dist = hdist(); alt = gv(st, "PLANE_ALTITUDE")
        print("周期%d: 距停机坪%.0fm 高度%.0fft (还需降%.0fft)" % (cyc + 1, dist, alt, max(0.0, alt - HOVER_ALT)))
        if dist < ARRIVE_DIST and alt <= HOVER_ALT + 8:
            print("  >> 已到停机坪正上方"); break
        if time.time() - W0 > MAX_WALL:
            print("  >> 到时限, 收尾"); break
        # 平飞段(还没水平到位才飞)
        if dist > ARRIVE_DIST:
            aborted = seg(FWD, 0.0, 5.0, "平飞", stop_dist=ARRIVE_DIST)
            if aborted:
                break
        # 下降段(还高才降; 已到坪上方就原地降不再前冲)
        st, dist = hdist(); alt = gv(st, "PLANE_ALTITUDE")
        if alt > HOVER_ALT + 8:
            thr_d = neut if dist < ARRIVE_DIST + 15 else FWD
            aborted = seg(thr_d, ELEV_DN, 5.0, "下降", stop_alt=HOVER_ALT)
            if aborted:
                break
finally:
    for _ in range(3):
        c.set_param(ELEV, 0.0); c.set_param(THR, neut); time.sleep(0.1)
    st, dfin = hdist()
    tag = " (触发离地保护)" if aborted == "AGL" else ""
    print("== 结束: 距停机坪%.0fm 高度%.0fft(坪上方%.0fft)%s | 收油门+升降舵回中, 悬停 ==" % (
        dfin, gv(st, "PLANE_ALTITUDE"), gv(st, "PLANE_ALTITUDE") - HP["alt_ft"], tag))
