# 系统故障场景

独立文件夹，与 `~/风切变/`、`~/障碍物场景/` 分离。

## 场景

下降阶段**自动驾驶系统断开**，飞行员需**人工接管**。

## 文件

| 文件 | 说明 |
|------|------|
| `position_archive.json` | 系统故障存档点 |
| `msfs_failure.py` | 主控制脚本 |
| `msfs_devkit_http.py` | DevKit HTTP 工具 |
| `events.log` | 运行日志（自动生成） |

## DevKit API

- `http://10.7.144.111:5000`
- `PUT /ap_stop` — 断开自动驾驶
- `GET /ap_state` — 查看 AP 状态

## 使用流程

### 1. 记录存档点（当前位置）

```bash
cd ~/系统故障
python3 msfs_failure.py save
```

### 2. 设置触发区（当前位置，半径 50m，高度 ±100ft）

```bash
python3 msfs_failure.py save-trigger
```

### 3. 开始训练

```bash
# 传送 + 监控；飞入触发区时自动 ap_stop（须先处于区外 ARMED）
python3 msfs_failure.py run --auto-fail
```

### 4. 手动模拟故障

```bash
python3 msfs_failure.py ap-stop
```

## 其他命令

```bash
python3 msfs_failure.py status
python3 msfs_failure.py ap-state
python3 msfs_failure.py monitor
python3 msfs_failure.py teleport
```
