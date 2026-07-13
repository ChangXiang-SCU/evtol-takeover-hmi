# -*- coding: utf-8 -*-
"""抽出 control_panel.py 里 PANEL_HTML / HMI_HTML 的 <script> 内容, 用 node --check 验语法。"""
import re, subprocess
src = open('control_panel.py', encoding='utf-8').read()
bad = 0
for name in ('PANEL_HTML', 'HMI_HTML'):
    m = re.search(name + r' = """(.*?)"""', src, re.S)
    if not m:
        print(name, 'NOT FOUND'); continue
    js = "\n".join(re.findall(r'<script>(.*?)</script>', m.group(1), re.S))
    fn = '_%s.js' % name
    open(fn, 'w', encoding='utf-8').write(js)
    try:
        r = subprocess.run(['node', '--check', fn], capture_output=True, text=True)
        if r.returncode == 0:
            print(name, 'JS OK')
        else:
            bad += 1; print(name, 'JS ERROR:\n', r.stderr[:400])
    except FileNotFoundError:
        print(name, '(node 未装, 跳过 JS 检查)')
print('ALLJS_OK' if bad == 0 else 'JS_HAS_ERROR')
