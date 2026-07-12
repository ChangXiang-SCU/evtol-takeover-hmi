# -*- coding: utf-8 -*-
"""SimConnect 直连探针(只读):确认 Python-SimConnect 能连上 MSFS(与DevKit并存),
读出 PLANE 位置/姿态的单位(度还是弧度、英尺还是米)与可写性,为回放控制器定标。"""
import time
try:
    from SimConnect import SimConnect, AircraftRequests
except Exception as e:
    print("IMPORT_FAIL", repr(e)); raise SystemExit

try:
    sm = SimConnect()
except Exception as e:
    print("CONNECT_FAIL", repr(e)); raise SystemExit
print("SimConnect 已连接")
aq = AircraftRequests(sm, _time=0)   # _time=0 → 每次实时取,不缓存

NAMES = ["PLANE_LATITUDE", "PLANE_LONGITUDE", "PLANE_ALTITUDE", "PLANE_ALT_ABOVE_GROUND",
         "PLANE_PITCH_DEGREES", "PLANE_BANK_DEGREES", "PLANE_HEADING_DEGREES_TRUE",
         "PLANE_HEADING_DEGREES_GYRO", "VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z",
         "GROUND_VELOCITY", "AIRSPEED_TRUE", "VERTICAL_SPEED", "SIM_ON_GROUND"]
for n in NAMES:
    r = aq.find(n)
    try:
        v = aq.get(n)
    except Exception as e:
        v = "GET_ERR:" + repr(e)
    st = getattr(r, "settable", None) if r else "NO_DEF"
    print("%-28s settable=%-5s val=%s" % (n, st, v))

# 读两次看是否实时推进(确认在飞/没暂停)
t = aq.get("PLANE_LONGITUDE"); time.sleep(1.0); t2 = aq.get("PLANE_LONGITUDE")
print("1秒内经度变化:", (None if (t is None or t2 is None) else (t2 - t)))
try: sm.exit()
except Exception: pass
print("DONE")
