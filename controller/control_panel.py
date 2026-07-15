# -*- coding: utf-8 -*-
"""
eVTOL 接管实验 · 操作台控制面板（被试手动飞，本面板只负责"进区即触发"）
==================================================================
在 sim 本机跑： python -X utf8 control_panel.py
浏览器打开：
  操作台(你看/选诱因/选模态/AP开关)：http://<sim-ip>:8000/
  被试 HMI(接管提示)               ：http://<sim-ip>:8000/hmi
流程：选 HMI 模态 → 点诱因 arm → AP 飞向触发区，面板实时算 距离/接近速度→ETA
→ ETA≤ALERT_LEAD_S(5s) 时预警：HMI 按模态报警 + t0 起算 RT
→ t0+5s 诱因生效：AP 还开着→断开+清速度悬停；已被手动接管→保持 AP off 不动
（风切变额外起注入线程）。接管识别双通道：触摸屏点击 或 舵面偏离"己方命令值/静息位"
超死区连续2帧——被试任意阶段动杆都立即拿回控制权(AP off)，HMI 可一键切回自动。
另有：手动立即触发(=立即预警)、复位、传送。纯标准库。
"""
import os, json, time, threading, csv, math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = os.environ.get("DEVKIT_URL", "http://127.0.0.1:5000")
import geo
from devkit_client import DevKitClient

PORT = int(os.environ.get("PANEL_PORT", "8000"))
HERE = os.path.dirname(os.path.abspath(__file__))
LOGD = os.path.join(HERE, "logs"); os.makedirs(LOGD, exist_ok=True)
SESSION_CSV = os.path.join(LOGD, "panel_events.csv")

client = DevKitClient()
LOCK = threading.Lock()
CAUSE_CN = {"wind_shear": "风切变", "ap_fail": "自驾故障", "obstacle": "障碍物", "blank": "空白"}
MODALITY_CN = {"visual": "视觉", "audio": "听觉", "multimodal": "视觉+听觉"}

# 全局设置（跨 trial 保持）：HMI 模态由操作台三个按钮控制
SETTINGS = {"modality": "multimodal"}

# 停机坪（返场点，来自 config.HELIPAD）；起点随所选诱因取 SCENARIOS[cause].restore
HELIPAD = getattr(config, "HELIPAD", None)

def new_state():
    return {"armed_cause": None, "modality": "", "trial_id": "", "phase": "idle",
            "armed_ok": False, "t0": None, "rt": None, "rt_touch": None, "rt_control": None,
            "alt": None, "dist": None, "in_zone": False, "max_g": 0.0,
            "lat": None, "lng": None, "vspeed": None, "ap_on": None, "note": "",
            "eta": None, "trigger_at": None, "cause_fired": False}
STATE = new_state()
TEL = []
CMD = {}      # 我们代码当前/上一次命令的舵面值 {axis:(cur,prev)}；通道B与其比对而非静态基线
REST = {}     # 摇杆静息位（arm/重开AP时抓取），未被命令的轴与其比对
DHIST = []    # (t, dist) 滑窗 → 接近速度与预计进区ETA
_DEV_N = 0    # 连续超死区采样计数
INJECT_STOP = threading.Event()
AUTO_STOP = threading.Event()   # 阶梯式自动驾驶航线的停止标志
SUBS = []  # SSE 队列
REC_LOCK = threading.Lock()
REC_DIR = os.environ.get("REC_DIR", r"F:\Evtol_TAKEOVER")   # 采集CSV存这里(sim主机F盘)
REC = {"on": False, "file": None, "writer": None, "fields": [], "path": "",
       "name": "", "subject": "", "n": 0, "started": None, "err": ""}

def g(st, k, d=0.0):
    v = st.get(k, d); return d if v is None else v

def broadcast(obj):
    line = ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8")
    for q in list(SUBS):
        try: q.append(line)
        except Exception: pass

def flush_tel():
    if not TEL: return
    tid = STATE.get("trial_id") or time.strftime("%H%M%S")
    p = os.path.join(LOGD, "tel_%s.csv" % tid)
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["t", "rel_t0", "cause", "phase", "lat", "lng", "alt_ft", "agl_ft",
                    "vspeed", "gforce", "aileron", "elevator", "rudder", "vbx", "vby", "vbz"])
        w.writerows(TEL)

