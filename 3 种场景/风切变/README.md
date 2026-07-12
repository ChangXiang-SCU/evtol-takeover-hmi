# MSFS 2024 eVTOL 风切变测试

本文件夹包含风切变场景存档、DevKit 控制脚本及测试日志。

## 环境

- **模拟器**: MSFS 2024
- **DevKit API**: `http://10.7.144.111:5000`（Windows 跑 MSFS + AICtrl DevKit）
- **Mac 端**: 通过 curl / Python 脚本远程控制
- **参考文档**: `~/Downloads/MSFS24AICtrlDevKit文档.pdf`

## 文件说明

| 文件 | 说明 |
|------|------|
| `position_archive.json` | 场景存档（恢复点 + 触发区 + 目标风况） |
| `msfs_windshear.py` | 主脚本 |
| `msfs_devkit_http.py` | DevKit HTTP 工具（标准库，无需 requests） |
| `msfs_save_position.py` | 快捷：记录恢复点 |
| `msfs_teleport_to_archive.py` | 快捷：传送到恢复点 |
| `events.log` | 运行日志 |

## 当前场景配置

### 恢复点（传送起点，触发区外）

- 纬度: 23.137925°
- 经度: 113.275666°
- 高度: 618 ft MSL
- 记录时间: 2026-07-07 08:41 UTC

### 风切变触发区

- 中心: 23.139094°, 113.276222°
- 半径: **50 m**
- 高度: **382 – 582 ft MSL**（记录高度 482 ft ± 100 ft）
- 目标风: **50 kt @ 270°**

### 测试流程

1. 从恢复点传送出发
2. 下降至触发区（水平进入 50 m 范围 + 高度在范围内）
3. 脚本检测进入并告警；**风速需在 MSFS 天气中手动设置**（DevKit 无法写入风速）

## 常用命令

```bash
cd ~/风切变

python3 msfs_windshear.py save-restore   # 记录恢复点
python3 msfs_windshear.py save-trigger   # 记录触发区
python3 msfs_windshear.py test-wind      # 测试能否改风
python3 msfs_windshear.py run            # 传送 + 监控
```

## 已知限制

- DevKit 的 `AMBIENT_WIND_VELOCITY` 为只读，位置监控正常，改风需 MSFS 天气或 Active Sky

## 连接检查

```bash
curl -s -o /dev/null -w "HTTP:%{http_code}\n" http://10.7.144.111:5000/get
```
