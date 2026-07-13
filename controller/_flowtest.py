# -*- coding: utf-8 -*-
"""离线全流程干跑（不连 sim）：
测1: AP接近→ETA≤5s预警(t0)→+5s诱因生效(断AP+悬停)→摇杆偏转→通道B记RT
     且航线线程自写ELEV(0/-0.85跳变)全程不得误判。
测2: 预警后、诱因生效前手动接管→AP立即off且记RT→生效时保持off、不清速度。
"""
import time, threading, sys, io

import config
import control_panel as cp
threading = __import__("threading")
_mon = None
def ensure_monitor():
    global _mon
    if _mon is None:
        _mon = threading.Thread(target=cp.monitor_loop, daemon=True)
        _mon.start()

TRIG = config.SCENARIOS["obstacle"]["trigger"]
ALT = (TRIG["alt_min_ft"] + TRIG["alt_max_ft"]) / 2.0
M2DEG = 1.0 / 111320.0

class FakeClient:
    """从触发区中心正南300m以40m/s向北飞。ELEV 模拟 MSFS 滑变：以 4.25/s 向
    目标值(joy优先于写入值)滑动——复现"命令切换瞬间中间过渡值"这一真机误判场景。"""
    SLEW = 4.25   # 实测 0→-0.85 约 0.2s
    def __init__(self):
        self.t0 = time.time(); self.speed = 40.0; self.start_off = 300.0
        self.written = {}; self.joy_elev = None
        self.ap_stopped = 0; self.zero_events = 0
        self.elev = 0.0; self._last = time.time()
        self.lock = threading.Lock()
    def get_state(self):
        adv = min(self.start_off + 60, self.speed * (time.time() - self.t0))  # 最多穿过中心60m
        lat = TRIG["lat"] + (adv - self.start_off) * M2DEG
        with self.lock:
            tgt = self.joy_elev if self.joy_elev is not None else self.written.get("ELEVATOR_POSITION", 0.0)
            now = time.time(); step = self.SLEW * (now - self._last); self._last = now
            d = tgt - self.elev
            self.elev = tgt if abs(d) <= step else self.elev + (step if d > 0 else -step)
            elev = self.elev
        return {"PLANE_LATITUDE": lat, "PLANE_LONGITUDE": TRIG["lng"], "PLANE_ALTITUDE": ALT,
                "VERTICAL_SPEED": 0.0, "G_FORCE": 1.0, "PLANE_ALT_ABOVE_GROUND": 200.0,
                "AILERON_POSITION": 0.0, "ELEVATOR_POSITION": elev, "RUDDER_POSITION": 0.0,
                "PLANE_HEADING_DEGREES_TRUE": 0.0,
                config.SV_VEL_BODY_X: 0.0, config.SV_VEL_BODY_Y: 0.0, config.SV_VEL_BODY_Z: 0.0}
    def set_param(self, name, val):
        with self.lock:
            self.written[name] = val
            if name in (config.SV_VEL_BODY_X, config.SV_VEL_BODY_Y, config.SV_VEL_BODY_Z) and val == 0.0:
                self.zero_events += 1
    def ap_stop(self): self.ap_stopped += 1

def mimic_route(fc):
    """模拟真实航线线程：12Hz写ELEV，0/-0.85每3s切换(真实段长~5s)；AUTO_STOP→回中收尾。"""
    v = 0.0; last = time.time()
    while not cp.AUTO_STOP.is_set():
        if time.time() - last > 3.0:
            v = -0.85 if v == 0.0 else 0.0; last = time.time()
        cp.cmd_set("ELEVATOR_POSITION", v); fc.set_param("ELEVATOR_POSITION", v)
        if cp.AUTO_STOP.wait(1 / 12): break
    cp.cmd_set("ELEVATOR_POSITION", 0.0); fc.set_param("ELEVATOR_POSITION", 0.0)
    with cp.LOCK: cp.STATE["ap_on"] = False

