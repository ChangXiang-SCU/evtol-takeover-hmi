# -*- coding: utf-8 -*-
"""
eVTOL 接管实验 — 事件控制器主程序
==================================
一个 trial 的闭环：
  自主飞行(旋翼定点) → 进入触发地理围栏 → t0 统一 /ap_stop
  → (风切变叠加速度扰动) → 广播接管请求给 HMI
  → 双通道检测接管(触摸屏点击 / 操纵面偏转) → 记录 RT
  → 落地/超时 → 记录触地指标

用法：
  python controller.py           # 按 config.SESSION 跑整个序列
  python controller.py --check   # 只测与 DevKit 的连接，打印一帧状态后退出
纯标准库，Python 3.8+。
"""
import os
import sys
import csv
import time
import math
import threading

import config
import geo
from devkit_client import make_client, DevKitClient
from event_server import EventServer

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(HERE, config.LOG_DIR)


def _g(st, key, default=0.0):
    v = st.get(key, default)
    return default if v is None else v


def groundspeed_fts(st):
    return math.hypot(_g(st, config.SV_VEL_BODY_X), _g(st, config.SV_VEL_BODY_Z))


def alt_agl(st):
    v = st.get("PLANE_ALT_ABOVE_GROUND")
    return _g(st, "PLANE_ALTITUDE") if v is None else v


def is_landed(st):
    return alt_agl(st) <= config.LANDING_ALT_AGL_FT and abs(_g(st, "VERTICAL_SPEED")) <= config.LANDING_VS_FTS


TEL_COLS = ["t", "rel_t0", "state", "lat", "lng", "alt_ft", "agl_ft", "pitch", "bank",
            "vspeed", "gforce", "aileron", "elevator", "rudder",
            "vbx", "vby", "vbz", "gs_fts"]


