# MSFS 2024 eVTOL 风切变测试

> 文件夹位置: **~/Desktop/风切变/**

本文件夹包含风切变场景存档、DevKit 控制脚本及测试日志。

## 环境

- **模拟器**: MSFS 2024
- **DevKit API**: `http://10.7.144.111:5000`
- **Mac 端**: 通过 Python 脚本远程控制
- **参考文档**: `~/Downloads/MSFS24AICtrlDevKit文档.pdf`

## 文件说明

| 文件 | 说明 |
|------|------|
| `position_archive.json` | 恢复点 + 触发区 + 目标风况 |
| `msfs_windshear.py` | 主脚本 |
| `msfs_devkit_http.py` | DevKit HTTP 工具 |
| `events.log` | 运行日志 |

## 当前配置

### 恢复点（已对齐，距停机坪 650 m）

- 纬度: 23.135712° | 经度: 113.274927° | 高度: **800 ft MSL**

### 风切变触发区

- 中心: 23.139094°, 113.276222°
- 半径: **50 m** | 高度: **382–582 ft MSL**
- 目标风: **50 kt @ 270°**（需 MSFS 天气手动设置）

## 常用命令

```bash
cd ~/Desktop/风切变

python3 msfs_windshear.py save-restore   # 覆盖恢复点
python3 msfs_windshear.py save-heading   # 仅更新起始点航向（当前机头方向）
python3 msfs_windshear.py save-trigger   # 覆盖触发区
python3 msfs_windshear.py teleport       # 传送到恢复点
python3 msfs_windshear.py run            # 传送 + 监控
```

## 连接检查

```bash
curl -s -o /dev/null -w "HTTP:%{http_code}\n" http://10.7.144.111:5000/get
```
