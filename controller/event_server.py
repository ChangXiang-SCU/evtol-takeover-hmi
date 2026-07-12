# -*- coding: utf-8 -*-
"""
事件服务器（纯标准库 http.server）
- GET  /            → 托管触摸屏测试 HMI (hmi_test.html)
- GET  /events      → SSE 流，向 HMI 实时推送接管请求
- POST /takeover    → HMI 回传触摸屏"接管"点击（含服务器接收时间戳）
- GET  /health      → 健康检查
控制器用 broadcast() 推事件、get_takeover() 取点击。
"""
import os
import json
import time
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config

_HMI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hmi_test.html")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 静默默认访问日志

    # ---------- GET ----------
    def do_GET(self):
        if self.path.startswith("/events"):
            return self._sse()
        if self.path.startswith("/health"):
            return self._send(200, "ok", "text/plain")
        # 其余一律返回 HMI 页面
        try:
            with open(_HMI_FILE, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self._send(404, "hmi_test.html not found", "text/plain")

    # ---------- POST ----------
    def do_POST(self):
        if not self.path.startswith("/takeover"):
            return self._send(404, "not found", "text/plain")
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace") if n else "{}"
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        payload["t_server"] = time.time()          # 以服务器接收时刻为准
        self.server.takeover_event = payload
        self._send(200, json.dumps({"ok": True}), "application/json")

    # ---------- SSE ----------
    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        q = queue.Queue()
        self.server.add_subscriber(q)
        try:
            while True:
                try:
                    ev = q.get(timeout=15)
                    self.wfile.write(("data: " + json.dumps(ev, ensure_ascii=False) + "\n\n").encode("utf-8"))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")   # 心跳保活
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.server.remove_subscriber(q)

    def _send(self, code, text, ctype):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass


class EventServer:
    def __init__(self, host=None, port=None):
        self.host = host or config.EVENT_SERVER_HOST
        self.port = port or config.EVENT_SERVER_PORT
        self._httpd = None
        self._thread = None

    def start(self):
        self._httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        self._httpd.daemon_threads = True
        self._httpd._subs = []
        self._httpd._subs_lock = threading.Lock()
        self._httpd.takeover_event = None
        # 给 server 实例挂上订阅者管理方法
        self._httpd.add_subscriber = lambda q: self._add(q)
        self._httpd.remove_subscriber = lambda q: self._rm(q)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def _add(self, q):
        with self._httpd._subs_lock:
            self._httpd._subs.append(q)

    def _rm(self, q):
        with self._httpd._subs_lock:
            if q in self._httpd._subs:
                self._httpd._subs.remove(q)

    def broadcast(self, event):
        """向所有已连接 HMI 推一条事件。"""
        if not self._httpd:
            return
        with self._httpd._subs_lock:
            subs = list(self._httpd._subs)
        for q in subs:
            q.put(event)

    def get_takeover(self):
        """返回最近一次触摸屏接管点击（dict，含 t_server）或 None。"""
        return self._httpd.takeover_event if self._httpd else None

    def reset_takeover(self):
        if self._httpd:
            self._httpd.takeover_event = None

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
