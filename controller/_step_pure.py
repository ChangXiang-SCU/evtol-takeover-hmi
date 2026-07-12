# -*- coding: utf-8 -*-
"""阶梯式进近到停机坪上方(纯操纵版) —— 只用 油门:1 + 升降舵, 飞行中不写姿态。
起点摆一次朝向(对准停机坪再左让 CRAB 度, 补 ~19° 右偏), 之后只 set 油门/升降舵。
- 平飞段: 油门固定前推 + 升降舵0; 下降段: 油门仍前推 + 升降舵-0.9。
- 逼近到停机坪上方~30ft、水平<25m 即停(不触地); 越飞越远(>起点+12m)则中止。"""
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
CRAB = 20.0
ELEV_DN = -0.9
ARRIVE_ALT = HP["alt_ft"] + 30.0
ARRIVE_DIST = 25.0
FLOOR_AGL = 18.0
HZ = 12.0
MAX_WALL = 42.0


def S():
    return c.get_state() or {}

def gv(st, k, d=0.0):
    v = st.get(k, d)
    return d if v is None else v

def dist_brg():
    st = S()
    la, lo = gv(st, "PLANE_LATITUDE"), gv(st, "PLANE_LONGITUDE")
    return st, geo.distance_m(la, lo, HP["lat"], HP["lng"]), geo.bearing_deg(la, lo, HP["lat"], HP["lng"])

# ---- 起点: 停机坪正南 50m, 250ft, 朝向=对准停机坪-20°(补右偏); 不用 ap_rotor_point 以免重置航向 ----
s0 = geo.move(HP["lat"], HP["lng"], 180.0, 50.0)
brg0 = geo.bearing_deg(s0[0], s0[1], HP["lat"], HP["lng"])
aim = (brg0 - CRAB) % 360.0
c.ap_stop(); time.sleep(0.2)
for n, v in [("PLANE_LATITUDE", s0[0]), ("PLANE_LONGITUDE", s0[1]), ("PLANE_ALTITUDE", 250.0),
             ("PLANE_HEADING_DEGREES_TRUE", aim), ("PLANE_PITCH_DEGREES", 0.0), ("PLANE_BANK_DEGREES", 0.0)]:
    c.set_param(n, v)
for n in ("VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"):
    c.set_param(n, 0.0)
time.sleep(3.0)   # 稳定(不加AP, 保住朝向)
b = S(); neut = gv(b, THR, 46.5)
FWD_THR = min(neut + 26.0, 82.0)
_, d0, _ = dist_brg()
print("起点 alt=%.0f 距停机坪=%.0fm 目标朝向=%.0f 实际航向=%.1f 中性油门=%.1f 前飞油门=%.1f" % (
    gv(b, "PLANE_ALTITUDE"), d0, aim, gv(b, "PLANE_HEADING_DEGREES_TRUE"), neut, FWD_THR))
print("(以下只写 油门 + 升降舵, 不写任何姿态; 航向只读)")

W0 = time.time()


def seg(kind, dur):
    t = time.time(); nxt = 0.0
    while time.time() - t < dur:
        st, dist, brg = dist_brg()
        alt = gv(st, "PLANE_ALTITUDE"); agl = gv(st, "PLANE_ALT_ABOVE_GROUND", 9e9)
        c.set_param(THR, FWD_THR)
        c.set_param(ELEV, 0.0 if kind == "level" else ELEV_DN)
        el = time.time() - t
        if el >= nxt:
            print("   [%-5s] 距停机坪%5.0fm 高%4.0fft 航向%5.1f(只读) AGL%.0f" % (
                kind, dist, alt, gv(st, "PLANE_HEADING_DEGREES_TRUE"), agl))
            nxt = el + 1.2
        if agl < FLOOR_AGL:
            return "AGL", dist, alt
        if dist < ARRIVE_DIST and alt <= ARRIVE_ALT + 15:
            return "arrive", dist, alt
        if dist > d0 + 12.0:
            return "diverge", dist, alt
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
            print("  >> 到时限"); break
        aborted, dist, alt = seg("level", 3.5)
        if aborted:
            break
        if alt > ARRIVE_ALT + 8:
            aborted, dist, alt = seg("down", 3.5)
            if aborted:
                break
finally:
    st, dist, brg = dist_brg(); alt = gv(st, "PLANE_ALTITUDE")
    c.set_param(ELEV, 0.0); c.set_param(THR, neut)
    c.ap_rotor_point(HP["lat"], HP["lng"])
    tag = {"AGL": " (离地保护)", "arrive": " (已到达)", "diverge": " (飞偏, 已中止)"}.get(aborted, "")
    print("== 结束: 距停机坪%.0fm 高度%.0fft%s | 停泊悬停 ==" % (dist, alt, tag))