class Controller:
    def __init__(self):
        self.client = make_client()
        self.events = EventServer().start()
        os.makedirs(LOG_DIR, exist_ok=True)
        self.session_rows = []
        print("[控制器] 模式:", "MOCK 干跑" if config.USE_MOCK else "真实 MSFS",
              "| DevKit:", config.DEVKIT_BASE_URL)
        print("[控制器] HMI 事件服务器: http://<本机IP>:%d/  (触摸屏浏览器打开)" % config.EVENT_SERVER_PORT)

    # ---------- 单个 trial ----------
    def run_trial(self, tr):
        cause, modality = tr["cause"], tr["modality"]
        scn = config.SCENARIOS.get(cause, {})
        trig = scn.get("trigger")
        if not trig:
            print("[跳过] 未知诱因/无触发区:", cause); return None
        restore = scn.get("restore")
        dt = 1.0 / config.CONTROL_HZ

        tel_path = os.path.join(LOG_DIR, "tel_%s.csv" % tr["id"])
        tf = open(tel_path, "w", newline="", encoding="utf-8-sig")
        tw = csv.writer(tf); tw.writerow(TEL_COLS)

        print("\n===== TRIAL %s | 诱因=%s 模态=%s =====" % (tr["id"], cause, modality))
        self.events.reset_takeover()
        self.events.broadcast({"type": "reset"})

        # INIT：传送到恢复点(可复现起点) + 命令自主飞向触发区
        if config.TELEPORT_TO_RESTORE and restore:
            self._teleport(restore)
        self.client.ap_rotor_point(trig["lat"], trig["lng"])
        print("[INIT] 触发区 (%.6f, %.6f) r=%dm 高度 %.0f-%.0f ft MSL" % (
            trig["lat"], trig["lng"], trig["radius_m"], trig["alt_min_ft"], trig["alt_max_ft"]))

        state = "AUTO_CRUISE"
        t_start = time.time()
        armed = False
        t0 = None; baseline = None
        rt_tap = None; rt_ctrl = None
        # 风切变由后台线程密集注入(见 _start_windshear)
        touchdown_g = None; max_g = 0.0; landed = False; note = ""

        while True:
            loop_t = time.time()
            st = self.client.get_state()
            lat, lng = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
            alt_msl = _g(st, "PLANE_ALTITUDE")
            dist = geo.distance_m(lat, lng, trig["lat"], trig["lng"]) if lat is not None and lng is not None else float("inf")
            in_zone = (dist <= trig["radius_m"] and trig["alt_min_ft"] <= alt_msl <= trig["alt_max_ft"])
            rel = (time.time() - t0) if t0 else ""
            tw.writerow([round(time.time(), 3), rel if rel == "" else round(rel, 3), state,
                         lat, lng, _g(st, "PLANE_ALTITUDE"), round(alt_agl(st), 2),
                         round(_g(st, "PLANE_PITCH_DEGREES"), 2), round(_g(st, "PLANE_BANK_DEGREES"), 2),
                         round(_g(st, "VERTICAL_SPEED"), 2), round(_g(st, "G_FORCE"), 3),
                         round(_g(st, "AILERON_POSITION"), 4), round(_g(st, "ELEVATOR_POSITION"), 4),
                         round(_g(st, "RUDDER_POSITION"), 4),
                         round(_g(st, config.SV_VEL_BODY_X), 3), round(_g(st, config.SV_VEL_BODY_Y), 3),
                         round(_g(st, config.SV_VEL_BODY_Z), 3), round(groundspeed_fts(st), 2)])

            if state == "AUTO_CRUISE":
                if not in_zone:
                    armed = True                                     # 须先在区外(ARMED)再飞入
                if in_zone and armed:
                    t0 = time.time()
                    self.client.ap_stop()                            # 三类统一断 AP
                    if cause == "wind_shear":
                        self._start_windshear(st)                    # 后台线程密集注入速度扰动
                    self.events.broadcast({"type": "takeover_request", "event_id": tr["id"],
                                           "t0": t0, "modality": modality, "cause": cause,
                                           "text": config.CAUSE_TEXT.get(cause, "请接管")})
                    baseline = {ax: _g(st, ax) for ax in config.CONTROL_AXES}
                    print("[t0] 触发! dist=%.1fm alt=%.0fft MSL → /ap_stop + 广播接管请求(%s)" % (dist, alt_msl, modality))
                    state = "AWAIT_TAKEOVER"
                elif time.time() - t_start > config.TIMEOUT_CRUISE_S:
                    note = "巡航超时未进触发区"; print("[WARN]", note); state = "END"

            elif state in ("AWAIT_TAKEOVER", "MANUAL"):
                # 风切变扰动由 _start_windshear 的后台线程密集注入，主循环无需处理
                # 通道A：触摸屏点击
                tk = self.events.get_takeover()
                if tk and rt_tap is None:
                    rt_tap = tk.get("t_server", time.time()) - t0
                    print("[接管·触摸屏] RT = %.3fs" % rt_tap)
                # 通道B：操纵面偏转
                if baseline and rt_ctrl is None:
                    for ax in config.CONTROL_AXES:
                        if abs(_g(st, ax) - baseline[ax]) > config.CONTROL_DEADBAND:
                            rt_ctrl = time.time() - t0
                            print("[接管·操控] RT = %.3fs (轴=%s)" % (rt_ctrl, ax)); break
                if state == "AWAIT_TAKEOVER" and (rt_tap is not None or rt_ctrl is not None):
                    state = "MANUAL"
                max_g = max(max_g, _g(st, "G_FORCE"))
                if is_landed(st):
                    landed = True; touchdown_g = _g(st, "G_FORCE")
                    note = "已落地"; print("[LAND] 触地 G=%.2f" % touchdown_g); state = "END"
                elif state == "AWAIT_TAKEOVER" and time.time() - t0 > config.TIMEOUT_TAKEOVER_S:
                    note = "超时未接管"; print("[WARN]", note); state = "END"
                elif t0 and time.time() - t0 > config.TIMEOUT_MANUAL_S:
                    note = "接管后超时未落地"; print("[WARN]", note); state = "END"

            if state == "END":
                break
            slp = dt - (time.time() - loop_t)
            if slp > 0:
                time.sleep(slp)

        tf.close()
        row = {"id": tr["id"], "cause": cause, "modality": modality,
               "visibility": tr.get("visibility", ""),
               "t0": round(t0, 3) if t0 else "",
               "rt_touch_s": round(rt_tap, 3) if rt_tap is not None else "",
               "rt_control_s": round(rt_ctrl, 3) if rt_ctrl is not None else "",
               "touchdown_g": round(touchdown_g, 3) if touchdown_g is not None else "",
               "max_g": round(max_g, 3), "landed": landed, "note": note,
               "tel_file": os.path.basename(tel_path)}
        self.session_rows.append(row)
        print("[TRIAL 完成]", row)
        return row

    def _teleport(self, restore):
        """传送复位：直接写 PLANE_LATITUDE/LONGITUDE/ALTITUDE + 姿态(同事的可复现起点做法)。"""
        print("[传送] 复位到恢复点 (%.6f, %.6f, %.0f ft MSL)" % (restore["lat"], restore["lng"], restore["alt_ft"]))
        for name, val in [("PLANE_LATITUDE", restore["lat"]), ("PLANE_LONGITUDE", restore["lng"]),
                          ("PLANE_ALTITUDE", restore["alt_ft"]),
                          ("PLANE_HEADING_DEGREES_TRUE", restore.get("heading", 0.0)),
                          ("PLANE_PITCH_DEGREES", restore.get("pitch", 0.0)),
                          ("PLANE_BANK_DEGREES", restore.get("bank", 0.0))]:
            self.client.set_param(name, val)
        time.sleep(1.0)

    def _start_windshear(self, st):
        """后台线程在扰动窗口内密集注入 VELOCITY_BODY_Y/Z（真机需 ~20+ 次/秒才有效）。"""
        base_z = _g(st, config.SV_VEL_BODY_Z)
        ws = config.WIND_SHEAR
        hz = getattr(config, "WIND_SHEAR_INJECT_HZ", 25)
        dt = 1.0 / hz
        end = time.time() + ws["duration_s"]
        def run():
            while time.time() < end:
                try:
                    self.client.set_param(config.SV_VEL_BODY_Y, ws["down_vspeed_fts"])
                    self.client.set_param(config.SV_VEL_BODY_Z, base_z * (1.0 - ws["speed_loss_frac"]))
                    if ws["roll_bias"]:
                        self.client.set_param("AILERON_POSITION", ws["roll_bias"])
                except Exception:
                    pass
                time.sleep(dt)
        threading.Thread(target=run, daemon=True).start()

    # ---------- 整个 session ----------
    def run_session(self, trials=None):
        trials = trials or config.SESSION
        try:
            for tr in trials:
                self.run_trial(tr)
                time.sleep(2)
        finally:
            self._write_summary()
            self.events.stop()

    def _write_summary(self):
        if not self.session_rows:
            return
        path = os.path.join(LOG_DIR, "session_events.csv")
        cols = ["id", "cause", "modality", "visibility", "t0", "rt_touch_s", "rt_control_s",
                "touchdown_g", "max_g", "landed", "note", "tel_file"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
            for r in self.session_rows:
                w.writerow(r)
        print("\n[汇总] 事件表 →", path)
        print("[汇总] 遥测逐帧 →", LOG_DIR)


def selftest():
    """--check：只验证与 DevKit 的连接。"""
    print("[自检] 连接 DevKit:", config.DEVKIT_BASE_URL, "(USE_MOCK=%s)" % config.USE_MOCK)
    c = make_client()
    try:
        st = c.get_state()
    except Exception as e:
        print("[自检] ✗ /get 失败:", repr(e))
        print("     检查：MSFS+DevKit 是否在跑；DEVKIT_BASE_URL 的 IP/端口；防火墙/路由是否放行 5000。")
        return
    if not st:
        print("[自检] ✗ /get 无数据（DevKit 在跑但没返回飞机状态？确认已进入飞行）")
        return
    print("[自检] /get 返回字段数:", len(st))
    for k in ["PLANE_LATITUDE", "PLANE_LONGITUDE", "PLANE_ALTITUDE"]:
        print("   ", k, "=", st.get(k))
    aps = c.ap_state()
    if isinstance(aps, dict) and aps.get("error"):
        print("[自检] /ap_state:", aps, "(辅助驾驶未启动，属正常)")
    else:
        print("[自检] /ap_state:", aps)
    print("[自检] ✓ 连接成功，实时遥测可读")


if __name__ == "__main__":
    if "--check" in sys.argv:
        selftest()
    else:
        Controller().run_session()
