# -*- coding: utf-8 -*-
"""
水平飞行控制探针 —— 到底用哪个输入让这台 eVTOL 前后平飞?
============================================================
背景(核对过两份资料后, 2026-07-09):
  专家说 GENERAL_ENG_THROTTLE_LEVER_POSITION:1 控制前后(纵向)。
  · Flight-Recorder 的 Structs.cs(SimConnect 客户端)把 油门杆:1~4 当作
    「可直接写」的 SimVar —— 和 ELEVATOR/AILERON/VELOCITY_BODY 同一类。
    所以在 SimConnect 层面, 写油门:1 是合法的, 专家的方向站得住。
  · 官方 SimVar 文档的「Settable」列在我的抓取里不可靠: ELEVATOR/AILERON
    POSITION(明明能写)也显示空白, 所以那列证明不了任何事, 不作依据。
  · 真正唯一的门槛: 这台 DevKit 的 /set 到底放不放行油门。PDF 字段表残缺,
    不能据此判断; 权威是 /get 每个字段自带的 writable 标志(跑 dump_fields.py 看)
    + 写后回读。本脚本每步写完都回读油门:1 来验证。
  · 直升机的 COLLECTIVE / CYCLIC / ROTOR 纵向横向 TRIM / 尾桨 全是只读,
    不能用 /set 开; 所以「用 collective/cyclic 直接飞」这条路走不通。
  纵向舵面 ELEVATOR_POSITION(升降舵) 是 DevKit 明确可写的对照通道。

本脚本一次跑完两组对照,用真实位移当裁判,直接看哪个真能让飞机前后平飞:
  A 组: 扫  油门:1        (专家建议;若 DevKit 不接受写,这里会看到"没反应")
  B 组: 扫  ELEVATOR_POSITION 升降舵 (文档可写的纵向舵面,作为对照)
eVTOL 有 4 个油门杆,全程记录油门:1~4 与旋翼内部只读量,便于判到底动了哪根轴。

判据:
  把每步的水平位移投影到"机头朝向":
     前进量 fwd(+前 / -后)   侧移量 right(+右 / -左)
  同时看  掉高 Δalt、俯仰 pitch、空速 airspeed。
  每步都从同一个悬停起点重新开始(传送复位),互不干扰,可反复比。

安全:
  起点 800ft(足够高);每步只推 ~4s 立刻中性化;AGL 破底或掉高过大即中止;
  Ctrl+C / 结束都会把油门、升降舵归中、清零体轴速度并悬停。

在 sim 主机上跑(推荐,和 MSFS 同机):
  python -X utf8 throttle_fly.py
从别的机器跑:先 set DEVKIT_URL=http://10.7.144.111:5000  再运行。
只用标准库,Python 3.8+。
"""
import os, sys, time, math
import config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = os.environ.get("DEVKIT_URL", "http://127.0.0.1:5000")
config.HTTP_TIMEOUT_S = 6
import geo
from devkit_client import DevKitClient

c = DevKitClient()

# ---- 被测输入名 ----
THR  = "GENERAL_ENG_THROTTLE_LEVER_POSITION:1"   # 专家建议(前后)
ELEV = "ELEVATOR_POSITION"                        # 文档可写的纵向舵面(对照)
# eVTOL 有 4 个油门杆, 全程记录, 看推:1 时其它杆/内部状态是否联动
THR_ALL = ["GENERAL_ENG_THROTTLE_LEVER_POSITION:%d" % i for i in (1, 2, 3, 4)]
# 直升机内部只读量(能读就读, DevKit 若不返回则为 None, 打印时跳过) —— 佐证到底动了哪根轴
ROTOR_PROBE = ["COLLECTIVE_POSITION", "ROTOR_LONGITUDINAL_TRIM_PCT",
               "ROTOR_LATERAL_TRIM_PCT", "DISK_PITCH_PCT:1"]

# ---- 起点(用风切变 restore 点, 800ft, 有余量) ----
P = config.SCENARIOS["wind_shear"]["restore"]

# ---- 安全阈值 ----
FLOOR_AGL_FT = 150.0     # 离地低于此立即中止本步
MAX_DROP_FT  = 200.0     # 相对本步基线掉高超过此立即中止
SETTLE_S     = 2.0       # 传送后稳定时间
HOLD_S       = 4.0       # 每步推杆时长
POLL_HZ      = 6.0       # 推杆窗口内的读/写频率
MOVE_THRESH  = 5.0       # 判定"动了"的位移阈值(m)
DROP_THRESH  = 30.0      # 判定"掉高"的阈值(ft)


