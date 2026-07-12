# eVTOL 接管 HMI — 微软模拟飞行 2024 上的自主飞行与接管

> 🇬🇧 English: **[README.md](README.md)**　｜　📖 详细文档：**[docs/USAGE.zh-CN.md](docs/USAGE.zh-CN.md)** · **[docs/DESIGN.zh-CN.md](docs/DESIGN.zh-CN.md)**

一个研究 eVTOL **自主飞行接管** 的实验平台，基于 **微软模拟飞行 2024（MSFS 2024）** 及其 **AICtrl DevKit** REST 接口。飞机自主地以**阶梯式进近**飞向楼顶停机坪；在预设点自动触发一种诱因——**风切变**、**自驾故障** 或 **障碍物**——同时**多模态接管 HMI**（视觉／听觉／两者）提示被试接管，系统记录**接管反应时**与逐帧**遥测**。

全部为**纯 Python 标准库**（无需 `pip install`，Python 3.8+），通过 HTTP 与 DevKit 通信。

## 亮点

- **像人一样开飞机，不作弊。** 只用真实操纵——**油门**（前后）+ **升降舵**（升降）——飞行，不去写姿态/位置。详见 [docs/DESIGN.zh-CN.md](docs/DESIGN.zh-CN.md)。
- **操作台 + 被试 HMI** 合在一个小型 HTTP 服务（`controller/control_panel.py`），分别在 `:8000/` 与 `:8000/hmi`。
- **一键自主进近**（"自动驾驶：开"）：平滑阶梯下降飞到停机坪；若已 arm 某诱因，航线会**路过其触发区**让场景自动触发。
- **三类诱因场景**，带地理围栏触发（半径 + 高度带）、双通道接管反应时（触摸屏 + 操纵杆偏转）、逐试次 CSV 遥测。
- **远程部署工具**（`controller/_ssh_deploy.py`）：通过 SSH 把控制器推到 sim 主机并运行。

## 目录结构

```
controller/            运行时：面板/HMI、DevKit 客户端、配置、飞行控制器、部署工具
  control_panel.py     操作台 + 被试 HMI + 场景逻辑 + "自动驾驶:开"阶梯进近
  devkit_client.py     纯标准库的 MSFS AICtrl DevKit REST 客户端（真实 + Mock）
  config.py            场景、坐标、触发区、可调参数
  geo.py               距离/方位/位移 计算（WGS84）
  _fwd_fly.py          闭环丝滑前飞（油门 PI 跟踪地速）
  _step_land.py        阶梯下降飞到停机坪（油门 + 升降舵台阶）
  _land.py             垂直降落（升降舵控下沉率）
  _ssh_deploy.py       paramiko 部署 / 远程运行 / 面板重启 / 防火墙
  ...                  各种探针与实验（throttle_fly.py, dump_fields.py, ...）
场景/ , 3 种场景/        场景脚本（停机坪 / 风切变 / 自驾故障 / 障碍物）
docs/                  USAGE 使用文档 与 DESIGN 设计文档（中英）
```

## 快速开始

在 **sim 主机**（跑 MSFS + DevKit 于 `127.0.0.1:5000` 的那台 Windows）上：

```bat
cd controller
python -X utf8 control_panel.py
```

浏览器打开（sim 本机或局域网任意设备）：

- 操作台：`http://<sim-ip>:8000/`
- 被试 HMI：`http://<sim-ip>:8000/hmi`

选一个 HMI 模态，（可选）**arm** 一个诱因，点 **自动驾驶：开** 即自主进近。完整流程见 **[docs/USAGE.zh-CN.md](docs/USAGE.zh-CN.md)**。

> 远程方式：从笔记本 `python -X utf8 _ssh_deploy.py restart` 即可通过 SSH 在 sim 上部署/启动面板。见 [controller/README_部署.md](controller/README_部署.md)。

## 关键实测结论（本机型，真机实测）

DevKit `/get` 暴露 **76 个变量、41 个可写**。这台 eVTOL 上：

- **`GENERAL ENG THROTTLE LEVER POSITION:1` = 前后**（可写、生效）。高于悬停中性值→前进，低于→后退；**不改变高度**。极限地速 ≈ 5 m/s。
- **`ELEVATOR POSITION` = 升降**（爬升/下降），约 10 ft/s 每单位——与固定翼直觉相反，符合该旋翼模型。
- 未暴露 collective/cyclic；`VELOCITY_BODY_X` 写入在飞行中**不生效**。姿态（航向/横滚）与操纵（油门/升降舵/方向舵）写入生效。
- **几何：** 起点机头约 0.3°、停机坪方位约 20°；油门推力在机头**右侧约 19°**，二者恰好抵消——从起点**只推油门就直奔停机坪**，无需给航向。

数字与控制回路见 **[docs/DESIGN.zh-CN.md](docs/DESIGN.zh-CN.md)**。

## 安全与范围

这是面向 MSFS 的**仿真研究**软件，只操控仿真中的飞机，**不用于真实飞行**。含个人信息的招募/被试/问卷文件已**排除**在本仓库之外。

## 许可

暂未设置开源许可证——在添加之前，版权归作者所有。如需使用条款请提 issue。
