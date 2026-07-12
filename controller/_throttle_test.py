# -*- coding: utf-8 -*-
"""测这台 eVTOL 的油门(和操纵面)到底有没有效:通过 DevKit 写油门,看是否起飞/爬升,平不平滑。
用完恢复油门。若能靠油门平滑控制升降,就为"控制输入式"方案奠基。"""
import time
import devkit_client as k

c = k.DevKitClient()
TH = "GENERAL_ENG_THROTTLE_LEVER_POSITION:1"

def g(n):
    s = c.get_state() or {}
    v = s.get(n)
    return v

def show(tag):
    print("  %-10s alt=%6.1f  vs=%7.1f  on_gnd=%s  throttle=%.1f" % (
        tag, g("PLANE_ALTITUDE") or 0, (g("VERTICAL_SPEED") or 0), g("SIM_ON_GROUND"), g(TH) or 0))

# 一并看看操纵面可写性
s0 = c.get_state() or {}
for n in ["AILERON_POSITION", "ELEVATOR_POSITION", "RUDDER_POSITION",
          "COLLECTIVE_POSITION", "CYCLIC_LONGITUDINAL", "ROTOR_LATERAL_TRIM_PCT"]:
    row = next((r for r in (s0 if isinstance(s0, list) else []) if r.get("name") == n), None)
    # get_state 已解析成 {name:val}，writable 看不到；这里只报是否存在
    print("有变量 %-24s = %s" % (n, s0.get(n) if isinstance(s0, dict) else "?"))

th0 = g(TH) or 53.5
print("初始:", end=""); show("start")
try:
    for target in [65, 75, 85]:
        c.set_param(TH, target)
        print("--- 设油门=%d%% ---" % target)
        for _ in range(5):
            time.sleep(0.6)
            show("t=%.1fs" % _)
finally:
    c.set_param(TH, th0)
    time.sleep(0.5)
    print("恢复油门=%.1f" % (g(TH) or 0)); show("end")
