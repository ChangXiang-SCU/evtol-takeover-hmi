# -*- coding: utf-8 -*-
"""打印 DevKit /get 的全部字段名(排序), 即 CSV 里 DevKit 部分的列顺序。"""
import urllib.request, json
d = json.loads(urllib.request.urlopen("http://127.0.0.1:5000/get", timeout=8).read().decode())
names = sorted(p["name"] for p in d if isinstance(p, dict) and "name" in p)
print("COUNT", len(names))
for n in names:
    print(n)
