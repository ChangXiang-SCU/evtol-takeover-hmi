# 停机坪

> 文件夹位置: **~/Desktop/停机坪/**

eVTOL 训练结束返场/停放位置，与各训练场景独立。

## 当前配置

- 纬度: 23.141249° | 经度: 113.277116° | 高度: **168 ft MSL**（地面）

## 常用命令

```bash
cd ~/Desktop/停机坪

python3 msfs_helipad.py save       # 覆盖停机坪位置
python3 msfs_helipad.py teleport   # 传送到停机坪
python3 msfs_helipad.py status       # 查看位置
```

## 检查各场景距停机坪距离

```bash
python3 ~/Desktop/align_restore_points.py check
```
