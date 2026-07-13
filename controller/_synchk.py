# -*- coding: utf-8 -*-
"""语法+静态自检：ast.parse 两个文件，并干跑关键函数引用。"""
import ast, io, sys

for f in ("control_panel.py", "config.py"):
    src = io.open(f, encoding="utf-8").read()
    try:
        ast.parse(src)
        print(f, "OK", src.count("\n"), "lines")
    except SyntaxError as e:
        print(f, "SYNTAX ERROR line", e.lineno, e.msg)
        sys.exit(1)

# 关键符号检查：新逻辑函数存在、旧 BASELINE 逻辑已清除
src = io.open("control_panel.py", encoding="utf-8").read()
need = ["def do_alert", "def do_cause", "def detect_manual", "def manual_input",
        "def capture_rest", "def cmd_set", "ALERT_LEAD_S", "trigger_at", "cause_fired"]
for n in need:
    if n not in src:
        print("MISSING:", n); sys.exit(1)
for bad in ["BASELINE", "do_trigger", "BASELINE_SETTLE_S"]:
    if bad in src:
        print("LEFTOVER:", bad); sys.exit(1)
cfg = io.open("config.py", encoding="utf-8").read()
for n in ["ALERT_LEAD_S", "DEFLECT_CONFIRM_N", "CLOSE_RATE_WIN_S"]:
    if n not in cfg:
        print("MISSING in config:", n); sys.exit(1)
print("ALL CHECKS PASSED")