def S():
    return c.get_state() or {}

def gv(st, k, d=0.0):
    v = st.get(k, d)
    return d if v is None else v

def proj(lat0, lon0, hdg, st):
    """当前位置相对起点、投影到机头朝向 → (前进m, 右移m)。"""
    la, lo = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
    if la is None or lo is None:
        return 0.0, 0.0
    d = geo.distance_m(lat0, lon0, la, lo)
    if d < 1e-6:
        return 0.0, 0.0
    rel = math.radians(geo.bearing_deg(lat0, lon0, la, lo) - hdg)
    return d * math.cos(rel), d * math.sin(rel)

def reset_to_start():
    """传送回同一起点 + 清零体轴速度 + 稳定,保证每步条件一致。"""
    c.ap_stop(); time.sleep(0.2)
    for n, v in [("PLANE_LATITUDE", P["lat"]), ("PLANE_LONGITUDE", P["lng"]),
                 ("PLANE_ALTITUDE", P["alt_ft"]), ("PLANE_HEADING_DEGREES_TRUE", P["heading"]),
                 ("PLANE_PITCH_DEGREES", 0.0), ("PLANE_BANK_DEGREES", 0.0)]:
        c.set_param(n, v)
    for n in ("VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"):
        c.set_param(n, 0.0)
    time.sleep(SETTLE_S)


results = []   # 收集每步结论,最后汇总

def step(tag, param, value, restore):
    """从起点重新开始,持续把 param 设为 value 约 HOLD_S 秒,记录真实位移。"""
    reset_to_start()
    b = S()
    lat0, lon0 = b.get("PLANE_LATITUDE"), b.get("PLANE_LONGITUDE")
    hdg  = gv(b, "PLANE_HEADING_DEGREES_TRUE")
    alt0 = gv(b, "PLANE_ALTITUDE")
    if lat0 is None:
        print("  [跳过] 拿不到位置(DevKit /get 空?)"); return
    print("\n=== %s : 设 %s = %s ,保持 %.0fs ===" % (tag, param, value, HOLD_S))
    print("  基线 alt=%.0f AGL=%.0f 航向=%.1f  油门1~4=[%s]" % (
        alt0, gv(b, "PLANE_ALT_ABOVE_GROUND"), hdg,
        " ".join("%.1f" % gv(b, n) for n in THR_ALL)))
    rp = ["%s=%.3f" % (n.split(':')[0], b[n]) for n in ROTOR_PROBE if b.get(n) is not None]
    if rp:
        print("  旋翼内部(只读):", "  ".join(rp))

    t0 = time.time(); nxt = 0.0; min_agl = 9e9; aborted = ""
    fwd = right = dalt = 0.0; last = b
    while time.time() - t0 < HOLD_S:
        c.set_param(param, value)          # 每帧重设,防止被衰减/复位
        st = S(); last = st
        agl = gv(st, "PLANE_ALT_ABOVE_GROUND", 9e9)
        min_agl = min(min_agl, agl)
        fwd, right = proj(lat0, lon0, hdg, st)
        dalt = gv(st, "PLANE_ALTITUDE") - alt0
        el = time.time() - t0
        if el >= nxt:                      # ~2Hz 打印
            print("  t=%.1fs 前进%+6.1fm 侧移%+6.1fm Δ高%+6.0fft 俯仰%+5.1f 空速%4.1f 油门:1=%.1f" % (
                el, fwd, right, dalt, gv(st, "PLANE_PITCH_DEGREES"),
                gv(st, "AIRSPEED_TRUE"), gv(st, THR)))
            nxt = el + 0.5
        if agl < FLOOR_AGL_FT:
            aborted = "AGL<%.0f" % FLOOR_AGL_FT; break
        if dalt < -MAX_DROP_FT:
            aborted = "掉高>%.0fft" % MAX_DROP_FT; break
        time.sleep(1.0 / POLL_HZ)

    # 立刻中性化被测输入
    c.set_param(param, restore)
    dur = time.time() - t0
    thr_end = gv(last, THR)     # 回读:1, 看 DevKit 到底有没有把写入透传进去
    # 结论
    if aborted:
        verdict = "!! 中止(%s)" % aborted
    elif abs(fwd) < MOVE_THRESH and abs(right) < MOVE_THRESH:
        verdict = "无明显水平位移(该输入可能不可写/无效)"
    else:
        d = "前进" if fwd >= MOVE_THRESH else ("后退" if fwd <= -MOVE_THRESH else "")
        s = "右移" if right >= MOVE_THRESH else ("左移" if right <= -MOVE_THRESH else "")
        d2 = " +掉高%.0fft" % (-dalt) if dalt <= -DROP_THRESH else (" +爬升%.0fft" % dalt if dalt >= DROP_THRESH else "")
        verdict = "→ %s%s%s (前进%.1fm/%.1fs=%.2fm/s)" % (d or "—", ("/"+s if s else ""), d2, fwd, dur, fwd/dur)
    print("  结论: %s | 期间最低AGL=%.0f | 收尾回读油门:1=%.1f" % (verdict, min_agl, thr_end))
    results.append((tag, param, value, round(fwd, 1), round(right, 1), round(dalt, 0),
                    round(gv(last, "PLANE_PITCH_DEGREES"), 1), round(gv(last, "AIRSPEED_TRUE"), 1),
                    round(min_agl, 0), verdict))


