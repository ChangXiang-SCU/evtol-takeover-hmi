# -*- coding: utf-8 -*-
"""
合并版·真机三场景端到端运行器
================================
把 live_demo 的已验证真机流程（传送到触发区上方 -> teleport 逐步降入高度带 ->
命中"半径+高度带"触发 -> t0 统一 /ap_stop -> 风切变仅 wind_shear 注入 ->
自动 HMI(SSE) 广播接管请求 -> 模拟触摸屏接管并测 RT -> 恢复旋翼定点悬停）
推广到三场景（wind_shear / ap_fail / obstacle），config 驱动。

- 逐场景遥测: logs/tel_R_<id>.csv（逐帧真实飞行轨迹）
- 事件汇总:   logs/session_real.csv
- 运行日志:   real_log.txt（每行 flush，供外部 tail 轮询，不阻塞）

用法: python real_trials.py            # 跑 config.SESSION 全部三场景
      python real_trials.py ws         # 只跑 wind_shear（先验证一条）
纯标准库，Python 3.8+。
"""
import os, sys, csv, json, time, threading, urllib.request

# —— 真机连接（从笔记本走 REST 到 sim 主机）——
import config
config.USE_MOCK = False
# 在 sim 本机跑=127.0.0.1（U盘部署推荐，延迟最低）；从笔记本跑设环境变量 DEVKIT_URL=http://10.7.144.111:5000
config.DEVKIT_BASE_URL = os.environ.get("DEVKIT_URL", "http://127.0.0.1:5000")
config.HTTP_TIMEOUT_S = 6
config.EVENT_SERVER_PORT = 8000

import geo
from devkit_client import DevKitClient
from event_server import EventServer

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(HERE, config.LOG_DIR)
os.makedirs(LOG_DIR, exist_ok=True)

LOG = open(os.path.join(HERE, "real_log.txt"), "w", encoding="utf-8")
def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.write(s + "\n"); LOG.flush()
    print(s, flush=True)

DESCEND_STEP_FT   = 15.0    # 每步传送下降量（模拟被试下降）
DESCEND_MAX_STEPS = 60
DESCEND_DT_S      = 0.5
START_ABOVE_FT    = 80.0    # 触发区上方多少 ft 作为 ARMED 起点
SIM_TAKEOVER_DELAY_S = 1.8  # 绿野仙踪：t0 后模拟触摸屏接管的时刻（真实实验由被试触发）
RECOVER_HOLD_S    = 6.0

TEL_COLS = ["t", "rel_t0", "cause", "phase", "lat", "lng", "alt_ft", "agl_ft",
            "pitch", "bank", "vspeed", "gforce",
            "aileron", "elevator", "rudder", "vbx", "vby", "vbz"]

def g(st, k, d=0.0):
    v = st.get(k, d)
    return d if v is None else v

def snap(tw, cause, phase, st, t0):
    rel = (time.time() - t0) if t0 else ""
    tw.writerow([round(time.time(), 3), (rel if rel == "" else round(rel, 3)), cause, phase,
                 st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE"),
                 round(g(st, "PLANE_ALTITUDE"), 1), round(g(st, "PLANE_ALT_ABOVE_GROUND"), 1),
                 round(g(st, "PLANE_PITCH_DEGREES"), 2), round(g(st, "PLANE_BANK_DEGREES"), 2),
                 round(g(st, "VERTICAL_SPEED"), 2), round(g(st, "G_FORCE"), 3),
                 round(g(st, "AILERON_POSITION"), 4), round(g(st, "ELEVATOR_POSITION"), 4),
                 round(g(st, "RUDDER_POSITION"), 4),
                 round(g(st, config.SV_VEL_BODY_X), 3), round(g(st, config.SV_VEL_BODY_Y), 3),
                 round(g(st, config.SV_VEL_BODY_Z), 3)])

c = DevKitClient()
ev = None

def teleport_to(lat, lon, alt, heading=0.0):
    for n, v in [("PLANE_LATITUDE", lat), ("PLANE_LONGITUDE", lon), ("PLANE_ALTITUDE", alt),
                 ("PLANE_HEADING_DEGREES_TRUE", heading),
                 ("PLANE_PITCH_DEGREES", 0.0), ("PLANE_BANK_DEGREES", 0.0)]:
        c.set_param(n, v)

