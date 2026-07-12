#!/usr/bin/env python3
"""
MSFS 2024 停机坪位置（配合 AICtrl DevKit）

用法:
  python3 msfs_helipad.py save       # 记录当前位置为停机坪
  python3 msfs_helipad.py teleport   # 传送到停机坪
  python3 msfs_helipad.py status     # 查看当前/停机坪位置
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from msfs_devkit_http import DevKitError, api_get, api_set, teleport_aircraft

SCRIPT_DIR = Path(__file__).resolve().parent
ARCHIVE_PATH = SCRIPT_DIR / "position_archive.json"
LOG_PATH = SCRIPT_DIR / "events.log"
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


def params_to_helipad(params: dict) -> dict:
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


def format_position(params: dict) -> str:
    lat = params["PLANE_LATITUDE"]["val"]
    lon = params["PLANE_LONGITUDE"]["val"]
    alt = params["PLANE_ALTITUDE"]["val"]
    agl = params["PLANE_ALT_ABOVE_GROUND"]["val"]
    hdg = params["PLANE_HEADING_DEGREES_TRUE"]["val"]
    on_ground = bool(params["SIM_ON_GROUND"]["val"])
    ground_tag = "地面" if on_ground else "空中"
    return (
        f"lat={lat:.6f}  lon={lon:.6f}  "
        f"alt={alt:.1f}ft MSL ({agl:.1f}ft AGL)  "
        f"hdg={hdg:.1f}°  [{ground_tag}]"
    )


def require_helipad(archive: dict) -> dict:
    point = archive.get("helipad_point")
    if not point or not point.get("teleport_set_payload"):
        print("尚未设置停机坪位置。请运行:")
        print(f"  python3 {SCRIPT_DIR / 'msfs_helipad.py'} save")
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

    helipad = params_to_helipad(params)
    archive["helipad_point"] = helipad
    save_archive(archive)

    pos = helipad["position"]
    print(f"停机坪位置已保存: {ARCHIVE_PATH}")
    print(f"  纬度: {pos['latitude']:.8f}°")
    print(f"  经度: {pos['longitude']:.8f}°")
    print(f"  高度: {pos['altitude_ft_msl']:.1f} ft MSL ({pos['altitude_ft_agl']:.1f} ft AGL)")
    print(f"  航向: {pos['heading_true_deg']:.2f}° (真北)")
    if helipad["environment"]["on_ground"]:
        print("  ✓ 当前在地面，适合作为停机坪")
    else:
        print("  ⚠ 当前在空中，建议降落到停机坪后再 save")
    log_event(
        f"SAVE_HELIPAD lat={pos['latitude']:.6f} lon={pos['longitude']:.6f} "
        f"alt={pos['altitude_ft_msl']:.1f}ft"
    )


def cmd_teleport(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = get_api(archive)
    point = require_helipad(archive)
    payload = point["teleport_set_payload"]

    print("传送到停机坪...")
    for name, ok, msg in teleport_aircraft(api, payload):
        print(f"  {'✓' if ok else '✗'} {name} ({msg})")

    pos = point["position"]
    log_event(
        f"TELEPORT_HELIPAD lat={pos['latitude']:.6f} lon={pos['longitude']:.6f} "
        f"alt={pos['altitude_ft_msl']:.1f}ft"
    )
    print("传送完成。")


def cmd_status(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = get_api(archive)
    try:
        params = api_get(api)
    except DevKitError as exc:
        print(f"错误: {exc}")
        sys.exit(1)

    print(f"描述: {archive.get('description', '')}")
    print(f"当前: {format_position(params)}")
    point = archive.get("helipad_point")
    if point:
        pos = point["position"]
        print(
            f"停机坪: lat={pos['latitude']:.6f} lon={pos['longitude']:.6f} "
            f"alt={pos['altitude_ft_msl']:.1f}ft ({point.get('saved_at_utc', '')})"
        )
    else:
        print("停机坪: 未设置（请先 save）")


def main() -> None:
    parser = argparse.ArgumentParser(description="MSFS 停机坪位置")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("save", help="记录当前位置为停机坪")
    sub.add_parser("teleport", help="传送到停机坪")
    sub.add_parser("status", help="查看位置")
    args = parser.parse_args()
    {"save": cmd_save, "teleport": cmd_teleport, "status": cmd_status}[args.command](args)


if __name__ == "__main__":
    main()
