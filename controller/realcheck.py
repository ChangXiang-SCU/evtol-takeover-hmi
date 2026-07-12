# -*- coding: utf-8 -*-
"""对真实 DevKit 的只读验收：连接 + DV 字段可用性 + 3 帧实时遥测。不发任何控制指令。"""
import time
import config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = "http://10.7.144.111:5000"
config.HTTP_TIMEOUT_S = 8
from devkit_client import DevKitClient

c = DevKitClient()
st = c.get_state()
print("字段总数:", len(st))
print("--- 因变量所需字段是否存在 ---")
for k in ["PLANE_PITCH_DEGREES", "PLANE_BANK_DEGREES", "PLANE_HEADING_DEGREES_TRUE",
          "VERTICAL_SPEED", "G_FORCE", "PLANE_ALT_ABOVE_GROUND",
          "VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z",
          "AILERON_POSITION", "ELEVATOR_POSITION", "RUDDER_POSITION"]:
    print(("  [OK] %s = %s" % (k, st[k])) if k in st else ("  [缺] %s" % k))
print("--- 3 帧实时遥测(每秒1帧) ---")
for i in range(3):
    st = c.get_state()
    print("  lat=%.6f lon=%.6f alt=%.1fft pitch=%s bank=%s" % (
        st.get("PLANE_LATITUDE", 0), st.get("PLANE_LONGITUDE", 0),
        st.get("PLANE_ALTITUDE", 0), st.get("PLANE_PITCH_DEGREES"), st.get("PLANE_BANK_DEGREES")))
    time.sleep(1)