FAIL = []
def chk(name, cond):
    print(("PASS " if cond else "FAIL ") + name); FAIL.append(name) if not cond else None

def wait_until(pred, timeout, step=0.02):
    t = time.time()
    while time.time() - t < timeout:
        if pred(): return True
        time.sleep(step)
    return False

def run_case(deflect_before_trigger):
    fc = FakeClient(); cp.client = fc
    ensure_monitor()
    cp.arm("obstacle")
    cp.AUTO_STOP.clear()                          # 同 reengage_autopilot：起航线前先清停止位
    with cp.LOCK: cp.STATE["ap_on"] = True
    threading.Thread(target=mimic_route, args=(fc,), daemon=True).start()

    ok = wait_until(lambda: cp.STATE["t0"] is not None, 8)
    chk("预警按时发出(ETA≤5s)", ok)
    if not ok: return
    t0 = cp.STATE["t0"]
    chk("预警时诱因未生效", not cp.STATE["cause_fired"])
    chk("接近段无误判(rt为空)", cp.STATE["rt"] is None)
    chk("预警时ETA≈5s(%.1f)" % (cp.STATE["eta"] or -1), cp.STATE["eta"] is not None and cp.STATE["eta"] <= 5.3)

    if deflect_before_trigger:
        time.sleep(1.0)
        with fc.lock: fc.joy_elev = -0.5          # 摇杆压杆(生效前)
        ok = wait_until(lambda: cp.STATE["rt"] is not None, 3.0)
        chk("生效前动杆→立即记RT", ok)
        chk("RT≈动杆时刻(%.2f)" % (cp.STATE["rt"] or -1), ok and 0.9 < cp.STATE["rt"] < 2.4)   # 含滑变+1s宽容窗延迟
        chk("动杆→AP立即off", wait_until(lambda: cp.STATE["ap_on"] is False, 1))
        z_before = fc.zero_events
        ok = wait_until(lambda: cp.STATE["cause_fired"], 6)
        chk("已手动后诱因仍按时生效", ok and abs(time.time() - (t0 + config.ALERT_LEAD_S)) < 0.8)
        chk("已手动→生效时不清速度(保持off不干预)", fc.zero_events == z_before)
        chk("note含已手动", "已手动" in cp.STATE["note"])
    else:
        ok = wait_until(lambda: cp.STATE["cause_fired"], 7)
        dt = time.time() - (t0 + config.ALERT_LEAD_S)
        chk("诱因在t0+5s生效(偏差%.2fs)" % dt, ok and abs(dt) < 0.5)
        chk("生效前无误判(rt为空)", cp.STATE["rt"] is None)
        chk("生效→AP断开", wait_until(lambda: cp.STATE["ap_on"] is False, 1))
        chk("生效→ap_stop已调", fc.ap_stopped >= 1)
        chk("生效→清速度悬停", fc.zero_events >= 3)
        time.sleep(0.6)                            # 悬停稳定期(线程收尾ELEV回中)
        chk("悬停期无误判(rt为空)", cp.STATE["rt"] is None)
        with fc.lock: fc.joy_elev = -0.5          # 摇杆压杆
        ok = wait_until(lambda: cp.STATE["rt"] is not None, 2)
        exp = time.time() - t0
        chk("动杆→通道B记RT", ok)
        chk("RT合理(%.2f≈%.2f)" % (cp.STATE["rt"] or -1, exp), ok and abs(cp.STATE["rt"] - exp) < 0.4)
        chk("phase=takeover", cp.STATE["phase"] == "takeover")
        chk("rt_control通道", cp.STATE["rt_control"] is not None)
    cp.reset()

print("== 测1: 全自动流程(预警→生效→接管) =="); run_case(False)
print("== 测2: 生效前手动接管 =="); run_case(True)
print("\n" + ("ALL FLOW TESTS PASSED" if not FAIL else "FAILED: %d 项" % len(FAIL)))
sys.exit(1 if FAIL else 0)
