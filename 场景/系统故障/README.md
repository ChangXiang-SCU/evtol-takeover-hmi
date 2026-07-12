# 系统故障场景

> 文件夹位置: **~/Desktop/系统故障/**

下降阶段自动驾驶断开，飞行员需人工接管。

## 文件

| 文件 | 说明 |
|------|------|
| `position_archive.json` | 存档点 + 故障触发区 |
| `msfs_failure.py` | 主脚本 |
| `msfs_devkit_http.py` | DevKit HTTP 工具 |

## 当前配置

### 存档点（已对齐，距停机坪 650 m）

- 纬度: 23.136023° | 经度: 113.279951° | 高度: **800 ft MSL**

### 故障触发区

- 中心: 23.139614°, 113.277990°
- 半径: **50 m** | 高度: **261–461 ft MSL**

## 常用命令

```bash
cd ~/Desktop/系统故障

python3 msfs_failure.py save           # 覆盖存档点
python3 msfs_failure.py save-heading   # 仅更新起始点航向（当前机头方向）
python3 msfs_failure.py save-trigger   # 覆盖触发区
python3 msfs_failure.py teleport       # 传送到存档点
python3 msfs_failure.py run --auto-fail  # 传送 + 飞入触发区自动 ap_stop
python3 msfs_failure.py ap-stop        # 手动断开 AP
```

## DevKit API

- `PUT /ap_stop` — 断开自动驾驶
- `GET /ap_state` — 查看 AP 状态
