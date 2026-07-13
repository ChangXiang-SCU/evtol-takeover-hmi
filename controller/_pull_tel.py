# -*- coding: utf-8 -*-
"""拉取 sim 上最新的 tel_*.csv 到本地并做误判分析：
找到舵面(实际值)首次超死区的时刻，看它前后各轴/相位/坐标在干什么。"""
import os, csv, io
from _ssh_deploy import connect

REMOTE_LOGS = "C:/Users/FlightSimulator/evtol_controller/logs"

c = connect()
sftp = c.open_sftp()
files = [f for f in sftp.listdir_attr(REMOTE_LOGS) if f.filename.startswith("tel_")]
files.sort(key=lambda a: a.st_mtime)
latest = files[-1].filename
lp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", latest)
os.makedirs(os.path.dirname(lp), exist_ok=True)
sftp.get(REMOTE_LOGS + "/" + latest, lp)
print("PULLED:", latest, files[-1].st_size, "bytes")
sftp.close(); c.close()

rows = list(csv.DictReader(io.open(lp, encoding="utf-8-sig")))
print("rows:", len(rows), "| phases:", sorted(set(r["phase"] for r in rows)))
if not rows:
    raise SystemExit
t0 = float(rows[0]["t"])
DB = 0.12
first_dev = None
for i, r in enumerate(rows):
    ail, ele, rud = (abs(float(r["aileron"])), abs(float(r["elevator"])), abs(float(r["rudder"])))
    # 静息位≈0，直接看绝对值超死区（近似：ELEV被命令0/-0.85间跳变，只有偏离两者才异常）
    ele_anom = min(abs(float(r["elevator"]) - 0.0), abs(float(r["elevator"]) - (-0.85))) > DB
    if (ail > DB or rud > DB or ele_anom) and first_dev is None:
        first_dev = i
        print("\n== 首个异常样本 @ row %d, t+%.2fs, phase=%s ==" % (i, float(r["t"]) - t0, r["phase"]))
        for j in range(max(0, i - 6), min(len(rows), i + 6)):
            rr = rows[j]
            print("t+%6.2f %-8s ail=%7.4f ele=%7.4f rud=%7.4f alt=%7s vs=%6s" % (
                float(rr["t"]) - t0, rr["phase"], float(rr["aileron"]), float(rr["elevator"]),
                float(rr["rudder"]), rr["alt_ft"], rr["vspeed"]))
        break
if first_dev is None:
    print("整个CSV无异常样本(按静息0近似)——误判可能发生在arm前或未落TEL")
# 全程各轴范围
for k in ("aileron", "elevator", "rudder"):
    vs = [float(r[k]) for r in rows]
    print("%s: min=%.4f max=%.4f" % (k, min(vs), max(vs)))
