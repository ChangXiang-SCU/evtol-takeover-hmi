# -*- coding: utf-8 -*-
"""方案B(改):高帧率位置回放 @45Hz(keep-alive)。直接每帧写 位置+航向+俯仰(绕开FBW),
机头精确对准停机坪、无蟹行。交替阶梯:平飞段(动水平)→下降段(动高度),远段幅度大近段小。
请看模拟器画面判断丝滑度。"""
import time, math, json, http.client, config, geo
config.USE_MOCK = False
config.DEVKIT_BASE_URL = "http://127.0.0.1:5000"
import devkit_client as k

c = k.DevKitClient(); HP = config.HELIPAD; p = config.SCENARIOS["wind_shear"]["restore"]
ARR_ALT = config.AUTO_ARRIVE_ALT_FT
HZ = 45.0

# 传送到起点
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
def ease(u):
    return u * u * (3 - 2 * u)  # smoothstep 平滑起落

s0 = sget()
lat, lng, alt = gv(s0, "PLANE_LATITUDE"), gv(s0, "PLANE_LONGITUDE"), gv(s0, "PLANE_ALTITUDE")

def glide(lat1, lng1, alt1, T, pitch):
    """从当前(lat,lng,alt)平滑移到目标,每帧写位置+航向(对准停机坪)+俯仰。"""
    global lat, lng, alt
    n = max(1, int(T * HZ)); lat0, lng0, alt0 = lat, lng, alt
    sset("PLANE_BANK_DEGREES", 0.0)
    for i in range(n + 1):
        u = ease(i / n)
        la = lat0 + (lat1 - lat0) * u; ln = lng0 + (lng1 - lng0) * u; al = alt0 + (alt1 - alt0) * u
        hdg = geo.bearing_deg(la, ln, HP["lat"], HP["lng"])
        sset("PLANE_LATITUDE", la); sset("PLANE_LONGITUDE", ln); sset("PLANE_ALTITUDE", al)
        sset("PLANE_HEADING_DEGREES_TRUE", hdg); sset("PLANE_PITCH_DEGREES", pitch)
        time.sleep(1.0 / HZ)
    lat, lng, alt = lat1, lng1, alt1

d_pad = geo.distance_m(lat, lng, HP["lat"], HP["lng"])
print("方案B 位置回放 @%.0fHz 起点 dist=%.0f alt=%.0f" % (HZ, d_pad, alt))
t0 = time.time()
while time.time() - t0 < 28:
    dh = geo.distance_m(lat, lng, HP["lat"], HP["lng"])
    if dh <= 15 and alt <= ARR_ALT + 5:
        break
    brg = geo.bearing_deg(lat, lng, HP["lat"], HP["lng"])
    if dh > 15:                                   # 平飞段:远段幅度大近段小
        chunk = min(dh, max(20.0, dh * 0.32))
        la, ln = geo.move(lat, lng, brg, chunk)
        glide(la, ln, alt, max(1.4, chunk / 16.0), -3.0)   # 略低头,自然前飞
        print("  平飞→ dist=%.0f alt=%.0f hdg对准=%.1f" % (
            geo.distance_m(lat, lng, HP["lat"], HP["lng"]), alt, brg))
    if alt > ARR_ALT + 3:                         # 下降段
        vchunk = min(alt - ARR_ALT, max(15.0, (alt - ARR_ALT) * 0.32))
        glide(lat, lng, alt - vchunk, max(1.2, vchunk / 20.0), 0.0)
        print("  下降↓ dist=%.0f alt=%.0f" % (geo.distance_m(lat, lng, HP["lat"], HP["lng"]), alt))
for n in ["VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"]:
    sset(n, 0.0)
print("方案B 结束 dist=%.0f alt=%.0f" % (geo.distance_m(lat, lng, HP["lat"], HP["lng"]), alt))
conn.close()
