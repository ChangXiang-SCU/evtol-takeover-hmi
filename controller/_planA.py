# -*- coding: utf-8 -*-
"""方案A:速度矢量制导 @45Hz(keep-alive长连接)。从风切变起点飞向停机坪,交替阶梯。
请看模拟器画面判断丝滑度;脚本每~2s打印 dist/alt/rotY。"""
import time, math, json, http.client, config, geo
config.USE_MOCK = False
config.DEVKIT_BASE_URL = "http://127.0.0.1:5000"
import devkit_client as k

c = k.DevKitClient()
HP = config.HELIPAD
p = config.SCENARIOS["wind_shear"]["restore"]
HZ = 45.0
V_FWD, V_DOWN, RAMP = config.AUTO_V_FWD, config.AUTO_V_DOWN, config.AUTO_SEG_RAMP_S

# --- 传送到起点(同事式) ---
c.ap_stop(); time.sleep(0.3)
for n, v in [("PLANE_LATITUDE", p["lat"]), ("PLANE_LONGITUDE", p["lng"]), ("PLANE_ALTITUDE", p["alt_ft"]),
             ("PLANE_HEADING_DEGREES_TRUE", p["heading"]), ("PLANE_PITCH_DEGREES", 0.0), ("PLANE_BANK_DEGREES", 0.0)]:
    c.set_param(n, v)
for n in ["VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"]:
    c.set_param(n, 0.0)
time.sleep(1.0)

conn = http.client.HTTPConnection("127.0.0.1", 5000, timeout=3)
def sset(n, v):
    conn.request("PUT", "/set", json.dumps({"name": n, "val": v}), {"Content-Type": "application/json"})
    conn.getresponse().read()
def sget():
    conn.request("GET", "/get"); raw = conn.getresponse().read()
    return {it["name"]: it.get("val") for it in json.loads(raw)}
def gv(s, n, d=0.0):
    v = s.get(n); return d if v is None else v
def hdist(s):
    return geo.distance_m(gv(s, "PLANE_LATITUDE"), gv(s, "PLANE_LONGITUDE"), HP["lat"], HP["lng"])

_last_print = [0.0]
def maybe_print(seg):
    now = time.time()
    if now - _last_print[0] >= 2.0:
        s = sget()
        print("  [%s] dist=%5.0f alt=%6.1f hdg=%4.1f rotY=%+.2f" % (
            seg, hdist(s), gv(s, "PLANE_ALTITUDE"), gv(s, "PLANE_HEADING_DEGREES_TRUE"),
            gv(s, "ROTATION_VELOCITY_BODY_Y")))
        _last_print[0] = now

def run_seg(horizontal, v_down, T):
    period = 1.0 / HZ; t0 = time.time()
    while time.time() - t0 < T:
        e = time.time() - t0; kk = min(1.0, e / RAMP, max(0.0, (T - e) / RAMP))
        s = sget()
        lat, lng, hdg = gv(s, "PLANE_LATITUDE"), gv(s, "PLANE_LONGITUDE"), gv(s, "PLANE_HEADING_DEGREES_TRUE")
        if horizontal:
            b = geo.bearing_deg(lat, lng, HP["lat"], HP["lng"]); rel = math.radians(((b - hdg + 540) % 360) - 180)
            vf = V_FWD * kk
            sset("VELOCITY_BODY_Z", vf * math.cos(rel)); sset("VELOCITY_BODY_X", vf * math.sin(rel)); sset("VELOCITY_BODY_Y", 0.0)
        else:
            sset("VELOCITY_BODY_X", 0.0); sset("VELOCITY_BODY_Z", 0.0); sset("VELOCITY_BODY_Y", -abs(v_down) * kk)
        maybe_print("平飞" if horizontal else "下降")
        time.sleep(period)

d0 = max(1.0, hdist(sget()))
print("方案A 速度矢量 @%.0fHz 起飞 dist=%.0f alt=800" % (HZ, d0))
t_start = time.time()
while time.time() - t_start < 30:
    s = sget(); dh = hdist(s); alt = gv(s, "PLANE_ALTITUDE")
    if dh <= 18 and alt <= config.AUTO_ARRIVE_ALT_FT + 6:
        break
    frac = min(1.0, dh / d0)
    if dh > 18:
        run_seg(True, 0.0, config.AUTO_FWD_S_NEAR + (config.AUTO_FWD_S_FAR - config.AUTO_FWD_S_NEAR) * frac)
    s = sget()
    if gv(s, "PLANE_ALTITUDE") > config.AUTO_ARRIVE_ALT_FT + 3:
        run_seg(False, V_DOWN, config.AUTO_DOWN_S_NEAR + (config.AUTO_DOWN_S_FAR - config.AUTO_DOWN_S_NEAR) * frac)
for n in ["VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"]:
    sset(n, 0.0)
s = sget()
print("方案A 结束 dist=%.0f alt=%.0f" % (hdist(s), gv(s, "PLANE_ALTITUDE")))
conn.close()
