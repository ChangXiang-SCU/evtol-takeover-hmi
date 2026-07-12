# -*- coding: utf-8 -*-
"""SimConnect 直连封装 + 自检。
pysimconnect 自带的 SimConnect.dll 常是 MSFS2020 版、连不上 2024；本模块自动在
DevKit 目录 / MSFS SDK 里找到正确的 SimConnect.dll 再连。直接运行=自检:找dll→连→读位姿。"""
import os, glob


def _devkit_dir():
    """通过监听 5000 的进程反查 DevKit 所在目录(其自带的 SimConnect.dll 一般就是对的版本)。"""
    try:
        out = os.popen("netstat -ano -p tcp").read()
        pid = None
        for line in out.splitlines():
            if ":5000" in line and "LISTEN" in line.upper():
                pid = line.split()[-1]
                break
        if pid:
            p = os.popen("wmic process where processid=%s get ExecutablePath /value" % pid).read()
            for l in p.splitlines():
                if "ExecutablePath=" in l:
                    exe = l.split("=", 1)[1].strip()
                    if exe:
                        return os.path.dirname(exe)
    except Exception:
        pass
    return None


def candidate_dlls():
    cands = []
    roots = []
    dk = _devkit_dir()
    if dk:
        roots.append(dk)
    roots += [r"C:\MSFS 2024 SDK", r"C:\MSFS SDK", r"C:\MSFS2024 SDK",
              os.path.dirname(os.path.abspath(__file__)),
              r"C:\Users\FlightSimulator"]
    for root in roots:
        if root and os.path.isdir(root):
            for dp, dn, fn in os.walk(root):
                if dp[len(root):].count(os.sep) > 5:
                    dn[:] = []
                    continue
                for f in fn:
                    if f.lower() == "simconnect.dll":
                        cands.append(os.path.join(dp, f))
    out = []
    for c in cands:
        if c not in out:
            out.append(c)
    return out


def connect(verbose=False):
    """返回 (SimConnect, dll_path)。先试自带,再试候选。找不到抛异常。"""
    from SimConnect import SimConnect
    try:
        sm = SimConnect()
        if verbose: print("连上(自带dll)")
        return sm, "(bundled)"
    except Exception as e:
        if verbose: print("自带dll失败:", type(e).__name__, str(e)[:70])
    for dll in candidate_dlls():
        try:
            sm = SimConnect(library_path=dll)
            if verbose: print("连上 dll=", dll)
            return sm, dll
        except Exception as e:
            if verbose: print("失败", os.path.basename(os.path.dirname(dll)), "->", type(e).__name__, str(e)[:60])
    raise ConnectionError("没有可用的 SimConnect.dll 能连上 MSFS")


if __name__ == "__main__":
    print("候选 SimConnect.dll:")
    for c in candidate_dlls():
        try: sz = os.path.getsize(c)
        except Exception: sz = "?"
        print("  ", c, sz)
    print("--- 尝试连接 ---")
    try:
        sm, dll = connect(verbose=True)
    except Exception as e:
        print("CONNECT_FAIL:", repr(e)); raise SystemExit
    from SimConnect import AircraftRequests
    aq = AircraftRequests(sm, _time=0)
    for n in ["PLANE_LATITUDE", "PLANE_LONGITUDE", "PLANE_ALTITUDE",
              "PLANE_PITCH_DEGREES", "PLANE_BANK_DEGREES", "PLANE_HEADING_DEGREES_TRUE", "SIM_ON_GROUND"]:
        r = aq.find(n)
        try: v = aq.get(n)
        except Exception as e: v = "ERR:" + repr(e)
        print("  %-26s settable=%s val=%s" % (n, getattr(r, "settable", None) if r else "?", v))
    try: sm.exit()
    except Exception: pass
    print("GOOD_DLL:", dll)
