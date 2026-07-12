# 障碍物场景 — 下降遇楼需人工接管

独立场景，与 `~/风切变/` 无关。

## 场景说明

模拟 eVTOL **下降进近**过程中遭遇**建筑物障碍物**，需要飞行员**人工接管**规避。

## 文件

| 文件 | 说明 |
|------|------|
| `position_archive.json` | 场景存档（恢复点） |
| `obstacle_corners.json` | **障碍物角点**（楼顶角，竖直向下为柱体区间） |
| `msfs_obstacle.py` | 主控制脚本 |
| `msfs_devkit_http.py` | DevKit HTTP 工具 |
| `msfs_save_position.py` | 快捷：保存恢复点 |
| `msfs_teleport_to_archive.py` | 快捷：传送 |
| `events.log` | 运行日志（自动生成） |

## DevKit

- API: `http://10.7.144.111:5000`
- 文档: `~/Downloads/MSFS24AICtrlDevKit文档.pdf`

## 使用流程

### 1. 记录恢复点（在 MSFS 中飞到场景起点）

```bash
cd ~/障碍物场景
python3 msfs_obstacle.py save
```

### 2. 记录建筑物楼顶角点（障碍物柱体顶点）

飞到**第 1 个楼顶角**，运行：

```bash
python3 msfs_obstacle.py save-corner 1
```

继续飞到角点 2、3、4…：

```bash
python3 msfs_obstacle.py save-corner 2
python3 msfs_obstacle.py save-corner 3
```

查看已记录角点：

```bash
python3 msfs_obstacle.py list-corners
```

每个角点会保存楼顶经纬度/高度，并自动生成**竖直向下至地面**的障碍物柱体区间（见 `vertical_obstacle` 字段）。

### 3. 开始训练

```bash
python3 msfs_obstacle.py run
```

传送到恢复点 → 实时监控位置 → 自行下降，遇障碍物人工接管。

### 其他命令

```bash
python3 msfs_obstacle.py status    # 查看当前/存档位置
python3 msfs_obstacle.py teleport  # 仅传送
python3 msfs_obstacle.py monitor   # 仅监控
```

## 连接检查

```bash
curl -s -o /dev/null -w "HTTP:%{http_code}\n" http://10.7.144.111:5000/get
```
