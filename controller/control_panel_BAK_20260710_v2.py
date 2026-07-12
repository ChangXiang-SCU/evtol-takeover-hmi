# -*- coding: utf-8 -*-
"""
eVTOL 接管实验 · 操作台控制面板（被试手动飞，本面板只负责"进区即触发"）
==================================================================
在 sim 本机跑： python -X utf8 control_panel.py
浏览器打开：
  操作台(你看/选诱因/选模态/AP开关)：http://<sim-ip>:8000/
  被试 HMI(接管提示)               ：http://<sim-ip>:8000/hmi
流程：选 HMI 模态(视觉/听觉/视觉+听觉) → 点一个诱因 arm → 面板后台盯被试位置
→ 先区外(ARMED)再飞进触发区(半径+高度带) → 自动 t0：断AP/风切变注入 + 按所选模态
广播 HMI 接管请求 + 记 RT(触摸屏点击 或 操纵杆偏转两通道) + 逐帧遥测。
另有：自动驾驶开/关、手动立即触发、复位。纯标准库。
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
            "lat": None, "lng": None, "vspeed": None, "ap_on": None, "note": ""}
STATE = new_state()
TEL = []
BASELINE = {}
INJECT_STOP = threading.Event()
AUTO_STOP = threading.Event()   # 阶梯式自动驾驶航线的停止标志
SUBS = []  # SSE 队列

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
    风切变/自驾故障触发即被 AUTO_STOP 打断=交还被试; 障碍物触发后继续飞停机坪);
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
            return trig["lat"], trig["lng"], trig["alt_max_ft"] - 20.0
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
                client.set_param(THR, thr_d); client.set_param(ELEV, ELEV_DN)
                if g(client.get_state() or {}, "PLANE_ALTITUDE") <= talt:
                    break
                if AUTO_STOP.wait(1.0 / HZ):
                    break
    # 收尾:升降舵回中、油门中性(松开操纵→自然悬停)
    try:
        client.set_param(ELEV, 0.0); client.set_param(THR, neut)
    except Exception:
        pass
    with LOCK:
        STATE["ap_on"] = False

def reengage_autopilot():
    """切回自动驾驶=恢复自主航线(阶梯式下降+飞向停机坪)。先停掉可能在跑的旧线程再起新线程。"""
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
    with LOCK: STATE["ap_on"] = True
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

def do_trigger(cause, manual=False):
    st = client.get_state() or {}
    with LOCK:
        if STATE["t0"] is not None:
            return
        STATE["t0"] = time.time()
        STATE["phase"] = "triggered"
        STATE["modality"] = SETTINGS["modality"]
        STATE["note"] = ("手动" if manual else "进区") + "触发"
        BASELINE.clear()
        for ax in config.CONTROL_AXES:
            BASELINE[ax] = g(st, ax)
    if cause in ("ap_fail", "wind_shear"):
        AUTO_STOP.set()          # 故障/风切变：中断自主航线，交还被试
        try: client.ap_stop()
        except Exception: pass
    if cause == "wind_shear":
        INJECT_STOP.clear()
        threading.Thread(target=inject_windshear, daemon=True).start()
    broadcast({"type": "takeover_request", "cause": cause, "modality": SETTINGS["modality"],
               "text": config.CAUSE_TEXT.get(cause, "请接管"), "t0": STATE["t0"]})

def inject_windshear():
    ws = config.WIND_SHEAR; end = time.time() + ws["duration_s"]
    z0 = g(client.get_state() or {}, config.SV_VEL_BODY_Z)
    while time.time() < end and not INJECT_STOP.is_set():
        try:
            client.set_param(config.SV_VEL_BODY_Y, ws["down_vspeed_fts"])
            client.set_param(config.SV_VEL_BODY_Z, z0 * (1 - ws["speed_loss_frac"]))
        except Exception: pass
        time.sleep(1.0 / config.WIND_SHEAR_INJECT_HZ)

def mark_takeover(channel):
    with LOCK:
        if STATE["t0"] and STATE["rt"] is None:
            rt = round(time.time() - STATE["t0"], 3)
            STATE["rt"] = rt; STATE["rt_" + channel] = rt; STATE["phase"] = "takeover"
            STATE["note"] += " 接管(%s)" % channel
    append_event()

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
            cause, phase = STATE["armed_cause"], STATE["phase"]
            if cause and cause != "blank" and phase in ("waiting", "triggered"):
                trig = config.SCENARIOS.get(cause, {}).get("trigger")
                if trig:
                    lat, lng = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
                    alt = g(st, "PLANE_ALTITUDE")
                    dist = geo.distance_m(lat, lng, trig["lat"], trig["lng"]) if lat else 9999
                    inz = (dist <= trig["radius_m"] and trig["alt_min_ft"] <= alt <= trig["alt_max_ft"])
                    with LOCK:
                        STATE["dist"] = round(dist, 1); STATE["in_zone"] = inz
                        STATE["max_g"] = max(STATE["max_g"], g(st, "G_FORCE"))
                    rel = (time.time() - STATE["t0"]) if STATE["t0"] else ""
                    TEL.append([round(time.time(), 3), (rel if rel == "" else round(rel, 3)),
                                cause, phase, lat, lng, round(alt, 1),
                                round(g(st, "PLANE_ALT_ABOVE_GROUND"), 1), round(g(st, "VERTICAL_SPEED"), 1),
                                round(g(st, "G_FORCE"), 3), round(g(st, "AILERON_POSITION"), 4),
                                round(g(st, "ELEVATOR_POSITION"), 4), round(g(st, "RUDDER_POSITION"), 4),
                                round(g(st, config.SV_VEL_BODY_X), 3), round(g(st, config.SV_VEL_BODY_Y), 3),
                                round(g(st, config.SV_VEL_BODY_Z), 3)])
                    if phase == "waiting":
                        if not inz:
                            with LOCK: STATE["armed_ok"] = True
                        elif STATE["armed_ok"]:
                            do_trigger(cause)
                    elif phase == "triggered":
                        for ax in config.CONTROL_AXES:
                            if abs(g(st, ax) - BASELINE.get(ax, 0.0)) > config.CONTROL_DEADBAND:
                                mark_takeover("control"); break
        # ap_on 由 reengage/set_ap/航线线程 直接维护(传送式航线不经 DevKit AP)
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
    broadcast({"type": "reset"})

def reset():
    global STATE, TEL
    INJECT_STOP.set(); AUTO_STOP.set(); flush_tel()
    with LOCK:
        STATE = new_state(); TEL = []
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
.idle{background:#26303f}.waiting{background:#1d4e89}.triggered{background:#b23b1e}.takeover{background:#1f7a43}
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
</div><script>
const CN={wind_shear:'风切变',ap_fail:'自驾故障',obstacle:'障碍物',blank:'空白'};
let apOn=null;
function setmod(m){fetch('/modality',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({modality:m})})}
function arm(c){fetch('/arm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cause:c})})}
function fire(){fetch('/fire',{method:'POST'})}
function rst(){fetch('/reset',{method:'POST'})}
function toggleap(){fetch('/ap',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({on:!apOn})})}
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
 else if(s.phase=='waiting'){b.firstChild.textContent='等待进入触发区 · '+(CN[s.armed_cause]||'');document.getElementById('bsub').textContent=(s.armed_ok?'已 ARMED ✓ 进区即触发':'请先飞到区外建立 ARMED')+(s.in_zone?' · 现在区内':'')}
 else if(s.phase=='triggered'){b.firstChild.textContent='★已触发★ '+(CN[s.armed_cause]||'');document.getElementById('bsub').textContent='等待被试接管（点触摸屏 或 动操纵杆）'}
 else if(s.phase=='takeover'){b.firstChild.textContent='已接管 · '+(CN[s.armed_cause]||'');document.getElementById('bsub').textContent='RT = '+s.rt+' s'}
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
 }catch(e){}}
setInterval(tick,400);tick();
</script></body></html>"""

