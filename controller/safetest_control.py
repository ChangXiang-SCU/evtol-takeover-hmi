# -*- coding: utf-8 -*-
"""安全写接口测试：命令 eVTOL 旋翼定点=当前坐标(原地保持)，观察~1.5s，结尾必发 /ap_stop。
全程只有几秒，且检查 DevKit 登记的目标坐标以验证经纬度字段顺序。"""
import time, math
import config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = "http://10.7.144.111:5000"
config.HTTP_TIMEOUT_S = 8
from devkit_client import DevKitClient

c = DevKitClient()

def pos():
    s = c.get_state()
    return s.get("PLANE_LATITUDE"), s.get("PLANE_LONGITUDE"), s.get("PLANE_ALTITUDE")

lat0, lon0, alt0 = pos()
print("起始: lat=%.6f lon=%.6f alt=%.1fft" % (lat0, lon0, alt0))
try:
    print(">> 发 /ap_start 旋翼定点 -> 当前坐标(原地保持)")
    print("   ap_start 返回:", c.ap_rotor_point(lat0, lon0))
    time.sleep(0.6)
    aps = c.ap_state()
    print("   /ap_state:", aps)
    if isinstance(aps, dict) and aps.get("target_coord"):
        tc = aps["target_coord"]
        print("   登记目标 lat=%s lon=%s  (应≈起始 %.4f / %.4f)" % (
            tc.get("latitude"), tc.get("longitude"), lat0, lon0))
        okorder = (tc.get("latitude") is not None and abs(float(tc["latitude"]) - lat0) < 0.01)
        print("   >> 经纬度字段顺序:", "正确(不用改 SWAP_LATLNG)" if okorder else "疑似反了! 需 SWAP_LATLNG=True")
    time.sleep(1.5)
    lat1, lon1, alt1 = pos()
    drift = 111320 * math.hypot(lat1 - lat0, (lon1 - lon0) * math.cos(math.radians(lat0)))
    print("   1.5s后: lat=%.6f lon=%.6f alt=%.1fft  水平漂移≈%.1fm" % (lat1, lon1, alt1, drift))
finally:
    print(">> 发 /ap_stop (务必释放控制)")
    print("   ap_stop 返回:", c.ap_stop())
    time.sleep(0.4)
    print("   停后 /ap_state:", c.ap_state())
print("done")
