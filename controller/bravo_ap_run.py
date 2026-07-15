# -*- coding: utf-8 -*-
"""
固定参数启动 Bravo「AUTO PILOT」按钮桥（供 _ssh_deploy.py bg 后台常驻用）。
按下物理键 → POST /ap {on:true} → 切回自主飞行（等同 HMI 的"🔄 自主飞行"）。
要换按钮/改行为，只改下面 JOY / BUTTON / TOGGLE 三个值即可。
后台运行时所有输出写到 F:\\_bravo_ap.log 方便查看/排错。
"""
import sys

JOY = 6          # 设备号（discover 得到）
BUTTON = 7       # 按钮号（discover 得到；AUTO PILOT = 设备#6 按钮#7）
URL = "http://127.0.0.1:8000"
TOGGLE = False   # False=每次按下都"切回自主飞行"；True=在 开/关 间切换

try:
    sys.stdout = open(r"F:\_bravo_ap.log", "a", encoding="utf-8", buffering=1)
    sys.stderr = sys.stdout
except Exception:
    pass

import time
import bravo_ap_bridge as b

print("=== bravo_ap_run 启动 %s  joy=%d button=%d toggle=%s ===" %
      (time.strftime("%Y-%m-%d %H:%M:%S"), JOY, BUTTON, TOGGLE))
b.do_run(JOY, BUTTON, URL, TOGGLE)