def recover_hover():
    try:
        st = c.get_state()
        c.ap_rotor_point(st["PLANE_LATITUDE"], st["PLANE_LONGITUDE"])
        time.sleep(RECOVER_HOLD_S)
        r = c.get_state()
        log("   [恢复] AGL=%.0f alt=%.0f VBY=%.1f" % (
            g(r, "PLANE_ALT_ABOVE_GROUND"), g(r, "PLANE_ALTITUDE"), g(r, "VELOCITY_BODY_Y")))
    except Exception as e:
        log("   [恢复异常]", e)

def run_trial(tr):
    cause, modality = tr["cause"], tr["modality"]
    scn = config.SCENARIOS.get(cause, {})
    trig = scn.get("trigger")
    if not trig:
        log("[跳过] 无触发区:", cause); return None
    start_alt = trig["alt_max_ft"] + START_ABOVE_FT

    tel_path = os.path.join(LOG_DIR, "tel_R_%s.csv" % tr["id"])
    tf = open(tel_path, "w", newline="", encoding="utf-8-sig")
    tw = csv.writer(tf); tw.writerow(TEL_COLS)

    log("\n===== TRIAL %s | 诱因=%s 模态=%s =====" % (tr["id"], cause, modality))
    ev.reset_takeover(); ev.broadcast({"type": "reset"})

    # 1) 断 AP + 传送到触发区正上方（ARMED 起点）
    c.ap_stop()
    log("[传送] 到触发区正上方 (%.6f,%.6f) @ %.0fft (带 %.0f-%.0f 之上)" % (
        trig["lat"], trig["lng"], start_alt, trig["alt_min_ft"], trig["alt_max_ft"]))
    teleport_to(trig["lat"], trig["lng"], start_alt); time.sleep(1.0)

    # 2) teleport 逐步降入高度带
    log("[下降] 逐步降入高度带...")
    t0 = None; armed = False; cur = start_alt; alt = start_alt; d = 999.0
    for _ in range(DESCEND_MAX_STEPS):
        st = c.get_state()
        if st:
            lat, lon = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
            alt = st.get("PLANE_ALTITUDE", cur) or cur
            d = geo.distance_m(lat, lon, trig["lat"], trig["lng"]) if lat else 999
            inz = (d <= trig["radius_m"] and trig["alt_min_ft"] <= alt <= trig["alt_max_ft"])
            snap(tw, cause, "descend", st, t0)
            if not inz:
                armed = True
            if inz and armed:
                t0 = time.time(); break
        cur -= DESCEND_STEP_FT
        teleport_to(trig["lat"], trig["lng"], cur)
        time.sleep(DESCEND_DT_S)

    row = {"id": tr["id"], "cause": cause, "modality": modality,
           "visibility": tr.get("visibility", ""), "t0": "", "in_zone_alt_ft": "",
           "hmi_received": False, "rt_takeover_s": "", "ws_drop_ft": "",
           "max_g": 0.0, "note": "", "tel_file": os.path.basename(tel_path)}

    if t0 is None:
        row["note"] = "未在带内触发"; log("[!] 未在带内触发")
        tf.close(); return row

    base_alt = alt
    row["t0"] = round(t0, 3); row["in_zone_alt_ft"] = round(base_alt, 1)
    log("[t0] ★带内触发★ d=%.0fm alt=%.0f (带 %.0f-%.0f) -> /ap_stop + HMI(%s) + %s" % (
        d, base_alt, trig["alt_min_ft"], trig["alt_max_ft"], modality,
        "风切变注入(-50@%dHz)" % config.WIND_SHEAR_INJECT_HZ if cause == "wind_shear" else "(无注入)"))
    c.ap_stop()
    ev.broadcast({"type": "takeover_request", "event_id": tr["id"], "t0": t0,
                  "modality": modality, "cause": cause,
                  "text": config.CAUSE_TEXT.get(cause, "请接管")})

    # 3) 风切变：后台线程密集注入 VELOCITY_BODY_Y/Z（仅 wind_shear）
    if cause == "wind_shear":
        z0 = g(c.get_state(), config.SV_VEL_BODY_Z)
        ws = config.WIND_SHEAR; end = t0 + ws["duration_s"]
        def inject():
            while time.time() < end:
                try:
                    c.set_param(config.SV_VEL_BODY_Y, ws["down_vspeed_fts"])
                    c.set_param(config.SV_VEL_BODY_Z, z0 * (1 - ws["speed_loss_frac"]))
                except Exception: pass
                time.sleep(1.0 / config.WIND_SHEAR_INJECT_HZ)
        threading.Thread(target=inject, daemon=True).start()

    # 4) t0 后采样窗 + 模拟触摸屏接管测 RT
    max_g = 0.0; posted = False
    win_end = t0 + SIM_TAKEOVER_DELAY_S + 1.6
    while time.time() < win_end:
        st = c.get_state()
        if st:
            snap(tw, cause, "await_takeover", st, t0)
            max_g = max(max_g, g(st, "G_FORCE"))
        if (not posted) and time.time() - t0 >= SIM_TAKEOVER_DELAY_S:
            posted = True
            log("[C] 模拟触摸屏接管 POST /takeover")
            try:
                urllib.request.urlopen(urllib.request.Request(
                    "http://127.0.0.1:%d/takeover" % config.EVENT_SERVER_PORT,
                    data=json.dumps({"event_id": tr["id"]}).encode(), method="POST",
                    headers={"Content-Type": "application/json"}), timeout=4)
            except Exception as e:
                log("   POST err:", e)
        time.sleep(0.1)

    st = c.get_state()
    tk = ev.get_takeover()
    rt = (tk.get("t_server") - t0) if tk else None
    row["hmi_received"] = bool(tk)
    row["rt_takeover_s"] = round(rt, 3) if rt else ""
    row["max_g"] = round(max_g, 3)
    if cause == "wind_shear":
        row["ws_drop_ft"] = round(base_alt - g(st, "PLANE_ALTITUDE"), 1)
    log("[结果] HMI收到=%s | 接管RT=%s s%s | maxG=%.2f" % (
        row["hmi_received"], row["rt_takeover_s"],
        (" | 风切变掉高=%.1fft" % row["ws_drop_ft"]) if cause == "wind_shear" else "", max_g))

    # 5) 恢复悬停
    recover_hover()
    tf.close()
    log("[TRIAL 完成]", row)
    return row

