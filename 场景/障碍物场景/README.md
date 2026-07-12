# 障碍物场景 — 下降遇楼需人工接管

> 文件夹位置: **~/Desktop/障碍物场景/**

模拟 eVTOL 下降进近遭遇建筑物障碍物，需人工接管规避。

## 文件

| 文件 | 说明 |
|------|------|
| `position_archive.json` | 恢复点存档 |
| `obstacle_corners.json` | 障碍物角点（9 个楼顶角） |
| `msfs_obstacle.py` | 主脚本 |
| `msfs_devkit_http.py` | DevKit HTTP 工具 |

## 当前配置

### 恢复点（已对齐，距停机坪 650 m）

- 纬度: 23.143219° | 经度: 113.271147° | 高度: **800 ft MSL**

### 障碍物角点

已记录 9 个角点，查看：`python3 msfs_obstacle.py list-corners`

## 常用命令

```bash
cd ~/Desktop/障碍物场景

python3 msfs_obstacle.py save              # 覆盖恢复点
python3 msfs_obstacle.py save-heading      # 仅更新起始点航向（当前机头方向）
python3 msfs_obstacle.py save-corner N     # 记录角点 N
python3 msfs_obstacle.py list-corners      # 列出角点
python3 msfs_obstacle.py teleport          # 传送到恢复点
python3 msfs_obstacle.py run               # 传送 + 监控
```

## DevKit

- API: `http://10.7.144.111:5000`