def append_event():
    head = not os.path.exists(SESSION_CSV)
    with open(SESSION_CSV, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if head:
            w.writerow(["trial_id", "cause", "modality", "t0", "rt_s", "rt_touch_s",
                        "rt_control_s", "in_zone_alt_ft", "max_g", "note", "ts"])
        w.writerow([STATE["trial_id"], STATE["armed_cause"], STATE["modality"],
                    STATE["t0"], STATE["rt"], STATE["rt_touch"], STATE["rt_control"],
                    STATE["alt"], round(STATE["max_g"], 3), STATE["note"],
                    time.strftime("%Y-%m-%d %H:%M:%S")])

def _hdist(st, hp):
    lat, lng = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
    if lat is None: return 9e9
    return geo.distance_m(lat, lng, hp["lat"], hp["lng"])

def _zero_vel():
    for vn in (config.SV_VEL_BODY_X, config.SV_VEL_BODY_Y, config.SV_VEL_BODY_Z):
        try: client.set_param(vn, 0.0)
        except Exception: pass

def cmd_set(ax, v):
    """记录我们即将写入的舵面命令值。仅在值变化时更新(prev,t_change)——
    重复写同值不得冲掉prev/刷新时间戳，否则滑变宽容窗口失效。"""
    with LOCK:
        cur, prev, tc = CMD.get(ax, (None, None, 0.0))
        if cur is None:
            CMD[ax] = (v, v, time.time())
        elif v != cur:
            CMD[ax] = (v, cur, time.time())

def capture_rest():
    """抓摇杆静息位(此刻被试没在操纵)：arm 时与重开 AP 时调用。"""
    global _DEV_N
    try:
        st = client.get_state() or {}
    except Exception:
        st = {}
    with LOCK:
        for ax in config.CONTROL_AXES:
            REST[ax] = g(st, ax)
    _DEV_N = 0

def manual_input(evidence=""):
    """确认到被试有意操控：AP在飞→立即交出控制权(AP off)；t0已起算→记通道B RT。"""
    was_ap = STATE["ap_on"]
    print("[通道B] 判定手动操控 %s ap_on=%s t0=%s" % (evidence, was_ap, STATE["t0"]))
    if was_ap:
        AUTO_STOP.set()                    # 航线线程退出并回中舵面/油门中性
        try: client.ap_stop()              # 释放可能在顶住的旋翼定点悬停(风切变保持悬停时),交还被试
        except Exception: pass
        with LOCK: STATE["ap_on"] = False
    if STATE["t0"] and STATE["rt"] is None:
        mark_takeover("control")
    elif was_ap and STATE["t0"] is None and "预警前手动接管" not in STATE["note"]:
        with LOCK: STATE["note"] += "；预警前手动接管(AP off:%s)" % evidence
        broadcast({"type": "manual_control"})

def detect_manual(st):
    """通道B：实际舵面 vs 合法区间。未被命令的轴：静息位±死区。被命令的轴：
    命令刚变化的 CMD_RAMP_GRACE_S 内=新旧命令值之间±死区(MSFS舵面是~0.2s滑变过去的，
    中间过渡值不是手动!)；窗口过后=当前命令值±死区。超区间且连续 DEFLECT_CONFIRM_N 帧
    → 判手动。全程有效(AP飞行中也允许被试夺权)。"""
    global _DEV_N
    if not (STATE["ap_on"] or (STATE["t0"] and STATE["rt"] is None)):
        return
    now = time.time()
    dev = None
    for ax in config.CONTROL_AXES:
        a = g(st, ax)
        cur, prev, tc = CMD.get(ax, (None, None, 0.0))
        if cur is None:
            lo = hi = REST.get(ax, 0.0)
        elif now - tc < config.CMD_RAMP_GRACE_S:
            lo, hi = min(cur, prev), max(cur, prev)
        else:
            lo = hi = cur
        if a < lo - config.CONTROL_DEADBAND or a > hi + config.CONTROL_DEADBAND:
            dev = "%s=%.3f 合法[%.2f,%.2f] cmd=(%s,%s,Δt%.2fs)" % (
                ax.split("_")[0], a, lo, hi, cur, prev, now - tc)
            break
    _DEV_N = _DEV_N + 1 if dev else 0
    if _DEV_N >= config.DEFLECT_CONFIRM_N:
        _DEV_N = 0
        manual_input(dev)

def _run_seg(hp, horizontal, v_down, T):
    """跑一段:horizontal=True→只注入指向停机坪的水平速度(平飞);False→只注入垂向v_down(下降)。
    速度按 AUTO_SEG_RAMP_S 渐入渐出(0→满→0),避免突起突停的抖动。可被 AUTO_STOP 立即打断。"""
    period = 1.0 / config.AUTO_INJECT_HZ
    ramp = max(0.05, config.AUTO_SEG_RAMP_S)
    t0 = time.time()
    while not AUTO_STOP.is_set():
        e = time.time() - t0
        if e >= T: break
        k = min(1.0, e / ramp, max(0.0, (T - e) / ramp))   # 梯形渐入渐出
        st = client.get_state() or {}
        lat, lng = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
        try:
            if horizontal and lat is not None:
                hdg = g(st, "PLANE_HEADING_DEGREES_TRUE")
                b = geo.bearing_deg(lat, lng, hp["lat"], hp["lng"])
                rel = math.radians(((b - hdg + 540) % 360) - 180)   # 停机坪相对机头的角
                vf = config.AUTO_V_FWD * k
                client.set_param(config.SV_VEL_BODY_Z, vf * math.cos(rel))   # 前进分量
                client.set_param(config.SV_VEL_BODY_X, vf * math.sin(rel))   # 横向分量→合速度正指停机坪
                client.set_param(config.SV_VEL_BODY_Y, 0.0)                  # 平飞不掉高
            else:
                client.set_param(config.SV_VEL_BODY_X, 0.0)
                client.set_param(config.SV_VEL_BODY_Z, 0.0)
                client.set_param(config.SV_VEL_BODY_Y, -abs(v_down) * k)     # 只下降
        except Exception:
            pass
        if AUTO_STOP.wait(period): break

def _auto_route_loop():
    """自主航线=自写速度矢量制导+交替阶梯(彻底不用DevKit AP,实测rotY≈0零摇摆)。
    循环:平飞一段(速度矢量指向停机坪)→下降一段→交替,直到到达停机坪上方。
    远段时长久(动作幅度大)、近段短(幅度小)。可被关AP/故障触发立即打断。"""
    hp = HELIPAD
    if not hp:
        return
    st0 = client.get_state() or {}
    d0 = max(1.0, _hdist(st0, hp))                     # 起始水平距离,用于远近插值
    def lerp_near_far(near, far):
        frac = min(1.0, _hdist(client.get_state() or {}, hp) / d0)   # 1=最远,0=到达
        return near + (far - near) * frac
    t_start = time.time()
    while not AUTO_STOP.is_set():
        st = client.get_state() or {}
        if st.get("PLANE_LATITUDE") is None: break
        dist_h = _hdist(st, hp)
        alt = g(st, "PLANE_ALTITUDE")
        arrived_h = dist_h <= config.AUTO_ARRIVE_DIST_M
        arrived_v = alt <= config.AUTO_ARRIVE_ALT_FT + 6
        if (arrived_h and arrived_v) or (time.time() - t_start > 300):
            break
        # 平飞段(还没水平到位才飞)
        if not arrived_h:
            _run_seg(hp, True, 0.0, lerp_near_far(config.AUTO_FWD_S_NEAR, config.AUTO_FWD_S_FAR))
        if AUTO_STOP.is_set(): break
        # 下降段(还在停机坪高度之上才降)
        st = client.get_state() or {}
        if g(st, "PLANE_ALTITUDE") > config.AUTO_ARRIVE_ALT_FT + 3:
            _run_seg(hp, False, config.AUTO_V_DOWN, lerp_near_far(config.AUTO_DOWN_S_NEAR, config.AUTO_DOWN_S_FAR))
    _zero_vel()
    with LOCK: STATE["ap_on"] = False   # 航线结束/被打断 → 状态复位

def _throttle_route_loop():
    """AP开=纯操纵阶梯进近:油门:1(前后)+升降舵(升降)。
    若已 arm 某诱因且未触发→先飞向该触发区并降入其高度带(令 monitor_loop 自动触发:
    任一诱因触发即被 AUTO_STOP 打断=交还被试);
    否则/触发后→飞停机坪上方约40ft 停。平飞段/下降段各≤5s 交替。可被 AUTO_STOP 立即打断。"""
    THR = "GENERAL_ENG_THROTTLE_LEVER_POSITION:1"; ELEV = "ELEVATOR_POSITION"
    hp = HELIPAD
    if not hp:
        return
    st0 = client.get_state() or {}
    neut = g(st0, THR, 46.5)
    FWD = min(neut + 32.0, 90.0)        # 平飞段固定油门(调速旋钮:越大越快, 极限~5m/s)
    ARRIVE = 25.0; ELEV_DN = -0.85; HZ = 12.0

    def target():
        """当前航路点(lat,lng,目标高度)。有已arm且未触发的诱因→其触发区(降到高度带内);否则→停机坪。"""
        cause = STATE.get("armed_cause")
        trig = config.SCENARIOS.get(cause, {}).get("trigger") if (cause and cause != "blank") else None
        if trig and STATE.get("t0") is None:
            # 障碍物: 降到高度带中值(与楼顶齐平, 不从楼顶上方飞过); 其它诱因: 高度带偏上
            talt = (trig["alt_min_ft"] + trig["alt_max_ft"]) / 2.0 if cause == "obstacle" else trig["alt_max_ft"] - 20.0
            return trig["lat"], trig["lng"], talt
        return hp["lat"], hp["lng"], hp["alt_ft"] + 40.0

    def dto(tlat, tlng):
        st = client.get_state() or {}
        la, lo = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
        return st, (geo.distance_m(la, lo, tlat, tlng) if la is not None else 9e9)

    cur = None; dmin = 9e9
    while not AUTO_STOP.is_set():
        tlat, tlng, talt = target()
        if (tlat, tlng) != cur:            # 航路点变了(如触发后转向停机坪) → 重置最近距离
            cur = (tlat, tlng); dmin = 9e9
        st, dist = dto(tlat, tlng); alt = g(st, "PLANE_ALTITUDE")
        dmin = min(dmin, dist)
        if (dist < ARRIVE and alt <= talt + 8) or dist > dmin + 25:   # 到位 或 跑偏/飞过头
            break
        # 平飞段
        if dist > ARRIVE:
            t = time.time()
            while not AUTO_STOP.is_set() and time.time() - t < 5.0:
                cmd_set(ELEV, 0.0)
                client.set_param(THR, FWD); client.set_param(ELEV, 0.0)
                st2 = client.get_state() or {}
                la, lo = st2.get("PLANE_LATITUDE"), st2.get("PLANE_LONGITUDE")
                dnow = geo.distance_m(la, lo, tlat, tlng) if la is not None else 9e9
                dmin = min(dmin, dnow)
                if dnow < ARRIVE or dnow > dmin + 25 or target()[0] != tlat:
                    break
                if AUTO_STOP.wait(1.0 / HZ):
                    break
        if AUTO_STOP.is_set():
            break
        # 下降段
        tlat, tlng, talt = target()
        st, dist = dto(tlat, tlng); alt = g(st, "PLANE_ALTITUDE")
        if alt > talt + 8:
            thr_d = neut if dist < ARRIVE + 15 else FWD
            t = time.time()
            while not AUTO_STOP.is_set() and time.time() - t < 5.0:
                cmd_set(ELEV, ELEV_DN)
                client.set_param(THR, thr_d); client.set_param(ELEV, ELEV_DN)
                if g(client.get_state() or {}, "PLANE_ALTITUDE") <= talt:
                    break
                if AUTO_STOP.wait(1.0 / HZ):
                    break
    # 收尾:升降舵回中、油门中性(松开操纵→自然悬停)
    try:
        cmd_set(ELEV, 0.0)
        client.set_param(ELEV, 0.0); client.set_param(THR, neut)
    except Exception:
        pass
    with LOCK:
        STATE["ap_on"] = False

def reengage_autopilot():
    """切回自动驾驶=恢复自主航线(阶梯式下降+飞向停机坪)。先停掉可能在跑的旧线程再起新线程。"""
    if STATE.get("ap_on"):        # 已在自主飞行→直接返回,避免重启航线造成 on→off→on 抖动/重置静息基准
        return True
    if not HELIPAD:
        try:
            st = client.get_state() or {}
            if st.get("PLANE_LATITUDE") is not None:
                client.ap_rotor_point(st["PLANE_LATITUDE"], st["PLANE_LONGITUDE"])
        except Exception:
            pass
        return True
    AUTO_STOP.set()
    time.sleep(1.0 / config.AUTO_ROUTE_HZ + 0.2)   # 等旧航线线程退出，避免双线程
    AUTO_STOP.clear()
    capture_rest()               # 重开AP时摇杆位=新静息基准，防重开即误判手动
    with LOCK:
        STATE["ap_on"] = True
        CMD.clear()
    threading.Thread(target=_throttle_route_loop, daemon=True).start()   # 纯操纵油门+升降舵阶梯进近
    return True

def set_ap(on):
    """开=切回自动驾驶(阶梯式下降飞向停机坪)；关=可靠停住(等线程退出后连发两次/ap_stop)。"""
    if on:
        return reengage_autopilot()
    AUTO_STOP.set()
    with LOCK: STATE["ap_on"] = False
    time.sleep(1.0 / config.AUTO_ROUTE_HZ + 0.3)   # 等航线线程退出
    for _ in range(2):
        try: client.ap_stop()
        except Exception: pass
    return True

def _teleport(p):
    if not p:
        return False
    try:
        AUTO_STOP.set()          # 传送前先停掉可能在跑的航线
        client.ap_stop()         # 同事式：先关AP
        for n, v in [("PLANE_LATITUDE", p["lat"]), ("PLANE_LONGITUDE", p["lng"]),
                     ("PLANE_ALTITUDE", p.get("alt_ft", 800.0)),
                     ("PLANE_HEADING_DEGREES_TRUE", p.get("heading", 0.0)),
                     ("PLANE_PITCH_DEGREES", 0.0), ("PLANE_BANK_DEGREES", 0.0)]:
            client.set_param(n, v)
        for n in (config.SV_VEL_BODY_X, config.SV_VEL_BODY_Y, config.SV_VEL_BODY_Z):
            client.set_param(n, 0.0)   # 清零速度，落定即稳
        with LOCK:
            DHIST.clear(); STATE["eta"] = None   # 位置跳变→接近速度滑窗作废，防假预警
        return True
    except Exception:
        return False

def start_point():
    """当前诱因的起点(恢复点)；未选诱因则回退停机坪。"""
    c = STATE.get("armed_cause")
    p = config.SCENARIOS.get(c, {}).get("restore") if c else None
    return p or HELIPAD

def teleport_start():
    return _teleport(start_point())

def teleport_helipad():
    return _teleport(HELIPAD)

def do_alert(cause, manual=False):
    """预警：HMI 立即报警，t0=RT计时起点；诱因在 ALERT_LEAD_S 秒后才生效。"""
    with LOCK:
        if STATE["t0"] is not None:
            return
        STATE["t0"] = time.time()
        STATE["trigger_at"] = STATE["t0"] + config.ALERT_LEAD_S
        STATE["phase"] = "alerted"
        STATE["modality"] = SETTINGS["modality"]
        STATE["note"] = ("手动" if manual else "预测进区") + "预警"
    broadcast({"type": "takeover_request", "cause": cause, "modality": SETTINGS["modality"],
               "text": config.CAUSE_TEXT.get(cause, "请接管"), "t0": STATE["t0"],
               "lead_s": config.ALERT_LEAD_S})

def do_cause(cause):
    """预警 ALERT_LEAD_S 秒后：诱因生效。
    AP 还开着→断开(ap_stop)+清速度。此机型断AP后靠自身飞控**被动悬停**(保持高度+姿态自稳,不会掉),
    风切变把横向阵风叠加其上,被试可用杆实时对抗;已被手动接管→AP 保持 off。"""
    with LOCK:
        if STATE["cause_fired"]:
            return
        STATE["cause_fired"] = True
        was_ap = STATE["ap_on"]
        if STATE["phase"] == "alerted":
            STATE["phase"] = "triggered"
    if was_ap:
        AUTO_STOP.set()                        # 停自主航线(线程收尾回中舵面/油门中性)
        try: client.ap_stop()                  # 断AP——飞机自身被动悬停(不会掉)
        except Exception: pass
        _zero_vel()                            # 清速度→被动悬停起点
        with LOCK: STATE["ap_on"] = False
    if cause == "wind_shear":
        INJECT_STOP.clear()
        threading.Thread(target=inject_windshear, daemon=True).start()
    with LOCK: STATE["note"] += "；诱因生效(断AP·被动悬停)" + ("" if was_ap else "(已手动)")
    broadcast({"type": "cause_active", "cause": cause})

def inject_windshear():
    """末端横向风切变/阵风:持续注入 横向阵风(VBX) + 一定垂直扰动(VBY),正弦调制来回吹。
    **不强写横滚**——强写会让被试修不动;滚转由 飞机(自动悬停在顶)/被试 对横向推移的响应
    自然产生,被试可用杆实时对抗。收尾清横向/垂向速度(不动横滚,交还被试)。
    滚转手感不够可加大 lateral_vx_fts;若想额外"踢"一下滚转再单独加冲量。"""
    ws = config.WIND_SHEAR
    hz = max(10.0, config.WIND_SHEAR_INJECT_HZ)
    gh = ws.get("gust_hz", 0.8)
    vx = ws.get("lateral_vx_fts", 26.0)
    dn = abs(ws.get("down_vspeed_fts", -22.0)); loss = ws.get("speed_loss_frac", 0.0)
    z0 = g(client.get_state() or {}, config.SV_VEL_BODY_Z)
    t0 = time.time(); end = t0 + ws["duration_s"]
    while time.time() < end and not INJECT_STOP.is_set():
        s = math.sin(2 * math.pi * gh * (time.time() - t0))        # -1..1 阵风相位
        try:
            client.set_param(config.SV_VEL_BODY_X, vx * s)                     # 横向推移(右/左来回)
            client.set_param(config.SV_VEL_BODY_Y, -dn * (0.4 + 0.6 * abs(s))) # 下沉阵风
            if loss > 0:
                client.set_param(config.SV_VEL_BODY_Z, z0 * (1 - loss))        # (可选)纵向空速骤减
        except Exception: pass
        time.sleep(1.0 / hz)
    try:
        client.set_param(config.SV_VEL_BODY_X, 0.0)
        client.set_param(config.SV_VEL_BODY_Y, 0.0)
    except Exception: pass

def mark_takeover(channel):
    fired = False; rtv = None
    with LOCK:
        if STATE["t0"] and STATE["rt"] is None:
            rt = round(time.time() - STATE["t0"], 3)
            STATE["rt"] = rt; STATE["rt_" + channel] = rt; STATE["phase"] = "takeover"
            STATE["note"] += " 接管(%s)" % channel
            fired = True; rtv = rt
    if fired:
        broadcast({"type": "takeover_done", "channel": channel, "rt": rtv})  # 通知HMI:红色报警→已接管
        append_event()

def rec_start(subject):
    """开始采集:取一帧 /get 的全部字段名做表头; 文件名=被试_诱因_模态_时间.csv, 存 REC_DIR(sim F盘)。"""
    with REC_LOCK:
        if REC["on"]:
            return True, REC["path"]
        try:
            st = client.get_state() or {}        # 单次探一帧拿字段做表头; MSFS在菜单会超时→干净失败,不卡
        except Exception:
            st = {}
        fields = sorted(st.keys())
        if not fields:
            REC["err"] = "DevKit 无数据(MSFS未进入飞行?), 未开始"; return False, REC["err"]
        cause = STATE.get("armed_cause") or "na"
        modality = SETTINGS.get("modality") or "na"
        subj = "".join(ch for ch in (subject or "").strip() if ch.isalnum() or ch in "_-") or "S"
        fname = "%s_%s_%s_%s.csv" % (subj, cause, modality, time.strftime("%Y%m%d_%H%M%S"))
        try:
            os.makedirs(REC_DIR, exist_ok=True)
            path = os.path.join(REC_DIR, fname)
            f = open(path, "w", newline="", encoding="utf-8-sig")
        except Exception as e:
            REC["err"] = "建目录/文件失败:%s" % e; return False, str(e)
        w = csv.writer(f)
        w.writerow(["ts_unix", "ts_local", "rel_t0_s", "phase", "cause", "modality",
                    "ap_on", "in_zone", "dist_trig_m", "eta_s", "rt_s"] + fields)
        REC.update({"on": True, "file": f, "writer": w, "fields": fields, "path": path,
                    "name": fname, "subject": subj, "n": 0, "started": time.time(), "err": ""})
    print("[采集] 开始 ->", path)
    return True, path

def rec_stop():
    with REC_LOCK:
        f = REC["file"]; REC["on"] = False
        if f:
            try: f.flush(); f.close()
            except Exception: pass
        REC["file"] = None; REC["writer"] = None
    print("[采集] 停止, 共 %d 帧" % REC.get("n", 0))
    return True

def rec_write(st):
    """每帧写一行:时间戳(unix+本地) + 试次上下文(相对t0/阶段/诱因/模态) + 全部 DevKit 字段值。"""
    if not REC["on"]:
        return
    with REC_LOCK:
        w = REC["writer"]
        if not w:
            return
        now = time.time()
        loc = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)) + (".%03d" % int(round((now - int(now)) * 1000)))
        rel = (now - STATE["t0"]) if STATE.get("t0") else ""
        row = [round(now, 3), loc, (rel if rel == "" else round(rel, 3)),
               STATE.get("phase"), STATE.get("armed_cause"), SETTINGS.get("modality"),
               STATE.get("ap_on"), STATE.get("in_zone"), STATE.get("dist"),
               STATE.get("eta"), STATE.get("rt")]
        row += [st.get(c) for c in REC["fields"]]
        try:
            w.writerow(row); REC["n"] += 1
            if REC["n"] % 20 == 0:
                REC["file"].flush()
        except Exception as e:
            REC["err"] = "写入异常:%s" % e

