#!/usr/bin/env python3
"""
MSFS 2024 系统故障场景（配合 AICtrl DevKit）

场景：下降阶段自动驾驶断开，需人工接管。

用法:
  python3 msfs_failure.py save           # 记录系统故障存档点
  python3 msfs_failure.py teleport       # 传送到存档点
  python3 msfs_failure.py ap-stop        # 断开自动驾驶（模拟故障）
  python3 msfs_failure.py ap-state       # 查看 AP 状态
  python3 msfs_failure.py status         # 查看位置
  python3 msfs_failure.py monitor          # 实时监控
  python3 msfs_failure.py run              # 传送 + 监控
  python3 msfs_failure.py save-trigger     # 当前位置设为触发区（50m，±100ft）
  python3 msfs_failure.py run --auto-fail  # 飞入触发区自动 ap-stop
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from msfs_devkit_http import DevKitError, api_get, api_get_path, api_put_path, api_set

SCRIPT_DIR = Path(__file__).resolve().parent
ARCHIVE_PATH = SCRIPT_DIR / "position_archive.json"
LOG_PATH = SCRIPT_DIR / "events.log"
POLL_HZ = 5
TRIGGER_RADIUS_M = 50
ALT_TOLERANCE_FT = 100

API_BASE_DEFAULT = "http://10.7.144.111:5000"


def load_archive() -> dict:
    if not ARCHIVE_PATH.exists():
        print(f"找不到存档: {ARCHIVE_PATH}")
        sys.exit(1)
    return json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))


def save_archive(archive: dict) -> None:
    ARCHIVE_PATH.write_text(
        json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_api(archive: dict) -> str:
    return archive.get("api_base", API_BASE_DEFAULT)


def log_event(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {message}\n"
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")


def write_status_line(text: str) -> None:
    sys.stdout.write("\033[2K\r" + text)
    sys.stdout.flush()


def notify_mac(title: str, message: str) -> None:
    safe = message.replace('"', "'")
    script = f'display notification "{safe}" with title "{title}" sound name "Glass"'
    try:
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
    except OSError:
        pass


def params_to_save_point(params: dict) -> dict:
    return {
        "saved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "position": {
            "latitude": params["PLANE_LATITUDE"]["val"],
            "longitude": params["PLANE_LONGITUDE"]["val"],
            "altitude_ft_msl": params["PLANE_ALTITUDE"]["val"],
            "altitude_ft_agl": params["PLANE_ALT_ABOVE_GROUND"]["val"],
            "heading_true_deg": params["PLANE_HEADING_DEGREES_TRUE"]["val"],
            "pitch_deg": params["PLANE_PITCH_DEGREES"]["val"],
            "bank_deg": params["PLANE_BANK_DEGREES"]["val"],
        },
        "teleport_set_payload": {
            "PLANE_LATITUDE": params["PLANE_LATITUDE"]["val"],
            "PLANE_LONGITUDE": params["PLANE_LONGITUDE"]["val"],
            "PLANE_ALTITUDE": params["PLANE_ALTITUDE"]["val"],
            "PLANE_HEADING_DEGREES_TRUE": params["PLANE_HEADING_DEGREES_TRUE"]["val"],
            "PLANE_PITCH_DEGREES": params["PLANE_PITCH_DEGREES"]["val"],
            "PLANE_BANK_DEGREES": params["PLANE_BANK_DEGREES"]["val"],
        },
        "environment": {
            "ground_altitude_ft": params["GROUND_ALTITUDE"]["val"],
            "wind_velocity_kt": params["AMBIENT_WIND_VELOCITY"]["val"],
            "wind_direction_deg": params["AMBIENT_WIND_DIRECTION"]["val"],
            "on_ground": bool(params["SIM_ON_GROUND"]["val"]),
            "vertical_speed_ft_min": params["VERTICAL_SPEED"]["val"],
            "ground_speed_kt": params["GPS_GROUND_SPEED"]["val"],
        },
    }


def format_position(params: dict) -> str:
    lat = params["PLANE_LATITUDE"]["val"]
    lon = params["PLANE_LONGITUDE"]["val"]
    alt = params["PLANE_ALTITUDE"]["val"]
    agl = params["PLANE_ALT_ABOVE_GROUND"]["val"]
    hdg = params["PLANE_HEADING_DEGREES_TRUE"]["val"]
    vs = params["VERTICAL_SPEED"]["val"]
    gs = params["GPS_GROUND_SPEED"]["val"]
    return (
        f"lat={lat:.6f}  lon={lon:.6f}  "
        f"alt={alt:.1f}ft MSL ({agl:.1f}ft AGL)  "
        f"hdg={hdg:.1f}°  VS={vs:.0f}ft/min  GS={gs:.1f}kt"
    )


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def in_trigger_zone(lat: float, lon: float, alt_ft: float, trigger: dict) -> bool:
    if not trigger.get("enabled"):
        return False
    center_lat = trigger.get("center_latitude")
    center_lon = trigger.get("center_longitude")
    if center_lat is None or center_lon is None:
        return False
    dist = haversine_m(lat, lon, center_lat, center_lon)
    return (
        dist <= trigger.get("radius_m", TRIGGER_RADIUS_M)
        and trigger["alt_min_ft"] <= alt_ft <= trigger["alt_max_ft"]
    )


def trigger_zone_configured(trigger: dict) -> bool:
    return bool(
        trigger.get("enabled")
        and trigger.get("center_latitude") is not None
        and trigger.get("center_longitude") is not None
        and trigger.get("alt_min_ft") is not None
        and trigger.get("alt_max_ft") is not None
    )


def format_trigger_summary(trigger: dict) -> str:
    return (
        f"中心 {trigger['center_latitude']:.6f}, {trigger['center_longitude']:.6f} | "
        f"半径 {trigger.get('radius_m', TRIGGER_RADIUS_M)} m | "
        f"高度 {trigger['alt_min_ft']:.0f}-{trigger['alt_max_ft']:.0f} ft MSL"
    )


def require_save_point(archive: dict) -> dict:
    point = archive.get("failure_save_point")
    if not point or not point.get("teleport_set_payload"):
        print("尚未设置系统故障存档点。请运行:")
        print(f"  python3 {SCRIPT_DIR / 'msfs_failure.py'} save")
        sys.exit(1)
    return point


def cmd_save(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = get_api(archive)
    try:
        params = api_get(api)
    except DevKitError as exc:
        print(f"错误: {exc}")
        sys.exit(1)

    save_point = params_to_save_point(params)
    archive["failure_save_point"] = save_point
    save_archive(archive)

    pos = save_point["position"]
    print(f"系统故障存档点已保存: {ARCHIVE_PATH}")
    print(f"  场景: {archive.get('scenario', '')}")
    print(f"  纬度: {pos['latitude']:.8f}°")
    print(f"  经度: {pos['longitude']:.8f}°")
    print(f"  高度: {pos['altitude_ft_msl']:.1f} ft MSL ({pos['altitude_ft_agl']:.1f} ft AGL)")
    print(f"  航向: {pos['heading_true_deg']:.2f}° (真北)")
    log_event(
        f"SAVE_FAILURE_POINT lat={pos['latitude']:.6f} lon={pos['longitude']:.6f} "
        f"alt={pos['altitude_ft_msl']:.1f}ft"
    )


def cmd_teleport(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = get_api(archive)
    point = require_save_point(archive)
    payload = point["teleport_set_payload"]

    print("传送到系统故障存档点...")
    for name, val in payload.items():
        ok, msg = api_set(api, name, val)
        print(f"  {'✓' if ok else '✗'} {name} = {val} ({msg})")

    pos = point["position"]
    log_event(
        f"TELEPORT lat={pos['latitude']:.6f} lon={pos['longitude']:.6f} "
        f"alt={pos['altitude_ft_msl']:.1f}ft"
    )
    print("传送完成。可开启 AP 后开始下降训练。")


def cmd_ap_stop(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = get_api(archive)
    print("断开自动驾驶 (ap_stop)...")
    ok, msg = api_put_path(api, "ap_stop")
    if ok:
        log_event("AP_STOP 系统故障模拟")
        notify_mac("系统故障", "自动驾驶已断开，请人工接管")
        print(f"  ✓ AP 已断开 ({msg})")
    else:
        print(f"  ✗ 失败: {msg}")
        sys.exit(1)


def cmd_ap_state(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = get_api(archive)
    try:
        state = api_get_path(api, "ap_state")
    except DevKitError as exc:
        print(f"错误: {exc}")
        sys.exit(1)
    print("辅助驾驶状态:")
    for key, val in state.items():
        print(f"  {key}: {val}")


def cmd_status(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = get_api(archive)
    try:
        params = api_get(api)
    except DevKitError as exc:
        print(f"错误: {exc}")
        sys.exit(1)

    print(f"场景: {archive.get('scenario', '')}")
    print(f"当前: {format_position(params)}")
    point = archive.get("failure_save_point")
    if point:
        pos = point["position"]
        print(
            f"存档: lat={pos['latitude']:.6f} lon={pos['longitude']:.6f} "
            f"alt={pos['altitude_ft_msl']:.1f}ft ({point.get('saved_at_utc', '')})"
        )
    else:
        print("存档: 未设置（请先 save）")
    trigger = archive.get("failure_trigger", {})
    if trigger_zone_configured(trigger):
        print(f"触发区: {format_trigger_summary(trigger)}")
    else:
        print("触发区: 未设置（请先 save-trigger）")


def trigger_ap_stop(api: str, *, reason: str) -> bool:
    ok, msg = api_put_path(api, "ap_stop")
    if ok:
        log_event(f"AP_STOP {reason}")
        notify_mac("系统故障", "AP 断开，请人工接管")
        return True
    print(f"  ✗ ap_stop 失败: {msg}")
    return False


def cmd_monitor(args: argparse.Namespace) -> None:
    archive = load_archive()
    api = get_api(archive)
    trigger = archive.get("failure_trigger", {})
    auto = args.auto_fail and trigger_zone_configured(trigger)
    failed = armed = False

    print(f"位置监控 — {archive.get('scenario', '')} (Ctrl+C 停止)")
    if auto:
        print(f"  自动故障: {format_trigger_summary(trigger)}")
        print("  须先处于触发区外（ARMED）再飞入才会触发 ap_stop")

    interval = 1.0 / POLL_HZ
    try:
        while True:
            try:
                params = api_get(api)
                lat = float(params["PLANE_LATITUDE"]["val"])
                lon = float(params["PLANE_LONGITUDE"]["val"])
                alt = float(params["PLANE_ALTITUDE"]["val"])
                inside = in_trigger_zone(lat, lon, alt, trigger)
                dist = (
                    haversine_m(
                        lat, lon,
                        trigger["center_latitude"], trigger["center_longitude"],
                    )
                    if trigger_zone_configured(trigger)
                    else 0.0
                )
                line = format_position(params)
                if auto:
                    if not inside:
                        armed = True
                    zone_tag = "IN" if inside else ("ARMED" if armed else "WAIT")
                    line += f"  [{zone_tag} dist={dist:.0f}m]"
                    if inside and armed and not failed:
                        failed = True
                        write_status_line(line)
                        print()
                        print(
                            f">>> 进入系统故障触发区 (dist={dist:.1f}m, alt={alt:.1f}ft)，断开 AP..."
                        )
                        if trigger_ap_stop(api, reason=f"AUTO_ZONE dist={dist:.1f}m alt={alt:.1f}ft"):
                            print("  ✓ AP 已断开")
                        line += "  [AP OFF]"
                write_status_line(line)
            except DevKitError as exc:
                write_status_line(f"[等待 DevKit] {exc}")
            time.sleep(interval)
    except KeyboardInterrupt:
        write_status_line("")
        print("\n监控已停止。")


def cmd_run(args: argparse.Namespace) -> None:
    require_save_point(load_archive())
    cmd_teleport(argparse.Namespace())
    print()
    time.sleep(1.0)
    cmd_monitor(args)


def cmd_save_trigger(args: argparse.Namespace) -> None:
    archive = load_archive()
    api = get_api(archive)
    try:
        params = api_get(api)
    except DevKitError as exc:
        print(f"错误: {exc}")
        sys.exit(1)

    lat = params["PLANE_LATITUDE"]["val"]
    lon = params["PLANE_LONGITUDE"]["val"]
    alt = params["PLANE_ALTITUDE"]["val"]
    radius = args.radius
    tolerance = args.tolerance
    trigger = archive.setdefault("failure_trigger", {})
    old_lat = trigger.get("center_latitude")
    old_lon = trigger.get("center_longitude")

    trigger["enabled"] = True
    trigger["center_latitude"] = lat
    trigger["center_longitude"] = lon
    trigger["center_altitude_ft_msl"] = alt
    trigger["radius_m"] = radius
    trigger["alt_tolerance_ft"] = tolerance
    trigger["alt_min_ft"] = alt - tolerance
    trigger["alt_max_ft"] = alt + tolerance
    trigger["saved_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    trigger["note"] = (
        f"系统故障触发区：半径 {radius}m，"
        f"高度 {trigger['alt_min_ft']:.0f}-{trigger['alt_max_ft']:.0f} ft MSL "
        f"(记录高度 {alt:.0f} ft ± {tolerance:.0f} ft)"
    )
    save_archive(archive)

    print(f"系统故障触发区已更新: {ARCHIVE_PATH}")
    print(f"  中心: {lat:.8f}°, {lon:.8f}°")
    print(f"  记录高度: {alt:.1f} ft MSL")
    print(f"  半径: {radius} m")
    print(
        f"  高度范围: {trigger['alt_min_ft']:.1f} - {trigger['alt_max_ft']:.1f} ft MSL "
        f"(±{tolerance:.0f} ft)"
    )
    if old_lat is not None and old_lon is not None:
        print(f"  相对旧中心位移: {haversine_m(old_lat, old_lon, lat, lon):.1f} m")
    log_event(
        f"SAVE_TRIGGER lat={lat:.6f} lon={lon:.6f} alt={alt:.1f}ft "
        f"r={radius}m ±{tolerance:.0f}ft"
    )


def cmd_set_trigger(args: argparse.Namespace) -> None:
    """兼容旧命令名。"""
    cmd_save_trigger(args)


def main() -> None:
    parser = argparse.ArgumentParser(description="MSFS 系统故障场景")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("save", help="记录系统故障存档点")
    sub.add_parser("teleport", help="传送到存档点")
    sub.add_parser("ap-stop", help="断开自动驾驶")
    sub.add_parser("ap-state", help="查看 AP 状态")
    sub.add_parser("status", help="查看位置")

    p_trigger = sub.add_parser(
        "save-trigger", help="用当前位置设为触发区（默认 50m，±100ft）"
    )
    p_trigger.add_argument("--radius", type=float, default=TRIGGER_RADIUS_M, help="半径 m")
    p_trigger.add_argument(
        "--tolerance", type=float, default=ALT_TOLERANCE_FT, help="高度容差 ft"
    )

    p_trigger_legacy = sub.add_parser("set-trigger", help="同 save-trigger（兼容）")
    p_trigger_legacy.add_argument("--radius", type=float, default=TRIGGER_RADIUS_M)
    p_trigger_legacy.add_argument("--tolerance", type=float, default=ALT_TOLERANCE_FT)

    p_monitor = sub.add_parser("monitor", help="实时监控")
    p_monitor.add_argument(
        "--auto-fail", action="store_true", help="飞入触发区自动 ap_stop"
    )

    p_run = sub.add_parser("run", help="传送并监控")
    p_run.add_argument(
        "--auto-fail", action="store_true", help="飞入触发区自动 ap_stop"
    )

    args = parser.parse_args()
    handlers = {
        "save": cmd_save,
        "teleport": cmd_teleport,
        "ap-stop": cmd_ap_stop,
        "ap-state": cmd_ap_state,
        "status": cmd_status,
        "monitor": cmd_monitor,
        "run": cmd_run,
        "save-trigger": cmd_save_trigger,
        "set-trigger": cmd_set_trigger,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
