# -*- coding: utf-8 -*-
"""垂直降落演示 —— 只用「操纵」不写姿态: 升降舵控下沉率, 油门保持中性(不前后)。
像人开飞机: 接管 → 按离地高度分级控制下沉率(高处快, 贴地拉平) → 触地收舵。
只写 ELEVATOR_POSITION 和 油门:1(=中性); 不写 航向/横滚/俯仰/经纬高/体轴速度。
(升降舵最大约给 -11 ft/s 下沉, 相当于这台 eVTOL 的"总距")。"""
import os, time
import config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = os.environ.get("DEVKIT_URL", "http://127.0.0.1:5000")
config.HTTP_TIMEOUT_S = 6
from devkit_client import DevKitClient

c = DevKitClient()
THR = "GENERAL_ENG_THROTTLE_LEVER_POSITION:1"; ELEV = "ELEVATOR_POSITION"
HZ = 12.0
MAX_WALL = 88.0
EMA = 0.4


def S():
    return c.get_state() or {}

def gv(st, k, d=0.0):
    v = st.get(k, d)
    return d if v is None else v

def target_vs(agl):
    """按离地高度定目标下沉率(ft/s, 负=下降): 高处快, 贴地拉平。"""
    if agl > 100: return -10.0
    if agl > 40:  return -6.0
    if agl > 15:  return -3.0
    if agl > 6:   return -1.8
    return -1.0

b = S()
neut = gv(b, THR, 46.5)
agl0 = gv(b, "PLANE_ALT_ABOVE_GROUND"); alt0 = gv(b, "PLANE_ALTITUDE")
on_gnd = gv(b, "SIM_ON_GROUND", 0)
print("接管前: alt=%.0f AGL=%.0f 在地=%s 中性油门=%.1f 升降舵=%.2f" % (
    alt0, agl0, on_gnd, neut, gv(b, ELEV, 0.0)))
if on_gnd >= 1 or agl0 < 2.0:
    print("已经在地面上, 无需降落。"); raise SystemExit

c.ap_stop(); time.sleep(0.3)      # 接管(松开定点保持), 之后只用操纵

t0 = time.time(); nxt = 0.0; pt = t0; palt = gv(S(), "PLANE_ALTITUDE"); vs = 0.0
agl_e = agl0; landed = False
try:
    while time.time() - t0 < MAX_WALL:
        st = S(); now = time.time()
        alt = gv(st, "PLANE_ALTITUDE"); agl = gv(st, "PLANE_ALT_ABOVE_GROUND", 9e9)
        og = gv(st, "SIM_ON_GROUND", 0)
        agl_e = EMA * agl + (1 - EMA) * agl_e          # 平滑 AGL(读数有跳变)
        dt = now - pt
        if dt > 1e-3:
            vs = EMA * ((alt - palt) / dt) + (1 - EMA) * vs   # 下沉率 ft/s
            palt, pt = alt, now
        if og >= 1 or agl < 1.5:
            landed = True; break
        tvs = target_vs(agl_e)
        elev = tvs / 11.5 + 0.06 * (tvs - vs)          # 前馈 + 比例
        if vs < -14.0:                                  # 下太猛 → 拉平
            elev = 0.4
        elev = max(-1.0, min(0.5, elev))
        c.set_param(ELEV, elev)
        c.set_param(THR, neut)                          # 油门中性: 不前后
        el = time.time() - t0
        if el >= nxt:
            print("  t=%4.1fs AGL≈%5.1f 高=%5.0fft 下沉率=%5.1f 目标=%5.1f 升降舵=%+.2f" % (
                el, agl_e, alt, vs, tvs, elev))
            nxt = el + 1.0
        time.sleep(1.0 / HZ)
finally:
    for _ in range(3):
        c.set_param(ELEV, 0.0); c.set_param(THR, neut); time.sleep(0.1)
    st = S()
    print("== %s: AGL=%.1f 高=%.0fft 在地=%s ==" % (
        "已着陆 ✔" if landed else "结束(未触地)", gv(st, "PLANE_ALT_ABOVE_GROUND"),
        gv(st, "PLANE_ALTITUDE"), gv(st, "SIM_ON_GROUND", 0)))