def monitor_loop():
    period = 1.0 / config.CONTROL_HZ
    i = 0
    while True:
        i += 1
        try: st = client.get_state()
        except Exception: st = None
        if st:
            with LOCK:
                STATE["alt"] = round(g(st, "PLANE_ALTITUDE"), 1)
                STATE["vspeed"] = round(g(st, "VERTICAL_SPEED"), 1)
                STATE["lat"], STATE["lng"] = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
            detect_manual(st)   # 通道B/随时手动接管：全程有效(AP飞行中动杆→AP off)
            rec_write(st)       # 数据采集(若在采集中): 时间戳 + 全部 DevKit 字段
            cause, phase = STATE["armed_cause"], STATE["phase"]
            now = time.time()
            if cause and cause != "blank" and phase in ("waiting", "alerted", "triggered", "takeover"):
                trig = config.SCENARIOS.get(cause, {}).get("trigger")
                if trig:
                    lat, lng = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
                    alt = g(st, "PLANE_ALTITUDE")
                    dist = geo.distance_m(lat, lng, trig["lat"], trig["lng"]) if lat else 9999
                    inz = (dist <= trig["radius_m"] and trig["alt_min_ft"] <= alt <= trig["alt_max_ft"])
                    # 接近速度(滑窗) → 预计进区 ETA(到边界)
                    eta = None
                    DHIST.append((now, dist))
                    while DHIST and now - DHIST[0][0] > config.CLOSE_RATE_WIN_S:
                        DHIST.pop(0)
                    if inz:
                        eta = 0.0
                    elif len(DHIST) >= 2 and now - DHIST[0][0] > 0.3:
                        v = (DHIST[0][1] - dist) / (now - DHIST[0][0])   # m/s, >0=接近
                        if abs(v) > 100.0:
                            DHIST.clear()        # 位置跳变(传送/复位)→速度不可信，重建滑窗
                        elif v > 0.3:
                            eta = max(0.0, (dist - trig["radius_m"]) / v)
                    with LOCK:
                        STATE["dist"] = round(dist, 1); STATE["in_zone"] = inz
                        STATE["eta"] = (round(eta, 1) if eta is not None else None)
                        STATE["max_g"] = max(STATE["max_g"], g(st, "G_FORCE"))
                    rel = (now - STATE["t0"]) if STATE["t0"] else ""
                    TEL.append([round(now, 3), (rel if rel == "" else round(rel, 3)),
                                cause, phase, lat, lng, round(alt, 1),
                                round(g(st, "PLANE_ALT_ABOVE_GROUND"), 1), round(g(st, "VERTICAL_SPEED"), 1),
                                round(g(st, "G_FORCE"), 3), round(g(st, "AILERON_POSITION"), 4),
                                round(g(st, "ELEVATOR_POSITION"), 4), round(g(st, "RUDDER_POSITION"), 4),
                                round(g(st, config.SV_VEL_BODY_X), 3), round(g(st, config.SV_VEL_BODY_Y), 3),
                                round(g(st, config.SV_VEL_BODY_Z), 3)])
                    if phase == "waiting":
                        if not inz:
                            with LOCK: STATE["armed_ok"] = True
                        if STATE["armed_ok"] and (inz or (eta is not None and eta <= config.ALERT_LEAD_S)):
                            do_alert(cause)   # ETA≤预警提前量(或已进区兜底) → 预警+起算RT
            # 诱因生效检查(独立于phase：预警后被试已接管也照常生效；含blank手动流程)
            if STATE["trigger_at"] and not STATE["cause_fired"] and now >= STATE["trigger_at"]:
                do_cause(cause or "blank")
        # ap_on 由 reengage/set_ap/航线线程/manual_input 直接维护
        time.sleep(period)