def neutralize_and_hover():
    """收尾: 油门/升降舵归中、清零体轴速度、原地悬停。"""
    try:
        st = S(); thr_n = gv(st, THR, 53.5)
        c.set_param(ELEV, 0.0)
        c.set_param(THR, thr_n)
        for n in ("VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z"):
            c.set_param(n, 0.0)
        la, lo = st.get("PLANE_LATITUDE"), st.get("PLANE_LONGITUDE")
        if la is not None:
            c.ap_rotor_point(la, lo)
        print("\n[收尾] 升降舵→0, 油门→%.1f, 速度清零, 原地悬停。" % thr_n)
    except Exception as e:
        print("[收尾异常]", e)


def main():
    b = S()
    if not b:
        print("拿不到飞机状态。确认 MSFS 已进入飞行、DevKit(5000) 在跑、DEVKIT_URL 正确。"); return
    thr_n = gv(b, THR, 53.5)
    print("连上了。当前 alt=%.0f AGL=%.0f 油门:1=%.3f  (把它当作中性/悬停值)" % (
        gv(b, "PLANE_ALTITUDE"), gv(b, "PLANE_ALT_ABOVE_GROUND"), thr_n))
    print("四个油门杆现值 1~4 = [%s]" % " ".join("%.1f" % gv(b, n) for n in THR_ALL))
    print("起点: %.6f,%.6f @%.0fft 航向%.1f" % (P["lat"], P["lng"], P["alt_ft"], P["heading"]))
    print("每步都会先传送回该起点。若飞机乱动请随时 Ctrl+C。\n")

    # ---------- A 组: 油门:1 (专家建议) ----------
    print("########## A 组: 油门:1 (专家说控前后) ##########")
    step("A0 油门中性",     THR, thr_n,        thr_n)   # 对照:无AP时的自然漂移
    step("A1 油门+8",       THR, thr_n + 8.0,  thr_n)
    step("A2 油门+16",      THR, thr_n + 16.0, thr_n)
    step("A3 油门-8",       THR, thr_n - 8.0,  thr_n)

    # ---------- B 组: 升降舵 (文档可写的纵向) ----------
    print("\n########## B 组: ELEVATOR 升降舵 (文档可写,作对照) ##########")
    step("B1 升降舵+0.4",   ELEV, 0.4,  0.0)
    step("B2 升降舵+0.8",   ELEV, 0.8,  0.0)
    step("B3 升降舵-0.4",   ELEV, -0.4, 0.0)

    # ---------- 汇总 ----------
    print("\n================= 汇总 (前进+ / 后退- , 单位 m 和 ft) =================")
    print("%-14s %-30s %7s %7s %6s %6s %6s %6s" % (
        "步骤", "输入", "前进", "侧移", "Δ高", "俯仰", "空速", "minAGL"))
    for r in results:
        tag, param, value, fwd, right, dalt, pit, spd, magl, verdict = r
        print("%-14s %-30s %7.1f %7.1f %6.0f %6.1f %6.1f %6.0f" % (
            tag, "%s=%s" % (param.split(':')[0][:20], value), fwd, right, dalt, pit, spd, magl))
    print("\n判读:")
    print("  · 若 A1/A2 前进量明显 > A0(中性漂移) → 油门:1 确实能控前后,记下 m/s 我给你做闭环。")
    print("  · 写:1 后回读「油门:1」没变 → DevKit 没把油门透传给 sim(=白写),改用 B 组升降舵。")
    print("  · 回读变了但飞机不动 → 值写进去了,但这台 eVTOL 的油门不驱动平飞,也改用升降舵。")
    print("  · 侧移/掉高很大 → 说明该输入耦合了别的轴,需要配合别的通道一起补偿。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Ctrl+C] 中断,正在复位…")
    finally:
        neutralize_and_hover()