HMI_HTML = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>接管请求</title><style>
*{box-sizing:border-box;font-family:system-ui,'Microsoft YaHei',sans-serif}
html,body{margin:0;height:100%;background:#0b0f16;color:#fff;overflow:hidden}
#s{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;transition:.12s}
#big{font-size:8vw;font-weight:900;text-align:center;padding:0 4vw}
#tk{position:fixed;left:50%;bottom:6vh;transform:translateX(-50%);font-size:4vw;padding:2.4vh 10vw;border-radius:16px;background:#fff;color:#000;font-weight:800;border:0}
.calm{background:#0b0f16}.alarm{background:#c00}
#reapbtn{position:fixed;right:3vw;top:3vh;font-size:2.6vw;padding:1.6vh 3.5vw;border-radius:12px;background:#2563eb;color:#fff;font-weight:800;border:0}
</style></head><body><div id=s class=calm>
<div id=big>监控中</div></div><button id=tk onclick="tk()">接 管</button><button id=reapbtn onclick="reap()">🔄 切回自动驾驶</button>
<script>
const CN={wind_shear:'检测到风切变',ap_fail:'自动驾驶故障',obstacle:'前方障碍物',blank:'请接管'};
let ev,actx;
function tk(){fetch('/takeover',{method:'POST'})}
function reap(){fetch('/ap',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({on:true})})}
function beep(){try{actx=actx||new(window.AudioContext||window.webkitAudioContext)();let n=0,t=setInterval(()=>{let o=actx.createOscillator(),gg=actx.createGain();o.frequency.value=880;o.connect(gg);gg.connect(actx.destination);gg.gain.value=.25;o.start();o.stop(actx.currentTime+.18);if(++n>=4)clearInterval(t)},260)}catch(_){}}
function flash(){let s=document.getElementById('s'),n=0,t=setInterval(()=>{s.className=(n++%2==0)?'alarm':'calm';if(n>12){clearInterval(t);s.className='alarm'}},220)}
function conn(){ev=new EventSource('/events');
 ev.onmessage=e=>{let d;try{d=JSON.parse(e.data)}catch(_){return}
  if(d.type=='takeover_request'){let m=d.modality||'multimodal';
   if(m=='visual'||m=='multimodal'){document.getElementById('big').textContent='⚠ 请接管 · '+(CN[d.cause]||d.text);flash()}
   if(m=='audio'||m=='multimodal'){beep()}}
  else if(d.type=='reset'){document.getElementById('big').textContent='监控中';document.getElementById('s').className='calm'}};
 ev.onerror=()=>{ev.close();setTimeout(conn,1500)}}
conn();
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
            if STATE["phase"] == "idle": STATE["phase"] = "waiting"
            do_trigger(c, manual=True); self._send(200, '{"ok":1}')
        elif self.path.startswith("/reset"):
            reset(); self._send(200, '{"ok":1}')
        elif self.path.startswith("/takeover"):
            mark_takeover("touch"); self._send(200, '{"ok":1}')
        else:
            self._send(404, "{}")

def main():
    try:
        st = client.get_state(); ok = bool(st); nf = len(st) if st else 0
    except Exception as e:
        ok, nf = False, 0; print("[警告] DevKit 异常:", e)
    threading.Thread(target=monitor_loop, daemon=True).start()
    print("=" * 56)
    print(" eVTOL 接管实验 · 操作台已启动 (模态三选一 + AP开关)")
    print("  DevKit:", config.DEVKIT_BASE_URL, "| /get 字段:", nf, ("OK" if ok else "未连上!"))
    print("  操作台: http://localhost:%d/   被试HMI: http://localhost:%d/hmi" % (PORT, PORT))
    print("=" * 56)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()

if __name__ == "__main__":
    main()
