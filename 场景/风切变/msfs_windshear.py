#!/usr/bin/env python3
"""
MSFS 2024 风切变触发脚本（配合 AICtrl DevKit）

恢复点与触发点分离:
  - restore_point: 传送恢复位置（起点，应在触发区外）
  - windshear_trigger: 风切变触发区（飞入后触发，非传送目标）

用法:
  python3 msfs_windshear.py save-heading   # 仅更新起始点航向（当前机头方向）
  python3 msfs_windshear.py save-trigger   # 记录当前位置为触发区中心（高度±100ft）
  python3 msfs_windshear.py teleport       # 传送到恢复点
  python3 msfs_windshear.py monitor        # 监控触发区
  python3 msfs_windshear.py run            # 传送到恢复点 + 监控
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

from msfs_devkit_http import DevKitError, api_get, api_set, teleport_aircraft

SCRIPT_DIR = Path(__file__).resolve().parent
ARCHIVE_PATH = SCRIPT_DIR / "position_archive.json"
LOG_PATH = SCRIPT_DIR / "events.log"
POLL_HZ = 10
ALT_TOLERANCE_FT = 100
WIND_VERIFY_TOLERANCE_KT = 8.0
SUSTAIN_INTERVAL_SEC = 0.5
KT_TO_MS = 0.514444


def load_archive() -> dict:
    if not ARCHIVE_PATH.exists():
        print(f"找不到存档: {ARCHIVE_PATH}")
        sys.exit(1)
    archive = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    return normalize_archive(archive)


def normalize_archive(archive: dict) -> dict:
    if "windshear_trigger" not in archive:
        draft = archive.get("windshear_trigger_draft", {})
        archive["windshear_trigger"] = {
            "center_latitude": draft.get(
                "center_latitude", archive.get("position", {}).get("latitude", 0)
            ),
            "center_longitude": draft.get(
                "center_longitude", archive.get("position", {}).get("longitude", 0)
            ),
            "radius_m": draft.get("radius_m", 50),
            "alt_tolerance_ft": draft.get("alt_tolerance_ft", ALT_TOLERANCE_FT),
            "alt_min_ft": draft.get("alt_min_ft", 400),
            "alt_max_ft": draft.get("alt_max_ft", 600),
        }
    if archive.get("restore_point") is None and archive.get("teleport_set_payload"):
        archive["restore_point"] = {
            "saved_at_utc": archive.get("saved_at_utc"),
            "position": archive.get("position", {}),
            "teleport_set_payload": archive["teleport_set_payload"],
            "environment": archive.get("environment", {}),
        }
    return archive


def save_archive(archive: dict) -> None:
    ARCHIVE_PATH.write_text(
        json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def params_to_restore_point(params: dict) -> dict:
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
        },
    }


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def in_trigger_zone(lat: float, lon: float, alt_ft: float, trigger: dict) -> bool:
    dist = haversine_m(lat, lon, trigger["center_latitude"], trigger["center_longitude"])
    return (
        dist <= trigger["radius_m"]
        and trigger["alt_min_ft"] <= alt_ft <= trigger["alt_max_ft"]
    )


def log_event(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {message}\n"
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")


def notify_mac(title: str, message: str) -> None:
    safe = message.replace('"', "'")
    script = f'display notification "{safe}" with title "{title}" sound name "Glass"'
    try:
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
    except OSError:
        pass


def require_restore_point(archive: dict) -> dict:
    restore = archive.get("restore_point")
    if not restore or not restore.get("teleport_set_payload"):
        print("尚未设置恢复传送点。")
        print("请先在 MSFS 中飞到起点位置，然后运行:")
        print(f"  python3 {SCRIPT_DIR / 'msfs_windshear.py'} save-restore")
        sys.exit(1)
    return restore


def cmd_save_restore(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = archive["api_base"]
    try:
        params = api_get(api)
    except DevKitError as exc:
        print(f"错误: {exc}")
        sys.exit(1)
    restore = params_to_restore_point(params)
    archive["restore_point"] = restore
    save_archive(archive)
    pos = restore["position"]
    trigger = archive["windshear_trigger"]
    dist = haversine_m(
        pos["latitude"], pos["longitude"],
        trigger["center_latitude"], trigger["center_longitude"],
    )
    inside = in_trigger_zone(
        pos["latitude"], pos["longitude"], pos["altitude_ft_msl"], trigger
    )
    print(f"恢复点已更新: {ARCHIVE_PATH}")
    print(f"  纬度: {pos['latitude']:.8f}°")
    print(f"  经度: {pos['longitude']:.8f}°")
    print(f"  高度: {pos['altitude_ft_msl']:.1f} ft MSL")
    print(f"  距触发区中心: {dist:.1f} m")
    if inside:
        print("\n⚠ 警告: 当前位置在触发区内！")
    else:
        print("  ✓ 当前位置在触发区外，适合作为恢复起点。")


def cmd_save_heading(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = archive["api_base"]
    restore = archive.get("restore_point")
    if not restore or not restore.get("teleport_set_payload"):
        print("尚未设置恢复点，请先 save-restore 或先对齐起始点。")
        sys.exit(1)
    try:
        params = api_get(api)
    except DevKitError as exc:
        print(f"错误: {exc}")
        sys.exit(1)

    hdg = params["PLANE_HEADING_DEGREES_TRUE"]["val"]
    pitch = params["PLANE_PITCH_DEGREES"]["val"]
    bank = params["PLANE_BANK_DEGREES"]["val"]
    restore["saved_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    restore["position"]["heading_true_deg"] = hdg
    restore["position"]["pitch_deg"] = pitch
    restore["position"]["bank_deg"] = bank
    restore["teleport_set_payload"]["PLANE_HEADING_DEGREES_TRUE"] = hdg
    restore["teleport_set_payload"]["PLANE_PITCH_DEGREES"] = pitch
    restore["teleport_set_payload"]["PLANE_BANK_DEGREES"] = bank
    save_archive(archive)

    print(f"风切变起始点航向已更新: {ARCHIVE_PATH}")
    print(f"  航向: {hdg:.2f}° (真北)")
    print(f"  俯仰: {pitch:.2f}°  滚转: {bank:.2f}°")
    print("  位置/高度未改动。")
    log_event(f"SAVE_HEADING hdg={hdg:.2f}")


def cmd_save_trigger(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = archive["api_base"]
    try:
        params = api_get(api)
    except DevKitError as exc:
        print(f"错误: {exc}")
        sys.exit(1)
    lat = params["PLANE_LATITUDE"]["val"]
    lon = params["PLANE_LONGITUDE"]["val"]
    alt = params["PLANE_ALTITUDE"]["val"]
    trigger = archive.setdefault("windshear_trigger", {})
    old_lat = trigger.get("center_latitude")
    old_lon = trigger.get("center_longitude")
    tolerance = trigger.get("alt_tolerance_ft", ALT_TOLERANCE_FT)
    trigger["center_latitude"] = lat
    trigger["center_longitude"] = lon
    trigger.setdefault("radius_m", 50)
    trigger["center_altitude_ft_msl"] = alt
    trigger["alt_tolerance_ft"] = tolerance
    trigger["alt_min_ft"] = alt - tolerance
    trigger["alt_max_ft"] = alt + tolerance
    trigger["saved_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    trigger["note"] = (
        f"风切变触发区：半径 {trigger.get('radius_m', 50)}m，"
        f"高度 {trigger['alt_min_ft']:.0f}-{trigger['alt_max_ft']:.0f} ft MSL "
        f"(记录高度 {alt:.0f} ft ± {tolerance:.0f} ft)"
    )
    save_archive(archive)
    print(f"触发区已更新: {ARCHIVE_PATH}")
    print(f"  新中心: {lat:.8f}°, {lon:.8f}°")
    print(f"  记录高度: {alt:.1f} ft MSL")
    print(f"  半径: {trigger['radius_m']} m")
    print(
        f"  高度范围: {trigger['alt_min_ft']:.1f} - {trigger['alt_max_ft']:.1f} ft MSL "
        f"(±{tolerance:.0f} ft)"
    )
    if old_lat is not None and old_lon is not None:
        print(f"  相对旧中心位移: {haversine_m(old_lat, old_lon, lat, lon):.1f} m")


def cmd_teleport(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = archive["api_base"]
    restore = require_restore_point(archive)
    payload = restore["teleport_set_payload"]
    print("传送到恢复点（非触发点）...")
    for name, ok, msg in teleport_aircraft(api, payload):
        print(f"  {'✓' if ok else '✗'} {name} ({msg})")
    pos = restore["position"]
    log_event(
        f"TELEPORT_RESTORE lat={pos['latitude']:.6f} lon={pos['longitude']:.6f} "
        f"alt={pos['altitude_ft_msl']:.1f}ft"
    )
    print("传送完成。")


def read_wind(params: dict) -> tuple[float, float]:
    return (
        float(params["AMBIENT_WIND_VELOCITY"]["val"]),
        float(params["AMBIENT_WIND_DIRECTION"]["val"]),
    )


def inject_wind(
    api: str, target_vel_kt: float, target_dir_deg: float, *, quiet: bool = False
) -> tuple[bool, str, float]:
    before_vel, _ = read_wind(api_get(api))
    for name, val in [
        ("AMBIENT_WIND_VELOCITY", target_vel_kt),
        ("AMBIENT_WIND_DIRECTION", target_dir_deg),
    ]:
        api_set(api, name, val)
    time.sleep(0.15)
    after_vel, after_dir = read_wind(api_get(api))
    if abs(after_vel - target_vel_kt) <= WIND_VERIFY_TOLERANCE_KT:
        detail = f"读回 {after_vel:.1f} kt @ {after_dir:.0f}°"
        if not quiet:
            print(f"  ✓ 风况已生效: {detail}")
        return True, detail, after_vel
    detail = f"仍为 {after_vel:.1f} kt (目标 {target_vel_kt:.1f} kt)"
    if not quiet:
        print(f"  ✗ 注入未生效: {detail}")
    return False, detail, after_vel


def apply_windshear(
    api: str, target: dict, baseline: dict, *, quiet: bool = False
) -> bool:
    target_vel = target["wind_velocity_kt"]
    target_dir = target["wind_direction_deg"]
    if not quiet:
        print(f"  尝试注入 {target_vel:.0f} kt @ {target_dir:.0f}° ...")
    ok, detail, _ = inject_wind(api, target_vel, target_dir, quiet=quiet)
    if ok:
        log_event(f"WIND_APPLIED {target_vel}kt @ {target_dir}deg ({detail})")
        if not quiet:
            notify_mac("MSFS 风切变", f"风况 {target_vel:.0f} kt 已生效")
        return True
    log_event(f"WIND_APPLY_FAILED target={target_vel}kt ({detail})")
    if not quiet:
        notify_mac("MSFS 风切变", f"DevKit 无法改风！请 MSFS 手动设 {target_vel:.0f} kt")
        print("\n⚠ DevKit 无法真正改变 MSFS 风速（AMBIENT_WIND_* 只读）。")
    return False


def cmd_test_wind(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = archive["api_base"]
    target = archive.get(
        "windshear_target", {"wind_velocity_kt": 50.0, "wind_direction_deg": 270.0}
    )
    before_vel, before_dir = read_wind(api_get(api))
    print(f"注入前: {before_vel:.1f} kt @ {before_dir:.0f}°")
    ok, detail, _ = inject_wind(
        api, target["wind_velocity_kt"], target["wind_direction_deg"]
    )
    print(f"结果: {'成功' if ok else '失败'} — {detail}")
    if not ok:
        sys.exit(1)


def cmd_monitor(args: argparse.Namespace) -> None:
    archive = load_archive()
    api = archive["api_base"]
    trigger = archive["windshear_trigger"]
    target = archive.get(
        "windshear_target", {"wind_velocity_kt": 50.0, "wind_direction_deg": 270.0}
    )
    restore = archive.get("restore_point") or {}
    baseline = restore.get("environment") or {
        "wind_velocity_kt": 0.0,
        "wind_direction_deg": 270.0,
    }
    print("风切变监控已启动 (Ctrl+C 停止)")
    if restore.get("position"):
        rp = restore["position"]
        print(
            f"  恢复点: {rp['latitude']:.6f}, {rp['longitude']:.6f} "
            f"({rp['altitude_ft_msl']:.0f} ft)"
        )
    print(f"  触发区: {trigger['center_latitude']:.6f}, {trigger['center_longitude']:.6f}")
    print(
        f"  范围: 半径 {trigger['radius_m']} m, "
        f"高度 {trigger['alt_min_ft']}-{trigger['alt_max_ft']} ft MSL"
    )
    print(f"  目标风: {target['wind_velocity_kt']} kt @ {target['wind_direction_deg']}°")
    triggered = armed = False
    injection_ok = None
    injection_disabled = False
    last_sustain = 0.0
    interval = 1.0 / POLL_HZ
    try:
        while True:
            try:
                params = api_get(api)
                lat = float(params["PLANE_LATITUDE"]["val"])
                lon = float(params["PLANE_LONGITUDE"]["val"])
                alt = float(params["PLANE_ALTITUDE"]["val"])
                wind, _ = read_wind(params)
                dist = haversine_m(
                    lat, lon, trigger["center_latitude"], trigger["center_longitude"]
                )
                inside = in_trigger_zone(lat, lon, alt, trigger)
                if not inside:
                    armed = True
                    if triggered and args.reset_on_exit:
                        print()
                        apply_windshear(
                            api,
                            {
                                "wind_velocity_kt": baseline["wind_velocity_kt"],
                                "wind_direction_deg": baseline["wind_direction_deg"],
                            },
                            baseline,
                        )
                        triggered = False
                        injection_ok = None
                if inside and armed and not triggered:
                    print()
                    log_event(f"TRIGGER dist={dist:.1f}m alt={alt:.1f}ft")
                    injection_ok = apply_windshear(api, target, baseline)
                    triggered = True
                    last_sustain = time.time()
                    if not injection_ok:
                        injection_disabled = True
                        notify_mac(
                            "风切变触发区",
                            f"已进入触发区！MSFS 设风 {target['wind_velocity_kt']:.0f}kt",
                        )
                elif inside and triggered and not injection_disabled:
                    if time.time() - last_sustain >= SUSTAIN_INTERVAL_SEC:
                        ok, _, read_vel = inject_wind(
                            api,
                            target["wind_velocity_kt"],
                            target["wind_direction_deg"],
                            quiet=True,
                        )
                        injection_ok = ok
                        if not ok:
                            injection_disabled = True
                        last_sustain = time.time()
                        wind = read_vel
                if inside and triggered:
                    status = "SUSTAIN" if injection_ok else ("IN_ZONE" if injection_disabled else "SUSTAIN?")
                elif inside and armed:
                    status = "TRIGGER"
                elif armed:
                    status = "ARMED"
                else:
                    status = "WAIT_ARM"
                flag = "OK" if injection_ok else ("MANUAL" if injection_disabled else "--")
                print(
                    f"\r[{status}|{flag}] dist={dist:5.1f}m alt={alt:6.1f}ft "
                    f"wind={wind:4.1f}kt tgt={target['wind_velocity_kt']:.0f}kt   ",
                    end="",
                    flush=True,
                )
            except DevKitError as exc:
                print(f"\r[等待 DevKit] {exc}          ", end="", flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n监控已停止。")


def cmd_run(args: argparse.Namespace) -> None:
    require_restore_point(load_archive())
    cmd_teleport(args)
    print()
    time.sleep(1.0)
    cmd_monitor(args)


def main() -> None:
    parser = argparse.ArgumentParser(description="MSFS 风切变触发工具")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("save-restore", help="记录恢复点")
    sub.add_parser("save-heading", help="用当前机头方向更新起始点航向")
    sub.add_parser("save-trigger", help="记录触发区")
    sub.add_parser("test-wind", help="测试改风")
    sub.add_parser("teleport", help="传送到恢复点")
    p_monitor = sub.add_parser("monitor", help="监控触发区")
    p_monitor.add_argument("--reset-on-exit", action="store_true")
    p_run = sub.add_parser("run", help="传送并监控")
    p_run.add_argument("--reset-on-exit", action="store_true")
    args = parser.parse_args()
    handlers = {
        "save-restore": cmd_save_restore,
        "save-heading": cmd_save_heading,
        "save-trigger": cmd_save_trigger,
        "test-wind": cmd_test_wind,
        "teleport": cmd_teleport,
        "monitor": cmd_monitor,
        "run": cmd_run,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
