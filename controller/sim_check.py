# -*- coding: utf-8 -*-
"""sim 本地真机自检：连 127.0.0.1:5000 的 DevKit，打印字段数与关键状态。"""
import config
config.USE_MOCK = False
config.DEVKIT_BASE_URL = "http://127.0.0.1:5000"
import controller
controller.selftest()
