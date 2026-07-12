# -*- coding: utf-8 -*-
"""合并后·真机演示(带内触发版)：传送到触发区正上方 -> 用 teleport 逐步降入高度带(AP 无法主动下降,
以传送模拟被试下降) -> 真正"半径+高度带"命中触发 -> /ap_stop + 我方风切变注入 + 自动HMI + RT -> 恢复。
写 demo_log.txt；恢复在 finally。"""
import time, threading, json, urllib.request, config, geo
config.USE_MOCK = False
config.DEVKIT_BASE_URL = "http://10.7.144.111:5000"
config.HTTP_TIMEOUT_S = 6
config.EVENT_SERVER_PORT = 8000
from devkit_client import DevKitClient
from event_server import EventServer

LOG = open("demo_log.txt", "w", encoding="utf-8")
def log(*a):
    s = " ".join(str(x) for x in a); LOG.write(s + "\n"); LOG.flush()

c = DevKitClient()
try:
    if not c.get_state():
        log("ABORT /get 无数据"); LOG.close(); raise SystemExit
except Exception as e:
    log("ABORT 连不上 DevKit:", e); LOG.close(); raise SystemExit

ev = EventServer().start()
hmi_got = []
def listen():
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8000/events", timeout=45)
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("data:"):
                try: d = json.loads(line[5:].strip())
                except Exception: continue
                if isinstance(d, dict) and d.get("type") == "takeover_request": hmi_got.append(d)
    except Exception: pass
threading.Thread(target=listen, daemon=True).start(); time.sleep(1)

scn = config.SCENARIOS["wind_shear"]; trig = scn["trigger"]
start_alt = trig["alt_max_ft"] + 80.0   # 带上方(ARMED)

def teleport_to(lat, lon, alt):
    for n, v in [("PLANE_LATITUDE", lat), ("PLANE_LONGITUDE", lon), ("PLANE_ALTITUDE", alt),
                 ("PLANE_HEADING_DEGREES_TRUE", 0.0), ("PLANE_PITCH_DEGREES", 0.0), ("PLANE_BANK_DEGREES", 0.0)]:
        c.set_param(n, v)

t0 = None; alt = start_alt; d = 0.0
try:
    c.ap_stop()                                   # 确保 AP 关(否则它会爬回~800ft)
    log("[传送] 到触发区正上方 (%.6f,%.6f) @ %.0fft (带 %.0f-%.0f 之上, ARMED)" % (
        trig["lat"], trig["lng"], start_alt, trig["alt_min_ft"], trig["alt_max_ft"]))
    teleport_to(trig["lat"], trig["lng"], start_alt); time.sleep(1.0)
    log("[下降] teleport 逐步降入高度带(模拟被试下降)...")
    armed = False; cur = start_alt
    for _ in range(50):
        st = c.get_state()
        lat, lon = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
        alt = st.get("PLANE_ALTITUDE", cur) or cur
        d = geo.distance_m(lat, lon, trig["lat"], trig["lng"]) if lat else 999
        inz = (d <= trig["radius_m"] and trig["alt_min_ft"] <= alt <= trig["alt_max_ft"])
        log("   d=%.0fm alt=%.0f 带内=%s armed=%s" % (d, alt, inz, armed))
        if not inz:
            armed = True
        if inz and armed:
            t0 = time.time(); break
        cur -= 15.0
        teleport_to(trig["lat"], trig["lng"], cur)
        time.sleep(0.5)

    if t0 is None:
        log("[!] 未在带内触发")
    else:
        base_alt = alt; z0 = c.get_state().get("VELOCITY_BODY_Z") or 0
        log("[t0] ★带内触发★ d=%.0fm alt=%.0f (带 %.0f-%.0f) -> /ap_stop + 广播HMI + 风切变注入(-50@%dHz)" % (
            d, base_alt, trig["alt_min_ft"], trig["alt_max_ft"], config.WIND_SHEAR_INJECT_HZ))
        c.ap_stop()
        ev.broadcast({"type": "takeover_request", "event_id": "MERGE", "t0": t0,
                      "modality": "multimodal", "cause": "wind_shear", "text": "请接管，检测到风切变"})
        ws = config.WIND_SHEAR; end = t0 + ws["duration_s"]
        def inject():
            while time.time() < end:
                try:
                    c.set_param("VELOCITY_BODY_Y", ws["down_vspeed_fts"])
                    c.set_param("VELOCITY_BODY_Z", z0 * (1 - ws["speed_loss_frac"]))
                except Exception: pass
                time.sleep(1.0 / config.WIND_SHEAR_INJECT_HZ)
        threading.Thread(target=inject, daemon=True).start()
        time.sleep(1.8)
        log("[C] 模拟触摸屏接管 POST /takeover")
        try:
            urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8000/takeover",
                data=json.dumps({"event_id": "MERGE"}).encode(), method="POST",
                headers={"Content-Type": "application/json"}), timeout=4)
        except Exception as e:
            log("   POST err:", e)
        time.sleep(1.5)
        st = c.get_state(); drop = base_alt - (st.get("PLANE_ALTITUDE", 0) or 0)
        tk = ev.get_takeover(); rt = (tk.get("t_server") - t0) if tk else None
        log("[结果] 风切变实际掉高=%.1fft | HMI收到接管请求=%s | 接管RT=%s s" % (
            drop, bool(hmi_got), ("%.2f" % rt) if rt else "无"))
finally:
    log("[恢复] 重新旋翼定点悬停(6s)")
    try:
        st = c.get_state(); c.ap_rotor_point(st["PLANE_LATITUDE"], st["PLANE_LONGITUDE"]); time.sleep(6)
        r = c.get_state(); log("   恢复后 AGL=%.0f alt=%.0f VBY=%.1f" % (
            r.get("PLANE_ALT_ABOVE_GROUND", 0) or 0, r.get("PLANE_ALTITUDE", 0) or 0, r.get("VELOCITY_BODY_Y", 0) or 0))
    except Exception as e:
        log("   恢复异常:", e)
    try: ev.stop()
    except Exception: pass
    log("=== 合并·带内触发演示完成 ===")
    LOG.close()
