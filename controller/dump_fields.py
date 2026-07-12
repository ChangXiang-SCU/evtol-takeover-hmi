# -*- coding: utf-8 -*-
"""从活的 DevKit 拉「全部字段 + 每个字段的 writable 标志 + 当前值」并存盘。
——PDF 的字段表是残缺的(连 /get 实际返回的很多字段都没列),
   真正权威的是 /get 里每个字段自带的 writable。这个脚本就把它原样打出来。
顺带测 /get、/set 往返延迟。

用法(sim 主机上跑, 和 MSFS 同机):  python -X utf8 dump_fields.py
从别的机器跑:  先 set DEVKIT_URL=http://10.7.144.111:5000  再运行。
只用标准库。
"""
import os, re, json, time, statistics, urllib.request
import config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = os.environ.get("DEVKIT_URL", "http://127.0.0.1:5000")
config.HTTP_TIMEOUT_S = 8
from devkit_client import DevKitClient

c = DevKitClient()
BASE = config.DEVKIT_BASE_URL.rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))

# 原始 /get:保留 writable 字段(注意 devkit_client.get_state() 会把 writable 丢掉,只留 name→val)
raw = json.loads(urllib.request.urlopen(BASE + "/get", timeout=8).read().decode("utf-8"))
fields = [p for p in raw if isinstance(p, dict)]

# 全量存盘,便于发我
outp = os.path.join(HERE, "fields_dump.txt")
with open(outp, "w", encoding="utf-8") as f:
    f.write("共 %d 字段 (名 | writable | 值)  来源 %s\n" % (len(fields), BASE))
    for p in sorted(fields, key=lambda x: str(x.get("name"))):
        f.write("%-42s writable=%-6s %s\n" % (p.get("name"), p.get("writable"), p.get("val")))
print("共 %d 字段,已存 -> %s" % (len(fields), outp))

# 可写字段清单(权威)
w = [p.get("name") for p in fields if p.get("writable") in (True, "true", "True", 1, "1")]
print("\n--- DevKit 报告「可写」的字段共 %d 个 ---" % len(w))
for n in sorted(w):
    print("  ", n)

# 控制/旋翼相关高亮(含 PDF 常漏的 throttle:1~4、collective、cyclic、rotor…)
KEYS = re.compile(r"THROTTLE|ELEVATOR|AILERON|RUDDER|VELOCITY_BODY|COLLECTIVE|CYCLIC|ROTOR|DISK|PROP", re.I)
print("\n--- 控制/旋翼相关字段 (名 | writable | 值) ---")
hit = [p for p in fields if KEYS.search(str(p.get("name")))]
for p in sorted(hit, key=lambda x: str(x.get("name"))):
    print("  %-42s writable=%-6s %s" % (p.get("name"), p.get("writable"), p.get("val")))
if not hit:
    print("  (没匹配到——把 fields_dump.txt 发我,我据实际字段名再筛)")

# 往返延迟(写 AILERON=0 安全, 不改变悬停)
gts = []
for _ in range(6):
    t = time.time(); c.get_state(); gts.append((time.time() - t) * 1000)
sts = []
for _ in range(6):
    t = time.time(); c.set_param("AILERON_POSITION", 0.0); sts.append((time.time() - t) * 1000)
print("\nGET 延迟 avg=%.0fms (min %.0f/max %.0f) | SET 延迟 avg=%.0fms (min %.0f/max %.0f)" % (
    statistics.mean(gts), min(gts), max(gts), statistics.mean(sts), min(sts), max(sts)))
print("\n把上面「可写字段清单」里有没有 GENERAL_ENG_THROTTLE_LEVER_POSITION:1 发我即可定论。")
