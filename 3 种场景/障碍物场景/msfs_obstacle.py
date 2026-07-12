#!/usr/bin/env python3
"""
MSFS 2024 障碍物场景控制（配合 AICtrl DevKit）

场景：模拟下降过程中遇建筑物障碍物，需人工接管。

用法:
  python3 msfs_obstacle.py save              # 记录当前位置为恢复点
  python3 msfs_obstacle.py save-corner 1     # 记录障碍物角点1（楼顶角）
  python3 msfs_obstacle.py list-corners      # 列出所有角点
  python3 msfs_obstacle.py teleport          # 传送到恢复点
  python3 msfs_obstacle.py status            # 查看当前位置
  python3 msfs_obstacle.py monitor           # 实时监控位置（下降过程）
  python3 msfs_obstacle.py run               # 传送到恢复点并开始监控
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from msfs_devkit_http import DevKitError, api_get, api_set

SCRIPT_DIR = Path(__file__).resolve().parent
ARCHIVE_PATH = SCRIPT_DIR / "position_archive.json"
CORNERS_PATH = SCRIPT_DIR / "obstacle_corners.json"
LOG_PATH = SCRIPT_DIR / "events.log"
POLL_HZ = 5


def load_archive() -> dict:
    if not ARCHIVE_PATH.exists():
        print(f"找不到存档: {ARCHIVE_PATH}")
        sys.exit(1)
    return json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))


def save_archive(archive: dict) -> None:
    ARCHIVE_PATH.write_text(
        json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def default_corners_archive() -> dict:
    return {
        "description": "障碍物角点 — 建筑物楼顶角点，竖直向下为障碍物柱体区间",
        "zone_model": "vertical_pillar",
        "zone_note": (
            "每个角点自楼顶高度(MSL)竖直向下延伸至地面；"
            "相邻角点连线围成柱状障碍物区域"
        ),
        "corners": [],
    }


def load_corners() -> dict:
    if not CORNERS_PATH.exists():
        return default_corners_archive()
    return json.loads(CORNERS_PATH.read_text(encoding="utf-8"))


def save_corners(data: dict) -> None:
    CORNERS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def params_to_corner(params: dict, corner_id: int, name: str) -> dict:
    return {
        "id": corner_id,
        "name": name,
        "saved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latitude": params["PLANE_LATITUDE"]["val"],
        "longitude": params["PLANE_LONGITUDE"]["val"],
        "altitude_ft_msl": params["PLANE_ALTITUDE"]["val"],
        "altitude_ft_agl": params["PLANE_ALT_ABOVE_GROUND"]["val"],
        "ground_altitude_ft": params["GROUND_ALTITUDE"]["val"],
        "heading_true_deg": params["PLANE_HEADING_DEGREES_TRUE"]["val"],
        "vertical_obstacle": {
            "top_ft_msl": params["PLANE_ALTITUDE"]["val"],
            "bottom_ft_msl": params["GROUND_ALTITUDE"]["val"],
            "note": "自角点楼顶高度竖直向下至该处地面海拔",
        },
    }


def get_api_base() -> str:
    if ARCHIVE_PATH.exists():
        return json.loads(ARCHIVE_PATH.read_text(encoding="utf-8")).get(
            "api_base", "http://10.7.144.111:5000"
        )
    return "http://10.7.144.111:5000"


def log_event(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {message}\n"
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")


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
            "vertical_speed_ft_min": params["VERTICAL_SPEED"]["val"],
            "ground_speed_kt": params["GPS_GROUND_SPEED"]["val"],
        },
    }


def write_status_line(text: str) -> None:
    """单行刷新显示，覆盖旧内容。"""
    sys.stdout.write("\033[2K\r" + text)
    sys.stdout.flush()


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


def require_restore(archive: dict) -> dict:
    restore = archive.get("restore_point")
    if not restore or not restore.get("teleport_set_payload"):
        print("尚未设置恢复点。请飞到场景起点后运行:")
        print(f"  python3 {SCRIPT_DIR / 'msfs_obstacle.py'} save")
        sys.exit(1)
    return restore


def cmd_save(_: argparse.Namespace) -> None:
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
    print(f"恢复点已保存: {ARCHIVE_PATH}")
    print(f"  场景: {archive.get('scenario', '')}")
    print(f"  纬度: {pos['latitude']:.8f}°")
    print(f"  经度: {pos['longitude']:.8f}°")
    print(f"  高度: {pos['altitude_ft_msl']:.1f} ft MSL ({pos['altitude_ft_agl']:.1f} ft AGL)")
    print(f"  航向: {pos['heading_true_deg']:.2f}° (真北)")
    log_event(
        f"SAVE_RESTORE lat={pos['latitude']:.6f} lon={pos['longitude']:.6f} "
        f"alt={pos['altitude_ft_msl']:.1f}ft"
    )


def cmd_save_corner(args: argparse.Namespace) -> None:
    api = get_api_base()
    try:
        params = api_get(api)
    except DevKitError as exc:
        print(f"错误: {exc}")
        sys.exit(1)

    corner_id = args.id
    name = args.name or f"角点{corner_id}"
    corner = params_to_corner(params, corner_id, name)

    data = load_corners()
    corners = data.setdefault("corners", [])
    corners = [c for c in corners if c.get("id") != corner_id]
    corners.append(corner)
    corners.sort(key=lambda c: c["id"])
    data["corners"] = corners
    save_corners(data)

    print(f"障碍物角点已保存: {CORNERS_PATH}")
    print(f"  编号: {corner_id} ({name})")
    print(f"  纬度: {corner['latitude']:.8f}°")
    print(f"  经度: {corner['longitude']:.8f}°")
    print(f"  楼顶: {corner['altitude_ft_msl']:.1f} ft MSL ({corner['altitude_ft_agl']:.1f} ft AGL)")
    print(f"  地面: {corner['ground_altitude_ft']:.1f} ft MSL")
    print(f"  竖直区间: {corner['vertical_obstacle']['bottom_ft_msl']:.1f} – "
          f"{corner['vertical_obstacle']['top_ft_msl']:.1f} ft MSL")
    log_event(
        f"SAVE_CORNER id={corner_id} lat={corner['latitude']:.6f} "
        f"lon={corner['longitude']:.6f} top={corner['altitude_ft_msl']:.1f}ft"
    )


def cmd_list_corners(_: argparse.Namespace) -> None:
    data = load_corners()
    corners = data.get("corners", [])
    print(data.get("description", ""))
    print(data.get("zone_note", ""))
    print()
    if not corners:
        print("尚无角点。飞到楼顶角点后运行:")
        print(f"  python3 {SCRIPT_DIR / 'msfs_obstacle.py'} save-corner 1")
        return
    print(f"共 {len(corners)} 个角点:\n")
    for c in corners:
        vo = c.get("vertical_obstacle", {})
        bottom = vo.get("bottom_ft_msl")
        top = vo.get("top_ft_msl")
        if bottom is not None and top is not None:
            pillar = f"{bottom:.1f}–{top:.1f} ft MSL"
        else:
            pillar = "未定义"
        print(
            f"  [{c['id']}] {c.get('name', '')}  "
            f"lat={c['latitude']:.6f} lon={c['longitude']:.6f}  "
            f"楼顶={c['altitude_ft_msl']:.1f}ft MSL  柱体={pillar}"
        )
        print(f"       记录于 {c.get('saved_at_utc', '')}")


def cmd_teleport(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = archive["api_base"]
    restore = require_restore(archive)
    payload = restore["teleport_set_payload"]

    print("传送到场景恢复点...")
    for name, val in payload.items():
        ok, msg = api_set(api, name, val)
        print(f"  {'✓' if ok else '✗'} {name} = {val} ({msg})")

    pos = restore["position"]
    log_event(
        f"TELEPORT lat={pos['latitude']:.6f} lon={pos['longitude']:.6f} "
        f"alt={pos['altitude_ft_msl']:.1f}ft"
    )
    print("传送完成。请开始下降，遇障碍物时人工接管。")


def cmd_status(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = archive["api_base"]
    try:
        params = api_get(api)
    except DevKitError as exc:
        print(f"错误: {exc}")
        sys.exit(1)

    print(f"场景: {archive.get('scenario', '')}")
    print(f"当前: {format_position(params)}")
    restore = archive.get("restore_point")
    if restore:
        pos = restore["position"]
        print(
            f"存档: lat={pos['latitude']:.6f} lon={pos['longitude']:.6f} "
            f"alt={pos['altitude_ft_msl']:.1f}ft "
            f"({restore.get('saved_at_utc', '')})"
        )
    else:
        print("存档: 未设置（请先 save）")


def cmd_monitor(_: argparse.Namespace) -> None:
    archive = load_archive()
    api = archive["api_base"]
    print(f"位置监控 — {archive.get('scenario', '')} (Ctrl+C 停止)")
    interval = 1.0 / POLL_HZ
    try:
        while True:
            try:
                params = api_get(api)
                write_status_line(format_position(params))
            except DevKitError as exc:
                write_status_line(f"[等待 DevKit] {exc}")
            time.sleep(interval)
    except KeyboardInterrupt:
        write_status_line("")
        print("\n监控已停止。")


def cmd_run(_: argparse.Namespace) -> None:
    require_restore(load_archive())
    cmd_teleport(argparse.Namespace())
    print()
    time.sleep(1.0)
    cmd_monitor(argparse.Namespace())


def main() -> None:
    parser = argparse.ArgumentParser(description="MSFS 障碍物场景控制")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("save", help="记录当前位置为恢复点")
    p_corner = sub.add_parser("save-corner", help="记录障碍物角点（楼顶角）")
    p_corner.add_argument("id", type=int, help="角点编号，如 1、2、3…")
    p_corner.add_argument("--name", default=None, help="角点名称，默认角点N")
    sub.add_parser("list-corners", help="列出所有障碍物角点")
    sub.add_parser("teleport", help="传送到恢复点")
    sub.add_parser("status", help="查看当前/存档位置")
    sub.add_parser("monitor", help="实时监控位置")
    sub.add_parser("run", help="传送并开始监控")
    args = parser.parse_args()
    handlers = {
        "save": cmd_save,
        "save-corner": cmd_save_corner,
        "list-corners": cmd_list_corners,
        "teleport": cmd_teleport,
        "status": cmd_status,
        "monitor": cmd_monitor,
        "run": cmd_run,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