def arm(cause, tid=""):
    global STATE, TEL
    INJECT_STOP.set(); AUTO_STOP.set(); flush_tel()
    with LOCK:
        STATE = new_state()
        STATE["armed_cause"] = cause
        STATE["trial_id"] = tid or (cause + "_" + time.strftime("%H%M%S"))
        STATE["phase"] = "waiting"
        TEL = []
        CMD.clear(); DHIST.clear()
    capture_rest()               # 摇杆此刻静息位 = 未命令轴的比对基准
    broadcast({"type": "reset"})

def reset():
    global STATE, TEL
    INJECT_STOP.set(); AUTO_STOP.set(); flush_tel()
    with LOCK:
        STATE = new_state(); TEL = []
        CMD.clear(); DHIST.clear()
    broadcast({"type": "reset"})

# ---------------- 前端 ----------------
PANEL_HTML = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>eVTOL 接管实验 · 操作台</title><style>
*{box-sizing:border-box;font-family:system-ui,'Microsoft YaHei',sans-serif}
body{margin:0;background:#0f1420;color:#e8edf6}.wrap{max-width:860px;margin:0 auto;padding:16px}
h1{font-size:19px;margin:6px 0 12px}.lbl{font-size:12px;opacity:.6;margin:14px 0 6px}
.banner{border-radius:14px;padding:20px 16px;text-align:center;font-size:28px;font-weight:800;transition:.2s}
.sub{font-size:14px;font-weight:500;opacity:.85;margin-top:6px}
.idle{background:#26303f}.waiting{background:#1d4e89}.alerted{background:#9a6a00}.triggered{background:#b23b1e}.takeover{background:#1f7a43}
.btns{display:grid;gap:10px}.c4{grid-template-columns:repeat(4,1fr)}.c3{grid-template-columns:repeat(3,1fr)}
button{border:0;border-radius:12px;padding:15px 8px;font-size:16px;font-weight:700;color:#fff;cursor:pointer}
small{font-weight:400;opacity:.9}
.b-ws{background:#c77d0a}.b-ap{background:#7a3fb0}.b-ob{background:#0a7fb0}.b-bl{background:#4a5568}
.m{background:#2b3a4d}.m.sel{background:#2563eb}
button.sel{outline:4px solid #fff}
.row{display:flex;gap:10px;margin:10px 0}.row button{flex:1}
.b-fire{background:#b23b1e}.b-reset{background:#334155}
.b-apon{background:#166534}.b-apoff{background:#7f1d1d}.b-tp{background:#0e7490}.b-savtp{background:#475569}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px}
.card{background:#1a2130;border-radius:10px;padding:10px 12px}.k{font-size:12px;opacity:.6}.v{font-size:20px;font-weight:700;margin-top:2px}
.zone{font-size:12px;opacity:.65;margin-top:10px;line-height:1.6}.in{color:#4ade80}.out{color:#f59e0b}
</style></head><body><div class=wrap>
<h1>eVTOL 接管实验 · 操作台 <small style="opacity:.5">被试手动飞，进区自动触发</small></h1>
<div id=banner class="banner idle">准备<div class=sub id=bsub>先选 HMI 模态，再点一个诱因</div></div>

<div class=lbl>① HMI 反馈模态（当次实验）</div>
<div class="btns c3">
<button class="m" id=m-visual onclick="setmod('visual')">视觉<br><small>闪红+文字</small></button>
<button class="m" id=m-audio onclick="setmod('audio')">听觉<br><small>蜂鸣提示</small></button>
<button class="m" id=m-multimodal onclick="setmod('multimodal')">视觉+听觉<br><small>两者兼有</small></button>
</div>

<div class=lbl>② 诱因（arm 触发区）</div>
<div class="btns c4">
<button class=b-ws onclick="arm('wind_shear')">风切变<br><small>掉高扰动</small></button>
<button class=b-ap onclick="arm('ap_fail')">自驾故障<br><small>断AP</small></button>
<button class=b-ob onclick="arm('obstacle')">障碍物<br><small>只弹HMI</small></button>
<button class=b-bl onclick="arm('blank')">空白<br><small>手动触发</small></button>
</div>

<div class=lbl>③ 控制</div>
<div class=row>
<button class=b-fire onclick="fire()">⚡ 手动立即触发</button>
<button id=apbtn class=b-apon onclick="toggleap()">自动驾驶：—</button>
<button class=b-reset onclick="rst()">↺ 复位(下一trial)</button>
</div>

<div class=lbl>④ 传送（起点随所选诱因·800ft｜停机坪返场）</div>
<div class=row>
<button class=b-tp onclick="teleport()">⤢ 传送到起点</button>
<button class=b-savtp onclick="tphelipad()">🏁 传送到停机坪</button>
</div>
<div class=zone id=startinfo></div>

<div class=grid>
<div class=card><div class=k>高度 ALT(MSL)</div><div class=v id=alt>—</div></div>
<div class=card><div class=k>距触发区中心</div><div class=v id=dist>—</div></div>
<div class=card><div class=k>垂速 ft/min</div><div class=v id=vs>—</div></div>
<div class=card><div class=k>接管 RT</div><div class=v id=rt>—</div></div>
</div>
<div class=zone id=zone></div>

<div class=lbl>⑤ 数据采集（存 sim 主机 F:\\Evtol_TAKEOVER，按 被试_诱因_模态_时间 自动命名）</div>
<div class=row>
<input id=subj placeholder="被试编号 如 P01" autocomplete=off style="flex:1;border-radius:12px;border:0;padding:14px;font-size:16px;background:#1a2130;color:#e8edf6">
<button id=recbtn class=b-apon onclick="togglerec()" style="flex:1">● 开始采集</button>
</div>
<div class=zone id=recinfo></div>
</div><script>
const CN={wind_shear:'风切变',ap_fail:'自驾故障',obstacle:'障碍物',blank:'空白'};
let apOn=null,recOn=false;
function setmod(m){fetch('/modality',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({modality:m})})}
function arm(c){fetch('/arm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cause:c})})}
function fire(){fetch('/fire',{method:'POST'})}
function rst(){fetch('/reset',{method:'POST'})}
function toggleap(){fetch('/ap',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({on:!apOn})})}
function togglerec(){if(!recOn){let s=document.getElementById('subj').value.trim();fetch('/rec_start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({subject:s})}).then(r=>r.json()).then(d=>{if(!d.ok)alert('采集启动失败：'+(d.info||''))})}else{fetch('/rec_stop',{method:'POST'})}}
function teleport(){if(confirm('把飞机传送到当前诱因的起点(800ft)？会立即重定位飞机。'))fetch('/teleport',{method:'POST'})}
function tphelipad(){if(confirm('把飞机传送到停机坪？'))fetch('/teleport_helipad',{method:'POST'})}
function selBtns(sel,mod){['wind_shear','ap_fail','obstacle','blank'].forEach(c=>{});}
async function tick(){try{let s=await(await fetch('/status')).json();
 let b=document.getElementById('banner');b.className='banner '+s.phase;
 // 模态高亮
 ['visual','audio','multimodal'].forEach(m=>{let el=document.getElementById('m-'+m);if(el)el.classList.toggle('sel',s.modality===m)});
 // 诱因高亮
 document.querySelectorAll('.c4 button').forEach(x=>x.classList.remove('sel'));
 let mi={wind_shear:0,ap_fail:1,obstacle:2,blank:3};if(s.armed_cause!=null&&mi[s.armed_cause]!=null)document.querySelectorAll('.c4 button')[mi[s.armed_cause]].classList.add('sel');
 // 横幅
 if(s.phase=='idle'){b.firstChild.textContent='准备';document.getElementById('bsub').textContent='先选 HMI 模态，再点一个诱因'}
 else if(s.phase=='waiting'){b.firstChild.textContent='等待接近触发区 · '+(CN[s.armed_cause]||'');document.getElementById('bsub').textContent=(s.armed_ok?'已 ARMED ✓ 预计进区≤10s时预警':'请先飞到区外建立 ARMED')+(s.eta!=null?(' · 预计进区 '+s.eta+' s'):'')+(s.in_zone?' · 现在区内':'')}
 else if(s.phase=='alerted'){let left=s.trigger_at?Math.max(0,(s.trigger_at-Date.now()/1000)).toFixed(1):'—';b.firstChild.textContent='⚠ 预警中 · '+(CN[s.armed_cause]||'');document.getElementById('bsub').textContent='RT 计时中 · '+left+' s 后诱因生效（动杆或点屏=接管）'}
 else if(s.phase=='triggered'){b.firstChild.textContent='★诱因已生效★ '+(CN[s.armed_cause]||'');document.getElementById('bsub').textContent=(s.ap_on===false?'AP已断开·悬停中 · ':'')+'等待被试接管（点触摸屏 或 动操纵杆）'}
 else if(s.phase=='takeover'){b.firstChild.textContent='已接管 · '+(CN[s.armed_cause]||'');document.getElementById('bsub').textContent='RT = '+s.rt+' s'+(s.cause_fired?'':' · 诱因未生效即接管')}
 // AP 按钮
 apOn=s.ap_on;let ab=document.getElementById('apbtn');
 if(s.ap_on===true){ab.textContent='自动驾驶：开（点击关）';ab.className='b-apon'}
 else if(s.ap_on===false){ab.textContent='自动驾驶：关（点击开）';ab.className='b-apoff'}
 else{ab.textContent='自动驾驶：—';ab.className='b-reset'}
 document.getElementById('alt').textContent=s.alt!=null?s.alt+' ft':'—';
 document.getElementById('dist').innerHTML=s.dist!=null?('<span class="'+(s.in_zone?'in':'out')+'">'+s.dist+' m</span>'):'—';
 document.getElementById('vs').textContent=s.vspeed!=null?s.vspeed:'—';
 document.getElementById('rt').textContent=s.rt!=null?(s.rt+' s'):'—';
 document.getElementById('zone').textContent=(s.modality?('模态：'+({visual:'视觉',audio:'听觉',multimodal:'视觉+听觉'}[s.modality])+'　'):'')+(s.zone||'');
 if(s.start){let st=s.start;document.getElementById('startinfo').textContent='起点(当前诱因)：'+(st.lat!=null?(st.lat.toFixed(5)+', '+st.lng.toFixed(5)+' @'+st.alt_ft+'ft'):'需先选诱因')+(s.helipad?('　｜停机坪：'+s.helipad.lat.toFixed(5)+', '+s.helipad.lng.toFixed(5)):'')}
 let rc=s.rec||{};recOn=!!rc.on;let rb=document.getElementById('recbtn');
 if(recOn){rb.textContent='■ 停止采集';rb.className='b-apoff'}else{rb.textContent='● 开始采集';rb.className='b-apon'}
 let ri;
 if(recOn){ri='● 采集中：'+(rc.name||'')+'　已 '+(rc.n||0)+' 帧'}
 else{ri=(rc.name?('上次：'+rc.name+'（'+(rc.n||0)+' 帧）　'):'')+'目录 '+(rc.dir||'F:\\\\Evtol_TAKEOVER');if(rc.err){ri+='　⚠ '+rc.err}}
 document.getElementById('recinfo').textContent=ri;
 }catch(e){}}
setInterval(tick,400);tick();
</script></body></html>"""

HMI_HTML = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>接管请求</title><style>
*{box-sizing:border-box;font-family:system-ui,'Microsoft YaHei',sans-serif}
html,body{margin:0;height:100%;background:#0b0f16;color:#fff;overflow:hidden}
#s{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;transition:.12s}
#big{font-size:8vw;font-weight:900;text-align:center;padding:0 4vw}
#sub{font-size:3vw;margin-top:1.6vh;opacity:.92;text-align:center}
.calm{background:#0b0f16}.alarm{background:#c00}.done{background:#137a43}
#apst{position:fixed;left:3vw;top:3vh;font-size:2.4vw;padding:1.1vh 2.6vw;border-radius:10px;background:#1f2836;color:#cbd5e1;font-weight:700}
#apst.on{background:#166534;color:#eafff0}#apst.off{background:#7f1d1d;color:#ffecec}
#reapbtn{position:fixed;left:50%;bottom:6vh;transform:translateX(-50%);font-size:4vw;padding:2.4vh 10vw;border-radius:16px;background:#2563eb;color:#fff;font-weight:800;border:0}
#gate{position:fixed;top:0;left:0;right:0;bottom:0;z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#0b0f16;color:#fff;text-align:center;cursor:pointer}
#gate b{font-size:9vw;font-weight:900}#gate span{font-size:3.4vw;margin-top:2vh;opacity:.75}
</style></head><body>
<div id=gate onclick="unlock()"><b>▶ 点击进入</b><span>开启声音提示（iPad 需先点一下屏幕）</span></div>
<div id=apst>自主飞行 —</div>
<div id=s class=calm><div id=big>监控中</div><div id=sub></div></div>
<button id=reapbtn onclick="reap()">🔄 自主飞行</button>
<script>
const CN={wind_shear:'检测到风切变',ap_fail:'自动驾驶故障',obstacle:'前方障碍物',blank:'请接管'};
let ev,actx,ftimer;
function unlock(){try{actx=actx||new(window.AudioContext||window.webkitAudioContext)();actx.resume();let b=actx.createBuffer(1,1,22050),s=actx.createBufferSource();s.buffer=b;s.connect(actx.destination);s.start(0)}catch(_){}
 try{let u=new SpeechSynthesisUtterance(' ');u.lang='zh-CN';window.speechSynthesis.speak(u)}catch(_){}
 let g=document.getElementById('gate');if(g)g.style.display='none'}
function tk(){fetch('/takeover',{method:'POST'})}
function reap(){fetch('/ap',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({on:true})})}
function beep(){try{actx=actx||new(window.AudioContext||window.webkitAudioContext)();if(actx.state==='suspended')actx.resume();let n=0,t=setInterval(()=>{let o=actx.createOscillator(),gg=actx.createGain();o.frequency.value=880;o.connect(gg);gg.connect(actx.destination);gg.gain.value=.25;o.start();o.stop(actx.currentTime+.18);if(++n>=4)clearInterval(t)},260)}catch(_){}}
function speak(t){try{window.speechSynthesis.resume();window.speechSynthesis.cancel();let u=new SpeechSynthesisUtterance(t);u.lang='zh-CN';u.rate=1.05;window.speechSynthesis.speak(u)}catch(_){}}
function stopflash(){if(ftimer){clearInterval(ftimer);ftimer=null}}
function scr(c){stopflash();document.getElementById('s').className=c}
function flash(){let s=document.getElementById('s'),n=0;stopflash();ftimer=setInterval(()=>{s.className=(n++%2==0)?'alarm':'calm';if(n>16){stopflash();s.className='alarm'}},220)}
async function pollap(){try{let s=await(await fetch('/status')).json();let e=document.getElementById('apst');
 if(s.ap_on===true){e.textContent='自主飞行 开';e.className='on'}
 else if(s.ap_on===false){e.textContent='自主飞行 关';e.className='off'}
 else{e.textContent='自主飞行 —';e.className=''}}catch(_){}}
function conn(){ev=new EventSource('/events');
 ev.onmessage=e=>{let d;try{d=JSON.parse(e.data)}catch(_){return}
  if(d.type=='takeover_request'){let m=d.modality||'multimodal',msg=d.text||CN[d.cause]||'请立即接管';
   if(m=='visual'||m=='multimodal'){let b=document.getElementById('big');b.style.fontSize='4.4vw';b.textContent='⚠ '+msg;document.getElementById('sub').textContent='请动操纵杆接管';flash()}
   if(m=='audio'||m=='multimodal'){beep();speak(msg)}}
  else if(d.type=='takeover_done'){scr('calm');let b=document.getElementById('big');b.style.fontSize='';b.textContent='监控中';document.getElementById('sub').textContent='';try{window.speechSynthesis.cancel()}catch(_){}}
  else if(d.type=='reset'){scr('calm');let b=document.getElementById('big');b.style.fontSize='';b.textContent='监控中';document.getElementById('sub').textContent=''}};
 ev.onerror=()=>{ev.close();setTimeout(conn,1500)}}
conn();pollap();setInterval(pollap,600);
</script></body></html>"""

def zone_desc(cause):
    t = config.SCENARIOS.get(cause, {}).get("trigger")
    if not t: return "空白试验：无触发区，用「手动立即触发」"
    return "触发区 %s：中心 %.5f,%.5f 半径 %dm 高度带 %.0f–%.0f ft(MSL)" % (
        CAUSE_CN.get(cause, cause), t["lat"], t["lng"], t["radius_m"], t["alt_min_ft"], t["alt_max_ft"])

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers()
        try: self.wfile.write(b)
        except Exception: pass

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/panel"):
            self._send(200, PANEL_HTML, "text/html; charset=utf-8")
        elif self.path.startswith("/hmi"):
            self._send(200, HMI_HTML, "text/html; charset=utf-8")
        elif self.path.startswith("/status"):
            with LOCK: s = dict(STATE)
            s["modality"] = SETTINGS["modality"]
            s["start"] = start_point()
            s["helipad"] = HELIPAD
            s["zone"] = zone_desc(s["armed_cause"]) if s["armed_cause"] else ""
            s["rec"] = {"on": REC["on"], "name": REC.get("name"), "n": REC.get("n"),
                        "dir": REC_DIR, "err": REC.get("err")}
            self._send(200, json.dumps(s, ensure_ascii=False))
        elif self.path.startswith("/events"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache"); self.end_headers()
            q = []; SUBS.append(q)
            try:
                self.wfile.write(b": ok\n\n"); self.wfile.flush()
                while True:
                    if q: self.wfile.write(q.pop(0)); self.wfile.flush()
                    else: self.wfile.write(b": ping\n\n"); self.wfile.flush(); time.sleep(1)
            except Exception: pass
            finally:
                try: SUBS.remove(q)
                except Exception: pass
        else:
            self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b""
        try: body = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception: body = {}
        if self.path.startswith("/arm"):
            arm(body.get("cause", "blank"), body.get("trial_id", "")); self._send(200, '{"ok":1}')
        elif self.path.startswith("/modality"):
            m = body.get("modality", "multimodal")
            if m in ("visual", "audio", "multimodal"): SETTINGS["modality"] = m
            self._send(200, '{"ok":1}')
        elif self.path.startswith("/ap"):
            set_ap(bool(body.get("on"))); self._send(200, '{"ok":1}')
        elif self.path.startswith("/teleport_helipad"):
            ok = teleport_helipad(); self._send(200, '{"ok":%d}' % (1 if ok else 0))
        elif self.path.startswith("/teleport"):
            ok = teleport_start(); self._send(200, '{"ok":%d}' % (1 if ok else 0))
        elif self.path.startswith("/fire"):
            c = STATE["armed_cause"] or "blank"
            if STATE["t0"] is not None:          # 上一trial已预警未复位→先重新arm(存盘+复位)保证手动触发每次都生效
                arm(c)
            elif STATE["phase"] == "idle":
                STATE["phase"] = "waiting"
            do_alert(c, manual=True); self._send(200, '{"ok":1}')   # 手动=立即预警,ALERT_LEAD_S 秒后诱因生效
        elif self.path.startswith("/reset"):
            reset(); self._send(200, '{"ok":1}')
        elif self.path.startswith("/takeover"):
            mark_takeover("touch"); self._send(200, '{"ok":1}')
        elif self.path.startswith("/rec_start"):
            ok, info = rec_start(body.get("subject", ""))
            self._send(200, json.dumps({"ok": 1 if ok else 0, "info": info}, ensure_ascii=False))
        elif self.path.startswith("/rec_stop"):
            rec_stop(); self._send(200, '{"ok":1}')
        else:
            self._send(404, "{}")

def _bravo_ap_loop():
    """后台线程：读 Honeycomb Bravo 的物理「AUTO PILOT」键 → 切回自主飞行(set_ap(True))。
    纯 stdlib(ctypes+winmm)，全程异常兜底；读不到手柄/非 Windows 只是禁用，绝不拖垮面板。
    参数见 config.BRAVO_AP({enabled,joy,button})。"""
    cfg = getattr(config, "BRAVO_AP", None) or {}
    if not cfg.get("enabled", False):
        return
    joy = int(cfg.get("joy", 6)); button = int(cfg.get("button", 7)); mask = 1 << button
    try:
        import ctypes
        from ctypes import wintypes
        winmm = ctypes.WinDLL("winmm")
    except Exception as e:
        print("[Bravo桥] 未启用(非Windows或无winmm):", e); return

    class JOYINFOEX(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("dwXpos", wintypes.DWORD), ("dwYpos", wintypes.DWORD), ("dwZpos", wintypes.DWORD),
                    ("dwRpos", wintypes.DWORD), ("dwUpos", wintypes.DWORD), ("dwVpos", wintypes.DWORD),
                    ("dwButtons", wintypes.DWORD), ("dwButtonNumber", wintypes.DWORD),
                    ("dwPOV", wintypes.DWORD), ("dwReserved1", wintypes.DWORD), ("dwReserved2", wintypes.DWORD)]

    def poll():
        info = JOYINFOEX(); info.dwSize = ctypes.sizeof(JOYINFOEX); info.dwFlags = 0xFF
        return info.dwButtons if winmm.joyGetPosEx(joy, ctypes.byref(info)) == 0 else None

    print("[Bravo桥] 已启用：监听 设备#%d 按钮#%d → 切回自主飞行" % (joy, button))
    prev = bool((poll() or 0) & mask); last = 0.0
    while True:
        try:
            b = poll()
            if b is None:
                time.sleep(1.0); prev = False; continue      # 手柄不在(未插/id变了)→退避重试
            pressed = bool(b & mask); now = time.time()
            if pressed and not prev and now - last > 0.3:     # 上升沿 + 去抖
                msg = "物理 AP 键按下 → 切回自主飞行 (ap_on前=%s)" % STATE.get("ap_on")
                print("[Bravo桥]", msg)
                try:
                    with open(r"F:\_bravo_ap.log", "a", encoding="utf-8") as _fh:
                        _fh.write(time.strftime("%H:%M:%S ") + msg + "\n")
                except Exception:
                    pass
                try:
                    set_ap(True)
                except Exception as ex:
                    print("[Bravo桥] set_ap 失败:", ex)
                last = now
            prev = pressed
            time.sleep(0.015)
        except Exception as ex:
            print("[Bravo桥] 循环异常(继续):", ex); time.sleep(1.0)


def main():
    try:
        st = client.get_state(); ok = bool(st); nf = len(st) if st else 0
    except Exception as e:
        ok, nf = False, 0; print("[警告] DevKit 异常:", e)
    threading.Thread(target=monitor_loop, daemon=True).start()
    threading.Thread(target=_bravo_ap_loop, daemon=True).start()   # Bravo 物理AP键桥(集成,取代独立 bravo_ap_run.py)
    print("=" * 56)
    print(" eVTOL 接管实验 · 操作台已启动 (模态三选一 + AP开关)")
    print("  DevKit:", config.DEVKIT_BASE_URL, "| /get 字段:", nf, ("OK" if ok else "未连上!"))
    print("  操作台: http://localhost:%d/   被试HMI: http://localhost:%d/hmi" % (PORT, PORT))
    print("=" * 56)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()

if __name__ == "__main__":
    main()