def main():
    # 选场景：无参=全部；ws/ap/ob=单场景
    sel = sys.argv[1].lower() if len(sys.argv) > 1 else None
    name_map = {"ws": "wind_shear", "ap": "ap_fail", "ob": "obstacle"}
    trials = list(config.SESSION)
    if sel in name_map:
        trials = [t for t in trials if t["cause"] == name_map[sel]]

    global ev
    # 连通性预检
    try:
        st = c.get_state()
        if not st:
            log("ABORT: /get 无数据（DevKit 在跑但没返回状态？确认已进入飞行）"); return
        log("[预检] DevKit OK, 字段=%d, 当前 alt=%.0f AGL=%.0f on_ground=%s" % (
            len(st), g(st, "PLANE_ALTITUDE"), g(st, "PLANE_ALT_ABOVE_GROUND"), st.get("SIM_ON_GROUND")))
    except Exception as e:
        log("ABORT: 连不上 DevKit:", e); return

    ev = EventServer().start()
    # SSE 监听器：确认 HMI 端真能收到广播
    got = []
    def listen():
        try:
            r = urllib.request.urlopen("http://127.0.0.1:%d/events" % config.EVENT_SERVER_PORT, timeout=120)
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("data:"):
                    try: dd = json.loads(line[5:].strip())
                    except Exception: continue
                    if isinstance(dd, dict) and dd.get("type") == "takeover_request":
                        got.append(dd)
        except Exception: pass
    threading.Thread(target=listen, daemon=True).start(); time.sleep(1)

    rows = []
    try:
        for tr in trials:
            try:
                r = run_trial(tr)
                if r: rows.append(r)
            except Exception as e:
                log("[TRIAL 异常]", tr.get("id"), e)
                recover_hover()
            time.sleep(1.5)
    finally:
        # 汇总
        if rows:
            path = os.path.join(LOG_DIR, "session_real.csv")
            cols = ["id", "cause", "modality", "visibility", "t0", "in_zone_alt_ft",
                    "hmi_received", "rt_takeover_s", "ws_drop_ft", "max_g", "note", "tel_file"]
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
                for r in rows: w.writerow(r)
            log("\n[汇总] 事件表 ->", path)
        log("[SSE] 监听器共收到 takeover_request 次数 =", len(got))
        try: ev.stop()
        except Exception: pass
        log("=== 真机三场景运行结束 ===")
        LOG.close()

if __name__ == "__main__":
    main()
