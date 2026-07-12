# -*- coding: utf-8 -*-
"""直接跑控制面板里真正的 _auto_route_loop(速度矢量制导+交替阶梯),
传送到风切变起点后开航线,监控40s:看阶梯(平飞段dist降/下降段alt降交替)+ rotY有无摇摆。"""
import os, time, threading, math
os.environ["DEVKIT_URL"] = "http://127.0.0.1:5000"
import config, geo
import control_panel as cp

HP = config.HELIPAD
c = cp.client

def snap():
    st = c.get_state() or {}
    lat, lng = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
    d = geo.distance_m(lat, lng, HP["lat"], HP["lng"]) if lat else -1
    return (d, cp.g(st, "PLANE_ALTITUDE"), cp.g(st, "PLANE_HEADING_DEGREES_TRUE"),
            cp.g(st, "ROTATION_VELOCITY_BODY_Y"),
            cp.g(st, "VELOCITY_BODY_Z"), cp.g(st, "VELOCITY_BODY_Y"))

print("传送到风切变起点...")
cp._teleport(config.SCENARIOS["wind_shear"]["restore"])
time.sleep(1.0)
d0, a0, h0, _, _, _ = snap()
print("起点: dist=%.0fm alt=%.0fft hdg=%.1f" % (d0, a0, h0))

cp.AUTO_STOP.clear()
th = threading.Thread(target=cp._auto_route_loop, daemon=True)
th.start()
print(">> 开航线, 监控40s (段=当前在平飞还是下降; rotY峰=1s内最大偏航,应≈0)")
t0 = time.time(); rmax = 0.0; last = 0.0
while time.time() - t0 < 40:
    d, a, h, ry, vz, vy = snap()
    rmax = max(rmax, abs(ry))
    e = time.time() - t0
    if e >= last:
        seg = "下降" if abs(vy) > abs(vz) and abs(vy) > 1 else ("平飞" if abs(vz) > 1 else "过渡")
        print("  t=%2ds dist=%4.0f alt=%4.0f hdg=%4.1f 段=%s rotY峰=%.2f" % (e, d, a, h, seg, rmax))
        rmax = 0.0; last += 2
    time.sleep(0.1)
cp.AUTO_STOP.set()
time.sleep(1.0)
df, af, hf, _, _, _ = snap()
print("停: dist=%.0fm alt=%.0fft hdg=%.1f (关航线后应稳住)" % (df, af, hf))
