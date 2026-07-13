# -*- coding: utf-8 -*-
"""切片分析 tel_obstacle_183306.csv：触发瞬间/掉高段/rt=14.3事件段。"""
import csv, io, os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "tel_obstacle_183306.csv")
rows = [r for r in csv.DictReader(io.open(p, encoding="utf-8-sig")) if r["rel_t0"]]
print("有rel_t0的行数:", len(rows))

def show(lo, hi, title, step=1):
    print("\n== %s (rel %.1f~%.1f) ==" % (title, lo, hi))
    print("rel     phase      ele     alt     agl   vs(ft/min)  vby     vbz")
    n = 0
    for r in rows:
        rel = float(r["rel_t0"])
        if lo <= rel <= hi:
            n += 1
            if n % step == 0:
                print("%6.2f %-9s %7.3f %7.1f %7.1f %8.1f %7.2f %7.2f" % (
                    rel, r["phase"], float(r["elevator"]), float(r["alt_ft"]),
                    float(r["agl_ft"]), float(r["vspeed"]), float(r["vby"]), float(r["vbz"])))

show(4.0, 7.0, "诱因生效瞬间(t0+5)", 2)
show(7.0, 14.0, "悬停段(掉高?)", 8)
show(14.0, 16.5, "rt=14.315 事件", 1)
# 高度概览
for mark in (0, 5, 8, 11, 14, 17, 20, 25, 30):
    cand = min(rows, key=lambda r: abs(float(r["rel_t0"]) - mark))
    print("rel≈%-3d alt=%7.1f vs=%8.1f ele=%7.3f" % (mark, float(cand["alt_ft"]), float(cand["vspeed"]), float(cand["elevator"])))
