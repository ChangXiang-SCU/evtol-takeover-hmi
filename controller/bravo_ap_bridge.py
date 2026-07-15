# -*- coding: utf-8 -*-
"""
bravo_ap_bridge.py — 把 Honeycomb Bravo（或任意 USB 游戏控制器）上的一个物理按钮
桥接到控制面板的 /ap 接口：按下 = POST /ap {on:true} = 切回自主飞行
（等同被试 HMI 上的 "🔄 自主飞行" 按钮）。

纯标准库（ctypes + winmm），Windows 专用，无需 pip install。
必须跑在 sim 那台电脑上（Bravo 插在那、control_panel.py 也在那跑）。

用法：
  列设备:   python -X utf8 bravo_ap_bridge.py list
  找按钮:   python -X utf8 bravo_ap_bridge.py discover
            然后按一下物理 AUTO PILOT 键，会打印  --joy i --button b
            （可选：discover 40 只监听 40 秒；discover 40 F:\\btn.txt 同时写文件）
  运行桥:   python -X utf8 bravo_ap_bridge.py run --joy i --button b
            每次按下打印一行；保持窗口开着。
            可选 --url http://127.0.0.1:8000   --toggle（按一下在 开/关 间切换，默认只"开"）
"""
import sys, time, ctypes, json, urllib.request
from ctypes import wintypes

winmm = ctypes.WinDLL("winmm")
JOY_RETURNALL = 0x000000FF
JOYERR_NOERROR = 0


class JOYINFOEX(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("dwXpos", wintypes.DWORD), ("dwYpos", wintypes.DWORD), ("dwZpos", wintypes.DWORD),
                ("dwRpos", wintypes.DWORD), ("dwUpos", wintypes.DWORD), ("dwVpos", wintypes.DWORD),
                ("dwButtons", wintypes.DWORD), ("dwButtonNumber", wintypes.DWORD),
                ("dwPOV", wintypes.DWORD), ("dwReserved1", wintypes.DWORD), ("dwReserved2", wintypes.DWORD)]


class JOYCAPSW(ctypes.Structure):
    _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD),
                ("szPname", wintypes.WCHAR * 32),
                ("wXmin", wintypes.UINT), ("wXmax", wintypes.UINT),
                ("wYmin", wintypes.UINT), ("wYmax", wintypes.UINT),
                ("wZmin", wintypes.UINT), ("wZmax", wintypes.UINT),
                ("wNumButtons", wintypes.UINT),
                ("wPeriodMin", wintypes.UINT), ("wPeriodMax", wintypes.UINT),
                ("wRmin", wintypes.UINT), ("wRmax", wintypes.UINT),
                ("wUmin", wintypes.UINT), ("wUmax", wintypes.UINT),
                ("wVmin", wintypes.UINT), ("wVmax", wintypes.UINT),
                ("wCaps", wintypes.UINT), ("wMaxAxes", wintypes.UINT), ("wNumAxes", wintypes.UINT),
                ("wMaxButtons", wintypes.UINT),
                ("szRegKey", wintypes.WCHAR * 32), ("szOEMVxD", wintypes.WCHAR * 260)]


def poll(joy_id):
    info = JOYINFOEX()
    info.dwSize = ctypes.sizeof(JOYINFOEX)
    info.dwFlags = JOY_RETURNALL
    if winmm.joyGetPosEx(joy_id, ctypes.byref(info)) == JOYERR_NOERROR:
        return info.dwButtons
    return None


def caps(joy_id):
    c = JOYCAPSW()
    if winmm.joyGetDevCapsW(joy_id, ctypes.byref(c), ctypes.sizeof(JOYCAPSW)) == 0:
        return c
    return None


def present_ids():
    return [i for i in range(winmm.joyGetNumDevs()) if poll(i) is not None]


def do_list():
    ids = present_ids()
    if not ids:
        print("没检测到游戏控制器（joyGetNumDevs=%d）。确认 Bravo 已插好、joy.cpl 能看到它。"
              % winmm.joyGetNumDevs())
        return
    for i in ids:
        c = caps(i)
        print("设备#%d  按钮数=%s  名称=%s" % (i, c.wNumButtons if c else "?", c.szPname if c else "?"))


def do_discover(seconds=None, outfile=None):
    ids = present_ids()
    fh = open(outfile, "w", encoding="utf-8") if outfile else None

    def emit(s):
        print(s, flush=True)
        if fh:
            fh.write(s + "\n"); fh.flush()

    if not ids:
        emit("没检测到控制器。");
        if fh: fh.close()
        return
    emit("监听中… 现在按一下你要用的物理按钮（如 AUTO PILOT）。%s"
         % ("%ds 后自动退出" % seconds if seconds else "Ctrl+C 退出"))
    for i in ids:
        c = caps(i)
        emit("  设备#%d  %s" % (i, c.szPname if c else ""))
    prev = {i: (poll(i) or 0) for i in ids}
    t_end = (time.time() + seconds) if seconds else None
    try:
        while True:
            for i in ids:
                b = poll(i)
                if b is None:
                    continue
                changed = b & ~prev[i]           # 新按下的位
                if changed:
                    for bit in range(32):
                        if changed & (1 << bit):
                            emit(">>> 检测到：设备#%d  按钮#%d  (joy.cpl 显示 Button %d)   →   运行用:  --joy %d --button %d"
                                 % (i, bit, bit + 1, i, bit))
                prev[i] = b
            if t_end and time.time() >= t_end:
                emit("（监听结束）")
                break
            time.sleep(0.02)
    except KeyboardInterrupt:
        emit("退出。")
    finally:
        if fh:
            fh.close()


def post_ap(url, on):
    data = json.dumps({"on": bool(on)}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/ap", data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).read()


def get_ap_on(url):
    try:
        s = json.load(urllib.request.urlopen(url.rstrip("/") + "/status", timeout=5))
        return s.get("ap_on")
    except Exception:
        return None


def do_run(joy, button, url, toggle):
    mask = 1 << button
    if get_ap_on(url) is None:
        print("⚠ 提醒：现在读不到面板 /status（%s）。确认 control_panel.py 在跑。仍会继续监听按键。" % url)
    print("桥接运行中：设备#%d 按钮#%d  →  %s/ap  （%s）  Ctrl+C 停止"
          % (joy, button, url, "toggle" if toggle else "engage-only 只切回自主飞行"), flush=True)
    prev = bool((poll(joy) or 0) & mask)
    last_fire = 0.0
    while True:
        b = poll(joy)
        if b is None:
            time.sleep(0.5); prev = False; continue
        pressed = bool(b & mask)
        now = time.time()
        if pressed and not prev and (now - last_fire) > 0.3:   # 上升沿 + 去抖
            on = True
            if toggle:
                on = not (get_ap_on(url) is True)
            try:
                post_ap(url, on)
                print("[%s] 物理键按下 → POST /ap {on:%s}" % (time.strftime("%H:%M:%S"), str(on).lower()), flush=True)
            except Exception as e:
                print("  POST 失败：", e, flush=True)
            last_fire = now
        prev = pressed
        time.sleep(0.015)


def main():
    args = sys.argv[1:]
    mode = args[0] if args else "discover"

    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default

    url = opt("--url", "http://127.0.0.1:8000")
    if mode == "list":
        do_list()
    elif mode == "discover":
        secs = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
        outf = args[2] if len(args) > 2 and not args[2].startswith("-") else None
        do_discover(secs, outf)
    elif mode == "run":
        do_run(int(opt("--joy", "0")), int(opt("--button", "0")), url, "--toggle" in args)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
