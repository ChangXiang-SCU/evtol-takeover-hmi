# -*- coding: utf-8 -*-
"""合并后验证：mock 跑三场景各一次，确认 传送→高度带围栏→断AP→(风切变注入)→HMI→RT→落地。"""
import config
config.USE_MOCK = True
config.EVENT_SERVER_PORT = 8000
config.CONTROL_HZ = 20
import controller

c = controller.Controller()
trials = [
    {"id": "M_ws",  "cause": "wind_shear", "modality": "multimodal", "visibility": "normal"},
    {"id": "M_ap",  "cause": "ap_fail",    "modality": "audio",      "visibility": "normal"},
    {"id": "M_ob",  "cause": "obstacle",   "modality": "visual",     "visibility": "low"},
]
for tr in trials:
    c.run_trial(tr)
c._write_summary()
c.events.stop()
print("VERIFY DONE")
