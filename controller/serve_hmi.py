# -*- coding: utf-8 -*-
"""可视 HMI 演示：启动事件服务器，循环推送三种模态的接管请求，供浏览器观看。不碰飞机。"""
import time, config
config.EVENT_SERVER_PORT = 8000
from event_server import EventServer
ev = EventServer().start()
print("HMI 服务器: http://127.0.0.1:8000/")
seq = [("multimodal", "wind_shear", "请接管，检测到风切变"),
       ("visual",     "obstacle",   "请接管，前方有障碍物"),
       ("audio",      "ap_fail",    "请接管，自动驾驶故障")]
time.sleep(9)   # 给你时间点“进入监控”启用声音
for rnd in range(6):
    for mod, cause, text in seq:
        ev.broadcast({"type": "takeover_request", "event_id": "DEMO",
                      "t0": time.time(), "modality": mod, "cause": cause, "text": text})
        time.sleep(6)
        ev.broadcast({"type": "reset"})
        time.sleep(4)
ev.stop()
