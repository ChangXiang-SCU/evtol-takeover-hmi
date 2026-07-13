# -*- coding: utf-8 -*-
"""拉取指定 tel 文件并扫描升降舵可疑段：
(a) ele > +0.12 (正向拉杆,航线从不命令正值)
(b) ele 在 (-0.73,-0.12) 连续≥6帧 (~0.3s；正常滑变只穿越1-3帧)
用法: python -X utf8 _tel_scan.py tel_ap_fail_203732.csv"""
import csv, io, os, sys
from _ssh_deploy import connect

fn = sys.argv[1]
lp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", fn)
if not os.path.exists(lp):
    c = connect(); sftp = c.open_sftp()
    sftp.get("C:/Users/FlightSimulator/evtol_controller/logs/" + fn, lp)
    sftp.close(); c.close()
    print("PULLED:", fn)
rows = list(csv.DictReader(io.open(lp, encoding="utf-8-sig")))
print("rows:", len(rows), "| span %.1fs" % (float(rows[-1]["t"]) - float(rows[0]["t"])))
t0 = float(rows[0]["t"])

segs = []
cur = None
for r in rows:
    e = float(r["elevator"]); t = float(r["t"]) - t0
    pos = e > 0.12
    mid = -0.73 < e < -0.12
    kind = "POS" if pos else ("MID" if mid else None)
    if kind:
        if cur and cur[0] == kind:
            cur[2] = t; cur[3] += 1; cur[4] = max(cur[4], abs(e))
        else:
            if cur: segs.append(cur)
            cur = [kind, t, t, 1, abs(e)]
    else:
        if cur: segs.append(cur); cur = None
if cur: segs.append(cur)

sus = [s for s in segs if s[0] == "POS" or s[3] >= 6]
print("可疑段 %d 个:" % len(sus))
for k, ta, tb, n, mx in sus[:20]:
    print("  [%s] t+%.2f ~ t+%.2f  帧数=%d  峰值=%.3f" % (k, ta, tb, n, mx))
if not sus:
    print("  (无——升降舵全程只有 0/-0.85 平台和正常滑变)")
# 看看最后10秒(被切AP前后)
print("\n最后8秒波形:")
for r in rows[-160::8]:
    print("  t+%7.2f ele=%7.3f ail=%7.3f rud=%7.3f alt=%7.1f" % (
        float(r["t"]) - t0, float(r["elevator"]), float(r["aileron"]), float(r["rudder"]), float(r["alt_ft"])))
