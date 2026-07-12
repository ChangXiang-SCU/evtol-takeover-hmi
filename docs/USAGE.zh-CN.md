# 使用文档

中文 · English see [USAGE.md](USAGE.md)

## 1. 前置条件

- **MSFS 2024** 已运行、已加载 eVTOL 且**处于飞行中**（必须有一架飞机/一段飞行是活动的）。
- **AICtrl DevKit** 在 sim 主机上运行，服务于 `http://127.0.0.1:5000`（`/get`、`/set`、`/ap_start`、`/ap_stop`）。
- sim 主机装 **Python 3.8+**。务必用 UTF‑8 启动：`python -X utf8 …`（否则控制台非 UTF‑8，中文会崩）。
- 在 sim 上运行**无需任何第三方包**。只有从笔记本 SSH 部署时才需要 `paramiko`。

## 2. 启动控制面板

在 sim 主机上：

```bat
cd controller
python -X utf8 control_panel.py
```

它会打印 DevKit 字段数（确认连上），并在 **8000** 端口服务。打开：

- **操作台** — `http://<sim-ip>:8000/`
- **被试 HMI** — `http://<sim-ip>:8000/hmi`

`<sim-ip>` 在 sim 本机是 `127.0.0.1`；别的设备（触摸屏、你的笔记本）用 sim 的局域网 IP。要让局域网可访问，先放行一次防火墙：`python -X utf8 _ssh_deploy.py openfw`（同时会打印局域网 IP）。

## 3. 跑一个试次

在**操作台**上：

1. **① 选 HMI 模态** — 视觉（闪红+文字）、听觉（蜂鸣）、或视觉+听觉。
2. **② arm 一个诱因** — 风切变 / 自驾故障 / 障碍物 / 空白。这会设定触发区与试次起点。
3. **④ 传送** — "传送到起点"把飞机放到该诱因的起点（约 800ft）；"传送到停机坪"停到坪上方。
4. **③ 控制** — 要么让**被试手动飞**进触发区，要么点 **自动驾驶：开** 跑自主阶梯进近。
5. 当飞机进入 arm 的触发区（在其半径内**且**高度带内），诱因**自动触发**：HMI 弹接管请求；风切变注入下沉+空速骤减；自驾故障清除自动驾驶。障碍物只弹 HMI 提示。
6. **接管**由双通道检测——点 HMI 的 **接管** 按钮，或**操纵杆偏转**超过死区。两者各记一个**反应时**。
7. **↺ 复位** 清理当前试次以便下一次；**⚡ 手动立即触发** 强制触发；**自动驾驶：关** 立即停止 AP 航线。

逐试次遥测写入 `controller/logs/tel_<id>.csv`；事件汇总写入 `controller/logs/panel_events.csv`。

## 4. "自动驾驶：开" —— 自主阶梯进近

点 **自动驾驶：开** 会运行 `_throttle_route_loop`（在 `control_panel.py` 里）：一个**纯油门 + 升降舵**的阶梯航线飞向停机坪——平飞段（油门前进、升降舵中立）→下降段（升降舵下压）→交替，到坪上方约 40ft 停。若已 arm 某个带触发区的诱因且尚未触发，航线会**先飞到该触发区、且降到其高度带内**，让场景自动触发；随后风切变/自驾故障会打断 AP（交还被试），障碍物则继续飞到坪。

`_throttle_route_loop` 顶部可调参数：

| 参数 | 含义 | 默认 |
|---|---|---|
| `FWD` | 平飞段固定油门（调速旋钮） | `min(中性+32, 90)` |
| `ELEV_DN` | 下降段升降舵（下沉率） | `-0.85`（约 8–9 ft/s） |
| `ARRIVE` | 水平到达半径 | `25 m` |
| `HOVER_ALT` | 坪上方停悬高度 | 坪 + `40 ft` |
| 障碍物目标高度 | 高度带中值（与楼顶齐平） | `(alt_min+alt_max)/2` |
| 其它诱因目标高度 | 高度带偏上 | `alt_max − 20` |
| `HZ` | 控制回路频率 | `12 Hz` |

## 5. 独立飞行控制器

这些直接对着 DevKit 跑（在 sim 上，或从笔记本 `set DEVKIT_URL=http://<sim-ip>:5000`），便于调参：

- `python -X utf8 _fwd_fly.py [目标m/s] [巡航s]` —— 丝滑前飞（油门 PI 跟踪地速）。
- `python -X utf8 _step_land.py` —— 阶梯下降飞到停机坪。
- `python -X utf8 _land.py` —— 垂直降落（升降舵控下沉率）。
- `python -X utf8 dump_fields.py` —— 打印所有 DevKit 字段及其 `writable` 标志（存 `fields_dump.txt`）。
- `python -X utf8 _goto_start.py` / `_recover.py` —— 传送到起点 / 恢复安全悬停。

## 6. 从笔记本远程部署

`controller/_ssh_deploy.py` 用 **paramiko**（笔记本自带 `ssh.exe` 不稳），私钥在 `~/.ssh/sim_evtol`，连 `flightsimulator@<sim-ip>`：

```bat
python -X utf8 _ssh_deploy.py test        REM 连接 + DevKit 存活检查
python -X utf8 _ssh_deploy.py restart      REM 在 sim 上（重）启动面板
python -X utf8 _ssh_deploy.py openfw       REM 放行防火墙 8000 + 打印局域网 IP
python -X utf8 _ssh_deploy.py put <files>  REM SFTP 上传文件到 sim
python -X utf8 _ssh_deploy.py run "<cmd>"  REM 在 sim 上执行命令
```

`_probe_remote.py <脚本.py> [参数]` 一步完成：上传脚本并在 sim 上运行。

## 7. 排障

- **面板打不开** → 进程没在跑。`python -X utf8 _ssh_deploy.py restart`，再刷新 URL。
- **中文乱码 / 脚本一启动就崩** → 忘了 `-X utf8`。
- **笔记本连不上 `sim:5000` / `:8000`** → 跨子网 + VPN/TUN 代理（如 FlClash）可能劫持局域网流量。把控制器跑在 **sim 本机**（`127.0.0.1`），或在代理里"绕过局域网"。实测 8000 端口经 Wi‑Fi 可达。
- **没触发** → 必须先 **arm** 诱因，且飞行要在触发区**半径内且高度带内**穿过。
