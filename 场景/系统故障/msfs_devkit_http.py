"""DevKit HTTP 工具（仅用 Python 标准库，无需 requests）。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

TIMEOUT_SEC = 5


class DevKitError(Exception):
    pass


def api_get(api_base: str) -> dict:
    url = f"{api_base.rstrip('/')}/get"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            if resp.status != 200:
                raise DevKitError(f"GET /get 失败: HTTP {resp.status}")
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise DevKitError(f"无法连接 DevKit: {exc}") from exc

    return {p["name"]: p for p in data}


def api_get_path(api_base: str, path: str) -> dict:
    url = f"{api_base.rstrip('/')}/{path.lstrip('/')}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8")
            if resp.status != 200:
                raise DevKitError(f"GET /{path} 失败: HTTP {resp.status}: {raw[:200]}")
            return json.loads(raw)
    except urllib.error.URLError as exc:
        raise DevKitError(f"无法连接 DevKit: {exc}") from exc


def api_put_path(api_base: str, path: str, payload: dict | None = None) -> tuple[bool, str]:
    url = f"{api_base.rstrip('/')}/{path.lstrip('/')}"
    body = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8")
            if resp.status != 200:
                return False, f"HTTP {resp.status}: {raw[:200]}"
            try:
                msg = json.loads(raw).get("message", "ok")
            except json.JSONDecodeError:
                msg = raw or "ok"
            return True, msg
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code}: {raw[:200]}"
    except urllib.error.URLError as exc:
        return False, str(exc)


def api_set(api_base: str, name: str, val: float) -> tuple[bool, str]:
    url = f"{api_base.rstrip('/')}/set"
    body = json.dumps({"name": name, "val": val}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8")
            if resp.status != 200:
                return False, f"HTTP {resp.status}: {raw[:200]}"
            try:
                msg = json.loads(raw).get("message", "ok")
            except json.JSONDecodeError:
                msg = raw or "ok"
            return True, msg
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code}: {raw[:200]}"
    except urllib.error.URLError as exc:
        return False, str(exc)


VELOCITY_ZERO_VARS = ("VELOCITY_BODY_X", "VELOCITY_BODY_Y", "VELOCITY_BODY_Z")


def teleport_aircraft(api_base: str, payload: dict) -> list[tuple[str, bool, str]]:
    """传送飞机：先关闭 AP（避免自动推油门），再设位置，最后清零速度。"""
    results: list[tuple[str, bool, str]] = []
    ok, msg = api_put_path(api_base, "ap_stop")
    results.append(("ap_stop", ok, msg))
    for name, val in payload.items():
        ok, msg = api_set(api_base, name, val)
        results.append((name, ok, msg))
    for name in VELOCITY_ZERO_VARS:
        ok, msg = api_set(api_base, name, 0.0)
        results.append((name, ok, msg))
    return results
