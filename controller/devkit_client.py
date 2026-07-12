# -*- coding: utf-8 -*-
"""
MSFS24 AICtrl DevKit REST 客户端（纯标准库 urllib）。
提供 Real 与 Mock 两种实现，接口一致，靠 config.USE_MOCK 切换。
"""
import json
import time
import math
import urllib.request
import urllib.error

import config
import geo


def _to_float(v):
    """尽量把 val 转成 float；转不了就原样返回。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


# ============================================================
# 真实客户端
# ============================================================
class DevKitClient:
    def __init__(self, base_url=None, timeout=None):
        self.base = (base_url or config.DEVKIT_BASE_URL).rstrip("/")
        self.timeout = timeout or config.HTTP_TIMEOUT_S

    def _req(self, method, path, body=None):
        url = self.base + path
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"   # 仅在有 body 时带，GET 不带（否则某些服务器对空body报400）
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")   # DevKit 用 4xx+{"error":...} 表达状态(如AP未启动)，读出body不抛异常
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    # ---- 状态 ----
    def get_state(self):
        """GET /get → {参数名: 值}"""
        arr = self._req("GET", "/get")
        out = {}
        if isinstance(arr, list):
            for p in arr:
                if isinstance(p, dict) and "name" in p:
                    out[p["name"]] = _to_float(p.get("val"))
        return out

    def set_param(self, name, val):
        """PUT /set 单个可写参数"""
        return self._req("PUT", "/set", {"name": name, "val": val})

    # ---- 辅助驾驶 ----
    def ap_state(self):
        return self._req("GET", "/ap_state")

    def ap_stop(self):
        """PUT /ap_stop 清除所有辅助驾驶"""
        return self._req("PUT", "/ap_stop", {})

    def ap_start(self, payload):
        """PUT /ap_start 通用入口"""
        return self._req("PUT", "/ap_start", payload)

    def ap_rotor_point(self, lat, lng, max_bank=config.MAX_BANK_DEG):
        """旋翼定点模式：飞向目标坐标并悬停"""
        tlat, tlng = (lng, lat) if config.SWAP_LATLNG else (lat, lng)
        p = {"state": config.FLY_STATE_ROTOR, "target_lat": tlat, "target_lng": tlng}
        if max_bank is not None:
            p["max_bank"] = max_bank
        return self.ap_start(p)

    def ap_alt_hold(self, target_alt_ft, target_v_speed_fts, state=config.FLY_STATE_ROTOR):
        """高度保持模式"""
        return self.ap_start({"state": state,
                              "target_alt": target_alt_ft,
                              "target_v_speed": target_v_speed_fts})

    def camera_image(self, save_path):
        """GET /camera_image → 存 PNG（可选，用于留证）"""
        url = self.base + "/camera_image"
        with urllib.request.urlopen(url, timeout=self.timeout) as resp:
            with open(save_path, "wb") as f:
                f.write(resp.read())
        return save_path


# ============================================================
# Mock 客户端（无 MSFS 干跑用）
# ============================================================
class MockDevKitClient:
    """
    模拟一次进近：从触发点外 MOCK_START_OFFSET_M 处沿直线飞向触发点；
    ap_stop 后继续缓慢下降直至"触地"；ap_stop 后 MOCK_AUTO_TAKEOVER_S 秒
    自动模拟一次操控输入（让整条链路在无人情况下也能跑完）。
    """
    def __init__(self):
        self.t0 = time.time()
        self.last = self.t0
        # 起点(会被 teleport 覆盖)：用 wind_shear 恢复点
        r = config.SCENARIOS["wind_shear"]["restore"]
        self.lat, self.lng, self.alt = r["lat"], r["lng"], r["alt_ft"]
        self.target = {"lat": r["lat"], "lng": r["lng"]}
        self.ground = 30.0
        self.pitch = 0.0
        self.bank = 0.0
        self.vspeed = 0.0
        self.gforce = 1.0
        self.ctrl = {ax: 0.0 for ax in config.CONTROL_AXES}
        self.vel = {config.SV_VEL_BODY_X: 0.0,
                    config.SV_VEL_BODY_Y: 0.0,
                    config.SV_VEL_BODY_Z: config.MOCK_GROUNDSPEED_FTS}
        self.ap_active = False
        self.ap_stop_t = None
        self.landed = False

    def _advance(self):
        now = time.time()
        dt = now - self.last
        self.last = now
        if dt <= 0:
            return
        if self.ap_active and not self.landed:
            # 巡航：朝目标推进 + 下降(进入触发高度带)
            d = geo.distance_m(self.lat, self.lng, self.target["lat"], self.target["lng"])
            step = min(config.MOCK_GROUNDSPEED_FTS * 0.3048 * dt, d)
            if d > 1e-6:
                brg = geo.bearing_deg(self.lat, self.lng, self.target["lat"], self.target["lng"])
                self.lat, self.lng = geo.move(self.lat, self.lng, brg, step)
            self.alt = max(self.ground + 3.0, self.alt - 20.0 * dt)
            self.vspeed = -20.0
            self.pitch = -2.0
        elif self.ap_stop_t is not None and not self.landed:
            # 断 AP 后：继续下降直至触地(干跑加快)
            self.alt = max(self.ground, self.alt - 60.0 * dt)
            self.vspeed = -60.0
            if self.alt <= self.ground + 0.5:
                self.landed = True
                self.vspeed = 0.0
                self.gforce = 1.6  # 模拟触地 G 峰值
            # 断 AP 后 MOCK_AUTO_TAKEOVER_S 秒自动"打杆"
            if time.time() - self.ap_stop_t >= config.MOCK_AUTO_TAKEOVER_S:
                self.ctrl["ELEVATOR_POSITION"] = config.CONTROL_DEADBAND + 0.1

    def get_state(self):
        self._advance()
        return {
            "PLANE_LATITUDE": self.lat,
            "PLANE_LONGITUDE": self.lng,
            "PLANE_ALTITUDE": self.alt,
            "PLANE_ALT_ABOVE_GROUND": max(0.0, self.alt - self.ground),
            "PLANE_PITCH_DEGREES": self.pitch,
            "PLANE_BANK_DEGREES": self.bank,
            "VERTICAL_SPEED": self.vspeed,
            "G_FORCE": self.gforce,
            config.SV_VEL_BODY_X: self.vel[config.SV_VEL_BODY_X],
            config.SV_VEL_BODY_Y: self.vel[config.SV_VEL_BODY_Y],
            config.SV_VEL_BODY_Z: self.vel[config.SV_VEL_BODY_Z],
            **self.ctrl,
        }

    def set_param(self, name, val):
        v = _to_float(val)
        if name == "PLANE_LATITUDE": self.lat = v            # teleport
        elif name == "PLANE_LONGITUDE": self.lng = v
        elif name == "PLANE_ALTITUDE": self.alt = v
        elif name == "PLANE_PITCH_DEGREES": self.pitch = v
        elif name == "PLANE_BANK_DEGREES": self.bank = v
        elif name in self.vel:
            self.vel[name] = v
            if name == config.SV_VEL_BODY_Y:
                self.vspeed = v
        elif name in self.ctrl:
            self.ctrl[name] = v
        return {"message": "ok(mock)"}

    def ap_state(self):
        return {"ap_enabled": self.ap_active, "ap_active": self.ap_active,
                "fly_status": config.FLY_STATE_ROTOR,
                "target_coord": {"latitude": self.target["lat"], "longitude": self.target["lng"]}}

    def ap_stop(self):
        self.ap_active = False
        self.ap_stop_t = time.time()
        return {"message": "ap stopped(mock)"}

    def ap_start(self, payload):
        self.ap_active = True
        if "target_lat" in payload and "target_lng" in payload:
            la, ln = payload["target_lat"], payload["target_lng"]
            if config.SWAP_LATLNG:
                la, ln = ln, la
            self.target = {"lat": la, "lng": ln}
        return {"message": "ap started(mock)"}

    def ap_rotor_point(self, lat, lng, max_bank=config.MAX_BANK_DEG):
        return self.ap_start({"state": config.FLY_STATE_ROTOR,
                              "target_lat": lat, "target_lng": lng})

    def ap_alt_hold(self, target_alt_ft, target_v_speed_fts, state=config.FLY_STATE_ROTOR):
        self.ap_active = True
        return {"message": "alt hold(mock)"}

    def camera_image(self, save_path):
        return None


def make_client():
    """按配置返回真实或 Mock 客户端。"""
    return MockDevKitClient() if config.USE_MOCK else DevKitClient()
